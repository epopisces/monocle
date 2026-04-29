"""Aggregated capture workbench endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from monocle.models import CaptureWorkbenchResponse
from monocle.services.capture_workbench import build_capture_workbench_response

router = APIRouter(tags=["capture-workbench"])


@router.get("/capture-workbench", response_model=CaptureWorkbenchResponse)
async def get_capture_workbench(
    request: Request,
    limit_per_section: int = Query(default=10, ge=1, le=100),
) -> CaptureWorkbenchResponse:
    return await build_capture_workbench_response(
        request.app.state.ingest_session_store,
        request.app.state.vault,
        request.app.state.failed_registry,
        request.app.state.settings,
        limit_per_section=limit_per_section,
    )