"""monocle/routers/notes.py — Note CRUD endpoints (stubs)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["notes"])

_501 = JSONResponse(status_code=501, content={"detail": "Not implemented"})


@router.get("/notes")
async def list_notes():
    return _501


@router.get("/notes/{path:path}/backlinks")
async def get_note_backlinks(path: str):
    return _501


@router.get("/notes/{path:path}")
async def get_note(path: str):
    return _501


@router.put("/notes/{path:path}")
async def put_note(path: str):
    return _501


@router.patch("/notes/{path:path}")
async def patch_note(path: str):
    return _501


@router.delete("/notes/{path:path}")
async def delete_note(path: str):
    return _501


@router.post("/notes/{path:path}/move")
async def move_note(path: str):
    return _501


@router.get("/templates")
async def list_templates():
    return _501
