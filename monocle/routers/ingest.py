"""monocle/routers/ingest.py — Ingest endpoints with rate limiting."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from monocle.models import IngestRequest, IngestResponse, IngestSession, IngestSessionDetailResponse
from monocle.rate_limit import limiter

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

# Maximum audio payload (25 MB)
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _check_audio_size(request: IngestRequest) -> None:
    if request.audio_bytes and len(request.audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Audio payload exceeds 25 MB limit ({len(request.audio_bytes)} bytes)",
        )


@router.post("/ingest", response_model=IngestResponse, status_code=202)
@limiter.limit("30/minute")
async def ingest(req: IngestRequest, request: Request) -> IngestResponse:
    """Create a persisted ingest session and archive its raw source."""
    _check_audio_size(req)

    store = request.app.state.ingest_session_store

    try:
        return await asyncio.to_thread(store.create_api_session, req)
    except Exception as exc:
        logger.error("[INGEST] Session capture error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Ingest session capture failed. See server logs for details.")


@router.get("/ingest/sessions", response_model=list[IngestSession])
async def list_sessions(
    request: Request,
    state: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    ready_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[IngestSession]:
    """List persisted ingest sessions for the review workspace."""
    store = request.app.state.ingest_session_store
    return await asyncio.to_thread(
        store.list_sessions,
        state=state,
        origin=origin,
        ready_only=ready_only,
        limit=limit,
        offset=offset,
    )


@router.get("/ingest/sessions/{session_id}", response_model=IngestSessionDetailResponse)
async def get_session(session_id: str, request: Request) -> IngestSessionDetailResponse:
    """Return the full persisted ingest session with its archived sources."""
    store = request.app.state.ingest_session_store
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Ingest session not found: {session_id}")
    return detail


@router.post("/ingest/stream")
@limiter.limit("30/minute")
async def ingest_stream(req: IngestRequest, request: Request) -> StreamingResponse:
    """Streaming ingest capture — emits SSE progress for archival and persistence."""
    _check_audio_size(req)

    store = request.app.state.ingest_session_store

    async def _event_stream() -> AsyncIterator[str]:
        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        t0 = time.perf_counter()
        try:
            yield _sse("step_complete", {"step": 1, "name": "source_archival_started"})
            response = await asyncio.to_thread(store.create_api_session, req)
            yield _sse("step_complete", {"step": 2, "name": "session_persisted"})
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            yield _sse(
                "done",
                {
                    "session_id": response.session_id,
                    "state": response.state,
                    "origin": response.origin,
                    "source_ids": response.source_ids,
                    "elapsed_ms": elapsed,
                },
            )
        except Exception as exc:
            logger.error("[INGEST] Stream session-capture error: %s", exc, exc_info=True)
            yield _sse("error", {"message": "Ingest session capture failed. See server logs for details."})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
