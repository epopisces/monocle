"""
monocle/tests/test_index.py — Parametrized tests for IndexLayer implementations.

Both MemoryIndex and ChromaIndex are exercised against the same test cases.
ChromaIndex is tested using a pure-Python fake ChromaDB client (injected via
monkeypatch) so that the tests do not depend on the ChromaDB Rust backend which
may be unavailable in some environments.

Chroma-specific tests (DimensionMismatch, factory) are kept in separate classes.
"""
from __future__ import annotations

import math
from typing import Any

import pytest

from monocle.index.base import DimensionMismatch
from monocle.index.memory import MemoryIndex
from monocle.models import IndexStats, NoteChunk

# ---------------------------------------------------------------------------
# Pure-Python ChromaDB fake — replaces PersistentClient in tests
# ---------------------------------------------------------------------------


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Return cosine distance in [0, 2] (same range as ChromaDB cosine space)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-10
    norm_b = math.sqrt(sum(x * x for x in b)) or 1e-10
    return 1.0 - dot / (norm_a * norm_b)


def _eval_where(meta: dict, where: dict) -> bool:
    """Evaluate a ChromaDB-style ``where`` clause against a metadata dict."""
    if "$and" in where:
        return all(_eval_where(meta, clause) for clause in where["$and"])
    for key, condition in where.items():
        if key.startswith("$"):
            continue
        if isinstance(condition, dict) and "$eq" in condition:
            if meta.get(key) != condition["$eq"]:
                return False
        elif meta.get(key) != condition:
            return False
    return True


class _FakeCollection:
    """Mimics the subset of the chromadb Collection API used by ChromaIndex."""

    def __init__(self, name: str, metadata: dict | None = None) -> None:
        self.name = name
        self.metadata: dict = metadata or {}
        self._store: dict[str, dict[str, Any]] = {}  # chunk_id → {embedding, document, metadata}

    def count(self) -> int:
        return len(self._store)

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        for id_, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self._store[id_] = {"embedding": emb, "document": doc, "metadata": meta}

    def delete(self, where: dict | None = None, ids: list[str] | None = None) -> None:
        if ids is not None:
            for id_ in ids:
                self._store.pop(id_, None)
        if where is not None:
            to_delete = [
                id_ for id_, item in self._store.items()
                if _eval_where(item["metadata"], where)
            ]
            for id_ in to_delete:
                del self._store[id_]

    def get(
        self,
        include: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict:
        items = list(self._store.items())
        start = offset or 0
        items = items[start:]
        if limit is not None:
            items = items[:limit]
        return {
            "ids": [id_ for id_, _ in items],
            "metadatas": [item["metadata"] for _, item in items],
            "documents": [item["document"] for _, item in items],
        }

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict | None = None,
        include: list[str] | None = None,
    ) -> dict:
        q = query_embeddings[0]
        candidates = list(self._store.items())

        if where:
            candidates = [
                (id_, item) for id_, item in candidates
                if _eval_where(item["metadata"], where)
            ]

        scored = sorted(
            [(id_, item, _cosine_distance(q, item["embedding"])) for id_, item in candidates],
            key=lambda t: t[2],
        )[:n_results]

        return {
            "ids": [[id_ for id_, _, _ in scored]],
            "documents": [[item["document"] for _, item, _ in scored]],
            "metadatas": [[item["metadata"] for _, item, _ in scored]],
            "distances": [[dist for _, _, dist in scored]],
        }


class _FakeChromaClient:
    """Mimics chromadb.PersistentClient (collection persistence only)."""

    def __init__(self) -> None:
        self._collections: dict[str, _FakeCollection] = {}

    def list_collections(self) -> list:
        # ChromaDB returns objects with a `.name` attribute
        return [type("Col", (), {"name": n})() for n in self._collections]

    def create_collection(self, name: str, metadata: dict | None = None) -> _FakeCollection:
        coll = _FakeCollection(name, metadata)
        self._collections[name] = coll
        return coll

    def get_collection(self, name: str) -> _FakeCollection:
        return self._collections[name]

    def delete_collection(self, name: str) -> None:
        self._collections.pop(name, None)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Three-dimensional unit vectors used as embeddings throughout (low overhead).
_E_A = [1.0, 0.0, 0.0]
_E_B = [0.0, 1.0, 0.0]
_E_C = [0.0, 0.0, 1.0]


def _chunk(
    chunk_id: str,
    file_path: str,
    text: str,
    embedding: list[float] | None = None,
    *,
    type_: str = "person_note",
    domain: str = "work",
    source: str = "web",
    chunk_index: int = 0,
) -> NoteChunk:
    return NoteChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        chunk_index=chunk_index,
        text=text,
        embedding=embedding or _E_A,
        metadata={"type": type_, "domain": domain, "source": source},
    )


def _make_fake_chroma_index(
    monkeypatch,
    embed_dimensions: int = 3,
    collection_name: str = "test_notes",
    fake_client: "_FakeChromaClient | None" = None,
):
    """Construct a ChromaIndex backed by a fake in-memory ChromaDB client."""
    from monocle.config import AIConfig, IndexConfig, Settings
    from monocle.index.chroma import ChromaIndex

    client = fake_client or _FakeChromaClient()
    monkeypatch.setattr("chromadb.PersistentClient", lambda path: client)

    settings = Settings(
        index=IndexConfig(collection_name=collection_name),
        ai=AIConfig(embed_dimensions=embed_dimensions),
    )
    return ChromaIndex(settings)


# ---------------------------------------------------------------------------
# Parametrized fixture — both backends
# ---------------------------------------------------------------------------


@pytest.fixture(params=["memory", "chroma"])
def index(request, tmp_path, monkeypatch):
    """Fresh index instance for each test, parametrized over both backends."""
    if request.param == "memory":
        return MemoryIndex()
    return _make_fake_chroma_index(monkeypatch)


# ---------------------------------------------------------------------------
# Common tests (run against both backends)
# ---------------------------------------------------------------------------


class TestUpsertAndSearch:
    def test_search_finds_upserted_chunk(self, index):
        c = _chunk("a.md::0", "a.md", "hello world")
        index.upsert_chunks([c])

        results = index.search(_E_A, n_results=10, query_text="hello")

        assert len(results) == 1
        assert results[0].chunk_id == "a.md::0"
        assert results[0].file_path == "a.md"

    def test_upsert_is_idempotent(self, index):
        """Upserting the same chunk_id twice should not create duplicates."""
        c1 = _chunk("a.md::0", "a.md", "hello world v1")
        c2 = _chunk("a.md::0", "a.md", "hello world v2")
        index.upsert_chunks([c1])
        index.upsert_chunks([c2])

        results = index.search(_E_A, n_results=10, query_text="world")
        chunk_ids = [r.chunk_id for r in results]
        assert chunk_ids.count("a.md::0") == 1

    def test_search_empty_index_returns_empty_list(self, index):
        results = index.search(_E_A, n_results=10, query_text="anything")
        assert results == []

    def test_search_respects_n_results_limit(self, index):
        chunks = [
            _chunk(f"a.md::{i}", "a.md", f"hello world chunk {i}", chunk_index=i)
            for i in range(5)
        ]
        index.upsert_chunks(chunks)

        results = index.search(_E_A, n_results=2, query_text="hello")
        assert len(results) <= 2

    def test_search_score_is_between_0_and_1(self, index):
        index.upsert_chunks([_chunk("a.md::0", "a.md", "hello world")])
        results = index.search(_E_A, n_results=10, query_text="hello")
        assert results
        for r in results:
            assert 0.0 <= r.score <= 1.0


class TestDeleteFile:
    def test_delete_file_removes_all_its_chunks(self, index):
        chunks = [
            _chunk("a.md::0", "a.md", "hello chunk 0"),
            _chunk("a.md::1", "a.md", "hello chunk 1", chunk_index=1),
        ]
        index.upsert_chunks(chunks)
        index.delete_file("a.md")

        results = index.search(_E_A, n_results=10, query_text="hello")
        assert all(r.file_path != "a.md" for r in results)

    def test_delete_file_leaves_other_files_intact(self, index):
        index.upsert_chunks([
            _chunk("a.md::0", "a.md", "hello from a", _E_A),
            _chunk("b.md::0", "b.md", "hello from b", _E_B),
        ])
        index.delete_file("a.md")

        results = index.search(_E_B, n_results=10, query_text="hello")
        file_paths = {r.file_path for r in results}

        assert "b.md" in file_paths
        assert "a.md" not in file_paths

    def test_delete_nonexistent_file_is_safe(self, index):
        """Deleting a file that was never indexed should not raise."""
        index.delete_file("nonexistent.md")  # should not raise


class TestMetadataFilters:
    """search() must honour type, domain, source equality filters."""

    def _setup(self, index):
        index.upsert_chunks([
            _chunk("a.md::0", "a.md", "hello work person",   _E_A, type_="person_note", domain="work",     source="web"),
            _chunk("b.md::0", "b.md", "hello work decision", _E_B, type_="decision",    domain="work",     source="web"),
            _chunk("c.md::0", "c.md", "hello personal idea", _E_C, type_="idea",        domain="personal", source="voice"),
        ])

    def test_filter_by_type(self, index):
        self._setup(index)
        results = index.search(_E_A, n_results=10, filters={"type": "person_note"}, query_text="hello")
        assert all(r.metadata.get("type") == "person_note" for r in results)
        assert len(results) == 1

    def test_filter_by_domain(self, index):
        self._setup(index)
        results = index.search(_E_A, n_results=10, filters={"domain": "work"}, query_text="hello")
        assert all(r.metadata.get("domain") == "work" for r in results)
        assert len(results) == 2

    def test_filter_by_source(self, index):
        self._setup(index)
        results = index.search(_E_C, n_results=10, filters={"source": "voice"}, query_text="hello")
        assert all(r.metadata.get("source") == "voice" for r in results)
        assert len(results) == 1

    def test_multi_filter(self, index):
        self._setup(index)
        results = index.search(
            _E_A, n_results=10,
            filters={"domain": "work", "source": "web"},
            query_text="hello",
        )
        assert len(results) == 2
        for r in results:
            assert r.metadata.get("domain") == "work"
            assert r.metadata.get("source") == "web"

    def test_filter_no_match_returns_empty(self, index):
        self._setup(index)
        results = index.search(_E_A, n_results=10, filters={"type": "weekly_summary"}, query_text="hello")
        assert results == []


class TestGetStats:
    def test_empty_index_stats(self, index):
        stats = index.get_stats()
        assert isinstance(stats, IndexStats)
        assert stats.total_chunks == 0
        assert stats.total_files == 0

    def test_stats_after_upsert(self, index):
        index.upsert_chunks([
            _chunk("a.md::0", "a.md", "hello", _E_A),
            _chunk("a.md::1", "a.md", "world", _E_A, chunk_index=1),
            _chunk("b.md::0", "b.md", "other", _E_B),
        ])
        stats = index.get_stats()
        assert stats.total_chunks == 3
        assert stats.total_files == 2

    def test_stats_decreases_after_delete_file(self, index):
        index.upsert_chunks([
            _chunk("a.md::0", "a.md", "hello"),
            _chunk("b.md::0", "b.md", "world", _E_B),
        ])
        index.delete_file("a.md")
        stats = index.get_stats()
        assert stats.total_chunks == 1
        assert stats.total_files == 1


class TestChromaIndexStats:
    """ChromaIndex-specific stats fields (backend label + collection_name)."""

    def test_backend_label_is_chroma(self, monkeypatch):
        index = _make_fake_chroma_index(monkeypatch, collection_name="my_notes")
        stats = index.get_stats()
        assert stats.backend == "chroma"

    def test_collection_name_matches_config(self, monkeypatch):
        index = _make_fake_chroma_index(monkeypatch, collection_name="custom_col")
        # After upsert we go through the non-zero branch
        index.upsert_chunks([_chunk("a.md::0", "a.md", "hello", _E_A)])
        stats = index.get_stats()
        assert stats.collection_name == "custom_col"

    def test_collection_name_in_empty_stats(self, monkeypatch):
        index = _make_fake_chroma_index(monkeypatch, collection_name="empty_col")
        stats = index.get_stats()
        assert stats.collection_name == "empty_col"


class TestDeleteAll:
    def test_delete_all_empties_index(self, index):
        index.upsert_chunks([
            _chunk("a.md::0", "a.md", "hello", _E_A),
            _chunk("b.md::0", "b.md", "world", _E_B),
        ])
        index.delete_all()
        stats = index.get_stats()
        assert stats.total_chunks == 0
        assert stats.total_files == 0

    def test_index_is_usable_after_delete_all(self, index):
        """delete_all should leave the index in a functional state."""
        index.upsert_chunks([_chunk("a.md::0", "a.md", "before delete")])
        index.delete_all()
        index.upsert_chunks([_chunk("b.md::0", "b.md", "after delete")])
        results = index.search(_E_A, n_results=10, query_text="after")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# ChromaIndex-only tests
# ---------------------------------------------------------------------------


class TestChromaDimensionMismatch:
    def test_raises_on_embed_dimension_mismatch(self, monkeypatch):
        """Creating a collection with dim=3 then opening with dim=5 must raise."""
        # Shared fake client so both instances see the same collections
        shared_client = _FakeChromaClient()

        # First open: creates collection with embed_dimensions=3
        _make_fake_chroma_index(monkeypatch, embed_dimensions=3, collection_name="dim_test", fake_client=shared_client)

        # Second open with different embed_dimensions: must raise DimensionMismatch
        with pytest.raises(DimensionMismatch):
            _make_fake_chroma_index(monkeypatch, embed_dimensions=5, collection_name="dim_test", fake_client=shared_client)

    def test_no_error_when_dimensions_match(self, monkeypatch):
        """Re-opening the same collection with the same dim should succeed."""
        shared_client = _FakeChromaClient()
        _make_fake_chroma_index(monkeypatch, embed_dimensions=3, collection_name="dim_match", fake_client=shared_client)
        _make_fake_chroma_index(monkeypatch, embed_dimensions=3, collection_name="dim_match", fake_client=shared_client)

    def test_upsert_raises_on_wrong_embedding_size(self, monkeypatch):
        """Chunks whose embedding length != embed_dimensions must raise ValueError."""
        index = _make_fake_chroma_index(monkeypatch, embed_dimensions=3)
        bad_chunk = NoteChunk(
            chunk_id="a.md::0",
            file_path="a.md",
            chunk_index=0,
            text="hello",
            embedding=[0.1, 0.2],  # length 2, expects 3
        )
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            index.upsert_chunks([bad_chunk])

    def test_upsert_raises_on_empty_embedding(self, monkeypatch):
        """Chunks with the default empty embedding (NoteChunk default) must raise ValueError."""
        index = _make_fake_chroma_index(monkeypatch, embed_dimensions=3)
        bad_chunk = NoteChunk(
            chunk_id="b.md::0",
            file_path="b.md",
            chunk_index=0,
            text="world",
            # embedding omitted → default []
        )
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            index.upsert_chunks([bad_chunk])

    def test_search_raises_on_wrong_query_embedding_size(self, monkeypatch):
        """Search with a query vector of the wrong length must raise ValueError."""
        index = _make_fake_chroma_index(monkeypatch, embed_dimensions=3)
        with pytest.raises(ValueError, match="Query embedding dimension mismatch"):
            index.search([0.1, 0.2], n_results=5)  # length 2, expects 3

    def test_search_raises_on_empty_query_embedding(self, monkeypatch):
        """Search with an empty query vector must raise ValueError."""
        index = _make_fake_chroma_index(monkeypatch, embed_dimensions=3)
        with pytest.raises(ValueError, match="Query embedding dimension mismatch"):
            index.search([], n_results=5)


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


def test_get_index_returns_chroma_for_chroma_backend(monkeypatch):
    from monocle.config import AIConfig, IndexConfig, Settings
    from monocle.index import get_index
    from monocle.index.chroma import ChromaIndex

    fake_client = _FakeChromaClient()
    monkeypatch.setattr("chromadb.PersistentClient", lambda path: fake_client)

    settings = Settings(
        index=IndexConfig(collection_name="factory_test"),
        ai=AIConfig(embed_dimensions=3),
    )
    idx = get_index(settings)
    assert isinstance(idx, ChromaIndex)


def test_get_index_raises_for_unknown_backend(monkeypatch):
    from monocle.config import IndexConfig, Settings
    from monocle.index import get_index

    settings = Settings(
        index=IndexConfig(backend="azure_search"),  # type: ignore[arg-type]
    )
    with pytest.raises(NotImplementedError):
        get_index(settings)


# ---------------------------------------------------------------------------
# MemoryIndex-specific behaviour
# ---------------------------------------------------------------------------


def test_memory_index_backend_label():
    idx = MemoryIndex()
    assert idx.get_stats().backend == "memory"


def test_memory_index_query_text_is_case_insensitive():
    idx = MemoryIndex()
    idx.upsert_chunks([_chunk("x.md::0", "x.md", "Hello World")])
    results = idx.search([], query_text="hello world")
    assert len(results) == 1


# ---------------------------------------------------------------------------
# ChromaIndex.get_file_timestamps() pagination
# ---------------------------------------------------------------------------


class TestChromaIndexGetFileTimestampsPagination:
    """get_file_timestamps() must page through results so peak memory is
    bounded by _GET_PAGE_SIZE rather than total collection size.
    """

    def _make_chunks_for_files(
        self, n_files: int, chunks_per_file: int = 2
    ) -> list[NoteChunk]:
        chunks = []
        for i in range(n_files):
            fp = f"work/note_{i:03d}.md"
            ts = f"2026-01-{(i % 28) + 1:02d}T12:00:00Z"
            for j in range(chunks_per_file):
                chunks.append(
                    NoteChunk(
                        chunk_id=f"{fp}::{j}",
                        file_path=fp,
                        chunk_index=j,
                        text=f"content {i} chunk {j}",
                        embedding=_E_A,
                        metadata={"updated_at": ts},
                    )
                )
        return chunks

    def test_all_files_returned_across_multiple_pages(self, monkeypatch):
        """With page_size=3 and 5 files (10 chunks), all 5 files are collected."""
        import monocle.index.chroma as chroma_mod

        original_page_size = chroma_mod._GET_PAGE_SIZE
        monkeypatch.setattr(chroma_mod, "_GET_PAGE_SIZE", 3)
        try:
            idx = _make_fake_chroma_index(monkeypatch, embed_dimensions=3)
            chunks = self._make_chunks_for_files(n_files=5, chunks_per_file=2)
            idx.upsert_chunks(chunks)

            ts = idx.get_file_timestamps()

            assert len(ts) == 5, f"Expected 5 files, got {len(ts)}: {list(ts.keys())}"
            for i in range(5):
                fp = f"work/note_{i:03d}.md"
                assert fp in ts, f"Missing {fp}"
        finally:
            monkeypatch.setattr(chroma_mod, "_GET_PAGE_SIZE", original_page_size)

    def test_exact_page_boundary_returns_all_files(self, monkeypatch):
        """Edge case: chunk count exactly equals page_size still loops correctly."""
        import monocle.index.chroma as chroma_mod

        original_page_size = chroma_mod._GET_PAGE_SIZE
        # 4 files × 1 chunk = 4 chunks; page size = 4 → first page full, needs
        # a second empty page to confirm exhaustion.
        monkeypatch.setattr(chroma_mod, "_GET_PAGE_SIZE", 4)
        try:
            idx = _make_fake_chroma_index(monkeypatch, embed_dimensions=3)
            chunks = self._make_chunks_for_files(n_files=4, chunks_per_file=1)
            idx.upsert_chunks(chunks)

            ts = idx.get_file_timestamps()

            assert len(ts) == 4, f"Expected 4 files, got {len(ts)}"
        finally:
            monkeypatch.setattr(chroma_mod, "_GET_PAGE_SIZE", original_page_size)


def test_memory_index_no_query_text_returns_all():
    idx = MemoryIndex()
    idx.upsert_chunks([
        _chunk("a.md::0", "a.md", "foo"),
        _chunk("b.md::0", "b.md", "bar"),
    ])
    # No query_text → return all
    results = idx.search([], query_text="")
    assert len(results) == 2
