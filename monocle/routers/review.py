"""monocle/routers/review.py — Review queue endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel

from monocle.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    approved_by: str = "user"


class ApprovalResult(BaseModel):
    file_path: str
    review_status: str
    approval_mode: str
    approved_by: str
    approved_at: str


class ApproveAllResponse(BaseModel):
    approved: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/review")
async def list_review(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return paginated notes with review_status=pending."""
    vault = request.app.state.vault
    page = await asyncio.to_thread(vault.list_notes, limit=10_000, offset=0)
    pending = [ref for ref in page.items if ref.review_status == "pending"]
    total = len(pending)
    # Warm the count cache as a free side-effect of the scan we've already done.
    request.app.state._review_pending_count = total
    items = pending[offset : offset + limit]
    return {
        "items": [r.model_dump() for r in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/review/count")
async def review_count(request: Request) -> dict[str, int]:
    """Return number of notes currently in the review queue.

    Returns the cached value from ``app.state._review_pending_count`` when
    available (O(1)), falling back to a full vault scan when the cache is
    cold (e.g. after a note write invalidates it).
    """
    cached = getattr(request.app.state, "_review_pending_count", None)
    if cached is not None:
        return {"count": cached}
    vault = request.app.state.vault
    page = await asyncio.to_thread(vault.list_notes, limit=10_000, offset=0)
    count = sum(1 for ref in page.items if ref.review_status == "pending")
    request.app.state._review_pending_count = count
    return {"count": count}


@router.patch("/review/{path:path}/approve")
@limiter.limit("60/minute")
async def approve_note(
    path: str,
    request: Request,
    body: ApproveRequest = Body(default_factory=ApproveRequest),
) -> ApprovalResult:
    """Approve a single note: sets review_status, approval_mode, approved_by, approved_at."""
    vault = request.app.state.vault
    index = request.app.state.index

    now_iso = datetime.now(timezone.utc).isoformat()
    updates = {
        "review_status": "approved",
        "approval_mode": "manual",
        "approved_by": body.approved_by,
        "approved_at": now_iso,
    }

    # patch_frontmatter raises NoteNotFound (HTTPException 404) if file is absent
    note = await asyncio.to_thread(vault.patch_frontmatter, path, updates)

    # Mirror review_status into ChromaDB metadata for index-side filtering
    try:
        await asyncio.to_thread(index.patch_file_metadata, path, {"review_status": "approved"})
    except Exception as exc:
        logger.warning("[API] ChromaDB metadata patch failed for %s: %s", path, exc)

    # Decrement count cache; next review_count request returns O(1).
    cached = getattr(request.app.state, "_review_pending_count", None)
    if cached is not None:
        request.app.state._review_pending_count = max(0, cached - 1)

    return ApprovalResult(
        file_path=note.file_path,
        review_status="approved",
        approval_mode="manual",
        approved_by=body.approved_by,
        approved_at=now_iso,
    )


@router.post("/review/approve-all")
@limiter.limit("30/minute")
async def approve_all(
    request: Request,
    body: ApproveRequest = Body(default_factory=ApproveRequest),
) -> ApproveAllResponse:
    """Approve every note currently in the review queue.

    Approvals run concurrently (up to 10 at a time) via ``asyncio.gather``
    so large queues complete significantly faster than a serial loop.
    """
    vault = request.app.state.vault
    index = request.app.state.index

    page = await asyncio.to_thread(vault.list_notes, limit=10_000, offset=0)
    pending = [ref for ref in page.items if ref.review_status == "pending"]

    now_iso = datetime.now(timezone.utc).isoformat()
    updates = {
        "review_status": "approved",
        "approval_mode": "manual",
        "approved_by": body.approved_by,
        "approved_at": now_iso,
    }

    sem = asyncio.Semaphore(10)

    async def _approve_one(ref) -> bool:
        async with sem:
            try:
                await asyncio.to_thread(vault.patch_frontmatter, ref.file_path, updates)
                await asyncio.to_thread(
                    index.patch_file_metadata, ref.file_path, {"review_status": "approved"}
                )
                return True
            except Exception as exc:
                logger.warning("[API] Failed to approve %s: %s", ref.file_path, exc)
                return False

    results = await asyncio.gather(*[_approve_one(ref) for ref in pending])
    approved = sum(1 for ok in results if ok)

    # Update cache: remaining = notes that could not be approved.
    request.app.state._review_pending_count = len(pending) - approved

    return ApproveAllResponse(approved=approved)
