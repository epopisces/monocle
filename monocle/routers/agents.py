"""monocle/routers/agents.py — Scheduled-agent trigger endpoints (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["agents"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.post("/agents/weekly-summary")
async def trigger_weekly_summary():
    return _501


@router.post("/agents/reindex")
async def trigger_reindex():
    return _501
