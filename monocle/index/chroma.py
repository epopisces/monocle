"""
monocle/index/chroma.py — ChromaDB-backed IndexLayer for production use.

Uses a cosine-distance HNSW collection.  The configured ``embed_dimensions``
is stored in collection metadata on creation and validated against it on every
subsequent startup to detect misconfiguration early.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from monocle.index.base import DimensionMismatch, IndexLayer
from monocle.models import IndexStats, NoteChunk, ScoredChunk
from monocle.telemetry import get_meter

if TYPE_CHECKING:
    from monocle.config import Settings

logger = logging.getLogger(__name__)

# OTel metric instruments — created once at import time
_meter = get_meter("monocle.index")
_search_histogram = _meter.create_histogram(
    "index.search_duration",
    unit="ms",
    description="Vector search latency per query",
)
_upsert_histogram = _meter.create_histogram(
    "index.upsert_duration",
    unit="ms",
    description="Chunk upsert latency per file",
)

_COSINE_META: dict[str, Any] = {"hnsw:space": "cosine"}


class ChromaIndex(IndexLayer):
    """Production index backed by a ChromaDB :class:`chromadb.PersistentClient`.

    Collection distance space: ``cosine``.
    On startup, ``embed_dimensions`` is validated against the stored collection
    metadata; :class:`DimensionMismatch` is raised on a mismatch so the
    operator is alerted before any corrupt data is written.
    """

    def __init__(self, settings: "Settings") -> None:
        import chromadb  # lazy — only required for production usage

        self._settings = settings
        self._embed_dimensions: int = settings.ai.embed_dimensions
        self._collection_name: str = settings.index.collection_name
        self._client = chromadb.PersistentClient(path=settings.index.chroma_persist_path)
        self._collection = self._open_collection()
        logger.info(
            "ChromaIndex ready — collection=%s dims=%d backend=chroma",
            self._collection_name,
            self._embed_dimensions,
        )

    # ------------------------------------------------------------------
    # IndexLayer interface
    # ------------------------------------------------------------------

    def upsert_chunks(self, chunks: list[NoteChunk]) -> None:
        if not chunks:
            return

        # Validate embedding dimensions before touching ChromaDB.  Catching this
        # early produces a clear error rather than an opaque ChromaDB exception.
        expected = self._embed_dimensions
        for c in chunks:
            actual = len(c.embedding)
            if actual != expected:
                raise ValueError(
                    f"Embedding dimension mismatch for chunk '{c.chunk_id}': "
                    f"expected {expected} but got {actual}. "
                    "Ensure the embedding was produced by the same model/settings "
                    "as settings.ai.embed_dimensions."
                )

        t0 = time.perf_counter()

        ids = [c.chunk_id for c in chunks]
        embeddings = [c.embedding for c in chunks]
        documents = [c.text for c in chunks]
        # Only scalar metadata values are accepted by ChromaDB
        metadatas: list[dict[str, Any]] = [
            {
                "file_path": c.file_path,
                "chunk_index": c.chunk_index,
                **{
                    k: v
                    for k, v in c.metadata.items()
                    if isinstance(v, (str, int, float, bool))
                },
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1_000
        _upsert_histogram.record(elapsed_ms, {"collection": self._collection_name})
        logger.debug(
            "ChromaIndex.upsert_chunks: %d chunk(s) in %.1f ms", len(chunks), elapsed_ms
        )

    def delete_file(self, file_path: str) -> None:
        self._collection.delete(where={"file_path": {"$eq": file_path}})
        logger.debug("ChromaIndex.delete_file(%s): done", file_path)

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        filters: dict | None = None,
        query_text: str = "",
    ) -> list[ScoredChunk]:
        actual = len(query_embedding)
        if actual != self._embed_dimensions:
            raise ValueError(
                f"Query embedding dimension mismatch: "
                f"expected {self._embed_dimensions} but got {actual}. "
                "Ensure the query was embedded with the same model/settings "
                "as settings.ai.embed_dimensions."
            )

        t0 = time.perf_counter()
        count = self._collection.count()
        if count == 0:
            return []

        effective_n = min(n_results, count)
        where = _build_where(filters) if filters else None

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": effective_n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = self._collection.query(**query_kwargs)

        elapsed_ms = (time.perf_counter() - t0) * 1_000
        _search_histogram.record(elapsed_ms, {"collection": self._collection_name})

        scored: list[ScoredChunk] = []
        for chunk_id, text, meta, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance ∈ [0, 2]; convert to similarity ∈ [0, 1]
            score = max(0.0, 1.0 - (distance / 2.0))
            scored.append(
                ScoredChunk(
                    chunk_id=chunk_id,
                    file_path=meta.get("file_path", ""),
                    score=score,
                    text=text,
                    metadata=meta,
                )
            )

        logger.debug(
            "ChromaIndex.search: %d result(s) in %.1f ms", len(scored), elapsed_ms
        )
        return scored

    def get_stats(self) -> IndexStats:
        count = self._collection.count()
        if count == 0:
            return IndexStats(
                total_chunks=0,
                total_files=0,
                collection_name=self._collection_name,
                backend="chroma",
            )
        all_items = self._collection.get(include=["metadatas"])
        unique_files = len({m.get("file_path", "") for m in all_items["metadatas"]})
        return IndexStats(
            total_chunks=count,
            total_files=unique_files,
            collection_name=self._collection_name,
            backend="chroma",
        )

    def delete_all(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.create_collection(
            name=self._collection_name,
            metadata={**_COSINE_META, "embed_dimensions": self._embed_dimensions},
        )
        logger.info(
            "ChromaIndex.delete_all: collection '%s' wiped and recreated",
            self._collection_name,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_collection(self):
        """Get existing collection (with dimension validation) or create a new one."""
        existing_names = [c.name for c in self._client.list_collections()]
        if self._collection_name in existing_names:
            collection = self._client.get_collection(name=self._collection_name)
            stored_dims = collection.metadata.get("embed_dimensions")
            if stored_dims is not None and int(stored_dims) != self._embed_dimensions:
                raise DimensionMismatch(
                    f"Collection '{self._collection_name}' was created with "
                    f"embed_dimensions={stored_dims} but settings.ai.embed_dimensions="
                    f"{self._embed_dimensions}. "
                    "Either update your config to match the existing collection, "
                    "or delete the collection and re-index."
                )
            return collection

        return self._client.create_collection(
            name=self._collection_name,
            metadata={**_COSINE_META, "embed_dimensions": self._embed_dimensions},
        )


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _build_where(filters: dict) -> dict:
    """Convert a plain equality-filter dict into a ChromaDB ``where`` clause."""
    items = list(filters.items())
    if len(items) == 1:
        key, value = items[0]
        return {key: {"$eq": value}}
    return {"$and": [{k: {"$eq": v}} for k, v in items]}
