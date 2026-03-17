"""
monocle/tests/test_reindex.py — Unit tests for ReindexAgent and chunker.

Tests use the ``tmp_vault`` and ``memory_index`` fixtures from conftest.py.
No real AI provider is needed — embeddings are skipped (embed_fn=None) and
MemoryIndex does not validate embedding dimensions.
"""
from __future__ import annotations

import asyncio
import datetime
import os
from pathlib import Path

import pytest
import yaml

from monocle.agents.reindex import ReindexAgent, _collect_md_files
from monocle.index.memory import MemoryIndex
from monocle.ingest.chunker import chunk_text
from monocle.models import NoteChunk
from monocle.vault import VaultLayer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = datetime.timezone.utc


def _write_vault_note(vault_root: Path, rel_path: str, body: str, updated: str) -> Path:
    """Write a minimal .md note with the given updated timestamp."""
    path = vault_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {"type": "other", "updated": updated, "created": updated}
    content = f"---\n{yaml.dump(fm)}---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def _t(delta_seconds: int = 0) -> str:
    """Return an ISO-8601 UTC timestamp offset by *delta_seconds* from epoch."""
    base = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=_UTC)
    ts = base + datetime.timedelta(seconds=delta_seconds)
    return ts.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# chunk_text tests
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_text_returns_empty(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   \n  ") == []

    def test_short_text_single_chunk(self):
        result = chunk_text("Hello world")
        assert len(result) == 1
        assert "Hello" in result[0]

    def test_long_text_produces_multiple_chunks(self):
        # 600 words → should exceed 512 tokens
        long_text = " ".join([f"word{i}" for i in range(600)])
        result = chunk_text(long_text, chunk_size=512, overlap=64)
        assert len(result) >= 2

    def test_overlap_creates_shared_tokens(self):
        long_text = " ".join([f"token{i}" for i in range(700)])
        result = chunk_text(long_text, chunk_size=100, overlap=20)
        # Adjacent chunks should share tokens from the overlap
        assert len(result) >= 2
        # The last words of chunk 0 should appear at the start of chunk 1
        # (this is a rough check — exact token boundaries may vary)
        assert len(result[0]) > 0
        assert len(result[1]) > 0

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("some text", chunk_size=10, overlap=10)


# ---------------------------------------------------------------------------
# ReindexAgent — stale detection
# ---------------------------------------------------------------------------


class TestReindexAgentStaleDetection:
    async def test_only_stale_notes_are_reindexed(self, tmp_path: Path):
        """Notes whose indexed updated_at < vault updated are re-indexed.

        Notes already up-to-date should be skipped.
        """
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        # Write two notes to the vault
        _write_vault_note(tmp_path, "work/stale.md", "Stale note body text here.", _t(100))
        _write_vault_note(tmp_path, "work/fresh.md", "Fresh note body text here.", _t(100))

        # Pre-populate index for 'fresh.md' with updated_at = t(100) (same as vault)
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/fresh.md::0",
                file_path="work/fresh.md",
                chunk_index=0,
                text="Fresh note body text here.",
                embedding=[],
                metadata={"updated_at": _t(100)},
            )
        ])
        # 'stale.md' is not in the index at all → stale

        agent = ReindexAgent()
        count = await agent.run(vault, index)

        assert count == 1, f"Expected 1 re-indexed note, got {count}"
        # stale.md should now have chunks
        stats = index.get_stats()
        assert stats.total_files == 2  # fresh (pre-existing) + stale (newly indexed)

    async def test_note_updated_after_index_is_reindexed(self, tmp_path: Path):
        """A note whose vault updated > indexed updated_at is re-indexed."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/note.md", "Updated content.", _t(200))

        # Index with an older timestamp
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/note.md::0",
                file_path="work/note.md",
                chunk_index=0,
                text="Old content.",
                embedding=[],
                metadata={"updated_at": _t(100)},
            )
        ])

        agent = ReindexAgent()
        count = await agent.run(vault, index)

        assert count == 1
        # The chunk should have been replaced with new content
        results = index.search([], query_text="Updated content")
        assert any(r.file_path == "work/note.md" for r in results)

    async def test_up_to_date_note_skipped(self, tmp_path: Path):
        """A note whose vault updated == indexed updated_at is skipped."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/note.md", "Content.", _t(100))
        # Index with same timestamp
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/note.md::0",
                file_path="work/note.md",
                chunk_index=0,
                text="Content.",
                embedding=[],
                metadata={"updated_at": _t(100)},
            )
        ])

        agent = ReindexAgent()
        count = await agent.run(vault, index)

        assert count == 0, "Up-to-date note should not be re-indexed"

    async def test_note_without_updated_frontmatter_always_reindexed(self, tmp_path: Path):
        """A note with no 'updated' frontmatter field is always re-indexed, even
        if it was previously indexed.

        Without this guard, ``note_updated`` is an empty string, and
        ``indexed_updated >= ""`` is always True in Python — permanently freezing
        the note in the index and preventing any future updates from landing.
        """
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        # Write a note with no 'updated' frontmatter (pass updated=None)
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        note_path = tmp_path / "work" / "no-ts.md"
        # Write raw markdown with frontmatter that has no 'updated' field
        note_path.write_text(
            "---\ntype: observation\ndomain: work\n---\nNote without timestamp.\n",
            encoding="utf-8",
        )

        # Pre-populate index with a non-empty updated_at so the bad comparison
        # would have triggered the skip if not guarded
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/no-ts.md::0",
                file_path="work/no-ts.md",
                chunk_index=0,
                text="old content",
                embedding=[],
                metadata={"updated_at": "2026-01-01T12:00:00Z"},
            )
        ])

        agent = ReindexAgent()
        count = await agent.run(vault, index)

        assert count == 1, (
            f"Note without 'updated' frontmatter must always be re-indexed; got count={count}. "
            "A count of 0 means the empty note_updated triggered an incorrect skip."
        )

    async def test_force_reindexes_all(self, tmp_path: Path):
        """force=True clears the index and re-indexes every note."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/a.md", "Note A.", _t(100))
        _write_vault_note(tmp_path, "work/b.md", "Note B.", _t(100))

        # Pre-populate with up-to-date entries
        for rel in ("work/a.md", "work/b.md"):
            index.upsert_chunks([
                NoteChunk(
                    chunk_id=f"{rel}::0",
                    file_path=rel,
                    chunk_index=0,
                    text="pre-indexed",
                    embedding=[],
                    metadata={"updated_at": _t(100)},
                )
            ])

        agent = ReindexAgent()
        count = await agent.run(vault, index, force=True)

        assert count == 2, f"force=True should re-index all 2 notes, got {count}"

    async def test_empty_body_note_not_counted_as_reindexed(self, tmp_path: Path):
        """A note whose body is empty/whitespace-only is NOT included in the
        returned count.  Its existing chunks are deleted from the index, but
        no new chunks are upserted — this is a removal, not an index, so it
        must not be reported as 're-indexed'.
        """
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        # One note with real content, one with an empty body
        _write_vault_note(tmp_path, "work/real.md", "Some actual content.", _t(100))
        _write_vault_note(tmp_path, "work/empty.md", "", _t(100))

        # Pre-index a stale chunk for the empty note so delete_file is exercised
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/empty.md::0",
                file_path="work/empty.md",
                chunk_index=0,
                text="old stale chunk",
                embedding=[],
                metadata={"updated_at": _t(50)},
            )
        ])

        agent = ReindexAgent()
        count = await agent.run(vault, index)

        assert count == 1, (
            f"Only the note with real content should be counted as re-indexed; got {count}"
        )
        # Empty note's stale chunk must have been removed
        assert index.get_file_timestamps().get("work/empty.md") is None, (
            "Empty note's old chunks should have been deleted from the index"
        )


# ---------------------------------------------------------------------------
# ReindexAgent — force=True clears first
# ---------------------------------------------------------------------------


class TestReindexAgentForce:
    async def test_force_calls_delete_all(self, tmp_path: Path):
        """force=True wipes the index before re-indexing."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/note.md", "Body text.", _t(100))

        # Insert some stale data
        index.upsert_chunks([
            NoteChunk(
                chunk_id="old_file.md::0",
                file_path="old_file.md",
                chunk_index=0,
                text="Old stale data",
                embedding=[],
                metadata={"updated_at": _t(0)},
            )
        ])
        assert index.get_stats().total_chunks == 1

        agent = ReindexAgent()
        await agent.run(vault, index, force=True)

        # Old stale data should be gone (index was wiped before re-index)
        results = index.search([], query_text="Old stale data")
        assert results == [], "force=True should wipe old stale entries"


# ---------------------------------------------------------------------------
# ReindexAgent — startup_check
# ---------------------------------------------------------------------------


class TestReindexAgentStartupCheck:
    async def test_startup_check_runs_when_index_empty(self, tmp_path: Path):
        """startup_check triggers a full re-index when the index is empty."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/note.md", "Important content.", _t(100))

        agent = ReindexAgent()
        assert agent.health_status == "ready"

        await agent.startup_check(vault, index)

        stats = index.get_stats()
        assert stats.total_chunks > 0, "startup_check should populate the index"

    async def test_startup_check_skips_when_index_not_empty(self, tmp_path: Path):
        """startup_check does nothing when the index already has content."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/note.md", "Body.", _t(100))

        # Pre-populate index
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/note.md::0",
                file_path="work/note.md",
                chunk_index=0,
                text="pre-indexed",
                embedding=[],
                metadata={"updated_at": _t(100)},
            )
        ])

        agent = ReindexAgent()
        call_count = [0]
        original_run = agent.run

        async def counting_run(v, i, force=False):
            call_count[0] += 1
            return await original_run(v, i, force=force)

        agent.run = counting_run  # type: ignore[method-assign]

        await agent.startup_check(vault, index)
        assert call_count[0] == 0, "startup_check should not call run() when index is non-empty"

    async def test_startup_check_skips_empty_vault(self, tmp_path: Path):
        """startup_check does nothing when the vault itself is empty."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        agent = ReindexAgent()
        await agent.startup_check(vault, index)

        # No crash; index remains empty
        assert index.get_stats().total_chunks == 0


# ---------------------------------------------------------------------------
# _collect_md_files helper
# ---------------------------------------------------------------------------


class TestCollectMdFiles:
    def test_finds_md_files(self, tmp_path: Path):
        (tmp_path / "work" / "note.md").parent.mkdir(parents=True)
        (tmp_path / "work" / "note.md").write_text("# Hi")
        (tmp_path / "people" / "alice.md").parent.mkdir(parents=True)
        (tmp_path / "people" / "alice.md").write_text("# Alice")

        files = _collect_md_files(str(tmp_path))
        rel = {os.path.relpath(f, str(tmp_path)).replace(os.sep, "/") for f in files}
        assert "work/note.md" in rel
        assert "people/alice.md" in rel

    def test_excludes_hidden_dirs(self, tmp_path: Path):
        (tmp_path / ".versions" / "note.md").parent.mkdir(parents=True)
        (tmp_path / ".versions" / "note.md").write_text("# Hidden")
        (tmp_path / ".trash" / "note.md").parent.mkdir(parents=True)
        (tmp_path / ".trash" / "note.md").write_text("# Trashed")
        (tmp_path / "work" / "note.md").parent.mkdir(parents=True)
        (tmp_path / "work" / "note.md").write_text("# Visible")

        files = _collect_md_files(str(tmp_path))
        rel = {os.path.relpath(f, str(tmp_path)).replace(os.sep, "/") for f in files}
        assert "work/note.md" in rel
        assert not any(".versions" in r for r in rel)
        assert not any(".trash" in r for r in rel)

    def test_empty_vault_returns_empty_list(self, tmp_path: Path):
        assert _collect_md_files(str(tmp_path)) == []

    def test_nonexistent_path_returns_empty_list(self):
        assert _collect_md_files("/nonexistent/path/xyz") == []

    def test_error_sidecar_files_excluded(self, tmp_path: Path):
        """.error.md sidecar files are excluded from collected results.

        These files are written on ingest failure and must not be fed back into
        the re-index pipeline as if they were regular vault notes.
        """
        (tmp_path / "inbox").mkdir(exist_ok=True)
        (tmp_path / "inbox" / "capture.md").write_text("# Note")
        (tmp_path / "inbox" / "capture.md.error.md").write_text(
            "---\ntype: ingest_error\n---\nFailed."
        )
        (tmp_path / "work").mkdir(exist_ok=True)
        (tmp_path / "work" / "another.md.error.md").write_text("---\ntype: ingest_error\n---\n")

        files = _collect_md_files(str(tmp_path))
        rel = {os.path.relpath(f, str(tmp_path)).replace(os.sep, "/") for f in files}

        assert "inbox/capture.md" in rel, "Regular .md file should be collected"
        assert not any(r.endswith(".error.md") for r in rel), (
            f"Error sidecars should not be collected: {sorted(r for r in rel if 'error' in r)}"
        )

    def test_vault_under_hidden_parent_dir_included(self, tmp_path: Path):
        """Notes are collected even when the vault itself lives inside a directory
        whose name starts with '.', e.g. ~/.config/monocle/vault.

        The hidden-dir guard must check only vault-relative path components,
        not the full absolute path.
        """
        hidden_parent = tmp_path / ".dotparent" / "vault"
        hidden_parent.mkdir(parents=True)
        (hidden_parent / "work").mkdir()
        (hidden_parent / "work" / "note.md").write_text("# Note", encoding="utf-8")

        files = _collect_md_files(str(hidden_parent))
        rel = {os.path.relpath(f, str(hidden_parent)).replace(os.sep, "/") for f in files}

        assert "work/note.md" in rel, (
            f"Note inside vault under hidden parent should be collected; got {rel}"
        )

    def test_dotfile_at_vault_root_included(self, tmp_path: Path):
        """A dotfile directly in the vault root (e.g. .frontmatter.md) is NOT
        excluded — the hidden filter applies only to *directory* components,
        not to the filename itself.
        """
        (tmp_path / ".hidden-note.md").write_text("# Dotfile note", encoding="utf-8")
        (tmp_path / "work").mkdir()
        (tmp_path / "work" / ".hidden-in-subdir.md").write_text("# Also a dotfile", encoding="utf-8")
        (tmp_path / ".versions").mkdir()
        (tmp_path / ".versions" / "note.md").write_text("# In hidden dir", encoding="utf-8")

        files = _collect_md_files(str(tmp_path))
        rel = {os.path.relpath(f, str(tmp_path)).replace(os.sep, "/") for f in files}

        assert ".hidden-note.md" in rel, (
            "Dotfile at vault root should be collected (filter is dir-only)"
        )
        assert "work/.hidden-in-subdir.md" in rel, (
            "Dotfile inside non-hidden subdir should be collected"
        )
        assert not any(".versions" in r for r in rel), (
            "Notes inside hidden directories should still be excluded"
        )


# ---------------------------------------------------------------------------
# MemoryIndex.get_file_timestamps
# ---------------------------------------------------------------------------


class TestMemoryIndexGetFileTimestamps:
    def test_returns_empty_when_no_chunks(self):
        index = MemoryIndex()
        assert index.get_file_timestamps() == {}

    def test_returns_updated_at_per_file(self):
        index = MemoryIndex()
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/a.md::0",
                file_path="work/a.md",
                chunk_index=0,
                text="chunk 0",
                embedding=[],
                metadata={"updated_at": "2026-01-01T12:00:00Z"},
            ),
            NoteChunk(
                chunk_id="work/a.md::1",
                file_path="work/a.md",
                chunk_index=1,
                text="chunk 1",
                embedding=[],
                metadata={"updated_at": "2026-01-01T12:00:00Z"},
            ),
            NoteChunk(
                chunk_id="work/b.md::0",
                file_path="work/b.md",
                chunk_index=0,
                text="chunk 0",
                embedding=[],
                metadata={"updated_at": "2026-01-02T00:00:00Z"},
            ),
        ])

        ts = index.get_file_timestamps()
        assert ts["work/a.md"] == "2026-01-01T12:00:00Z"
        assert ts["work/b.md"] == "2026-01-02T00:00:00Z"
        assert len(ts) == 2

    def test_chunks_without_updated_at_omitted(self):
        index = MemoryIndex()
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/a.md::0",
                file_path="work/a.md",
                chunk_index=0,
                text="no timestamp",
                embedding=[],
                metadata={},
            ),
        ])
        assert index.get_file_timestamps() == {}


# ---------------------------------------------------------------------------
# Timestamp normalisation
# ---------------------------------------------------------------------------


class TestTimestampNormalisation:
    """Tests for _normalise_ts() and its effect on stale-detection logic."""

    def test_normalise_z_unchanged(self):
        """Z-format timestamp is returned unchanged."""
        from monocle.agents.reindex import _normalise_ts

        assert _normalise_ts("2026-01-01T12:00:00Z") == "2026-01-01T12:00:00Z"

    def test_normalise_plus00_converted_to_z(self):
        """+00:00 suffix is normalised to Z."""
        from monocle.agents.reindex import _normalise_ts

        assert _normalise_ts("2026-01-01T12:00:00+00:00") == "2026-01-01T12:00:00Z"

    def test_normalise_empty_string_unchanged(self):
        """Empty string is returned unchanged (no crash)."""
        from monocle.agents.reindex import _normalise_ts

        assert _normalise_ts("") == ""

    def test_normalise_non_utc_offset_unchanged(self):
        """A non-UTC offset (e.g. +05:30) is left as-is — only +00:00 is replaced."""
        from monocle.agents.reindex import _normalise_ts

        ts = "2026-01-01T17:30:00+05:30"
        assert _normalise_ts(ts) == ts

    async def test_z_indexed_plus00_vault_not_reindexed(self, tmp_path: Path):
        """A note whose index entry uses Z is treated as up-to-date vs vault +00:00.

        Python's datetime.isoformat() emits +00:00 for UTC datetimes, while the
        index may have been seeded with the Z representation of the same moment.
        After the _normalise_ts fix both sides compare equal so the note is
        correctly skipped.
        """
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        ts_z = "2026-01-01T12:00:00Z"
        ts_plus = "2026-01-01T12:00:00+00:00"

        path = tmp_path / "work" / "note.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Use single-quoted YAML string so pyyaml does not auto-parse as datetime,
        # ensuring the vault note's 'updated' field is read back as the string
        # with +00:00 suffix (simulating the datetime.isoformat() round-trip).
        content = (
            "---\n"
            "type: other\n"
            f"updated: '{ts_plus}'\n"
            f"created: '{ts_plus}'\n"
            "---\n\n"
            "Body text here.\n"
        )
        path.write_text(content, encoding="utf-8")

        # Seed index with the Z-format representation of the same instant
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/note.md::0",
                file_path="work/note.md",
                chunk_index=0,
                text="Body text here.",
                embedding=[],
                metadata={"updated_at": ts_z},
            )
        ])

        agent = ReindexAgent()
        count = await agent.run(vault, index)
        assert count == 0, (
            f"Same instant expressed as Z vs +00:00 should not trigger re-index; "
            f"got count={count}"
        )

    async def test_plus00_indexed_z_vault_not_reindexed(self, tmp_path: Path):
        """A note whose index entry uses +00:00 is treated as up-to-date vs vault Z."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        ts_z = "2026-01-01T12:00:00Z"
        ts_plus = "2026-01-01T12:00:00+00:00"

        _write_vault_note(tmp_path, "work/note.md", "Body.", ts_z)

        # Seed index with +00:00 format
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/note.md::0",
                file_path="work/note.md",
                chunk_index=0,
                text="Body.",
                embedding=[],
                metadata={"updated_at": ts_plus},
            )
        ])

        agent = ReindexAgent()
        count = await agent.run(vault, index)
        assert count == 0, (
            f"+00:00 index vs Z vault should not trigger re-index; got count={count}"
        )


# ---------------------------------------------------------------------------
# ReindexAgent — per-note error isolation
# ---------------------------------------------------------------------------


class TestReindexAgentNoteIsolation:
    """Failures on individual notes must not abort the rest of the run."""

    async def test_embed_failure_leaves_empty_embedding_run_completes(self, tmp_path: Path):
        """When embed_fn raises for a chunk, that chunk is stored with an empty
        embedding and run() completes without raising.  MemoryIndex accepts
        any embedding size so both notes are indexed.
        """
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/good.md", "Good note contents.", _t(100))
        _write_vault_note(tmp_path, "work/bad.md", "Bad embed note.", _t(100))

        def flaky_embed(text: str) -> list[float]:
            if "bad embed" in text.lower():
                raise RuntimeError("embedding service unavailable")
            return [0.0]

        agent = ReindexAgent(embed_fn=flaky_embed)

        # Should not raise — embed failure is caught per-chunk inside _reindex_note;
        # the chunk is stored with embedding=[] which MemoryIndex accepts.
        count = await agent.run(vault, index)

        assert count == 2, (
            f"Both notes should be indexed despite embed error on one chunk; got {count}"
        )

    async def test_run_continues_after_per_note_exception(self, tmp_path: Path, caplog):
        """A hard failure in _reindex_note (e.g. index write error) is logged at
        ERROR level and skipped; subsequent notes are still processed.
        """
        import logging

        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        _write_vault_note(tmp_path, "work/a.md", "Note A contents.", _t(100))
        _write_vault_note(tmp_path, "work/b.md", "Note B contents.", _t(100))
        _write_vault_note(tmp_path, "work/c.md", "Note C contents.", _t(100))

        agent = ReindexAgent()
        original_reindex = agent._reindex_note
        call_order: list[str] = []

        async def patched_reindex(vault_rel, body, updated_at, idx):
            call_order.append(vault_rel)
            if "b.md" in vault_rel:
                raise RuntimeError("simulated index write failure for b.md")
            return await original_reindex(vault_rel, body, updated_at, idx)

        agent._reindex_note = patched_reindex  # type: ignore[method-assign]

        with caplog.at_level(logging.ERROR, logger="monocle.agents.reindex"):
            count = await agent.run(vault, index)

        # a.md and c.md should be indexed; b.md failed
        assert count == 2, (
            f"Expected 2 successful re-indexes (a + c); got {count}.  "
            f"Call order: {call_order}"
        )
        assert any("b.md" in r.message for r in caplog.records if r.levelno >= logging.ERROR), (
            "Expected an ERROR log mentioning the failing note (b.md)"
        )
        # Confirm all three were attempted
        assert len(call_order) == 3, f"Expected all 3 notes attempted; got {call_order}"


# ---------------------------------------------------------------------------
# ReindexAgent — embed_fn=None guard (non-memory backend safety)
# ---------------------------------------------------------------------------


class TestReindexAgentEmbedGuard:
    """run() must skip re-indexing (with a WARNING) when embed_fn is None and
    the index backend requires real embeddings (i.e. backend != "memory").

    Without this guard the agent would call delete_file() on every note then
    fail at upsert_chunks() because the empty embeddings don't match the
    configured embedding dimensions — silently wiping the entire index.

    MemoryIndex accepts any embedding size, so the guard must NOT fire for the
    "memory" backend; run() must proceed normally in that case.
    """

    def _make_chroma_index(self) -> MemoryIndex:
        """Return a MemoryIndex whose get_stats() reports backend='chroma'."""
        from monocle.models import IndexStats as _IndexStats

        index = MemoryIndex()
        orig = index.get_stats

        def chroma_stats() -> _IndexStats:
            s = orig()
            return _IndexStats(
                backend="chroma",
                total_chunks=s.total_chunks,
                total_files=s.total_files,
                collection_name=s.collection_name,
            )

        index.get_stats = chroma_stats  # type: ignore[method-assign]
        return index

    async def test_run_skips_and_warns_when_no_embed_fn_and_non_memory_backend(
        self, tmp_path: Path, caplog
    ):
        """run() returns 0 and emits a WARNING without calling delete_file when
        embed_fn is None and the backend is not 'memory'."""
        import logging

        vault = VaultLayer(str(tmp_path))
        _write_vault_note(tmp_path, "work/note.md", "Some content.", _t(100))

        index = self._make_chroma_index()

        # Track whether delete_file is ever called
        delete_calls: list[str] = []
        orig_delete = index.delete_file  # type: ignore[attr-defined]

        def tracking_delete(path: str) -> None:
            delete_calls.append(path)
            orig_delete(path)

        index.delete_file = tracking_delete  # type: ignore[method-assign]

        agent = ReindexAgent()  # embed_fn=None

        with caplog.at_level(logging.WARNING, logger="monocle.agents.reindex"):
            count = await agent.run(vault, index)

        assert count == 0, (
            "run() must return 0 when embed_fn is None and backend is non-memory; "
            f"got count={count}"
        )
        assert not delete_calls, (
            "delete_file must not be called when the embed guard fires; "
            f"called with: {delete_calls}"
        )
        assert any(
            "embed_fn" in r.message and r.levelno >= logging.WARNING
            for r in caplog.records
        ), "Expected a WARNING message containing 'embed_fn'"

    async def test_run_skips_and_warns_for_force_mode_too(
        self, tmp_path: Path, caplog
    ):
        """The embed guard must trigger even when force=True to prevent a full
        index wipe when no embed_fn is available."""
        import logging

        vault = VaultLayer(str(tmp_path))
        _write_vault_note(tmp_path, "work/note.md", "Content.", _t(100))

        index = self._make_chroma_index()

        agent = ReindexAgent()  # embed_fn=None

        with caplog.at_level(logging.WARNING, logger="monocle.agents.reindex"):
            count = await agent.run(vault, index, force=True)

        assert count == 0, (
            "force=True must still be blocked by embed guard when embed_fn is None"
        )
        assert any(
            "embed_fn" in r.message and r.levelno >= logging.WARNING
            for r in caplog.records
        ), "Expected a WARNING message containing 'embed_fn'"

    async def test_run_proceeds_for_memory_backend_without_embed_fn(self, tmp_path: Path):
        """MemoryIndex accepts any embedding size, so the guard must NOT fire
        when backend='memory'.  run() must index the note normally."""
        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()
        _write_vault_note(tmp_path, "work/note.md", "Memory backend note.", _t(100))

        agent = ReindexAgent()  # embed_fn=None, memory backend → no guard
        count = await agent.run(vault, index)

        assert count == 1, (
            "run() must proceed normally for MemoryIndex even without embed_fn; "
            f"got count={count}"
        )

    async def test_run_proceeds_for_non_memory_backend_when_embed_fn_provided(
        self, tmp_path: Path
    ):
        """When an embed_fn IS provided, run() must proceed for any backend,
        including non-memory ones."""
        vault = VaultLayer(str(tmp_path))
        _write_vault_note(tmp_path, "work/note.md", "Content.", _t(100))

        index = self._make_chroma_index()

        agent = ReindexAgent(embed_fn=lambda t: [0.1])  # embed_fn provided
        count = await agent.run(vault, index)

        assert count == 1, (
            "run() must proceed when embed_fn is provided, regardless of backend; "
            f"got count={count}"
        )
