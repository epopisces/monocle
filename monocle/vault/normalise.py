"""
monocle/vault/normalise.py — Frontmatter schema normalisation.

`normalise_frontmatter` is applied on every note read so that callers
always receive a dict with all expected fields, regardless of whether
the note was written by the ingest pipeline or hand-crafted in Obsidian.
"""
from __future__ import annotations

from typing import Any


# Defaults matching the NoteMetadata schema (see monocle/models.py and build-plan.md)
_DEFAULTS: dict[str, Any] = {
    "type": "other",
    "domain": "personal",
    "people": [],
    "tags": [],
    "action_items": [],
    "links": [],
    "sources": [],
    "confidence": 1.0,
    "confidence_rationale": None,
    "review_status": "approved",  # existing Obsidian notes are trusted
    "approved_by": None,
    "approved_at": None,
    "approval_mode": None,
}


def normalise_frontmatter(fm: dict[str, Any]) -> dict[str, Any]:
    """Apply schema defaults to a parsed frontmatter dict.

    Mutates *and* returns the dict for convenient in-place use::

        fm = normalise_frontmatter(post.metadata)

    Rules:
    - Missing keys are filled from ``_DEFAULTS``.
    - ``links: null``  → ``[]``
    - ``people: null`` → ``[]``
    - ``tags: null``   → ``[]``
    - ``action_items: null`` → ``[]``
    - ``sources: null`` → ``[]``
    """
    for key, default in _DEFAULTS.items():
        if key not in fm or fm[key] is None:
            # For list fields the default is a new list each time
            fm[key] = list(default) if isinstance(default, list) else default

    # Coerce null list fields that were explicitly set to None in YAML
    for list_field in ("people", "tags", "action_items", "links", "sources"):
        if fm.get(list_field) is None:
            fm[list_field] = []

    return fm
