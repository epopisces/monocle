"""monocle/routers/notes.py — Note CRUD endpoints (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["notes"])

def _not_implemented() -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/notes")
async def list_notes():
    return _not_implemented()


@router.get("/notes/{path:path}/backlinks")
async def get_note_backlinks(path: str):
    return _not_implemented()


@router.get("/notes/{path:path}")
async def get_note(path: str):
    return _not_implemented()


@router.put("/notes/{path:path}")
async def put_note(path: str):
    return _not_implemented()


@router.patch("/notes/{path:path}")
async def patch_note(path: str):
    return _not_implemented()


@router.delete("/notes/{path:path}")
async def delete_note(path: str):
    return _not_implemented()


@router.post("/notes/{path:path}/move")
async def move_note(path: str):
    return _not_implemented()


@router.get("/templates")
async def list_templates():
    return _not_implemented()
