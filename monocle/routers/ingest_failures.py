"""monocle/routers/ingest_failures.py — Ingest failure management (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["ingest"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/ingest/failures")
async def list_failures():
    return _501


@router.post("/ingest/failures/retry")
async def retry_failures():
    return _501


@router.delete("/ingest/failures/{failure_id}")
async def delete_failure(failure_id: str):
    return _501
