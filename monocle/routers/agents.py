"""monocle/routers/agents.py — Scheduled-agent trigger endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse

from monocle.rate_limit import limiter

router = APIRouter(tags=["agents"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /api/agents/weekly-summary  — SSE streaming response
# ---------------------------------------------------------------------------


@router.post("/agents/weekly-summary")
@limiter.limit("10/minute")
async def trigger_weekly_summary(request: Request) -> StreamingResponse:
    """Trigger the weekly summary agent and stream progress via SSE.

    Events emitted:
      ``start``    — agent started
      ``done``     — summary written; ``data`` contains ``file_path``
      ``error``    — agent failed; ``data`` contains ``message``
    """
    app = request.app

    async def _event_stream() -> AsyncIterator[str]:
        yield _sse("start", {"status": "running"})
        try:
            ai = getattr(app.state, "ai", None)
            vault = getattr(app.state, "vault", None)
            index = getattr(app.state, "index", None)
            settings = getattr(app.state, "settings", None)

            if ai is None:
                yield _sse("error", {"message": "AI provider not available"})
                return
            if vault is None or index is None or settings is None:
                yield _sse("error", {"message": "Server not fully initialised"})
                return

            agent = getattr(app.state, "weekly_summary_agent", None)
            if agent is None:
                # Instantiate on demand if not registered via scheduler
                from monocle.agents.weekly_summary import WeeklySummaryAgent

                agent = WeeklySummaryAgent()

            file_path = await agent.run(vault, index, ai, settings)
            yield _sse("done", {"file_path": file_path})
        except RuntimeError as exc:
            # No recent notes found — not a fatal error
            logger.info("[AGENT] Weekly summary skipped: %s", exc)
            yield _sse("done", {"file_path": None, "skipped": True, "reason": str(exc)})
        except Exception as exc:
            logger.error("[AGENT] Weekly summary failed: %s", exc, exc_info=True)
            yield _sse("error", {"message": "Agent error — see server logs"})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# POST /api/agents/reindex  — 202 Accepted, background task
# ---------------------------------------------------------------------------


@router.post("/agents/reindex", status_code=202)
@limiter.limit("6/minute")
async def trigger_reindex(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Trigger a full-vault incremental re-index in the background.

    Returns 202 Accepted immediately; the re-index runs asynchronously.
    """
    app = request.app
    vault = getattr(app.state, "vault", None)
    index = getattr(app.state, "index", None)
    reindex_agent = getattr(app.state, "reindex_agent", None)

    if vault is None or index is None or reindex_agent is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Server not fully initialised"},
        )

    async def _run() -> None:
        try:
            count = await reindex_agent.run(vault, index)
            logger.info("[AGENT] Manual re-index complete: %d note(s) re-indexed", count)
        except Exception as exc:
            logger.error("[AGENT] Manual re-index failed: %s", exc, exc_info=True)

    background_tasks.add_task(_run)
    return JSONResponse(status_code=202, content={"status": "accepted"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
