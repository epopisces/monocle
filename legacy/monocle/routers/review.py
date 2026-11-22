"""monocle/routers/review.py — Review action endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel

from monocle.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review"])


#endregion

# ---------------------------------------------------------------------------
#region #*   Request / response models
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    approved_by: str = "user"


class ApprovalResult(BaseModel):
    file_path: str
    review_status: str
    approval_mode: str
    approved_by: str
    approved_at: str


#endregion

# ---------------------------------------------------------------------------
#region #*   Endpoints
# ---------------------------------------------------------------------------


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

    return ApprovalResult(
        file_path=note.file_path,
        review_status="approved",
        approval_mode="manual",
        approved_by=body.approved_by,
        approved_at=now_iso,
    )


@router.patch("/review/{path:path}/reject")
@limiter.limit("60/minute")
async def reject_note(
    path: str,
    request: Request,
) -> ApprovalResult:
    """Reject a pending note: sets review_status=rejected and removes it from the queue."""
    vault = request.app.state.vault
    index = request.app.state.index

    now_iso = datetime.now(timezone.utc).isoformat()
    updates = {
        "review_status": "rejected",
        "approval_mode": "manual",
        "approved_by": "user",
        "approved_at": now_iso,
    }

    note = await asyncio.to_thread(vault.patch_frontmatter, path, updates)

    try:
        await asyncio.to_thread(index.patch_file_metadata, path, {"review_status": "rejected"})
    except Exception as exc:
        logger.warning("[API] ChromaDB metadata patch failed for %s: %s", path, exc)

    return ApprovalResult(
        file_path=note.file_path,
        review_status="rejected",
        approval_mode="manual",
        approved_by="user",
        approved_at=now_iso,
    )
