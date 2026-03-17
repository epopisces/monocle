"""
monocle/main.py — FastAPI application entry point.

Registers all routers, CORS middleware, OTel middleware, rate limiting,
static file serving, and the lifespan context (startup / shutdown hooks).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

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

    # ------------------------------------------------------------------
    # Re-index queue (used by write routes in M8+)
    # ------------------------------------------------------------------
    from monocle.watcher import ReindexQueue

    reindex_queue = ReindexQueue()
    await reindex_queue.start()
    app.state.reindex_queue = reindex_queue

    # ------------------------------------------------------------------
    # Scheduler (cron jobs — weekly summary + re-index)
    # ------------------------------------------------------------------
    from monocle.agents.reindex import ReindexAgent
    from monocle.agents.scheduler import MonocleScheduler

    # TODO (M6): pass embed_fn=ai_provider.embed once AIProvider is wired.
    # Without embed_fn, ReindexAgent.run() will skip re-indexing for any
    # non-memory backend (ChromaDB) to prevent the delete-before-upsert data
    # loss that would occur if empty embeddings are rejected at upsert time.
    reindex_agent = ReindexAgent(
        chunk_size=cfg.index.chunk_size_tokens,
        chunk_overlap=cfg.index.chunk_overlap_tokens,
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

    # Weekly summary job stub — implemented in M11
    if cfg.agents.weekly_summary.enabled:
        logger.info(
            "[SCHEDULER] Weekly summary job registered (cron=%s) — active in M11",
            cfg.agents.weekly_summary.cron,
        )

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
        # Ingest callback is wired in M7 when IngestPipeline is implemented
        await watcher.start()
    else:
        logger.info("[WATCHER] vault.watch=false — inbox watcher disabled")
    app.state.watcher = watcher

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
    # Static files — serve frontend/dist at root (noop if not built)
    # ------------------------------------------------------------------
    import pathlib
    dist = pathlib.Path(cfg.server.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app


# Module-level app instance (used by uvicorn and test client)
app = create_app()
