"""monocle/routers/settings.py — Settings endpoints (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["settings"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/settings")
async def get_settings():
    return _501


@router.patch("/settings")
async def patch_settings():
    return _501


@router.post("/settings/rotate-mcp-key")
async def rotate_mcp_key():
    return _501
