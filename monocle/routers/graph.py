"""monocle/routers/graph.py — Knowledge graph endpoint (stub)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["graph"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/graph")
async def get_graph():
    return _501
