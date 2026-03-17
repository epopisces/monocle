"""
monocle/index/base.py — IndexLayer abstract base class and shared exceptions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from monocle.models import IndexStats, NoteChunk, ScoredChunk


class DimensionMismatch(RuntimeError):
    """Raised when the configured embed_dimensions doesn't match an existing collection."""


class IndexLayer(ABC):
    """Abstract interface for the vector index backend.

    All methods are synchronous.  Call-sites that require async should wrap
    calls with ``asyncio.to_thread(index.method, ...)`` or equivalent.
    """

    @abstractmethod
    def upsert_chunks(self, chunks: list[NoteChunk]) -> None:
        """Insert or update chunks.  Keyed on ``NoteChunk.chunk_id``."""

    @abstractmethod
    def delete_file(self, file_path: str) -> None:
        """Remove every chunk associated with *file_path*."""

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        filters: dict | None = None,
        query_text: str = "",
    ) -> list[ScoredChunk]:
        """Return up to *n_results* chunks ranked by relevance.

        Parameters
        ----------
        query_embedding:
            Embedding vector used by ``ChromaIndex`` for cosine similarity.
        n_results:
            Maximum number of results to return.
        filters:
            Optional metadata equality filters.  Supported keys: ``type``,
            ``domain``, ``source``.  Multiple keys are combined with AND.
        query_text:
            Plain-text query used by ``MemoryIndex`` for substring matching.
            Ignored by ``ChromaIndex``.
        """

    @abstractmethod
    def get_stats(self) -> IndexStats:
        """Return aggregate statistics for the index."""

    @abstractmethod
    def delete_all(self) -> None:
        """Wipe the entire index (all chunks for all files)."""
