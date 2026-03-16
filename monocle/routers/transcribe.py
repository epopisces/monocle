"""monocle/routers/transcribe.py — Audio transcription endpoint (stub)."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from monocle.rate_limit import limiter

router = APIRouter(tags=["transcribe"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.post("/transcribe")
@limiter.limit("30/minute")
async def transcribe(request: Request):
    return _501
