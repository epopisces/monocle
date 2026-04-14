"""monocle/services/notes.py — Canonical read / create / update note services."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from monocle.models import Note
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

logger = logging.getLogger(__name__)

_MAX_BODY_LENGTH = 50_000

_METADATA_TYPE_ALIASES = {
    "person": "person_note",
    "meeting": "meeting_note",
    "blank": "other",
}


async def read_note(vault: "VaultLayer", file_path: str) -> "Note":
    """Read a full note by vault-relative path.

    Args:
        vault: The vault layer instance.
        file_path: Vault-relative path, e.g. ``people/alice.md``.

    Returns:
        The ``Note`` object with metadata and body.
    """
    return await asyncio.to_thread(vault.read_note, file_path)


async def create_note(
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    title: str,
    body: str,
    note_type: str = "observation",
    domain: str = "personal",
    tags: list[str] | None = None,
) -> "Note":
    """Create a new note from a template.

    Notes created through this service are always placed in the review queue
    (``review_status: pending``).

    Args:
        vault: The vault layer instance.
        reindex_queue: Optional reindex queue for triggering embedding updates.
        title: Note title.
        body: Markdown body content.
        note_type: Template type, e.g. ``idea``, ``decision``, ``person_note``.
        domain: Knowledge domain, e.g. ``work`` or ``personal``.
        tags: Optional list of topic tags.

    Returns:
        The newly created ``Note`` object.

    Raises:
        ValueError: If *body* exceeds the character limit or *note_type* is invalid.
    """
    if len(body) > _MAX_BODY_LENGTH:
        raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")
    
    from monocle.vault import TEMPLATE_FILE_MAP

    if note_type not in TEMPLATE_FILE_MAP:
        raise ValueError(
            f"note_type {note_type!r} is not valid. "
            f"Allowed: {', '.join(sorted(TEMPLATE_FILE_MAP))}"
        )

    from monocle.models import NoteMetadata

    metadata_type = _METADATA_TYPE_ALIASES.get(note_type, note_type)

    metadata = NoteMetadata(
        type=metadata_type,  # type: ignore[arg-type]
        domain=domain,
        tags=tags or [],
        review_status="pending",
    )
    note = await asyncio.to_thread(
        vault.create_from_template,
        note_type,
        {"title": title, **metadata.model_dump(exclude={"template"}, exclude_none=True)},
        body,
    )
    await asyncio.to_thread(vault.write_note, note.file_path, note)
    if reindex_queue is not None:
        reindex_queue.push(note.file_path)
    return note


async def update_note(
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    file_path: str,
    body: str,
) -> "Note":
    """Update the body of an existing note (hard overwrite).

    Preserves existing frontmatter and updates the ``updated`` timestamp.

    Args:
        vault: The vault layer instance.
        reindex_queue: Optional reindex queue for triggering embedding updates.
        file_path: Vault-relative path to the existing note.
        body: New Markdown body content (replaces old body entirely).

    Returns:
        The updated ``Note`` object.

    Raises:
        ValueError: If *body* exceeds the character limit.
        FileNotFoundError: If the note does not exist at *file_path*.
    """
    if len(body) > _MAX_BODY_LENGTH:
        raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")

    note = await asyncio.to_thread(vault.read_note, file_path)
    note.body = body
    note.metadata.updated = datetime.now(timezone.utc)
    await asyncio.to_thread(vault.write_note, file_path, note)
    if reindex_queue is not None:
        reindex_queue.push(note.file_path)
    return note
