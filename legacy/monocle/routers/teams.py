"""monocle/routers/teams.py — Microsoft Teams Bot Framework endpoint (stub)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["teams"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.post("/teams/messages")
async def teams_messages():
    return _501
