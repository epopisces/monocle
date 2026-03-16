"""monocle/routers/stats.py — Brain stats endpoint (stub)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["stats"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/stats")
async def get_stats():
    return _501
