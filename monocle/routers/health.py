"""monocle/routers/health.py — GET /api/health"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

VERSION = "0.1.0"


class HealthResponse(BaseModel):
    status: str  # starting | ready | indexing | error
    version: str
    ai_reachable: bool
    index_status: str  # empty | ready
    watcher_running: bool
    telemetry_endpoint: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Return current system health, AI reachability, and index status."""
    settings = getattr(request.app.state, "settings", None)
    index = getattr(request.app.state, "index", None)
    ai = getattr(request.app.state, "ai", None)
    watcher = getattr(request.app.state, "watcher", None)

    # -- Watcher status --
    watcher_running = watcher is not None and watcher.status().get("running", False)

    # -- AI reachability: try a quick embed ping --
    ai_reachable = False
    if ai is not None:
        try:
            await ai.embed("ping")
            ai_reachable = True
        except Exception as exc:
            logger.debug("AI ping failed: %s", exc)

    # -- Index status --
    index_status = "empty"
    overall_status = "starting"
    if index is not None:
        try:
            stats = await asyncio.to_thread(index.get_stats)
            index_status = "ready" if stats.total_chunks > 0 else "empty"
            overall_status = "ready"
        except Exception as exc:
            logger.debug("Index stats failed: %s", exc)
            overall_status = "error"
    else:
        overall_status = "starting"

    # Downgrade to degraded if non-critical subsystems are unavailable
    if overall_status == "ready" and not ai_reachable:
        overall_status = "degraded"
    elif overall_status == "ready" and watcher is not None and not watcher_running:
        overall_status = "degraded"

    # -- Telemetry endpoint --
    telemetry_endpoint: str | None = None
    if settings is not None and settings.telemetry.enabled:
        telemetry_endpoint = settings.telemetry.otlp_endpoint

    return HealthResponse(
        status=overall_status,
        version=VERSION,
        ai_reachable=ai_reachable,
        index_status=index_status,
        watcher_running=watcher_running,
        telemetry_endpoint=telemetry_endpoint,
    )
