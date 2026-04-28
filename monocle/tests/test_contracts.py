"""monocle/tests/test_contracts.py — MCP contract parity tests (M31).

Verifies that the MCP tool layer is the authoritative description of Monocle-owned
operations by asserting:

1. Tool registry contains exactly the 7 canonical tools.
2. Input schemas match the canonical contract (parameter names, types, required/optional).
3. Output JSON keys match the documented frozen contract for each tool.
4. Both MCP tools and agent tools resolve to the same shared service functions.
5. Review-status and reindex behaviors are consistent between surfaces.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monocle.models import (
    GraphData,
    GraphNode,
    IngestConfidence,
    Note,
    NoteMetadata,
    ScoredChunk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(result) -> str:
    """Extract text from mcp.call_tool() return value.

    call_tool() returns (list[ContentBlock], raw_dict). Text at result[0][0].text.
    """
    content_blocks = result[0]
    if not content_blocks:
        return ""
    block = content_blocks[0]
    return block.text if hasattr(block, "text") else str(block)


def _make_note(
    file_path: str = "work/test.md",
    title: str = "Test",
    body: str = "Body text.",
    **meta_overrides,
) -> Note:
    meta = NoteMetadata(**meta_overrides) if meta_overrides else NoteMetadata()
    return Note(file_path=file_path, title=title, body=body, metadata=meta)


def _mock_mcp_state(
    vault=None, index=None, ai=None, pipeline=None, graph=None, rq=None,
    ingest_session_store=None, ingest_prepare_worker=None,
):
    """Inject mock state into the MCP singleton for testing."""
    from monocle.mcp_server import _state

    _state.vault = vault or MagicMock()
    _state.index = index or MagicMock()
    _state.ai = ai
    _state.ingest_pipeline = pipeline
    _state.ingest_session_store = ingest_session_store
    _state.ingest_prepare_worker = ingest_prepare_worker
    _state.graph_builder = graph
    _state.reindex_queue = rq
    _state._initialised = True


# ===========================================================================
# 1. Tool registry — canonical tool names
# ===========================================================================


class TestToolRegistry:
    """Assert the MCP server exposes exactly the 7 canonical tools."""

    CANONICAL_NAMES = {
        "search_vault",
        "read_note",
        "capture_thought",
        "create_note",
        "update_note",
        "get_graph",
        "create_reference_from_url",
    }

    def test_mcp_exposes_exactly_7_canonical_tools(self):
        from monocle.mcp_server import mcp

        tools = mcp._tool_manager.list_tools()
        names = {t.name for t in tools}
        assert names == self.CANONICAL_NAMES, (
            f"Expected {self.CANONICAL_NAMES}, got {names}"
        )

    def test_no_extra_tools_registered(self):
        from monocle.mcp_server import mcp

        tools = mcp._tool_manager.list_tools()
        assert len(tools) == 7


# ===========================================================================
# 2. Input schema parity — parameter names, types, required vs optional
# ===========================================================================


class TestInputSchemas:
    """Assert MCP tool input schemas match the canonical contract in tool-contracts.md."""

    def _get_schema(self, tool_name: str) -> dict:
        from monocle.mcp_server import mcp

        for t in mcp._tool_manager.list_tools():
            if t.name == tool_name:
                return t.model_dump().get("parameters", {})
        raise KeyError(f"Tool {tool_name!r} not found")

    # -- search_vault --

    def test_search_vault_params(self):
        s = self._get_schema("search_vault")
        props = s["properties"]
        assert "query" in props
        assert "n_results" in props
        assert "note_type" in props
        assert "domain" in props
        assert s["required"] == ["query"]

    def test_search_vault_defaults(self):
        s = self._get_schema("search_vault")
        assert s["properties"]["n_results"]["default"] == 5
        assert s["properties"]["note_type"]["default"] is None
        assert s["properties"]["domain"]["default"] is None

    # -- read_note --

    def test_read_note_params(self):
        s = self._get_schema("read_note")
        assert list(s["properties"].keys()) == ["file_path"]
        assert s["required"] == ["file_path"]

    # -- capture_thought --

    def test_capture_thought_params(self):
        s = self._get_schema("capture_thought")
        props = s["properties"]
        assert "content" in props
        assert "source" in props
        assert s["required"] == ["content"]
        assert props["source"]["default"] == "mcp"

    # -- create_note --

    def test_create_note_params(self):
        s = self._get_schema("create_note")
        props = s["properties"]
        assert "title" in props
        assert "body" in props
        assert "note_type" in props
        assert "domain" in props
        assert "tags" in props
        assert "metadata_updates" in props
        assert set(s["required"]) == {"title", "body"}

    def test_create_note_defaults(self):
        s = self._get_schema("create_note")
        assert s["properties"]["note_type"]["default"] == "observation"
        assert s["properties"]["domain"]["default"] == "personal"
        assert s["properties"]["tags"]["default"] is None
        assert s["properties"]["metadata_updates"]["default"] is None

    # -- update_note --

    def test_update_note_params(self):
        s = self._get_schema("update_note")
        props = s["properties"]
        assert set(props.keys()) == {"file_path", "body", "title", "metadata_updates"}
        assert set(s["required"]) == {"file_path", "body"}

    # -- get_graph --

    def test_get_graph_params(self):
        s = self._get_schema("get_graph")
        props = s["properties"]
        assert "focus" in props
        assert "max_degree" in props
        assert props["focus"]["default"] is None
        assert props["max_degree"]["default"] == 2
        # No required params — both are optional
        assert "required" not in s or s.get("required", []) == []

    # -- create_reference_from_url --

    def test_create_reference_from_url_params(self):
        s = self._get_schema("create_reference_from_url")
        props = s["properties"]
        assert "url" in props
        assert "extra_context" in props
        assert s["required"] == ["url"]
        assert props["extra_context"]["default"] is None


# ===========================================================================
# 3. Output schema parity — JSON keys match frozen contract
# ===========================================================================


class TestOutputSchemas:
    """Assert each MCP tool returns JSON with exactly the documented keys."""

    @pytest.fixture(autouse=True)
    def _reset_state(self):
        from monocle.mcp_server import _state
        orig = (
            _state.vault, _state.index, _state.ai,
            _state.ingest_pipeline, _state.ingest_session_store,
            _state.ingest_prepare_worker, _state.graph_builder,
            _state.reindex_queue, _state._initialised,
        )
        yield
        (_state.vault, _state.index, _state.ai,
         _state.ingest_pipeline, _state.ingest_session_store,
         _state.ingest_prepare_worker, _state.graph_builder,
         _state.reindex_queue, _state._initialised) = orig

    @pytest.mark.asyncio
    async def test_search_vault_output_keys(self):
        from monocle.mcp_server import mcp

        chunk = ScoredChunk(
            chunk_id="x::0", file_path="work/test.md",
            score=0.87, text="chunk text", metadata={},
        )
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)
        index = MagicMock()
        index.search = MagicMock(return_value=[chunk])
        _mock_mcp_state(ai=ai, index=index)

        result = await mcp.call_tool("search_vault", {"query": "test"})
        data = json.loads(_extract_text(result))

        assert isinstance(data, list)
        assert len(data) == 1
        assert set(data[0].keys()) == {"file_path", "similarity", "chunk"}

    @pytest.mark.asyncio
    async def test_read_note_output_keys(self):
        from monocle.mcp_server import mcp

        note = _make_note(
            type="person_note", domain="work",
            tags=["colleague"], people=["Alice"],
        )
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=note)
        _mock_mcp_state(vault=vault)

        result = await mcp.call_tool("read_note", {"file_path": "work/test.md"})
        data = json.loads(_extract_text(result))

        assert set(data.keys()) == {
            "file_path", "title", "type", "domain", "tags", "people", "body",
        }

    @pytest.mark.asyncio
    async def test_capture_thought_output_keys(self):
        from monocle.mcp_server import mcp

        response = MagicMock(
            session_id="sess_123",
            state="completed",
            source_ids=["src_1"],
            created_at="2026-04-27T10:00:00Z",
            updated_at="2026-04-27T10:00:01Z",
        )
        detail = MagicMock()
        detail.session = MagicMock(
            state="completed",
            source_ids=["src_1"],
            updated_at="2026-04-27T10:00:01Z",
            execution_summary=MagicMock(affected_file_paths=["work/test.md"]),
        )
        _mock_mcp_state(vault=MagicMock(), ingest_session_store=MagicMock())

        with patch("monocle.services.ingest.capture_thought_session", new=AsyncMock(return_value=(response, detail))):
            result = await mcp.call_tool("capture_thought", {"content": "A thought"})
            data = json.loads(_extract_text(result))

        assert set(data.keys()) == {
            "session_id", "state", "source_ids", "affected_file_paths", "created_at", "updated_at",
        }

    @pytest.mark.asyncio
    async def test_create_note_output_keys(self):
        from monocle.mcp_server import mcp

        note = _make_note()
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        _mock_mcp_state(vault=vault, rq=MagicMock())

        result = await mcp.call_tool("create_note", {
            "title": "Test", "body": "Body",
        })
        data = json.loads(_extract_text(result))

        assert set(data.keys()) == {"file_path", "title", "status"}
        assert data["status"] == "created"

    @pytest.mark.asyncio
    async def test_update_note_output_keys(self):
        from monocle.mcp_server import mcp

        note = _make_note()
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        _mock_mcp_state(vault=vault, rq=MagicMock())

        result = await mcp.call_tool("update_note", {
            "file_path": "work/test.md", "body": "New body",
        })
        data = json.loads(_extract_text(result))

        assert set(data.keys()) == {"file_path", "status"}
        assert data["status"] == "updated"

    @pytest.mark.asyncio
    async def test_get_graph_output_keys(self):
        from monocle.mcp_server import mcp

        graph_data = GraphData(
            focus="people/alice.md",
            nodes=[GraphNode(id="people/alice.md", label="Alice", type="person_note")],
            edges=[],
        )
        builder = MagicMock()
        builder.build = MagicMock(return_value=graph_data)
        _mock_mcp_state(graph=builder)

        result = await mcp.call_tool("get_graph", {"focus": "people/alice.md"})
        data = json.loads(_extract_text(result))

        assert set(data.keys()) == {"focus", "nodes", "edges"}
        assert data["focus"] == "people/alice.md"
        assert len(data["nodes"]) == 1
        assert set(data["nodes"][0].keys()) >= {"id", "label", "type"}

    @pytest.mark.asyncio
    async def test_create_reference_from_url_output_keys(self):
        from monocle.mcp_server import mcp

        note = _make_note(type="reference", review_status="pending")
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="Summary\n```json\n{}\n```")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        _mock_mcp_state(vault=vault, ai=ai, rq=MagicMock())

        with patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Page")):
            result = await mcp.call_tool("create_reference_from_url", {
                "url": "https://example.com",
            })
        data = json.loads(_extract_text(result))

        assert set(data.keys()) == {"file_path", "title", "url", "status"}
        assert data["status"] == "created"
        assert data["url"] == "https://example.com"


# ===========================================================================
# 4. Service delegation parity — both surfaces use the same services
# ===========================================================================


class TestServiceDelegation:
    """Assert that both MCP tools and agent tools import from monocle.services."""

    def test_mcp_tools_import_from_services(self):
        """All MCP tools import their service from monocle.services.*."""
        import inspect
        import monocle.mcp_server as mod

        source = inspect.getsource(mod)

        expected_imports = [
            "from monocle.services.search import search_vault",
            "from monocle.services.notes import read_note",
            "from monocle.services.notes import create_note",
            "from monocle.services.notes import update_note",
            "from monocle.services.graph import get_graph",
            "from monocle.services.references import create_reference_from_url",
            "from monocle.services.ingest import capture_thought_session",
        ]
        for imp in expected_imports:
            assert imp in source, f"MCP server missing: {imp}"

    def test_agent_tools_import_from_services(self):
        """All agent tools import from monocle.services.* (not inline logic)."""
        import inspect
        import monocle.agents.tools as mod

        source = inspect.getsource(mod)

        expected_imports = [
            "from monocle.services.search import search_vault",
            "from monocle.services.notes import read_note",
            "from monocle.services.notes import create_note",
            "from monocle.services.notes import update_note",
            "from monocle.services.graph import get_graph",
            "from monocle.services.references import create_reference_from_url",
        ]
        for imp in expected_imports:
            assert imp in source, f"Agent tools missing: {imp}"

    def test_service_modules_exist(self):
        """All canonical service modules are importable."""
        from monocle.services import search, notes, graph, references, ingest  # noqa: F401

    def test_service_functions_are_async(self):
        """All canonical service functions are async."""
        import inspect

        from monocle.services.search import search_vault
        from monocle.services.notes import read_note, create_note, update_note
        from monocle.services.graph import get_graph
        from monocle.services.references import create_reference_from_url
        from monocle.services.ingest import capture_thought_session

        for fn in [search_vault, read_note, create_note, update_note,
                get_graph, create_reference_from_url, capture_thought_session]:
            assert inspect.iscoroutinefunction(fn), f"{fn.__name__} is not async"


# ===========================================================================
# 5. Behavioral parity — review-status, reindex, and side-effect consistency
# ===========================================================================


class TestBehavioralParity:
    """Assert shared behaviors between MCP and agent surfaces are consistent."""

    @pytest.fixture(autouse=True)
    def _reset_state(self):
        from monocle.mcp_server import _state
        orig = (
            _state.vault, _state.index, _state.ai,
            _state.ingest_pipeline, _state.graph_builder,
            _state.reindex_queue, _state._initialised,
        )
        yield
        (_state.vault, _state.index, _state.ai,
         _state.ingest_pipeline, _state.graph_builder,
         _state.reindex_queue, _state._initialised) = orig

    @pytest.mark.asyncio
    async def test_create_note_sets_review_pending_via_mcp(self):
        """MCP create_note always sets review_status=pending (via service)."""
        from monocle.mcp_server import mcp

        note = _make_note(review_status="pending")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        _mock_mcp_state(vault=vault, rq=MagicMock())

        await mcp.call_tool("create_note", {"title": "T", "body": "B"})

        # The service should have been called with review_status=pending
        call = vault.create_from_template.call_args[0]
        template_data = call[1]
        assert template_data["review_status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_note_sets_review_pending_via_agent(self):
        """Agent create_note also sets review_status=pending (via same service)."""
        from monocle.agents.tools import VaultTools

        note = _make_note(review_status="pending")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        rq = MagicMock()

        tools = VaultTools(vault=vault, index=MagicMock(), ai=None, reindex_queue=rq)
        await tools.create_note(title="T", body="B")

        call = vault.create_from_template.call_args[0]
        template_data = call[1]
        assert template_data["review_status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_note_triggers_reindex_both_surfaces(self):
        """Both MCP and agent create_note push to ReindexQueue."""
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        note = _make_note()
        rq = MagicMock()

        # MCP surface
        vault_mcp = MagicMock()
        vault_mcp.create_from_template = MagicMock(return_value=note)
        vault_mcp.write_note = MagicMock()
        _mock_mcp_state(vault=vault_mcp, rq=rq)
        await mcp.call_tool("create_note", {"title": "T", "body": "B"})
        mcp_push_count = rq.push.call_count

        rq.reset_mock()

        # Agent surface
        vault_agent = MagicMock()
        vault_agent.create_from_template = MagicMock(return_value=note)
        vault_agent.write_note = MagicMock()
        tools = VaultTools(vault=vault_agent, index=MagicMock(), ai=None, reindex_queue=rq)
        await tools.create_note(title="T", body="B")
        agent_push_count = rq.push.call_count

        assert mcp_push_count == 1
        assert agent_push_count == 1

    @pytest.mark.asyncio
    async def test_update_note_triggers_reindex_both_surfaces(self):
        """Both MCP and agent update_note push to ReindexQueue."""
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        note = _make_note()
        rq = MagicMock()

        # MCP surface
        vault_mcp = MagicMock()
        vault_mcp.read_note = MagicMock(return_value=note)
        vault_mcp.write_note = MagicMock()
        _mock_mcp_state(vault=vault_mcp, rq=rq)
        await mcp.call_tool("update_note", {
            "file_path": "work/test.md", "body": "New",
        })
        assert rq.push.call_count == 1

        rq.reset_mock()

        # Agent surface (with file_path, no query resolution)
        vault_agent = MagicMock()
        vault_agent.read_note = MagicMock(return_value=note)
        vault_agent.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="merged body")
        tools = VaultTools(
            vault=vault_agent, index=MagicMock(), ai=ai, reindex_queue=rq,
        )
        await tools.update_note(file_path="work/test.md", body="New")
        assert rq.push.call_count == 1

    @pytest.mark.asyncio
    async def test_mcp_update_note_does_hard_overwrite(self):
        """MCP update_note does a hard body overwrite, no AI merge."""
        from monocle.mcp_server import mcp

        note = _make_note(body="original body")
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        _mock_mcp_state(vault=vault, rq=MagicMock())

        await mcp.call_tool("update_note", {
            "file_path": "work/test.md", "body": "completely new body",
        })

        # The note body should be the new content, not merged
        written_note = vault.write_note.call_args[0][1]
        assert written_note.body == "completely new body"

    @pytest.mark.asyncio
    async def test_search_vault_output_shape_identical(self):
        """MCP and agent search_vault return the same result structure."""
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        chunk = ScoredChunk(
            chunk_id="x::0", file_path="work/test.md",
            score=0.87, text="chunk text", metadata={},
        )
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)
        index = MagicMock()
        index.search = MagicMock(return_value=[chunk])

        # MCP surface
        _mock_mcp_state(ai=ai, index=index)
        mcp_result = await mcp.call_tool("search_vault", {"query": "test"})
        mcp_data = json.loads(_extract_text(mcp_result))

        # Agent surface
        tools = VaultTools(vault=MagicMock(), index=index, ai=ai)
        agent_result = await tools.search_vault(query="test")
        agent_data = json.loads(agent_result)

        # Both should have the same keys per result item
        assert set(mcp_data[0].keys()) == set(agent_data[0].keys())


# ===========================================================================
# 6. Backward compatibility — tool names and shapes are preserved
# ===========================================================================


class TestBackwardCompatibility:
    """Assert external MCP clients see stable tool names, input schemas, and outputs."""

    def test_all_7_tool_names_stable(self):
        """External clients rely on these exact names. No renames allowed."""
        from monocle.mcp_server import mcp

        expected = [
            "search_vault",
            "read_note",
            "capture_thought",
            "create_note",
            "update_note",
            "get_graph",
            "create_reference_from_url",
        ]
        tools = mcp._tool_manager.list_tools()
        names = sorted(t.name for t in tools)
        assert names == sorted(expected)

    def test_search_vault_query_is_required(self):
        """External clients sending search_vault must provide 'query'."""
        from monocle.mcp_server import mcp

        for t in mcp._tool_manager.list_tools():
            if t.name == "search_vault":
                schema = t.model_dump()["parameters"]
                assert "query" in schema["required"]
                break

    def test_create_note_requires_title_and_body(self):
        """External clients must provide both title and body."""
        from monocle.mcp_server import mcp

        for t in mcp._tool_manager.list_tools():
            if t.name == "create_note":
                schema = t.model_dump()["parameters"]
                assert "title" in schema["required"]
                assert "body" in schema["required"]
                break

    def test_tool_descriptions_present(self):
        """All tools have non-empty descriptions (required by MCP protocol)."""
        from monocle.mcp_server import mcp

        for t in mcp._tool_manager.list_tools():
            desc = t.model_dump().get("description", "")
            assert desc and len(desc) > 10, f"Tool {t.name} has no meaningful description"


# ===========================================================================
# 7. Adapter ↔ MCP output key parity (M32-D5)
# ===========================================================================


class TestAdapterMCPOutputParity:
    """Assert that agent adapter tool output JSON keys are a superset of the
    corresponding MCP tool output keys.

    The canonical contract (tool-contracts.md) requires both surfaces to share
    the same *minimum* key set.  Agent adapters may include extra keys
    (e.g. ``node_count``, ``title`` in update_note) for LLM context, but must
    never *omit* a key that the MCP surface returns.
    """

    @pytest.fixture(autouse=True)
    def _reset_state(self):
        from monocle.mcp_server import _state
        orig = (
            _state.vault, _state.index, _state.ai,
            _state.ingest_pipeline, _state.graph_builder,
            _state.reindex_queue, _state._initialised,
        )
        yield
        (_state.vault, _state.index, _state.ai,
         _state.ingest_pipeline, _state.graph_builder,
         _state.reindex_queue, _state._initialised) = orig

    # -- read_note --

    @pytest.mark.asyncio
    async def test_read_note_output_keys_match(self):
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        note = _make_note(
            type="person_note", domain="work",
            tags=["colleague"], people=["Alice"],
        )
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=note)

        # MCP surface
        _mock_mcp_state(vault=vault)
        mcp_result = await mcp.call_tool("read_note", {"file_path": "work/test.md"})
        mcp_keys = set(json.loads(_extract_text(mcp_result)).keys())

        # Agent surface
        tools = VaultTools(vault=vault, index=MagicMock(), ai=None)
        agent_result = await tools.read_note(file_path="work/test.md")
        agent_keys = set(json.loads(agent_result).keys())

        assert mcp_keys == agent_keys, (
            f"read_note key mismatch: MCP={mcp_keys}, agent={agent_keys}"
        )

    # -- create_note --

    @pytest.mark.asyncio
    async def test_create_note_output_keys_match(self):
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        note = _make_note()
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        rq = MagicMock()

        # MCP surface
        _mock_mcp_state(vault=vault, rq=rq)
        mcp_result = await mcp.call_tool("create_note", {"title": "T", "body": "B"})
        mcp_keys = set(json.loads(_extract_text(mcp_result)).keys())

        rq.reset_mock()
        vault.reset_mock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()

        # Agent surface
        tools = VaultTools(vault=vault, index=MagicMock(), ai=None, reindex_queue=rq)
        agent_result = await tools.create_note(title="T", body="B")
        agent_keys = set(json.loads(agent_result).keys())

        assert mcp_keys == agent_keys, (
            f"create_note key mismatch: MCP={mcp_keys}, agent={agent_keys}"
        )

    # -- update_note --

    @pytest.mark.asyncio
    async def test_update_note_agent_superset_of_mcp_keys(self):
        """Agent update_note includes MCP keys plus optional extras (title)."""
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        note = _make_note()
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        rq = MagicMock()

        # MCP surface
        _mock_mcp_state(vault=vault, rq=rq)
        mcp_result = await mcp.call_tool("update_note", {
            "file_path": "work/test.md", "body": "New",
        })
        mcp_keys = set(json.loads(_extract_text(mcp_result)).keys())

        rq.reset_mock()
        vault.reset_mock()
        vault.read_note = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="merged body")

        # Agent surface
        tools = VaultTools(vault=vault, index=MagicMock(), ai=ai, reindex_queue=rq)
        agent_result = await tools.update_note(body="New", file_path="work/test.md")
        agent_keys = set(json.loads(agent_result).keys())

        # Agent is a superset (adds ``title`` for LLM context)
        assert mcp_keys <= agent_keys, (
            f"update_note: agent missing MCP keys. MCP={mcp_keys}, agent={agent_keys}"
        )
        assert "title" in agent_keys - mcp_keys, (
            "Agent update_note should include 'title' beyond MCP keys"
        )

    # -- get_graph --

    @pytest.mark.asyncio
    async def test_get_graph_agent_superset_of_mcp_keys(self):
        """Agent get_graph includes MCP keys plus optional extras (node_count, edge_count)."""
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        graph_data = GraphData(
            focus="people/alice.md",
            nodes=[GraphNode(id="people/alice.md", label="Alice", type="person_note")],
            edges=[],
        )
        builder = MagicMock()
        builder.build = MagicMock(return_value=graph_data)

        # MCP surface
        _mock_mcp_state(graph=builder)
        mcp_result = await mcp.call_tool("get_graph", {"focus": "people/alice.md"})
        mcp_keys = set(json.loads(_extract_text(mcp_result)).keys())

        builder.reset_mock()
        builder.build = MagicMock(return_value=graph_data)
        vault = MagicMock()
        vault.resolve_wikilink = MagicMock(return_value="people/alice.md")

        # Agent surface
        tools = VaultTools(
            vault=vault, index=MagicMock(), ai=None, graph_builder=builder,
        )
        agent_result = await tools.get_graph(name_or_path="people/alice.md")
        agent_keys = set(json.loads(agent_result).keys())

        # Agent is a superset (adds node_count, edge_count for LLM context)
        assert mcp_keys <= agent_keys, (
            f"get_graph: agent missing MCP keys. MCP={mcp_keys}, agent={agent_keys}"
        )
        assert {"node_count", "edge_count"} <= agent_keys - mcp_keys

    # -- create_reference_from_url --

    @pytest.mark.asyncio
    async def test_create_reference_from_url_output_keys_match(self):
        from monocle.mcp_server import mcp
        from monocle.agents.tools import VaultTools

        note = _make_note(type="reference", review_status="pending")
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="Summary\n```json\n{}\n```")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        rq = MagicMock()

        # MCP surface
        _mock_mcp_state(vault=vault, ai=ai, rq=rq)
        with patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Page")):
            mcp_result = await mcp.call_tool("create_reference_from_url", {
                "url": "https://example.com",
            })
        mcp_keys = set(json.loads(_extract_text(mcp_result)).keys())

        rq.reset_mock()
        vault.reset_mock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()

        # Agent surface
        tools = VaultTools(vault=vault, index=MagicMock(), ai=ai, reindex_queue=rq)
        with patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Page")):
            agent_result = await tools.create_reference_from_url(url="https://example.com")
        agent_keys = set(json.loads(agent_result).keys())

        assert mcp_keys == agent_keys, (
            f"create_reference_from_url key mismatch: MCP={mcp_keys}, agent={agent_keys}"
        )

    # -- Agent tool name alignment --

    def test_agent_tool_names_match_canonical_minus_capture_thought(self):
        """VaultTools must expose exactly the 6 canonical tool names (all except
        capture_thought which is MCP-only)."""
        from monocle.agents.tools import VaultTools

        tools = VaultTools(
            vault=MagicMock(), index=MagicMock(), ai=None,
        )
        agent_names = {
            getattr(t, "name", None) or t.__name__ for t in tools.tools
        }
        expected = {
            "search_vault", "read_note", "update_note",
            "create_note", "create_reference_from_url", "get_graph",
        }
        assert agent_names == expected, (
            f"Agent tool names mismatch: got {agent_names}, expected {expected}"
        )
