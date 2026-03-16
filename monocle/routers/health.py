"""monocle/routers/health.py — GET /api/health"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    ai_reachable: bool
    index_status: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="starting",
        version="0.1.0",
        ai_reachable=False,
        index_status="empty",
    )
