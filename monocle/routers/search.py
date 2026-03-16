"""monocle/routers/search.py — Search endpoints (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["search"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/search")
async def semantic_search():
    return _501


@router.get("/search/keyword")
async def keyword_search():
    return _501
