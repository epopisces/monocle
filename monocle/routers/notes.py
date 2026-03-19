"""monocle/routers/notes.py — Note CRUD endpoints."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from monocle.models import Note, NoteMetadata, NoteRef, Page

router = APIRouter(tags=["notes"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class NoteWriteRequest(BaseModel):
    """Body for PUT /api/notes/{path} — full note write."""

    title: str
    body: str = ""
    metadata: NoteMetadata = NoteMetadata()
    if_mtime: float | None = None  # optimistic concurrency guard


class NotePatchRequest(BaseModel):
    """Body for PATCH /api/notes/{path} — frontmatter-only patch."""

    updates: dict[str, Any]
    if_mtime: float | None = None


class NoteMoveRequest(BaseModel):
    to_path: str


class BacklinkRef(BaseModel):
    source: str       # vault-relative path of the linking note
    relation: str | None = None
    context: str = ""  # excerpt of linking text


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/notes", response_model=Page[NoteRef])
async def list_notes(
    request: Request,
    folder: str | None = Query(None),
    type: str | None = Query(None),
    domain: str | None = Query(None),
    sort: str = Query("updated"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[NoteRef]:
    vault = request.app.state.vault
    return await asyncio.to_thread(
        vault.list_notes,
        folder=folder,
        type=type,
        domain=domain,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/notes/{path:path}/backlinks", response_model=list[BacklinkRef])
async def get_note_backlinks(path: str, request: Request) -> list[BacklinkRef]:
    """Return all notes that link to `path` via structured links, wikilinks, or people co-mention."""
    vault = request.app.state.vault

    # Normalise target name for matching
    from pathlib import Path
    target_stem = Path(path).stem.lower()

    def _scan() -> list[BacklinkRef]:
        from monocle.vault.wikilinks import parse_wikilinks

        results: list[BacklinkRef] = []
        page = vault.list_notes(limit=10000)
        for ref in page.items:
            if ref.file_path == path:
                continue
            try:
                note = vault.read_note(ref.file_path)
            except Exception:
                continue

            linked = False
            relation: str | None = None
            context = ""

            # 1. Structured links frontmatter
            for lnk in note.metadata.links:
                lnk_target = (lnk.target or "").lower()
                if lnk_target == target_stem or lnk_target == path.lower():
                    linked = True
                    relation = lnk.relation
                    context = f"Structured link: {lnk.target}"
                    break

            # 2. Body wikilinks
            if not linked:
                wikilinks = parse_wikilinks(note.body)
                for wl in wikilinks:
                    if wl.lower() == target_stem or wl.lower() == path.lower():
                        linked = True
                        relation = "links-to"
                        context = f"[[{wl}]]"
                        break

            # 3. People co-mention
            if not linked:
                for person in note.metadata.people:
                    person_slug = re.sub(r"[^\w]", "-", person.lower()).strip("-")
                    if person_slug == target_stem or person.lower() == target_stem:
                        linked = True
                        relation = "mentions"
                        context = f"People mention: {person}"
                        break

            if linked:
                results.append(
                    BacklinkRef(
                        source=ref.file_path,
                        relation=relation,
                        context=context,
                    )
                )
        return results

    return await asyncio.to_thread(_scan)


@router.get("/notes/{path:path}", response_model=Note)
async def get_note(path: str, request: Request) -> Note:
    vault = request.app.state.vault
    return await asyncio.to_thread(vault.read_note, path)


@router.put("/notes/{path:path}", response_model=Note)
async def put_note(path: str, body: NoteWriteRequest, request: Request, response: Response) -> Note:
    vault = request.app.state.vault
    reindex_queue = getattr(request.app.state, "reindex_queue", None)

    # Detect create vs update before writing so we can return 201 vs 200.
    # _safe_resolve validates the path (raises 403 on traversal) without
    # touching the filesystem beyond stat — safe to call pre-write.
    try:
        resolved = vault._safe_resolve(path)
        already_exists = resolved.exists()
    except HTTPException:
        raise

    note = Note(
        file_path=path,
        title=body.title,
        body=body.body,
        metadata=body.metadata,
    )
    await asyncio.to_thread(vault.write_note, path, note, body.if_mtime)

    if reindex_queue is not None:
        reindex_queue.push(path)
    request.app.state._review_pending_count = None  # note write may change review_status

    if not already_exists:
        response.status_code = 201

    # Return the persisted note (with updated mtime)
    return await asyncio.to_thread(vault.read_note, path)


@router.patch("/notes/{path:path}", response_model=Note)
async def patch_note(path: str, body: NotePatchRequest, request: Request) -> Note:
    vault = request.app.state.vault
    reindex_queue = getattr(request.app.state, "reindex_queue", None)

    updated_note = await asyncio.to_thread(vault.patch_frontmatter, path, body.updates, body.if_mtime)

    if reindex_queue is not None:
        reindex_queue.push(path)
    request.app.state._review_pending_count = None  # frontmatter patch may change review_status

    return updated_note


@router.delete("/notes/{path:path}", status_code=204)
async def delete_note(path: str, request: Request) -> None:
    vault = request.app.state.vault
    await asyncio.to_thread(vault.delete_note, path)
    request.app.state._review_pending_count = None  # deleted note may have been pending


@router.post("/notes/{path:path}/move", response_model=dict)
async def move_note(path: str, body: NoteMoveRequest, request: Request) -> dict:
    vault = request.app.state.vault
    await asyncio.to_thread(vault.move_note, path, body.to_path)
    return {"from_path": path, "to_path": body.to_path}


@router.get("/templates", response_model=list[dict])
async def list_templates(request: Request) -> list[dict]:
    vault = request.app.state.vault
    return await asyncio.to_thread(vault.list_templates)
