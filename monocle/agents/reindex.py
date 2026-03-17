"""
monocle/agents/reindex.py — ReindexAgent: full-vault re-indexing.

The ReindexAgent scans all Markdown files in the vault, detects which have
changed since they were last indexed (by comparing the note's frontmatter
``updated`` field to the ``updated_at`` value stored in chunk metadata), and
re-embeds only stale files.

Embed function injection
------------------------
In M5 the AI provider does not yet exist (M6).  The agent accepts an optional
``embed_fn: Callable[[str], list[float]] | None`` in its constructor.  When
``None`` (or when running under ``MemoryIndex`` in tests), chunks are stored
without valid embeddings — MemoryIndex ignores embeddings and uses substring
search instead.

In M6+, ``ReindexAgent`` is constructed with a real ``AIProvider.embed``
reference so every chunk is properly embedded.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from monocle.ingest.chunker import chunk_text
from monocle.models import NoteChunk

if TYPE_CHECKING:
    from monocle.index.base import IndexLayer
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)


def _normalise_ts(ts: str) -> str:
    """Normalise an ISO-8601 UTC timestamp to ``Z`` suffix for comparison.

    Python's ``datetime.isoformat()`` emits ``+00:00`` for UTC datetimes;
    the index may store the equivalent ``Z`` form.  Normalise both sides of
    every timestamp comparison so the two representations compare equal.
    """
    return ts.replace("+00:00", "Z") if ts else ts


# Health status string set during a running startup re-index
_HEALTH_STATUS_INDEXING = "indexing"


class ReindexAgent:
    """Full-vault re-index agent.

    Parameters
    ----------
    embed_fn:
        Optional callable ``(text: str) -> list[float]`` used to produce
        embeddings for each chunk.  When ``None`` empty embeddings are stored
        (suitable for ``MemoryIndex`` in tests; ChromaIndex will reject them
        unless dimensions match — ensure the index backend is compatible).
    chunk_size:
        Maximum tokens per chunk (passed to ``chunk_text``).
    chunk_overlap:
        Overlap tokens between adjacent chunks.
    """

    def __init__(
        self,
        embed_fn: Callable[[str], list[float]] | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self._embed_fn = embed_fn
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        # Health status exposed to the /api/health endpoint
        self.health_status: str = "ready"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        vault: "VaultLayer",
        index: "IndexLayer",
        force: bool = False,
    ) -> int:
        """Re-index vault notes that have changed since last index.

        Parameters
        ----------
        vault:
            Vault layer used to list and read notes.
        index:
            Index layer for upsert and delete operations.
        force:
            When ``True``, wipe the entire index before re-indexing all notes
            (full rebuild).  When ``False`` (default), only stale/new notes
            are processed.

        Returns
        -------
        int
            Number of notes re-indexed.
        """
        if force:
            logger.info("[INGEST] ReindexAgent.run(force=True): clearing index")
            await asyncio.to_thread(index.delete_all)

        # Collect all indexed timestamps before scanning (one batch call)
        indexed_ts: dict[str, str] = await asyncio.to_thread(index.get_file_timestamps)

        md_files = _collect_md_files(str(vault.root))
        logger.info(
            "[INGEST] ReindexAgent.run: found %d .md file(s), force=%s", len(md_files), force
        )

        reindexed = 0
        for file_path in md_files:
            vault_rel = os.path.relpath(file_path, str(vault.root)).replace(os.sep, "/")
            try:
                note = vault.read_note(vault_rel)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[INGEST] ReindexAgent: skipping unreadable note %s: %s", vault_rel, exc)
                continue

            note_updated = _normalise_ts(
                note.metadata.updated.isoformat()
                if note.metadata.updated is not None
                else ""
            )
            indexed_updated = _normalise_ts(indexed_ts.get(vault_rel, ""))

            if not force and indexed_updated and indexed_updated >= note_updated:
                logger.debug("[INGEST] ReindexAgent: up-to-date, skipping %s", vault_rel)
                continue

            try:
                indexed = await self._reindex_note(vault_rel, note.body, note_updated, index)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[INGEST] ReindexAgent: failed to re-index %s: %s",
                    vault_rel,
                    exc,
                    exc_info=True,
                )
                continue
            if indexed:
                reindexed += 1

        logger.info("[INGEST] ReindexAgent.run complete: %d note(s) re-indexed", reindexed)
        return reindexed

    async def startup_check(
        self,
        vault: "VaultLayer",
        index: "IndexLayer",
    ) -> None:
        """Trigger a full re-index on startup if the index is empty.

        Sets ``health_status`` to ``"indexing"`` while running so the
        ``GET /api/health`` endpoint can report progress.
        """
        stats = await asyncio.to_thread(index.get_stats)
        if stats.total_chunks > 0:
            logger.debug(
                "[INGEST] ReindexAgent.startup_check: index not empty (%d chunk(s)), skipping",
                stats.total_chunks,
            )
            return

        md_files = _collect_md_files(str(vault.root))
        if not md_files:
            logger.debug("[INGEST] ReindexAgent.startup_check: vault is empty, nothing to index")
            return

        logger.info(
            "[INGEST] ReindexAgent.startup_check: index empty, triggering full re-index "
            "(%d note(s) found)",
            len(md_files),
        )
        self.health_status = _HEALTH_STATUS_INDEXING
        try:
            await self.run(vault, index, force=False)
        finally:
            self.health_status = "ready"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _reindex_note(
        self,
        vault_rel: str,
        body: str,
        updated_at: str,
        index: "IndexLayer",
    ) -> bool:
        """Chunk, embed (if embed_fn configured), and upsert a single note.

        Returns
        -------
        bool
            ``True`` if at least one chunk was upserted, ``False`` if the note
            body was empty/whitespace-only (existing chunks were still deleted).
        """
        # Remove existing chunks so stale chunk count doesn't accumulate
        await asyncio.to_thread(index.delete_file, vault_rel)

        texts = chunk_text(body, chunk_size=self._chunk_size, overlap=self._chunk_overlap)
        if not texts:
            logger.debug("[INGEST] ReindexAgent: empty body, removed existing chunks for %s", vault_rel)
            return False

        chunks: list[NoteChunk] = []
        for i, text in enumerate(texts):
            embedding: list[float] = []
            if self._embed_fn is not None:
                try:
                    embedding = await asyncio.to_thread(self._embed_fn, text)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[INGEST] ReindexAgent: embed failed for %s chunk %d: %s",
                        vault_rel, i, exc,
                    )

            chunks.append(
                NoteChunk(
                    chunk_id=f"{vault_rel}::{i}",
                    file_path=vault_rel,
                    chunk_index=i,
                    text=text,
                    embedding=embedding,
                    metadata={"updated_at": updated_at},
                )
            )

        await asyncio.to_thread(index.upsert_chunks, chunks)
        logger.debug(
            "[INGEST] ReindexAgent: upserted %d chunk(s) for %s", len(chunks), vault_rel
        )
        return True


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _collect_md_files(vault_root: str) -> list[str]:
    """Return absolute paths of all .md files in *vault_root* (recursive).

    Excludes:
    - Hidden directories (path components starting with ``.``) such as
      ``.versions/``, ``.trash/``, and ``.templates/``.
    - Dotfiles (files whose names start with ``.'') are **not** excluded —
      only hidden *directory* components in the vault-relative path are
      filtered.
    - ``.error.md`` sidecar files written on ingest failure.
    - Symlinks that resolve outside *vault_root* (path-traversal guard).
    """
    results: list[str] = []
    root = Path(vault_root)
    if not root.is_dir():
        return results

    real_root = os.path.realpath(str(root))

    for f in root.rglob("*.md"):
        # Skip hidden subdirectories (.versions, .trash, .templates, etc.).
        # Check only the directory components of the vault-relative path
        # (rel_parts[:-1]) so that:
        # 1. Dotfiles like .frontmatter.md at the vault root are NOT excluded.
        # 2. A vault installed under a hidden parent dir (e.g. ~/.config/…)
        #    is not silently emptied (rel_parts is vault-relative, not absolute).
        try:
            rel_parts = f.relative_to(root).parts
        except ValueError:
            rel_parts = f.parts  # fall back to full parts if relative_to fails
        if any(part.startswith(".") for part in rel_parts[:-1]):
            continue

        # Skip .error.md sidecar files written on ingest failure
        if f.name.endswith(".error.md"):
            continue

        # Reject symlinks that resolve outside the vault root
        real_f = os.path.realpath(str(f))
        try:
            Path(real_f).relative_to(real_root)
        except ValueError:
            logger.warning(
                "[INGEST] _collect_md_files: skipping path that escapes vault root: %s → %s",
                f,
                real_f,
            )
            continue

        results.append(str(f))

    return results
