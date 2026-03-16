"""monocle/routers/ingest.py — Ingest endpoints (stubs) with rate limiting."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from monocle.rate_limit import limiter

router = APIRouter(tags=["ingest"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.post("/ingest")
@limiter.limit("30/minute")
async def ingest(request: Request):
    return _501


@router.post("/ingest/stream")
@limiter.limit("30/minute")
async def ingest_stream(request: Request):
    return _501
