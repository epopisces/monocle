"""
monocle/main.py — FastAPI application entry point.

Registers all routers, CORS middleware, OTel middleware, rate limiting,
static file serving, and the lifespan context (startup / shutdown hooks).
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from monocle.config import Settings
from monocle.telemetry import configure_telemetry

# Router imports
from monocle.routers import (
    agents,
    chat,
    graph,
    health,
    ingest,
    ingest_failures,
    notes,
    review,
    search,
    settings as settings_router,
    stats,
    teams,
    transcribe,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state (shared across requests)
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks for the unified process."""
    cfg = get_settings()
    configure_telemetry(cfg)
    logger.info("[API] Monocle starting — provider=%s port=%d", cfg.ai.provider, cfg.server.port)

    # ------------------------------------------------------------------
    # Core layers
    # ------------------------------------------------------------------
    from monocle.index import get_index
    from monocle.vault import VaultLayer

    vault = VaultLayer(cfg.vault.path)
    index = get_index(cfg)
    app.state.vault = vault
    app.state.index = index
    app.state.settings = cfg
    # Lazy pending-review count cache; invalidated on any vault write.
    # review_count endpoint reads this before falling back to a full scan.
    app.state._review_pending_count = None

    # ------------------------------------------------------------------
    # Graph builder (in-memory cache; invalidated on any vault file change)
    # ------------------------------------------------------------------
    from monocle.graph import GraphBuilder

    graph_builder = GraphBuilder(vault)
    app.state.graph_builder = graph_builder

    # ------------------------------------------------------------------
    # AI Provider
    # ------------------------------------------------------------------
    from monocle.ai import get_provider

    ai = None
    try:
        ai = get_provider(cfg)
        logger.info("[API] AI provider initialised: %s", cfg.ai.provider)

        # Auto-detect embedding dimensions if not explicitly configured
        if cfg.ai.embed_dimensions is None and ai is not None:
            detected_dims = await ai.detect_embed_dimensions()
            logger.info(
                "[API] Auto-detected embedding dimensions: %d (model=%s)",
                detected_dims,
                cfg.ai.embed_model,
            )
            # Update index with detected dimensions (updates metadata if needed)
            if hasattr(index, "update_embed_dimensions"):
                index.update_embed_dimensions(detected_dims)
        elif cfg.ai.embed_dimensions is not None and ai is not None:
            # Explicit config — validate that AI provider matches
            detected_dims = await ai.detect_embed_dimensions()
            if detected_dims != cfg.ai.embed_dimensions:
                logger.warning(
                    "[API] Embedding dimension mismatch: config specifies %d but "
                    "model '%s' produces %d-dimensional embeddings. "
                    "Update config.ai.embed_dimensions or switch to a compatible model.",
                    cfg.ai.embed_dimensions,
                    cfg.ai.embed_model,
                    detected_dims,
                )

    except Exception as exc:  # pragma: no cover
        logger.warning("[API] AI provider init failed (non-fatal): %s", exc)
    app.state.ai = ai

    # ------------------------------------------------------------------
    # Re-index queue (used by write routes in M8+)
    # ------------------------------------------------------------------
    from monocle.watcher import ReindexQueue

    reindex_queue = ReindexQueue()
    await reindex_queue.start()
    app.state.reindex_queue = reindex_queue

    # ------------------------------------------------------------------
    # Re-index queue callback — re-index a single file on write
    # ------------------------------------------------------------------
    async def _reindex_file(file_path: str) -> None:
        from monocle.ingest.chunker import chunk_text

        logger.debug("[API] ReindexQueue: re-indexing %s", file_path)
        # Any vault file change may alter review_status — invalidate count cache.
        app.state._review_pending_count = None
        # Always invalidate the graph cache when a vault file changes,
        # regardless of whether re-indexing succeeds or the file is gone.
        graph_builder.invalidate()
        try:
            note = await asyncio.to_thread(vault.read_note, file_path)
        except Exception:
            logger.debug("[API] ReindexQueue: file gone, skipping %s", file_path)
            return
        chunks_text = chunk_text(
            note.body or "",
            chunk_size=cfg.index.chunk_size_tokens,
            overlap=cfg.index.chunk_overlap_tokens,
        )
        if not chunks_text:
            await asyncio.to_thread(index.delete_file, file_path)
            return
        if ai is None:
            return  # no embeddings available
        from monocle.models import NoteChunk

        # Use the note's own `updated` timestamp so duplicate-detection's
        # recency window is based on when the note was last edited, not
        # when the background re-index ran.
        note_updated_iso = (
            note.metadata.updated.isoformat()
            if note.metadata.updated is not None
            else note.metadata.created.isoformat()
            if note.metadata.created is not None
            else datetime.now(timezone.utc).isoformat()
        )

        embeddings = await ai.embed_batch(chunks_text)
        note_chunks = [
            NoteChunk(
                chunk_id=f"{file_path}::{i}",
                file_path=file_path,
                chunk_index=i,
                text=t,
                embedding=e,
                metadata={
                    "type": note.metadata.type,
                    "domain": note.metadata.domain,
                    "source": note.metadata.source,
                    "updated_at": note_updated_iso,
                },
            )
            for i, (t, e) in enumerate(zip(chunks_text, embeddings))
        ]
        await asyncio.to_thread(index.upsert_chunks, note_chunks)
        logger.info("[API] ReindexQueue: re-indexed %s (%d chunks)", file_path, len(note_chunks))

    reindex_queue.set_callback(_reindex_file)

    # ------------------------------------------------------------------
    # Failed-ingest registry
    # ------------------------------------------------------------------
    from monocle.ingest.failed_registry import FailedIngestRegistry

    failed_registry = FailedIngestRegistry()
    app.state.failed_registry = failed_registry

    # ------------------------------------------------------------------
    # Ingest pipeline singleton
    # ------------------------------------------------------------------
    from monocle.ingest import IngestPipeline
    from monocle.ingest.plugins import register_default_plugins
    from monocle.ingest.plugin import IngestPluginRegistry

    _registry = IngestPluginRegistry.get()
    if not _registry.plugins:
        register_default_plugins(_registry)

    ingest_pipeline = IngestPipeline(
        vault=vault,
        index=index,
        ai=ai,
        settings=cfg,
        registry=_registry,
        failed_registry=failed_registry,
    )
    app.state.ingest_pipeline = ingest_pipeline

    # ------------------------------------------------------------------
    # Scheduler (cron jobs — weekly summary + re-index)
    # ------------------------------------------------------------------
    from monocle.agents.reindex import ReindexAgent
    from monocle.agents.scheduler import MonocleScheduler

    reindex_agent = ReindexAgent(
        chunk_size=cfg.index.chunk_size_tokens,
        chunk_overlap=cfg.index.chunk_overlap_tokens,
        embed_fn=ai.embed if ai is not None else None,
    )
    app.state.reindex_agent = reindex_agent

    scheduler = MonocleScheduler(cfg)
    await scheduler.start()
    app.state.scheduler = scheduler

    # Register scheduled re-index job (incremental)
    if cfg.agents.reindex.enabled:

        async def _scheduled_reindex() -> None:
            logger.info("[SCHEDULER] Scheduled re-index starting")
            await reindex_agent.run(vault, index)
            logger.info("[SCHEDULER] Scheduled re-index complete")

        scheduler.add_cron_job(
            "reindex",
            _scheduled_reindex,
            cfg.agents.reindex.cron,
        )

    # Weekly summary job — implemented in M11
    if cfg.agents.weekly_summary.enabled:
        from monocle.agents.weekly_summary import WeeklySummaryAgent

        _weekly_summary_agent = WeeklySummaryAgent()

        async def _scheduled_weekly_summary() -> None:
            logger.info("[SCHEDULER] Weekly summary starting")
            if ai is None:
                logger.warning("[SCHEDULER] Weekly summary skipped — AI provider not available")
                return
            try:
                file_path = await _weekly_summary_agent.run(vault, index, ai, cfg)
                logger.info("[SCHEDULER] Weekly summary written: %s", file_path)
            except Exception as exc:
                logger.error("[SCHEDULER] Weekly summary failed: %s", exc, exc_info=True)

        scheduler.add_cron_job(
            "weekly_summary",
            _scheduled_weekly_summary,
            cfg.agents.weekly_summary.cron,
        )
        app.state.weekly_summary_agent = _weekly_summary_agent

    # ------------------------------------------------------------------
    # Inbox watcher (async task — Phase 1 integration)
    # ------------------------------------------------------------------
    watcher: "InboxWatcher | None" = None
    if cfg.vault.watch:
        from monocle.watcher import InboxWatcher

        watcher = InboxWatcher(
            inbox_path=cfg.vault.inbox_path,
            debounce_s=cfg.vault.debounce_ms / 1000,
        )

        # Wire ingest callback for inbox file captures
        async def _inbox_ingest_callback(file_path: str) -> None:
            """Run the ingest pipeline for a newly stable inbox file."""
            import asyncio as _asyncio
            from pathlib import Path as _Path

            try:
                content = await _asyncio.to_thread(_Path(file_path).read_text, encoding="utf-8")
                from monocle.models import IngestRequest

                req = IngestRequest(content=content, source="web")
                await ingest_pipeline.run(req)
                logger.info("[WATCHER] Ingest complete for %s", file_path)
            except Exception as exc:  # noqa: BLE001
                logger.error("[WATCHER] Ingest failed for %s: %s", file_path, exc, exc_info=True)

        watcher.set_ingest_callback(_inbox_ingest_callback)
        await watcher.start()
    else:
        logger.info("[WATCHER] vault.watch=false — inbox watcher disabled")
    app.state.watcher = watcher

    # ------------------------------------------------------------------
    # MCP server state — inject shared layers so tool functions can access them
    # ------------------------------------------------------------------
    from monocle.mcp_server import init_mcp_state

    init_mcp_state(vault, index, ai, ingest_pipeline, graph_builder, reindex_queue=reindex_queue)

    # ------------------------------------------------------------------
    # Startup re-index (runs if index is empty and vault has notes)
    # ------------------------------------------------------------------
    await reindex_agent.startup_check(vault, index)

    logger.info("[API] Monocle ready")
    yield

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    logger.info("[API] Monocle shutting down")
    if watcher is not None:
        await watcher.stop()
    await reindex_queue.stop()
    await scheduler.stop()
    logger.info("[API] Monocle shutdown complete")


# ---------------------------------------------------------------------------
# Rate limiting (slowapi)
# ---------------------------------------------------------------------------

from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from monocle.rate_limit import limiter  # noqa: E402


# ---------------------------------------------------------------------------
# Factory — build the FastAPI app
# ---------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    app = FastAPI(
        title="Monocle",
        description="Personal knowledge capture and retrieval API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Rate limiter
    # ------------------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    origins = [
        f"http://localhost:{cfg.server.port}",
        f"http://127.0.0.1:{cfg.server.port}",
    ]
    if cfg.server.dev_cors or os.environ.get("MONOCLE_DEV"):
        origins += [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # OpenTelemetry FastAPI instrumentation
    # ------------------------------------------------------------------
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # pragma: no cover
        logger.warning("[API] OTel FastAPI instrumentation skipped: %s", exc)

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(health.router, prefix="/api")
    app.include_router(notes.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(ingest.router, prefix="/api")
    app.include_router(ingest_failures.router, prefix="/api")
    app.include_router(transcribe.router, prefix="/api")
    app.include_router(graph.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(review.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(teams.router, prefix="/api")

    # ------------------------------------------------------------------
    # MCP server — mounted at /mcp with key-based auth
    # ------------------------------------------------------------------
    from monocle.mcp_server import create_mcp_app

    mcp_key = os.environ.get(cfg.server.mcp_access_key_env, "")
    app.mount("/mcp", create_mcp_app(mcp_key))

    # ------------------------------------------------------------------
    # Static files — serve frontend/dist at root (noop if not built)
    # ------------------------------------------------------------------
    import pathlib
    dist = pathlib.Path(cfg.server.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app


# Module-level app instance (used by uvicorn and test client)
app = create_app()
