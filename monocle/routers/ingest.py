"""monocle/routers/ingest.py — Ingest endpoints with rate limiting."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from fastapi import Response

from monocle.models import (
    CountResponse,
    IngestOpenQuestionAnswerRequest,
    IngestNotificationSummary,
    IngestRequest,
    IngestResponse,
    IngestSession,
    IngestSessionDetailResponse,
    IngestTrueUpResponse,
    ProposedActionPatchRequest,
)
from monocle.rate_limit import limiter
from monocle.services.ingest_review import (
    answer_review_question,
    approve_all_review_actions,
    load_review_session,
    set_review_action_approval,
    start_review_session,
    update_review_action,
)

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


def _api_ingest_request(request: IngestRequest) -> IngestRequest:
    return request.model_copy(update={"origin": "api"})


@router.post("/ingest", response_model=IngestResponse, status_code=202)
@limiter.limit("30/minute")
async def ingest(req: IngestRequest, request: Request) -> IngestResponse:
    """Create a persisted ingest session and archive its raw source."""
    api_req = _api_ingest_request(req)
    _check_audio_size(api_req)

    store = request.app.state.ingest_session_store

    try:
        return await asyncio.to_thread(store.create_api_session, api_req)
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
    vault = request.app.state.vault
    detail = await load_review_session(store, vault, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Ingest session not found: {session_id}")
    return detail


@router.post("/ingest/sessions/{session_id}/start-review", response_model=IngestSessionDetailResponse)
async def start_review(session_id: str, request: Request) -> IngestSessionDetailResponse:
    store = request.app.state.ingest_session_store
    vault = request.app.state.vault
    detail = await start_review_session(store, vault, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Ingest session not found: {session_id}")
    return detail


@router.patch("/ingest/sessions/{session_id}/questions/{question_id}", response_model=IngestSessionDetailResponse)
async def answer_question(
    session_id: str,
    question_id: str,
    body: IngestOpenQuestionAnswerRequest,
    request: Request,
) -> IngestSessionDetailResponse:
    store = request.app.state.ingest_session_store
    vault = request.app.state.vault
    detail = await answer_review_question(store, vault, session_id, question_id, body.answer)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Question not found for ingest session: {session_id}")
    return detail


@router.patch("/ingest/sessions/{session_id}/actions/{action_id}", response_model=IngestSessionDetailResponse)
async def patch_proposed_action(
    session_id: str,
    action_id: str,
    body: ProposedActionPatchRequest,
    request: Request,
) -> IngestSessionDetailResponse:
    store = request.app.state.ingest_session_store
    vault = request.app.state.vault
    detail = await update_review_action(
        store,
        vault,
        session_id,
        action_id,
        target_file_path=body.target_file_path,
        target_note_type=body.target_note_type,
        rationale=body.rationale,
        proposed_content=body.proposed_content,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Proposed action not found: {action_id}")
    return detail


@router.post("/ingest/sessions/{session_id}/actions/{action_id}/approve", response_model=IngestSessionDetailResponse)
async def approve_proposed_action(
    session_id: str,
    action_id: str,
    request: Request,
) -> IngestSessionDetailResponse:
    store = request.app.state.ingest_session_store
    vault = request.app.state.vault
    detail = await set_review_action_approval(store, vault, session_id, action_id, "approved")
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Proposed action not found: {action_id}")
    return detail


@router.post("/ingest/sessions/{session_id}/actions/{action_id}/reject", response_model=IngestSessionDetailResponse)
async def reject_proposed_action(
    session_id: str,
    action_id: str,
    request: Request,
) -> IngestSessionDetailResponse:
    store = request.app.state.ingest_session_store
    vault = request.app.state.vault
    detail = await set_review_action_approval(store, vault, session_id, action_id, "rejected")
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Proposed action not found: {action_id}")
    return detail


@router.post("/ingest/sessions/{session_id}/approve-all", response_model=IngestSessionDetailResponse)
async def approve_all_actions(session_id: str, request: Request) -> IngestSessionDetailResponse:
    store = request.app.state.ingest_session_store
    vault = request.app.state.vault
    detail = await approve_all_review_actions(store, vault, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Ingest session not found: {session_id}")
    return detail


@router.post("/ingest/sessions/{session_id}/true-up", response_model=IngestTrueUpResponse, status_code=202)
async def true_up_session(session_id: str, request: Request) -> IngestTrueUpResponse:
    store = request.app.state.ingest_session_store
    response = await asyncio.to_thread(store.enqueue_true_up, session_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"Ingest session not found: {session_id}")
    return response


@router.get("/ingest/notifications", response_model=list[IngestNotificationSummary])
async def list_notifications(
    request: Request,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[IngestNotificationSummary]:
    store = request.app.state.ingest_session_store
    return await asyncio.to_thread(
        store.list_notifications,
        status=status,
        kind=kind,
        limit=limit,
        offset=offset,
    )


@router.get("/ingest/notifications/count", response_model=CountResponse)
async def count_notifications(
    request: Request,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
) -> CountResponse:
    store = request.app.state.ingest_session_store
    count = await asyncio.to_thread(store.count_notifications, status=status, kind=kind)
    return CountResponse(count=count)


@router.post("/ingest/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(notification_id: str, request: Request) -> Response:
    store = request.app.state.ingest_session_store
    updated = await asyncio.to_thread(store.set_notification_status, notification_id, "read")
    if not updated:
        raise HTTPException(status_code=404, detail=f"Notification not found: {notification_id}")
    return Response(status_code=204)


@router.post("/ingest/notifications/{notification_id}/dismiss", status_code=204)
async def dismiss_notification(notification_id: str, request: Request) -> Response:
    store = request.app.state.ingest_session_store
    updated = await asyncio.to_thread(store.set_notification_status, notification_id, "dismissed")
    if not updated:
        raise HTTPException(status_code=404, detail=f"Notification not found: {notification_id}")
    return Response(status_code=204)


@router.post("/ingest/stream")
@limiter.limit("30/minute")
async def ingest_stream(req: IngestRequest, request: Request) -> StreamingResponse:
    """Streaming ingest capture — emits SSE progress for archival and persistence."""
    api_req = _api_ingest_request(req)
    _check_audio_size(api_req)

    store = request.app.state.ingest_session_store

    async def _event_stream() -> AsyncIterator[str]:
        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        t0 = time.perf_counter()
        try:
            yield _sse("step_complete", {"step": 1, "name": "source_archival_started"})
            response = await asyncio.to_thread(store.create_api_session, api_req)
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
