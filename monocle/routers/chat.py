"""monocle/routers/chat.py — Chat / agent streaming endpoint (stub)."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from monocle.rate_limit import limiter

router = APIRouter(tags=["chat"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(request: Request):
    return _501
