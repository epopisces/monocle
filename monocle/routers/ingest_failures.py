"""monocle/routers/ingest_failures.py — Failed-ingest management endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)


class RetryRequest(BaseModel):
    id: str  # record id to retry


@router.get("/ingest/failures")
async def list_failures(request: Request) -> list[dict]:
    """Return all failed-ingest records, newest first."""
    registry = request.app.state.failed_registry
    return registry.get_all()


@router.post("/ingest/failures/retry", status_code=200)
async def retry_failure(body: RetryRequest, request: Request) -> dict:
    """Retry a previously failed ingest using stored content preview."""
    registry = request.app.state.failed_registry
    pipeline = request.app.state.ingest_pipeline

    record = registry.get(body.id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Failed-ingest record not found: {body.id}")

    from monocle.models import IngestRequest

    # Reconstruct the request from stored data.
    # content_preview is truncated to 200 chars; this is the best we can do
    # without storing the full original content.
    source = record.get("source", "web")
    content = record.get("content_preview", "")

    req = IngestRequest(content=content, source=source, allow_duplicate=True)

    content_truncated = len(content) >= 200

    try:
        note, confidence = await pipeline.run(req)
        registry.mark_retried(body.id)
        logger.info("[INGEST] Retry succeeded for record %s → %s", body.id, note.file_path)
        return {
            "status": "ok",
            "note_path": note.file_path,
            "confidence": confidence.score,
            "content_truncated": content_truncated,
        }
    except Exception as exc:
        logger.error("[INGEST] Retry failed for record %s: %s", body.id, exc)
        raise HTTPException(status_code=422, detail="Retry failed. See server logs for details.")


@router.delete("/ingest/failures/{failure_id}", status_code=204)
async def delete_failure(failure_id: str, request: Request) -> None:
    """Remove a failed-ingest record from the list.

    The underlying ``.error.md`` sidecar file is NOT deleted.
    """
    registry = request.app.state.failed_registry
    found = registry.delete(failure_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Record not found: {failure_id}")
