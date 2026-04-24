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
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from monocle.config import Settings
from monocle.services.activity import ActivityMonitor
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

#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _is_monocle_note(raw: str) -> bool:
    """Return True if *raw* is a file already written by the Monocle pipeline.

    Monocle's ``create_from_template`` always writes ``approval_mode:`` into
    the frontmatter (even as null).  Hand-crafted Obsidian notes never contain
    this field.  Checking the first 3 KB is enough to cover normal frontmatter.

    Used by the inbox watcher callback to skip re-ingesting files that were
    already processed (e.g. notes placed in inbox/ by the agent's create_note
    tool), preventing spurious duplicates like ``people/person.md``.
    """
    return raw.startswith("---") and "approval_mode:" in raw[:3000]


def _strip_frontmatter(raw: str) -> str:
    """Return the body of *raw*, with the leading YAML frontmatter block removed.

    If no closing ``---`` delimiter is found the original string is returned.
    """
    if not raw.startswith("---"):
        return raw
    end = raw.find("\n---", 3)
    if end == -1:
        return raw
    return raw[end + 4:].lstrip("\n")


def _infer_inbox_request_source(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".webm", ".mp3", ".wav", ".m4a", ".flac"}:
        return "voice"
    return "web"

# ---------------------------------------------------------------------------
#region #*   Application state (shared across requests)
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


#endregion

# ---------------------------------------------------------------------------
#region #*   Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks for the unified process."""
    cfg = get_settings()
    route_filter_processor = configure_telemetry(cfg)
    logger.info("[API] Monocle starting — provider=%s port=%d", cfg.ai.provider, cfg.server.port)

    # Determine if this process is a capture-only (API-only) server.
    # When True the inline watcher and APScheduler are skipped — they
    # are managed externally (either by ProcessManager subprocesses or by a
    # user running `monocle watch` / `monocle scheduler` directly).
    #
    # Activated by (any of):
    #  - config:  server.separate_processes: true
    #  - env var: MONOCLE_SEPARATE_PROCESSES=1   (set by `serve/dev --separate-processes`)
    #  - env var: MONOCLE_COMPONENT=capture       (set by `monocle capture`)
    _separate = (
        cfg.server.separate_processes
        or os.environ.get("MONOCLE_SEPARATE_PROCESSES") == "1"
    )
    _capture_only = _separate or os.environ.get("MONOCLE_COMPONENT") == "capture"
    if _capture_only:
        logger.info(
            "[API] Capture-only mode — watcher and scheduler managed externally"
        )

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
    app.state.route_filter_processor = route_filter_processor
    app.state.activity_monitor = ActivityMonitor()
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
    from monocle.services.ingest_sessions import IngestSessionStore

    failed_registry = FailedIngestRegistry()
    app.state.failed_registry = failed_registry
    app.state.ingest_session_store = IngestSessionStore(cfg)

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

    from monocle.services.ingest_prepare import IngestPreparationWorker

    ingest_prepare_worker = IngestPreparationWorker(
        store=app.state.ingest_session_store,
        pipeline=ingest_pipeline,
        vault=vault,
        index=index,
        ai=ai,
        settings=cfg,
        activity=app.state.activity_monitor,
    )
    app.state.ingest_prepare_worker = ingest_prepare_worker
    await ingest_prepare_worker.start()

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

    scheduler = None
    if not _capture_only:
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
    else:
        logger.info("[SCHEDULER] Capture-only mode — APScheduler managed externally")
        app.state.scheduler = None

    # ------------------------------------------------------------------
    # Inbox watcher (async task — Phase 1 integration)
    # ------------------------------------------------------------------
    watcher: "InboxWatcher | None" = None
    if _capture_only:
        logger.info("[WATCHER] Capture-only mode — inbox watcher managed externally")
    elif cfg.vault.watch:
        from monocle.watcher import InboxWatcher

        watcher = InboxWatcher(
            inbox_path=cfg.vault.inbox_path,
            debounce_s=cfg.vault.debounce_ms / 1000,
        )

        # Wire ingest callback for inbox file captures
        async def _inbox_ingest_callback(file_path: str) -> bool:
            """Archive a stable inbox file and persist an ingest session.

            Files already written by the Monocle pipeline or agent tools have
            full Monocle frontmatter (detected via ``_is_monocle_note``).
            Those are queued for re-indexing only — running them through
            IngestPipeline again creates spurious duplicates (e.g.
            ``people/person.md``) when the LLM cannot extract the title.

            All other inbox files are archived outside the vault and captured
            as persisted ingest sessions for later preparation and review.

            Returns:
                True if the file was archived into a persisted ingest session
                (file should be deleted).
                False if ingest was skipped (file should NOT be deleted).
            """
            import asyncio as _asyncio
            from pathlib import Path as _Path

            try:
                path = _Path(file_path)
                if path.suffix.lower() == ".md":
                    raw = await _asyncio.to_thread(path.read_text, encoding="utf-8")

                    if _is_monocle_note(raw):
                        reindex_queue.push(file_path)
                        logger.info(
                            "[WATCHER] Skipped re-ingest of already-processed note %s", file_path
                        )
                        return False  # Do NOT delete; this file was intentionally queued for re-index only

                await _asyncio.to_thread(
                    app.state.ingest_session_store.create_inbox_session,
                    file_path,
                    request_source=_infer_inbox_request_source(file_path),
                )
                logger.info("[WATCHER] Ingest session captured for %s", file_path)
                return True  # Ingest succeeded; file can be deleted
            except Exception as exc:  # noqa: BLE001
                logger.error("[WATCHER] Ingest failed for %s: %s", file_path, exc, exc_info=True)
                return False  # Do NOT delete; ingest failed, keep the file for debugging

        watcher.set_ingest_callback(_inbox_ingest_callback)
        await watcher.start()
    else:
        logger.info("[WATCHER] vault.watch=false — inbox watcher disabled")
    app.state.watcher = watcher

    # ------------------------------------------------------------------
    # Process Manager (separate-processes mode only)
    # Spawns `monocle watch` and `monocle scheduler` as subprocesses so that
    # the inbox watcher and APScheduler run in dedicated OS processes.
    # In the default unified mode this is a no-op.
    # ------------------------------------------------------------------
    from monocle.process_manager import ProcessManager

    process_manager = ProcessManager(cfg)
    if _separate:
        await process_manager.start_all()
    app.state.process_manager = process_manager

    # ------------------------------------------------------------------
    # MCP server state — inject shared layers so tool functions can access them
    # ------------------------------------------------------------------
    from monocle.mcp_server import init_mcp_state

    init_mcp_state(
        vault,
        index,
        ai,
        ingest_pipeline,
        graph_builder,
        settings=cfg,
        reindex_queue=reindex_queue,
    )

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
    await ingest_prepare_worker.stop()
    await reindex_queue.stop()
    if scheduler is not None:
        await scheduler.stop()
    if _separate:
        await process_manager.stop_all()
    logger.info("[API] Monocle shutdown complete")


#endregion

# ---------------------------------------------------------------------------
#region #*   Rate limiting (slowapi)
# ---------------------------------------------------------------------------

from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from monocle.rate_limit import limiter  # noqa: E402


#endregion

# ---------------------------------------------------------------------------
#region #*   Factory — build the FastAPI app
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

        # /api/chat streams SSE responses. Keeping the request span open across
        # that async stream lifecycle triggers cross-context detach errors, so
        # chat uses its own explicit span in the router instead.
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/chat")
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
