"""
monocle/tests/conftest.py — Shared pytest fixtures for M1 and beyond.
"""
from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path

import pytest

from monocle.models import Note, NoteMetadata


# ---------------------------------------------------------------------------
# Fixture: tmp_vault
# ---------------------------------------------------------------------------

_FIXTURE_NOTES: list[dict] = [
    {
        "path": "people/alice-example.md",
        "frontmatter": {
            "type": "person_note",
            "domain": "work",
            "people": ["Alice Example"],
            "tags": ["colleague"],
            "source": "web",
            "confidence": 0.9,
            "review_status": "approved",
        },
        "body": "Alice is a senior engineer on the platform team.",
    },
    {
        "path": "work/decide-python-stack.md",
        "frontmatter": {
            "type": "decision",
            "domain": "work",
            "tags": ["architecture", "python"],
            "source": "web",
            "confidence": 0.85,
            "review_status": "approved",
        },
        "body": "We decided to use Python 3.12 + FastAPI for the backend.",
    },
    {
        "path": "work/kickoff-meeting.md",
        "frontmatter": {
            "type": "meeting_note",
            "domain": "work",
            "people": ["Alice Example", "Bob Smith"],
            "tags": ["kickoff"],
            "source": "web",
            "confidence": 0.8,
            "review_status": "approved",
        },
        "body": "Discussed project timeline and assigned initial tasks.",
    },
    {
        "path": "technologies/idea-graph-viz.md",
        "frontmatter": {
            "type": "idea",
            "domain": "personal",
            "tags": ["graph", "visualization"],
            "source": "web",
            "confidence": 0.7,
            "review_status": "pending",
        },
        "body": "What if we visualised note connections as a force-directed graph?",
    },
    {
        "path": "inbox/raw-capture.md",
        "frontmatter": {
            "type": "other",
            "domain": "personal",
            "tags": [],
            "source": "voice",
            "confidence": 0.35,
            "review_status": "pending",
        },
        "body": "Unprocessed voice capture — needs routing.",
    },
]


def _write_note(vault_root: Path, path: str, frontmatter: dict, body: str) -> None:
    """Write a minimal Obsidian-compatible Markdown note."""
    import yaml

    note_path = vault_root / path
    note_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    fm = {"created": now, "updated": now, **frontmatter}
    content = f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n"
    note_path.write_text(content, encoding="utf-8")


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Temporary vault directory with one fixture note per template type."""
    try:
        import yaml  # noqa: F401 — ensure it's available
    except ImportError:
        pytest.skip("pyyaml not installed")

    for note in _FIXTURE_NOTES:
        _write_note(tmp_path, note["path"], note["frontmatter"], note["body"])

    # Create expected vault subdirectories
    for subdir in ("inbox", "people", "work", "technologies", "summaries", ".templates"):
        (tmp_path / subdir).mkdir(exist_ok=True)

    return tmp_path


# ---------------------------------------------------------------------------
# Fixture: memory_index
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_index():
    """Fresh MemoryIndex instance (no embeddings, substring search).

    The MemoryIndex class is created in M4; this fixture returns None in M1
    and is replaced with a real instance when monocle.index.memory is wired.
    """
    try:
        from monocle.index.memory import MemoryIndex

        return MemoryIndex()
    except ImportError:
        return None
