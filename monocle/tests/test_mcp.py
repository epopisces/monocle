"""
monocle/tests/test_mcp.py — Tests for the FastMCP server (M12).

Tests are organised into three groups:
  TestMCPAuth       — Auth middleware (401/200 behaviour)
  TestMCPTools      — Tool logic via mcp.call_tool() (unit tests)
  TestMCPIntegration — HTTP-level tool invocations via JSON-RPC

Auth tests use the FastAPI TestClient so the full ASGI middleware stack
is exercised.  Tool tests call mcp.call_tool() directly with mocked state
so no HTTP overhead or MCP handshake is required.
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monocle.models import (
    GraphData,
    GraphEdge,
    GraphNode,
    IngestConfidence,
    Note,
    NoteMetadata,
    NoteRef,
    Page,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

_TEST_KEY = "test-mcp-key-1234"
_WRONG_KEY = "wrong-key"


@pytest.fixture(autouse=True)
def _reset_mcp_state():
    """Reset module-level MCP state before each test to avoid cross-test bleed."""
    from monocle.mcp_server import _state as mcp_state

    orig = (
        mcp_state.vault,
        mcp_state.index,
        mcp_state.ai,
        mcp_state.ingest_pipeline,
        mcp_state.graph_builder,
        mcp_state.reindex_queue,
        mcp_state._initialised,
    )
    yield
    (
        mcp_state.vault,
        mcp_state.index,
        mcp_state.ai,
        mcp_state.ingest_pipeline,
        mcp_state.graph_builder,
        mcp_state.reindex_queue,
        mcp_state._initialised,
    ) = orig


@pytest.fixture
def mock_vault(tmp_path: Path):
    """VaultLayer-like mock with common methods pre-configured."""
    from monocle.vault import VaultLayer

    vault = VaultLayer(str(tmp_path))

    # Write a real fixture note so read_note, list_notes, etc. work
    note_dir = tmp_path / "people"
    note_dir.mkdir()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    import yaml

    fm = {
        "title": "Alice",
        "type": "person_note",
        "domain": "work",
        "source": "web",
        "created": now,
        "updated": now,
        "confidence": 0.9,
        "review_status": "approved",
        "tags": ["colleague"],
    }
    (note_dir / "alice.md").write_text(
        f"---\n{yaml.dump(fm)}---\n\nAlice is an engineer.\n", encoding="utf-8"
    )
    return vault


@pytest.fixture
def mock_index():
    from monocle.index.memory import MemoryIndex

    return MemoryIndex()


@pytest.fixture
def mock_ai():
    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[0.1] * 1536)
    ai.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    ai.chat = AsyncMock(
        return_value='{"type": "idea", "domain": "personal", "tags": [], "title": "Test Thought"}'
    )
    ai.extract_note_metadata = AsyncMock(return_value=NoteMetadata(type="idea"))
    return ai


@pytest.fixture
def mock_pipeline(mock_vault, mock_index, mock_ai, tmp_path):
    """A real IngestPipeline backed by mock_vault, mock_index, and mock_ai."""
    from monocle.config import Settings
    from monocle.ingest import IngestPipeline
    from monocle.ingest.failed_registry import FailedIngestRegistry
    from monocle.ingest.plugin import IngestPluginRegistry
    from monocle.ingest.plugins import register_default_plugins

    reg = IngestPluginRegistry.get()
    if not reg.plugins:
        register_default_plugins(reg)

    settings = Settings()
    failed_reg = FailedIngestRegistry(path=tmp_path / "failed.json")
    return IngestPipeline(
        vault=mock_vault,
        index=mock_index,
        ai=mock_ai,
        settings=settings,
        registry=reg,
        failed_registry=failed_reg,
    )


@pytest.fixture
def mock_graph_builder(mock_vault):
    from monocle.graph import GraphBuilder

    return GraphBuilder(mock_vault)


@pytest.fixture
def mcp_state(mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder):
    """Inject all components into the MCP module-level state."""
    from monocle.mcp_server import init_mcp_state

    init_mcp_state(mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder)
    return mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder


@pytest.fixture
def auth_client(tmp_path: Path):
    """FastAPI TestClient with the MCP key set so we can exercise auth."""
    from unittest.mock import patch as _patch

    from fastapi.testclient import TestClient

    from monocle.index.memory import MemoryIndex
    from monocle.ingest.failed_registry import FailedIngestRegistry
    from monocle.ingest.plugin import IngestPluginRegistry
    from monocle.ingest.plugins import register_default_plugins
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    (vault_path / "inbox").mkdir()

    vault = VaultLayer(str(vault_path))
    index = MemoryIndex()
    failed_reg = FailedIngestRegistry(path=tmp_path / "failed.json")
    mock_ai_inst = AsyncMock()
    mock_ai_inst.embed = AsyncMock(return_value=[0.1] * 1536)
    mock_ai_inst.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    mock_ai_inst.chat = AsyncMock(return_value='{"type": "other", "domain": "personal", "tags": []}')
    mock_ai_inst.extract_note_metadata = AsyncMock(return_value=NoteMetadata())

    @asynccontextmanager
    async def _test_lifespan(app):
        from monocle.config import Settings
        from monocle.graph import GraphBuilder
        from monocle.ingest import IngestPipeline
        from monocle.mcp_server import init_mcp_state

        _reg = IngestPluginRegistry.get()
        if not _reg.plugins:
            register_default_plugins(_reg)

        settings = Settings()
        rq = ReindexQueue()
        await rq.start()

        pipeline = IngestPipeline(
            vault=vault,
            index=index,
            ai=mock_ai_inst,
            settings=settings,
            registry=_reg,
            failed_registry=failed_reg,
        )

        graph_builder = GraphBuilder(vault)

        app.state.vault = vault
        app.state.index = index
        app.state.ai = mock_ai_inst
        app.state.settings = settings
        app.state.reindex_queue = rq
        app.state.ingest_pipeline = pipeline
        app.state.failed_registry = failed_reg
        app.state.watcher = None
        app.state.graph_builder = graph_builder

        init_mcp_state(vault, index, mock_ai_inst, pipeline, graph_builder)

        yield

        await rq.stop()

    with _patch.dict(os.environ, {"MCP_ACCESS_KEY": _TEST_KEY}):
        with _patch("monocle.main.lifespan", new=_test_lifespan):
            from monocle.main import create_app

            test_app = create_app()
            with TestClient(test_app, raise_server_exceptions=False) as client:
                yield client


# ──────────────────────────────────────────────────────────────────────────────
# TestMCPAuth
# ──────────────────────────────────────────────────────────────────────────────


class TestMCPAuth:
    """Auth middleware enforces x-monocle-key or ?key= before reaching FastMCP."""

    def test_no_key_returns_401(self, auth_client):
        r = auth_client.post("/mcp", json={})
        assert r.status_code == 401

    def test_wrong_key_header_returns_401(self, auth_client):
        r = auth_client.post("/mcp", json={}, headers={"x-monocle-key": _WRONG_KEY})
        assert r.status_code == 401

    def test_wrong_key_query_param_returns_401(self, auth_client):
        r = auth_client.post(f"/mcp?key={_WRONG_KEY}", json={})
        assert r.status_code == 401

    def test_valid_key_header_passes_auth(self, auth_client):
        """A valid header key should not get 401.  Any other status is fine (MCP
        will reject an empty / invalid JSON-RPC body with 4xx, not 401)."""
        r = auth_client.post("/mcp", json={}, headers={"x-monocle-key": _TEST_KEY})
        assert r.status_code != 401

    def test_valid_key_query_param_passes_auth(self, auth_client):
        r = auth_client.post(f"/mcp?key={_TEST_KEY}", json={})
        assert r.status_code != 401

    def test_no_key_configured_rejects_all(self, tmp_path: Path):
        """If MCP_ACCESS_KEY is not set, all requests are rejected."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from monocle.index.memory import MemoryIndex
        from monocle.ingest.failed_registry import FailedIngestRegistry
        from monocle.vault import VaultLayer
        from monocle.watcher import ReindexQueue

        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()
        failed_reg = FailedIngestRegistry(path=tmp_path / "failed.json")
        mock_ai_inst = AsyncMock()

        @asynccontextmanager
        async def _tl(app):
            from monocle.config import Settings
            from monocle.graph import GraphBuilder
            from monocle.ingest import IngestPipeline
            from monocle.ingest.plugin import IngestPluginRegistry
            from monocle.ingest.plugins import register_default_plugins
            from monocle.mcp_server import init_mcp_state

            _reg = IngestPluginRegistry.get()
            if not _reg.plugins:
                register_default_plugins(_reg)
            s = Settings()
            rq = ReindexQueue()
            await rq.start()
            pipeline = IngestPipeline(
                vault=vault,
                index=index,
                ai=mock_ai_inst,
                settings=s,
                registry=_reg,
                failed_registry=failed_reg,
            )
            gb = GraphBuilder(vault)
            app.state.vault = vault
            app.state.index = index
            app.state.ai = mock_ai_inst
            app.state.settings = s
            app.state.reindex_queue = rq
            app.state.ingest_pipeline = pipeline
            app.state.failed_registry = failed_reg
            app.state.watcher = None
            app.state.graph_builder = gb
            init_mcp_state(vault, index, mock_ai_inst, pipeline, gb)
            yield
            await rq.stop()

        # Ensure MCP_ACCESS_KEY is not set
        env_without_key = {k: v for k, v in os.environ.items() if k != "MCP_ACCESS_KEY"}
        with _patch.dict(os.environ, env_without_key, clear=True):
            with _patch("monocle.main.lifespan", new=_tl):
                from monocle.main import create_app

                app = create_app()
                with TestClient(app, raise_server_exceptions=False) as client:
                    # Any key should fail because _key="" matches nothing
                    r = client.post(
                        "/mcp",
                        json={},
                        headers={"x-monocle-key": "any-value"},
                    )
                    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# TestMCPTools
# ──────────────────────────────────────────────────────────────────────────────


def _extract_text(result) -> str:
    """Extract the text content from an mcp.call_tool() return value.

    mcp.call_tool() returns a tuple of (list[ContentBlock], dict).
    The text is at result[0][0].text.
    """
    # result is (list[ContentBlock], raw_dict)
    content_blocks = result[0]
    if not content_blocks:
        return ""
    block = content_blocks[0]
    return block.text if hasattr(block, "text") else str(block)


class TestMCPTools:
    """Direct unit tests for each MCP tool function via mcp.call_tool()."""

    @pytest.mark.asyncio
    async def test_search_vault_returns_list(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("search_vault", {"query": "engineer"})
        data = json.loads(_extract_text(result))
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_search_vault_result_fields(self, mcp_state, mock_index):
        """After upsert, search should return file_path / similarity / chunk fields."""
        from monocle.models import NoteChunk
        from monocle.mcp_server import mcp

        mock_index.upsert_chunks(
            [
                NoteChunk(
                    chunk_id="people/alice.md::0",
                    file_path="people/alice.md",
                    chunk_index=0,
                    text="Alice is a senior engineer",
                    embedding=[0.1] * 1536,
                )
            ]
        )

        result = await mcp.call_tool("search_vault", {"query": "engineer"})
        data = json.loads(_extract_text(result))
        if data:
            assert "file_path" in data[0]
            assert "similarity" in data[0]
            assert "chunk" in data[0]

    @pytest.mark.asyncio
    async def test_read_note_returns_note_data(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("read_note", {"file_path": "people/alice.md"})
        data = json.loads(_extract_text(result))
        assert data["file_path"] == "people/alice.md"
        assert "body" in data
        assert "type" in data

    @pytest.mark.asyncio
    async def test_read_note_missing_file_raises(self, mcp_state):
        from monocle.mcp_server import mcp

        with pytest.raises(Exception):
            await mcp.call_tool("read_note", {"file_path": "nonexistent/note.md"})

    @pytest.mark.asyncio
    async def test_browse_recent_returns_list(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("browse_recent", {"limit": 5})
        data = json.loads(_extract_text(result))
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_browse_recent_result_fields(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("browse_recent", {"limit": 5})
        data = json.loads(_extract_text(result))
        if data:
            item = data[0]
            assert "file_path" in item
            assert "title" in item
            assert "type" in item
            assert "domain" in item

    @pytest.mark.asyncio
    async def test_create_note_returns_file_path(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool(
            "create_note",
            {
                "title": "Test Idea",
                "body": "# Test\n\nSome content here.",
                "note_type": "idea",
                "domain": "personal",
            },
        )
        data = json.loads(_extract_text(result))
        assert "file_path" in data
        assert data["status"] == "created"

    @pytest.mark.asyncio
    async def test_create_note_pending_review(self, mcp_state, mock_vault):
        """Notes created via MCP must have review_status=pending."""
        from monocle.mcp_server import mcp

        result = await mcp.call_tool(
            "create_note",
            {"title": "MCP Created Note", "body": "Some content.", "note_type": "idea"},
        )
        data = json.loads(_extract_text(result))
        file_path = data["file_path"]

        note = mock_vault.read_note(file_path)
        assert note.metadata.review_status == "pending"

    @pytest.mark.asyncio
    async def test_update_note_changes_body(self, mcp_state, mock_vault):
        from monocle.mcp_server import mcp

        new_body = "# Updated\n\nThis body was updated by the MCP tool."
        result = await mcp.call_tool(
            "update_note",
            {"file_path": "people/alice.md", "body": new_body},
        )
        data = json.loads(_extract_text(result))
        assert data["status"] == "updated"

        note = mock_vault.read_note("people/alice.md")
        assert note.body.strip() == new_body.strip()

    @pytest.mark.asyncio
    async def test_update_note_body_too_long(self, mcp_state):
        from monocle.mcp_server import mcp

        with pytest.raises(Exception):
            await mcp.call_tool(
                "update_note",
                {"file_path": "people/alice.md", "body": "x" * 50_001},
            )

    @pytest.mark.asyncio
    async def test_get_graph_returns_graph_data(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("get_graph", {})
        data = json.loads(_extract_text(result))
        assert "nodes" in data
        assert "edges" in data

    @pytest.mark.asyncio
    async def test_get_graph_with_focus(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("get_graph", {"focus": "people/alice.md"})
        data = json.loads(_extract_text(result))
        assert "nodes" in data
        assert "edges" in data

    @pytest.mark.asyncio
    async def test_get_stats_returns_counts(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("get_stats", {})
        data = json.loads(_extract_text(result))
        assert "total_notes" in data
        assert "by_type" in data
        assert "by_domain" in data
        assert "pending_review" in data
        assert "index_chunks" in data

    @pytest.mark.asyncio
    async def test_capture_thought_creates_note(self, mcp_state, mock_vault):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool(
            "capture_thought",
            {"content": "I had an idea about using graph visualisation for note clusters."},
        )
        data = json.loads(_extract_text(result))
        assert "file_path" in data
        assert "review_status" in data

    @pytest.mark.asyncio
    async def test_capture_thought_returns_file_path(self, mcp_state):
        from monocle.mcp_server import mcp

        result = await mcp.call_tool(
            "capture_thought",
            {"content": "Short thought."},
        )
        data = json.loads(_extract_text(result))
        assert isinstance(data["file_path"], str)
        assert len(data["file_path"]) > 0

    @pytest.mark.asyncio
    async def test_capture_thought_body_too_long(self, mcp_state):
        """content exceeding _MAX_BODY_LENGTH should raise an error."""
        from monocle.mcp_server import mcp

        with pytest.raises(Exception):
            await mcp.call_tool("capture_thought", {"content": "x" * 50_001})

    @pytest.mark.asyncio
    async def test_capture_thought_source_propagated(self, mcp_state, mock_vault):
        """The source parameter must be forwarded to IngestRequest and persisted."""
        from monocle.mcp_server import mcp

        result = await mcp.call_tool(
            "capture_thought",
            {"content": "Important meeting notes about the Q2 roadmap.", "source": "teams"},
        )
        data = json.loads(_extract_text(result))
        note = mock_vault.read_note(data["file_path"])
        assert note.metadata.source == "teams"

    @pytest.mark.asyncio
    async def test_search_vault_n_results_clamped_low(self, mcp_state):
        """n_results=0 should be clamped to 1 — no crash, returns a list."""
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("search_vault", {"query": "engineer", "n_results": 0})
        data = json.loads(_extract_text(result))
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_search_vault_n_results_clamped_high(self, mcp_state, mock_index):
        """n_results=100 should be clamped to _MAX_SEARCH_RESULTS (10)."""
        from monocle.models import NoteChunk
        from monocle.mcp_server import mcp, _MAX_SEARCH_RESULTS

        chunks = [
            NoteChunk(
                chunk_id=f"work/note{i}.md::0",
                file_path=f"work/note{i}.md",
                chunk_index=0,
                text=f"Work note number {i}",
                embedding=[0.1] * 1536,
            )
            for i in range(15)
        ]
        mock_index.upsert_chunks(chunks)

        result = await mcp.call_tool("search_vault", {"query": "work note", "n_results": 100})
        data = json.loads(_extract_text(result))
        assert len(data) <= _MAX_SEARCH_RESULTS

    @pytest.mark.asyncio
    async def test_browse_recent_limit_clamped_low(self, mcp_state):
        """limit=0 should be clamped to 1 — no crash, returns a list."""
        from monocle.mcp_server import mcp

        result = await mcp.call_tool("browse_recent", {"limit": 0})
        data = json.loads(_extract_text(result))
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_browse_recent_limit_clamped_high(self, mcp_state):
        """limit=200 should be clamped to _MAX_LIST_RESULTS (50)."""
        from monocle.mcp_server import mcp, _MAX_LIST_RESULTS

        result = await mcp.call_tool("browse_recent", {"limit": 200})
        data = json.loads(_extract_text(result))
        assert len(data) <= _MAX_LIST_RESULTS

    @pytest.mark.asyncio
    async def test_search_vault_without_ai_provider(self, mcp_state):
        """search_vault must raise RuntimeError when no AI provider is configured."""
        from monocle.mcp_server import mcp, _state

        _state.ai = None
        with pytest.raises(Exception, match="AI provider"):
            await mcp.call_tool("search_vault", {"query": "anything"})

    @pytest.mark.asyncio
    async def test_update_note_missing_file_raises(self, mcp_state):
        """update_note for a non-existent path must raise an exception."""
        from monocle.mcp_server import mcp

        with pytest.raises(Exception):
            await mcp.call_tool("update_note", {"file_path": "nonexistent/x.md", "body": "hi"})

    @pytest.mark.asyncio
    async def test_create_note_triggers_reindex(self, mcp_state):
        """create_note must push the new file onto reindex_queue when configured."""
        from monocle.mcp_server import mcp, _state

        mock_rq = MagicMock()
        _state.reindex_queue = mock_rq

        await mcp.call_tool(
            "create_note",
            {"title": "Reindex Test", "body": "Body content.", "note_type": "idea"},
        )
        mock_rq.push.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_note_triggers_reindex(self, mcp_state):
        """update_note must push the updated file onto reindex_queue when configured."""
        from monocle.mcp_server import mcp, _state

        mock_rq = MagicMock()
        _state.reindex_queue = mock_rq

        await mcp.call_tool(
            "update_note",
            {"file_path": "people/alice.md", "body": "Updated content."},
        )
        mock_rq.push.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_note_refreshes_updated_timestamp(self, mcp_state, mock_vault):
        """update_note must advance metadata.updated to at least the call time."""
        from monocle.mcp_server import mcp

        before = datetime.datetime.now(datetime.timezone.utc)
        await mcp.call_tool(
            "update_note",
            {"file_path": "people/alice.md", "body": "Freshly updated body."},
        )
        note = mock_vault.read_note("people/alice.md")
        assert note.metadata.updated is not None
        # Allow a small clock-skew tolerance; the key invariant is it's not stale.
        updated_aware = note.metadata.updated.replace(tzinfo=datetime.timezone.utc) \
            if note.metadata.updated.tzinfo is None else note.metadata.updated
        assert updated_aware >= before


# ──────────────────────────────────────────────────────────────────────────────
# TestMCPSecurityBoundaries
# ──────────────────────────────────────────────────────────────────────────────


class TestMCPSecurityBoundaries:
    """Path traversal and input-boundary safety via direct mcp.call_tool() calls."""

    @pytest.mark.asyncio
    async def test_read_note_path_traversal_blocked(self, mcp_state):
        """read_note with a traversal path must raise (VaultLayer returns HTTP 403)."""
        from monocle.mcp_server import mcp

        with pytest.raises(Exception):
            await mcp.call_tool("read_note", {"file_path": "../../etc/passwd"})

    @pytest.mark.asyncio
    async def test_update_note_path_traversal_blocked(self, mcp_state):
        """update_note with a traversal path must raise (VaultLayer returns HTTP 403)."""
        from monocle.mcp_server import mcp

        with pytest.raises(Exception):
            await mcp.call_tool(
                "update_note",
                {"file_path": "../../etc/passwd", "body": "injected"},
            )

    def test_auth_middleware_uses_constant_time_compare(self):
        """_MCPAuthMiddleware stores its key for hmac.compare_digest, not plain ==."""
        from monocle.mcp_server import _MCPAuthMiddleware
        import inspect

        # Verify hmac.compare_digest is referenced in the source; plain == is absent
        src = inspect.getsource(_MCPAuthMiddleware.__call__)
        assert "compare_digest" in src
        # The comparison must NOT use !=  or == after extracting the provided key
        # (the only != / == allowed is the `scope["type"] == "http"` guard)
        assert src.count("!= self._key") == 0
        assert src.count("== self._key") == 0

    def test_assert_ready_raises_before_init(self):
        """_MCPState.assert_ready() must raise RuntimeError if not initialised."""
        from monocle.mcp_server import _MCPState

        fresh = _MCPState()
        with pytest.raises(RuntimeError, match="init_mcp_state"):
            fresh.assert_ready()

    def test_assert_ready_passes_after_init(
        self, mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder
    ):
        """_MCPState.assert_ready() must not raise after init_mcp_state() is called."""
        from monocle.mcp_server import _MCPState, _state, init_mcp_state

        init_mcp_state(mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder)
        _state.assert_ready()  # must not raise


# ──────────────────────────────────────────────────────────────────────────────
# TestMCPServerConfig
# ──────────────────────────────────────────────────────────────────────────────


class TestMCPServerConfig:
    """Tests for module-level config and factory behaviour."""

    def test_init_mcp_state_sets_all_fields(
        self, mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder
    ):
        from monocle.mcp_server import _state, init_mcp_state

        init_mcp_state(mock_vault, mock_index, mock_ai, mock_pipeline, mock_graph_builder)
        assert _state.vault is mock_vault
        assert _state.index is mock_index
        assert _state.ai is mock_ai
        assert _state.ingest_pipeline is mock_pipeline
        assert _state.graph_builder is mock_graph_builder

    def test_create_mcp_app_returns_middleware(self):
        from monocle.mcp_server import _MCPAuthMiddleware, create_mcp_app

        app = create_mcp_app("some-key")
        assert isinstance(app, _MCPAuthMiddleware)

    def test_mcp_has_8_tools(self):
        from monocle.mcp_server import mcp

        tool_names = {t.name for t in mcp._tool_manager._tools.values()}
        expected = {
            "search_vault",
            "read_note",
            "browse_recent",
            "capture_thought",
            "create_note",
            "update_note",
            "get_graph",
            "get_stats",
        }
        assert expected == tool_names
