"""monocle/routers/review.py — Review queue endpoints (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["review"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/review")
async def list_review():
    return _501


@router.get("/review/count")
async def review_count():
    return _501


@router.patch("/review/{path:path}/approve")
async def approve_note(path: str):
    return _501


@router.post("/review/approve-all")
async def approve_all():
    return _501
