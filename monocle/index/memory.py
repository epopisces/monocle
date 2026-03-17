"""
monocle/index/memory.py — In-memory IndexLayer for unit tests.

No embeddings are computed.  Search is substring-based.
Never use this in production.
"""
from __future__ import annotations

import logging

from monocle.index.base import IndexLayer
from monocle.models import IndexStats, NoteChunk, ScoredChunk

logger = logging.getLogger(__name__)


class MemoryIndex(IndexLayer):
    """Dict-backed index with no embedding computation.

    Intended **exclusively** for unit tests where a real ChromaDB or AI
    provider would be unnecessary and slow.
    """

    def __init__(self) -> None:
        # chunk_id → NoteChunk
        self._chunks: dict[str, NoteChunk] = {}

    # ------------------------------------------------------------------
    # IndexLayer interface
    # ------------------------------------------------------------------

    def upsert_chunks(self, chunks: list[NoteChunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
        logger.debug("MemoryIndex.upsert_chunks: stored %d chunk(s)", len(chunks))

    def delete_file(self, file_path: str) -> None:
        before = len(self._chunks)
        self._chunks = {
            cid: c for cid, c in self._chunks.items() if c.file_path != file_path
        }
        removed = before - len(self._chunks)
        logger.debug("MemoryIndex.delete_file(%s): removed %d chunk(s)", file_path, removed)

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        filters: dict | None = None,
        query_text: str = "",
    ) -> list[ScoredChunk]:
        candidates = list(self._chunks.values())

        # Apply metadata equality filters first
        if filters:
            candidates = [c for c in candidates if self._matches_filters(c, filters)]

        # Substring search (case-insensitive) when query_text is given
        if query_text:
            lower = query_text.lower()
            scored: list[tuple[float, NoteChunk]] = [
                (1.0, c) for c in candidates if lower in c.text.lower()
            ]
        else:
            # No text query — return all (filtered) candidates with score 1.0
            scored = [(1.0, c) for c in candidates]

        # Stable sort: score desc, then chunk_id asc for determinism
        scored.sort(key=lambda t: (-t[0], t[1].chunk_id))
        page = scored[:n_results]

        return [
            ScoredChunk(
                chunk_id=c.chunk_id,
                file_path=c.file_path,
                score=score,
                text=c.text,
                metadata=c.metadata,
            )
            for score, c in page
        ]

    def get_stats(self) -> IndexStats:
        unique_files = len({c.file_path for c in self._chunks.values()})
        return IndexStats(
            total_chunks=len(self._chunks),
            total_files=unique_files,
            collection_name="memory",
            backend="memory",
        )

    def delete_all(self) -> None:
        self._chunks.clear()
        logger.debug("MemoryIndex.delete_all: index cleared")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _matches_filters(self, chunk: NoteChunk, filters: dict) -> bool:
        for key, value in filters.items():
            if chunk.metadata.get(key) != value:
                return False
        return True
