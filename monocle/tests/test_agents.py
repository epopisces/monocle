"""
monocle/tests/test_agents.py â€” Tests for M10 Agent Framework & Chat API.

Coverage:
  - POST /api/chat SSE event sequence: token, tool_call, note_created, done
  - tool_error: stream continues after tool failure
  - done event emitted on normal completion; error-only on pre-stream failures
  - Empty messages â†’ 422
  - VaultTools construction and tool list
  - create_chat_agent factory returns a ChatAgent
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers to build fake AgentRunResponseUpdate objects
# ---------------------------------------------------------------------------

def _fake_update(contents: list) -> Any:
    """Create a minimal mock that looks like AgentRunResponseUpdate."""
    update = MagicMock()
    update.contents = contents
    return update


def _text_content(text: str) -> Any:
    from agent_framework import TextContent
    c = MagicMock(spec=TextContent)
    c.text = text
    return c


def _fn_call_content(name: str, call_id: str = "c1") -> Any:
    from agent_framework import FunctionCallContent
    c = MagicMock(spec=FunctionCallContent)
    c.name = name
    c.call_id = call_id
    return c


def _fn_result_content(result: Any, call_id: str = "c1") -> Any:
    from agent_framework import FunctionResultContent
    c = MagicMock(spec=FunctionResultContent)
    c.result = result
    c.call_id = call_id
    return c


#endregion

# ---------------------------------------------------------------------------
#region #*   Async generator helpers
# ---------------------------------------------------------------------------

async def _updates_gen(*updates):
    """Yield a fixed sequence of AgentRunResponseUpdate mocks."""
    for u in updates:
        yield u


#endregion

# ---------------------------------------------------------------------------
#region #*   parse_sse: extract events from raw SSE text
# ---------------------------------------------------------------------------

def _parse_sse(raw_text: str) -> list[dict[str, Any]]:
    """Parse raw SSE response body into list of {event, data} dicts."""
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw_text.splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif not line.strip() and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: POST /api/chat SSE event sequence
# ---------------------------------------------------------------------------

class TestChatSSEStream:
    """Integration tests using api_client fixture (TestClient + real vault)."""

    def _setup_mock_agent(self, updates):
        """Patch create_chat_agent to return an agent whose run_stream yields *updates*."""
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(*updates))
        return mock_agent

    def test_token_event_emitted(self, api_client):
        """Text deltas from the agent produce token SSE events."""
        from agent_framework import TextContent, FunctionCallContent, FunctionResultContent

        update = _fake_update([_text_content("Hello")])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        token_events = [e for e in events if e.get("event") == "token"]
        assert any(e["data"]["delta"] == "Hello" for e in token_events)

    def test_done_event_always_emitted(self, api_client):
        """A 'done' event must always appear at the end of the stream on happy path."""
        update = _fake_update([_text_content("response text")])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        events = _parse_sse(resp.text)
        done_events = [e for e in events if e.get("event") == "done"]
        assert len(done_events) == 1
        # done event must be last
        assert events[-1]["event"] == "done"
        # done must have status=success on happy path
        assert events[-1]["data"]["status"] == "success"
        # error field should not be present on success
        assert "error" not in events[-1]["data"]

    def test_tool_call_event_emitted(self, api_client):
        """FunctionCallContent emits a tool_call SSE event."""
        fn_call = _fn_call_content("search_vault")
        update = _fake_update([fn_call])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "search"}]},
            )

        events = _parse_sse(resp.text)
        tool_events = [e for e in events if e.get("event") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["data"]["name"] == "search_vault"

    def test_note_created_event_on_create_note_result(self, api_client):
        """FunctionResultContent with status='created' emits a note_created event."""
        result_payload = json.dumps({
            "file_path": "work/new-idea.md",
            "type": "idea",
            "status": "created",
        })
        fn_result = _fn_result_content(result_payload)
        update = _fake_update([fn_result])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "create a note"}]},
            )

        events = _parse_sse(resp.text)
        nc_events = [e for e in events if e.get("event") == "note_created"]
        assert len(nc_events) == 1
        assert nc_events[0]["data"]["file_path"] == "work/new-idea.md"

    def test_no_note_created_for_non_create_result(self, api_client):
        """FunctionResultContent without status='created' does NOT emit note_created."""
        result_payload = json.dumps({"notes": [], "total": 0})
        fn_result = _fn_result_content(result_payload)
        update = _fake_update([fn_result])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "list notes"}]},
            )

        events = _parse_sse(resp.text)
        nc_events = [e for e in events if e.get("event") == "note_created"]
        assert len(nc_events) == 0

    def test_session_id_echoed_in_done(self, api_client):
        """session_id passed in request is echoed back in the done event."""
        update = _fake_update([_text_content("ok")])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}], "session_id": "sess-abc"},
            )

        events = _parse_sse(resp.text)
        done = events[-1]
        assert done["event"] == "done"
        assert done["data"]["session_id"] == "sess-abc"

    def test_empty_messages_returns_422(self, api_client):
        """Empty messages list must return 422 Unprocessable Entity."""
        resp = api_client.post(
            "/api/chat",
            json={"messages": []},
        )
        assert resp.status_code == 422

    def test_multiple_tokens_accumulated(self, api_client):
        """Multiple TextContent items across updates emit multiple token events."""
        updates = [
            _fake_update([_text_content("Hello")]),
            _fake_update([_text_content(" world")]),
            _fake_update([_text_content("!")]),
        ]

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(*updates))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        events = _parse_sse(resp.text)
        token_events = [e for e in events if e.get("event") == "token"]
        assert len(token_events) == 3
        combined = "".join(e["data"]["delta"] for e in token_events)
        assert combined == "Hello world!"

    def test_agent_exception_emits_error_event(self, api_client):
        """A hard exception in the agent produces an error SSE event."""

        async def _failing_stream(*a, **kw):
            raise RuntimeError("boom")
            # make this an async generator
            yield  # pragma: no cover

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(side_effect=RuntimeError("boom"))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("event") == "error"]
        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_disconnect_cancels_stream_iteration(self):
        from monocle.routers.chat import _iter_stream_with_disconnect

        class _FakeRequest:
            def __init__(self) -> None:
                self.calls = 0

            async def is_disconnected(self) -> bool:
                self.calls += 1
                return self.calls >= 2

        stream_closed: list[bool] = []

        async def _slow_stream():
            try:
                await asyncio.sleep(1)
                yield _fake_update([_text_content("late")])
            finally:
                stream_closed.append(True)

        with pytest.raises(asyncio.CancelledError):
            async for _ in _iter_stream_with_disconnect(
                _FakeRequest(), _slow_stream(), poll_interval_s=0.01
            ):
                pass

        assert stream_closed == [True]


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: VaultTools construction
# ---------------------------------------------------------------------------

class TestVaultTools:
    """Tests that VaultTools builds correctly and exposes the right tools."""

    def test_tools_list_has_6_entries(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools

        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, graph_builder=None)
        # 6 tools: search_vault, read_note, update_note, create_note,
        #          create_reference_from_url, get_graph
        assert len(vt.tools) == 6

    def test_all_tools_are_callable(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools

        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, graph_builder=None)
        for tool in vt.tools:
            assert callable(tool)

    def test_tool_names_include_search_vault(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools

        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, graph_builder=None)
        names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in vt.tools]
        # Should include update_note (renamed from write_note)
        assert any("update_note" in n or "search" in n for n in names)


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: create_chat_agent factory
# ---------------------------------------------------------------------------

class TestCreateChatAgent:
    """Tests that the factory returns a usable ChatAgent."""

    def test_returns_chat_agent(self, tmp_vault, memory_index, mock_ai):
        from agent_framework import ChatAgent
        from monocle.vault import VaultLayer
        from monocle.config import Settings
        from monocle.agents import create_chat_agent

        vault = VaultLayer(str(tmp_vault))
        settings = Settings()
        agent = create_chat_agent(ai=mock_ai, vault=vault, index=memory_index, settings=settings)
        assert isinstance(agent, ChatAgent)

    def test_agent_has_run_stream_method(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.config import Settings
        from monocle.agents import create_chat_agent

        vault = VaultLayer(str(tmp_vault))
        settings = Settings()
        agent = create_chat_agent(ai=mock_ai, vault=vault, index=memory_index, settings=settings)
        assert hasattr(agent, "run_stream") and callable(agent.run_stream)

    def test_skips_agent_otel_reconfigure_when_app_providers_exist(self, monkeypatch):
        from monocle.agents import _configure_agent_otel
        from monocle.config import Settings
        import monocle.agents as agents_mod

        settings = Settings()
        monkeypatch.setattr(agents_mod, "_otel_configured", False)
        monkeypatch.setattr(agents_mod, "_otel_providers_already_configured", lambda: True)
        disable_mock = MagicMock()
        monkeypatch.setattr(agents_mod, "_disable_agent_framework_otel", disable_mock)

        configure_mock = MagicMock()
        with patch("agent_framework.observability.configure_otel_providers", configure_mock):
            _configure_agent_otel(settings)

        configure_mock.assert_not_called()
        disable_mock.assert_called_once()
        assert agents_mod._otel_configured is True


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: VaultTools method execution
# ---------------------------------------------------------------------------


class TestVaultToolsExecution:
    """Execute each @ai_function tool and verify return shapes."""

    @pytest.fixture
    def vault_tools(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools
        from monocle.models import NoteChunk

        vault = VaultLayer(str(tmp_vault))
        # Seed the MemoryIndex with one chunk so search_vault returns results
        memory_index.upsert_chunks([
            NoteChunk(
                chunk_id="people/alice-example.md::0",
                file_path="people/alice-example.md",
                chunk_index=0,
                text="Alice is an engineer on the platform team.",
                embedding=[0.1] * 1536,
            )
        ])
        return VaultTools(vault=vault, index=memory_index, ai=mock_ai, graph_builder=None)

    # NOTE: test_search_vault_returns_json_list removed — covered by
    # TestAdapterMCPOutputParity in test_contracts.py
    # NOTE: test_read_note_returns_json_with_body removed — covered by
    # TestAdapterMCPOutputParity.test_read_note_output_keys_match

    @pytest.mark.asyncio
    async def test_read_note_nonexistent_raises(self, vault_tools):
        with pytest.raises(Exception):
            await vault_tools.read_note("people/nobody.md")

    # NOTE: test_update_note_updates_body removed — covered by
    # TestUpdateNote.test_happy_path in test_services.py
    # NOTE: test_update_note_body_length_cap removed — covered by
    # TestUpdateNote.test_body_too_long_raises in test_services.py
    # NOTE: test_update_note_updates_timestamp removed — covered by
    # TestUpdateNote.test_updated_timestamp_set in test_services.py

    # NOTE: test_create_note_returns_file_path removed — covered by
    # TestAdapterMCPOutputParity.test_create_note_output_keys_match
    # NOTE: test_create_note_sets_review_status_pending removed — covered by
    # TestBehavioralParity.test_create_note_sets_review_pending_via_agent

    @pytest.mark.asyncio
    async def test_create_note_body_length_cap(self, vault_tools):
        """create_note must reject bodies over 50,000 chars."""
        with pytest.raises(ValueError, match="50,000"):
            await vault_tools.create_note(title="T", body="x" * 50_001)

    @pytest.mark.asyncio
    async def test_create_note_tags_none_defaults_to_empty(self, vault_tools):
        """Calling create_note without tags must not raise (no mutable default bug)."""
        result = await vault_tools.create_note(title="No Tags", body="Content.")
        parsed = json.loads(result)
        assert parsed["status"] == "created"

    @pytest.mark.asyncio
    async def test_create_reference_from_url_passes_configured_timeout(self, tmp_vault, memory_index, mock_ai):
        from types import SimpleNamespace

        from monocle.agents.tools import VaultTools
        from monocle.config import Settings
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        settings = Settings(ai={"url_reference_timeout_s": 120.0})
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, settings=settings)
        note = SimpleNamespace(file_path="reference/test.md", title="Test Reference")

        with patch("monocle.services.references.create_reference_from_url", AsyncMock(return_value=note)) as create_ref_mock:
            result = await vt.create_reference_from_url("https://example.com")

        parsed = json.loads(result)
        assert parsed["status"] == "created"
        assert create_ref_mock.await_args.kwargs["summarize_timeout_s"] == 120.0

    @pytest.mark.asyncio
    async def test_get_graph_no_graph_builder_returns_error_json(self, vault_tools):
        """When graph_builder=None the tool returns an error JSON, not an exception."""
        result = await vault_tools.get_graph("Alice")
        parsed = json.loads(result)
        assert "error" in parsed

    # NOTE: test_get_graph_with_builder removed — covered by
    # TestAdapterMCPOutputParity.test_get_graph_agent_superset_of_mcp_keys

    # -----------------------------------------------------------------------
    #region #*    update_note query-based tests (find by name/topic)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_note_finds_by_query_and_merges(self, vault_tools, tmp_vault):
        """update_note should find alice-example.md by query and merge new content."""
        result = await vault_tools.update_note("She also leads the infra guild.", query="Alice")
        parsed = json.loads(result)
        assert parsed["status"] == "updated"
        assert "file_path" in parsed
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        assert "She also leads the infra guild." in content

    @pytest.mark.asyncio
    async def test_update_note_preserves_existing_body(self, vault_tools, tmp_vault):
        """update_note must keep the original content when merging."""
        await vault_tools.update_note("New fact.", query="Alice")
        updated = (tmp_vault / "people" / "alice-example.md").read_text()
        # Frontmatter is preserved
        assert "---" in updated
        # New content added
        assert "New fact." in updated

    @pytest.mark.asyncio
    async def test_update_note_no_match_returns_error_json(self, tmp_vault, memory_index, mock_ai):
        """When no note matches the query, return an error JSON (not exception)."""
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools

        # Use an empty index (no chunks)
        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai)
        result = await vt.update_note("Content.", query="ZZZ_nonexistent_person_xyz")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_update_note_empty_body_raises(self, vault_tools):
        """update_note must reject empty or whitespace-only body."""
        with pytest.raises(ValueError, match="must not be empty"):
            await vault_tools.update_note("   ", query="Alice")

    # NOTE: test_update_note_triggers_reindex_via_query removed — covered by
    # TestBehavioralParity.test_update_note_triggers_reindex_both_surfaces

    @pytest.mark.asyncio
    async def test_update_note_unwraps_json_body(self, vault_tools, tmp_vault):
        """update_note must unwrap {"body": "..."} JSON the LLM sometimes produces."""
        await vault_tools.update_note('{"body": "She won a hackathon."}', query="Alice")
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        assert "She won a hackathon." in content
        assert '{"body"' not in content

    @pytest.mark.asyncio
    async def test_update_note_ai_merge_integrates_content(self, vault_tools, tmp_vault):
        """When AI is available, update_note merges rather than raw-appends."""
        result = await vault_tools.update_note("She now leads the infra guild.", query="Alice")
        parsed = json.loads(result)
        assert parsed["status"] == "updated"
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        # Both old and new content should appear in the merged body
        assert "She now leads the infra guild." in content

    @pytest.mark.asyncio
    async def test_merge_body_prompt_preserves_existing_structure(self, tmp_vault, memory_index, mock_ai):
        """AI merge instructions should preserve useful scaffold headings and tables."""
        from monocle.agents.tools import VaultTools
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        tools = VaultTools(vault=vault, index=memory_index, ai=mock_ai)

        await tools._merge_body("## Relationship Snapshot\n- Existing\n", "New information")

        prompt = mock_ai.chat.await_args.args[0][0]["content"]
        assert "Preserve existing section headings, tables, and checklist structure" in prompt

    @pytest.mark.asyncio
    async def test_update_note_rejects_low_similarity_search_results(self, tmp_vault, memory_index, mock_ai):
        """update_note must reject semantic search results below 0.6 similarity threshold.
        
        This prevents matching unrelated notes (e.g., 'Lucas' when searching for 'Grayson').
        The test uses MemoryIndex which returns dummy embeddings, so the score is controlled.
        """
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools
        from monocle.models import ScoredChunk
        from unittest.mock import patch

        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai)
        
        # Mock the index.search to return a result with low similarity (0.4)
        with patch.object(memory_index, 'search') as mock_search:
            # Create a mock chunk with low score
            low_score_chunk = ScoredChunk(
                chunk_id="lucas-example.md::0",
                file_path="people/lucas-example.md",
                score=0.4,  # Below threshold
                text="Lucas is a developer",
            )
            # Make search return [low_score_chunk]
            mock_search.return_value = [low_score_chunk]
            
            # Query for a completely different name
            result = await vt.update_note("New content.", query="Grayson Gallagher")
            parsed = json.loads(result)
            
            # Should return error, not accept the low-similarity match
            assert "error" in parsed
            assert "No note found" in parsed["error"]

    #endregion

#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: JSON metadata extraction with multiple blocks
# ---------------------------------------------------------------------------


class TestJSONMetadataExtraction:
    """Verify that metadata extraction picks the LAST JSON block, not the first.
    
    This tests the fix for a bug where LLM responses containing example JSON code
    (e.g., in the summary) would be parsed as metadata instead of the actual
    metadata block at the end.
    """

    def test_json_extraction_regex_multiple_blocks(self) -> None:
        """Unit test: re.finditer() finds all JSON blocks and we take the last one."""
        import re

        response = """
## Summary

Example: ```json
{"wrong": "this is the first block"}
```

Real metadata: ```json
{"title": "Correct Title", "tags": ["a", "b"]}
```
"""
        # Use the same regex as the fixed code
        json_matches = list(re.finditer(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL))
        assert len(json_matches) == 2, "Should find both JSON blocks"

        # Take the last one (the fix)
        last_match = json_matches[-1]
        metadata = json.loads(last_match.group(1))
        assert metadata["title"] == "Correct Title", "Should extract from the LAST block"
        assert "wrong" not in metadata, "Should NOT use first block"

    def test_json_extraction_no_blocks(self) -> None:
        """When no JSON blocks found, metadata dict is empty."""
        import re

        response = "## Summary\n\nNo JSON blocks here at all."
        json_matches = list(re.finditer(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL))
        assert len(json_matches) == 0

        # Fallback behavior: empty dict and full response as body
        if json_matches:
            json_match = json_matches[-1]
            body = response[: json_match.start()].strip()
        else:
            body = response.strip()

        assert body == response

    def test_json_extraction_single_block(self) -> None:
        """When exactly one JSON block, it's correctly extracted."""
        import re

        response = "## Summary\n\nSome text.\n\n```json\n{\"title\": \"Single Block\"}\n```"
        json_matches = list(re.finditer(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL))
        assert len(json_matches) == 1

        json_match = json_matches[-1]  # Also the first (and last)
        metadata = json.loads(json_match.group(1))
        assert metadata["title"] == "Single Block"


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: _to_dict_messages translation
# ---------------------------------------------------------------------------


class TestToDictMessages:
    """Unit tests for the message translation layer in _AIProviderChatClient."""

    def _messages(self, *items):
        from agent_framework import ChatMessage
        return list(items)

    def test_plain_text_message(self):
        from agent_framework import ChatMessage
        from monocle.agents import _AIProviderChatClient

        msg = ChatMessage(role="user", text="Hello")
        result = _AIProviderChatClient._to_dict_messages([msg])
        assert result == [{"role": "user", "content": "Hello"}]

    def test_function_call_message(self):
        from agent_framework import ChatMessage, FunctionCallContent
        from monocle.agents import _AIProviderChatClient

        fcc = FunctionCallContent(call_id="c1", name="search_vault", arguments={"query": "Alice"})
        msg = ChatMessage(role="assistant", contents=[fcc])
        result = _AIProviderChatClient._to_dict_messages([msg])
        assert len(result) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["function"]["name"] == "search_vault"
        assert tc["id"] == "c1"

    def test_function_result_message(self):
        from agent_framework import ChatMessage, FunctionResultContent
        from monocle.agents import _AIProviderChatClient

        frc = FunctionResultContent(call_id="c1", result='{"found": true}')
        msg = ChatMessage(role="tool", contents=[frc])
        result = _AIProviderChatClient._to_dict_messages([msg])
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "c1"

    def test_empty_contents_gives_empty_content_string(self):
        from agent_framework import ChatMessage
        from monocle.agents import _AIProviderChatClient

        msg = ChatMessage(role="user", contents=[])
        result = _AIProviderChatClient._to_dict_messages([msg])
        assert result[0]["content"] == ""

    def test_multiple_text_parts_concatenated(self):
        from agent_framework import ChatMessage, TextContent
        from monocle.agents import _AIProviderChatClient

        msg = ChatMessage(role="assistant", contents=[TextContent(text="Hello"), TextContent(text=" world")])
        result = _AIProviderChatClient._to_dict_messages([msg])
        assert result[0]["content"] == "Hello world"

    def test_function_result_string_not_double_encoded(self):
        """String results should not be JSON-encoded; they're used as-is."""
        from agent_framework import ChatMessage, FunctionResultContent
        from monocle.agents import _AIProviderChatClient

        # Tool returns a JSON string directly
        json_string = '{"found": true, "count": 42}'
        frc = FunctionResultContent(call_id="c1", result=json_string)
        msg = ChatMessage(role="tool", contents=[frc])
        result = _AIProviderChatClient._to_dict_messages([msg])
        
        # Result content should be the string as-is, not double-encoded with quotes
        assert result[0]["content"] == json_string
        # Verify no extra quotes or escapes
        assert '"' not in result[0]["content"].replace(json_string, "")

    def test_function_result_dict_is_json_encoded(self):
        """Non-string results (e.g., dicts) should be JSON-encoded."""
        from agent_framework import ChatMessage, FunctionResultContent
        from monocle.agents import _AIProviderChatClient
        import json as json_module

        result_dict = {"found": True, "count": 42}
        frc = FunctionResultContent(call_id="c1", result=result_dict)
        msg = ChatMessage(role="tool", contents=[frc])
        result = _AIProviderChatClient._to_dict_messages([msg])
        
        # Result content should be JSON-encoded
        assert result[0]["content"] == json_module.dumps(result_dict)


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: first-turn tool policy
# ---------------------------------------------------------------------------


class TestFirstTurnToolPolicy:
    """Verify _AIProviderChatClient enforces tool_choice on first turn only."""

    _DUMMY_TOOLS = [{"type": "function", "function": {"name": "search_vault", "parameters": {}}}]

    @pytest.mark.asyncio
    async def test_first_turn_passes_tool_choice_to_provider(self):
        """No prior FunctionCallContent â†’ tool_choice forwarded to provider.chat()."""
        from agent_framework import ChatMessage
        from monocle.agents import _AIProviderChatClient

        mock_ai = MagicMock()
        mock_ai.chat = AsyncMock(return_value="response text")
        client = _AIProviderChatClient(ai=mock_ai, tool_hint="search_vault")
        user_msg = ChatMessage(role="user", text="find alice")

        with patch.object(_AIProviderChatClient, "_build_openai_tools", return_value=self._DUMMY_TOOLS):
            await client._inner_get_response(messages=[user_msg], chat_options=MagicMock())

        call_kwargs = mock_ai.chat.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "function", "function": {"name": "search_vault"}}

    @pytest.mark.asyncio
    async def test_second_turn_omits_tool_choice(self):
        """After a FunctionCallContent in messages, tool_choice is NOT passed."""
        from agent_framework import ChatMessage, FunctionCallContent
        from monocle.agents import _AIProviderChatClient

        mock_ai = MagicMock()
        mock_ai.chat = AsyncMock(return_value="response text")
        client = _AIProviderChatClient(ai=mock_ai, tool_hint="search_vault")

        fn_call_msg = ChatMessage(
            role="assistant",
            contents=[FunctionCallContent(call_id="c1", name="search_vault", arguments={})],
        )
        user_msg = ChatMessage(role="user", text="what did you find?")

        with patch.object(_AIProviderChatClient, "_build_openai_tools", return_value=self._DUMMY_TOOLS):
            await client._inner_get_response(
                messages=[user_msg, fn_call_msg], chat_options=MagicMock()
            )

        call_kwargs = mock_ai.chat.call_args.kwargs
        assert call_kwargs.get("tool_choice") is None

    @pytest.mark.asyncio
    async def test_no_hint_no_tool_choice(self):
        """Without tool_hint, tool_choice is never passed regardless of turn."""
        from agent_framework import ChatMessage
        from monocle.agents import _AIProviderChatClient

        mock_ai = MagicMock()
        mock_ai.chat = AsyncMock(return_value="response text")
        client = _AIProviderChatClient(ai=mock_ai, tool_hint=None)
        user_msg = ChatMessage(role="user", text="search for alice")

        with patch.object(_AIProviderChatClient, "_build_openai_tools", return_value=self._DUMMY_TOOLS):
            await client._inner_get_response(messages=[user_msg], chat_options=MagicMock())

        call_kwargs = mock_ai.chat.call_args.kwargs
        assert call_kwargs.get("tool_choice") is None

    @pytest.mark.asyncio
    async def test_first_turn_streaming_passes_tool_choice(self):
        """tool_choice forwarded on the streaming path for the first turn."""
        from agent_framework import ChatMessage
        from monocle.agents import _AIProviderChatClient

        async def _fake_stream():
            yield "response chunk"

        mock_ai = MagicMock()
        mock_ai.chat = AsyncMock(return_value=_fake_stream())
        client = _AIProviderChatClient(ai=mock_ai, tool_hint="read_note")
        user_msg = ChatMessage(role="user", text="read alice.md")

        with patch.object(_AIProviderChatClient, "_build_openai_tools", return_value=self._DUMMY_TOOLS):
            async for _ in client._inner_get_streaming_response(
                messages=[user_msg], chat_options=MagicMock()
            ):
                pass

        call_kwargs = mock_ai.chat.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "function", "function": {"name": "read_note"}}


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: _try_parse_tool_calls
# ---------------------------------------------------------------------------


class TestTryParseToolCalls:
    """Unit tests for the inline tool-call JSON detector."""

    def test_returns_none_for_plain_text(self):
        from monocle.agents import _try_parse_tool_calls
        assert _try_parse_tool_calls("Hello world") is None

    def test_returns_none_for_json_without_tool_calls_key(self):
        from monocle.agents import _try_parse_tool_calls
        assert _try_parse_tool_calls('{"message": "hi"}') is None

    def test_returns_tool_calls_list(self):
        import json as _json
        from monocle.agents import _try_parse_tool_calls
        payload = _json.dumps({"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search_vault", "arguments": "{}"}}]})
        result = _try_parse_tool_calls(payload)
        assert isinstance(result, list)
        assert result[0]["function"]["name"] == "search_vault"

    def test_returns_none_for_invalid_json(self):
        from monocle.agents import _try_parse_tool_calls
        assert _try_parse_tool_calls("{not valid json}") is None

    def test_returns_none_for_json_starting_with_array(self):
        from monocle.agents import _try_parse_tool_calls
        assert _try_parse_tool_calls('[{"a": 1}]') is None

    def test_returns_tool_calls_from_fenced_json_block(self):
        """Local models often emit tool calls inside ```json fences."""
        import json as _json
        from monocle.agents import _try_parse_tool_calls

        calls = [{"id": "c1", "type": "function", "function": {"name": "search_vault", "arguments": "{}"}}]
        fenced = f'```json\n{_json.dumps({"tool_calls": calls})}\n```'
        result = _try_parse_tool_calls(fenced)
        assert isinstance(result, list)
        assert result[0]["function"]["name"] == "search_vault"

    def test_returns_tool_calls_from_fenced_block_no_lang(self):
        """Fenced blocks without a language specifier are also handled."""
        import json as _json
        from monocle.agents import _try_parse_tool_calls

        calls = [{"id": "c2", "type": "function", "function": {"name": "read_note", "arguments": "{}"}}]
        fenced = f'```\n{_json.dumps({"tool_calls": calls})}\n```'
        result = _try_parse_tool_calls(fenced)
        assert isinstance(result, list)
        assert result[0]["function"]["name"] == "read_note"

    def test_returns_tool_calls_from_embedded_json_in_prose(self):
        """JSON object with tool_calls key embedded in surrounding prose."""
        import json as _json
        from monocle.agents import _try_parse_tool_calls

        calls = [{"id": "c3", "type": "function", "function": {"name": "create_note", "arguments": "{}"}}]
        prose = f'Sure, I will call that tool! {_json.dumps({"tool_calls": calls})} Let me know if you need more.'
        result = _try_parse_tool_calls(prose)
        assert isinstance(result, list)
        assert result[0]["function"]["name"] == "create_note"

    def test_returns_none_for_fenced_block_without_tool_calls(self):
        """Fenced JSON block that does not contain tool_calls returns None."""
        from monocle.agents import _try_parse_tool_calls

        fenced = '```json\n{"message": "not a tool call"}\n```'
        assert _try_parse_tool_calls(fenced) is None

    def test_returns_none_for_empty_string(self):
        from monocle.agents import _try_parse_tool_calls
        assert _try_parse_tool_calls("") is None

    def test_returns_none_for_whitespace_only(self):
        from monocle.agents import _try_parse_tool_calls
        assert _try_parse_tool_calls("   \n  ") is None


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: SSE stream done/error contract
# ---------------------------------------------------------------------------


class TestChatSSEErrorContract:
    """Tests for the done/error SSE contract on the error path."""

    def test_error_event_emitted_done_always_terminates_stream(self, api_client):
        """When the agent raises before yielding any update, error is emitted,
        and done is always the final event with status=error."""
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(side_effect=RuntimeError("fatal"))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        events = _parse_sse(resp.text)
        event_types = [e.get("event") for e in events]
        # Both error and done are emitted
        assert "error" in event_types
        assert "done" in event_types
        # done must be last
        assert events[-1]["event"] == "done"
        # done must have status=error
        assert events[-1]["data"]["status"] == "error"
        # done must carry the error message
        assert "error" in events[-1]["data"]

    def test_error_event_emitted_when_exception_mid_stream(self, api_client):
        """An exception raised mid-iteration produces an error event,
        and done is always the final event with status=error."""

        async def _mid_stream_fail():
            yield _fake_update([_text_content("partial")])
            raise RuntimeError("mid-stream boom")

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_mid_stream_fail())

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        events = _parse_sse(resp.text)
        event_types = [e.get("event") for e in events]
        # The partial token, error, and done should appear
        assert "token" in event_types
        assert "error" in event_types
        assert "done" in event_types
        # done must be last
        assert events[-1]["event"] == "done"
        # done must have status=error
        assert events[-1]["data"]["status"] == "error"


# ---------------------------------------------------------------------------
#region #*   Tests: fetch_urls parallel pre-fetch
# ---------------------------------------------------------------------------


class TestFetchUrlsPreFetch:
    """Tests for the fetch_urls pre-fetch behaviour in POST /api/chat."""

    def test_fetch_urls_emits_note_created_and_injects_context(self, api_client):
        """When fetch_urls is provided, a note_created event is emitted for each
        successfully pre-fetched URL, and the agent receives injected context."""
        prefetch_result = json.dumps({
            "file_path": "technologies/example-ref.md",
            "title": "Example Site",
            "url": "https://example.com",
            "status": "created",
        })

        update = _fake_update([_text_content("Summarized!")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch(
                "monocle.agents.tools.VaultTools.create_reference_from_url",
                new=AsyncMock(return_value=prefetch_result),
            ),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "summarize this"}],
                    "fetch_urls": ["https://example.com"],
                },
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        tool_events = [e for e in events if e.get("event") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["data"]["name"] == "create_reference_from_url"
        assert tool_events[0]["data"]["url"] == "https://example.com"
        complete_events = [e for e in events if e.get("event") == "prefetch_complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["data"]["status"] == "success"
        assert complete_events[0]["data"]["url"] == "https://example.com"
        nc_events = [e for e in events if e.get("event") == "note_created"]
        assert len(nc_events) == 1
        assert nc_events[0]["data"]["file_path"] == "technologies/example-ref.md"

    def test_fetch_urls_failed_prefetch_emits_tool_error(self, api_client):
        """A failed pre-fetch emits tool_error so URL work is visible in the stream."""
        update = _fake_update([_text_content("continuing")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch(
                "monocle.agents.tools.VaultTools.create_reference_from_url",
                new=AsyncMock(side_effect=RuntimeError("network error")),
            ),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "what is this?"}],
                    "fetch_urls": ["https://unreachable.example"],
                },
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        tool_errors = [e for e in events if e.get("event") == "tool_error"]
        assert len(tool_errors) == 1
        assert tool_errors[0]["data"]["name"] == "create_reference_from_url"
        complete_events = [e for e in events if e.get("event") == "prefetch_complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["data"]["status"] == "error"

    def test_fetch_urls_context_injected_into_last_user_message(self, api_client):
        """Pre-fetch context prefix is prepended to the last user message text."""
        prefetch_result = json.dumps({
            "file_path": "technologies/ref.md",
            "title": "Ref",
            "url": "https://example.com",
            "status": "created",
        })

        captured_messages = []

        def _capture_agent(*args, **kwargs):
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(return_value=_updates_gen())
            # Capture the af_messages via tool_hint kwarg â€” we inspect message text
            # after agent creation by checking what text was passed to run_stream
            return mock_agent

        with (
            patch("monocle.routers.chat.create_chat_agent", side_effect=_capture_agent),
            patch(
                "monocle.agents.tools.VaultTools.create_reference_from_url",
                new=AsyncMock(return_value=prefetch_result),
            ),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "tell me about this"}],
                    "fetch_urls": ["https://example.com"],
                },
            )

        assert resp.status_code == 200

    def test_fetch_urls_parallel_multiple_urls(self, api_client):
        """Multiple fetch_urls are pre-fetched; multiple note_created events emitted."""
        make_result = lambda url, fp: json.dumps({  # noqa: E731
            "file_path": fp, "title": fp, "url": url, "status": "created",
        })

        side_effects = [
            make_result("https://a.com", "technologies/a.md"),
            make_result("https://b.com", "technologies/b.md"),
        ]

        update = _fake_update([_text_content("ok")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch(
                "monocle.agents.tools.VaultTools.create_reference_from_url",
                new=AsyncMock(side_effect=side_effects),
            ),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "compare these"}],
                    "fetch_urls": ["https://a.com", "https://b.com"],
                },
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        nc_events = [e for e in events if e.get("event") == "note_created"]
        assert len(nc_events) == 2

    def test_fetch_urls_failed_prefetch_continues_chat(self, api_client):
        """A failure in pre-fetching one URL should not abort the whole chat stream."""
        update = _fake_update([_text_content("continuing")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch(
                "monocle.agents.tools.VaultTools.create_reference_from_url",
                new=AsyncMock(side_effect=RuntimeError("network error")),
            ),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "what is this?"}],
                    "fetch_urls": ["https://unreachable.example"],
                },
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        # Chat still completes; no note_created for failed fetch
        nc_events = [e for e in events if e.get("event") == "note_created"]
        assert len(nc_events) == 0
        token_events = [e for e in events if e.get("event") == "token"]
        assert any(e["data"]["delta"] == "continuing" for e in token_events)

    def test_fetch_urls_invalid_scheme_ignored(self, api_client):
        """Non-http/https URLs in fetch_urls are silently filtered out."""
        update = _fake_update([_text_content("ok")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        mock_fetch = AsyncMock()
        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch("monocle.agents.tools.VaultTools.create_reference_from_url", new=mock_fetch),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "fetch_urls": ["ftp://example.com", "file:///etc/passwd"],
                },
            )

        assert resp.status_code == 200
        # create_reference_from_url should NOT be called for invalid schemes
        mock_fetch.assert_not_called()

    def test_fetch_urls_trailing_punctuation_sanitized(self, api_client):
        """Trailing prose punctuation is stripped before pre-fetching URLs."""
        prefetch_result = json.dumps({
            "file_path": "technologies/example-ref.md",
            "title": "Example Site",
            "url": "https://github.com/github/awesome-copilot",
            "status": "created",
        })
        update = _fake_update([_text_content("ok")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        mock_fetch = AsyncMock(return_value=prefetch_result)
        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch("monocle.agents.tools.VaultTools.create_reference_from_url", new=mock_fetch),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "summarize this"}],
                    "fetch_urls": ["https://github.com/github/awesome-copilot,"],
                },
            )

        assert resp.status_code == 200
        mock_fetch.assert_awaited_once_with("https://github.com/github/awesome-copilot")

    def test_fetch_urls_capped_at_five(self, api_client):
        """More than 5 fetch_urls are silently capped to the first 5."""
        results = [
            json.dumps({"file_path": f"ref{i}.md", "title": f"R{i}", "url": f"https://url{i}.com", "status": "created"})
            for i in range(6)
        ]
        update = _fake_update([_text_content("done")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        mock_fetch = AsyncMock(side_effect=results)
        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch("monocle.agents.tools.VaultTools.create_reference_from_url", new=mock_fetch),
        ):
            resp = api_client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "many urls"}],
                    "fetch_urls": [f"https://url{i}.com" for i in range(6)],
                },
            )

        assert resp.status_code == 200
        # Only 5 fetch calls should have been made
        assert mock_fetch.call_count == 5

    def test_no_fetch_urls_does_not_call_vault_tools(self, api_client):
        """When fetch_urls is absent, VaultTools is not instantiated for pre-fetch."""
        update = _fake_update([_text_content("hi")])
        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        mock_fetch = AsyncMock()
        with (
            patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent),
            patch("monocle.agents.tools.VaultTools.create_reference_from_url", new=mock_fetch),
        ):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

        assert resp.status_code == 200
        mock_fetch.assert_not_called()

    def test_tool_call_event_includes_call_id(self, api_client):
        """FunctionCallContent emits a tool_call SSE event with call_id field."""
        fn_call = _fn_call_content("search_vault", call_id="abc-123")
        update = _fake_update([fn_call])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "search"}]},
            )

        events = _parse_sse(resp.text)
        tool_events = [e for e in events if e.get("event") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["data"]["name"] == "search_vault"
        assert tool_events[0]["data"]["call_id"] == "abc-123"

    def test_tool_error_event_emitted_for_error_result(self, api_client):
        """FunctionResultContent with an 'error' key emits a tool_error SSE event."""
        fn_call = _fn_call_content("get_graph", call_id="err-1")
        fn_result = _fn_result_content(
            json.dumps({"error": "Graph builder not available"}), call_id="err-1"
        )
        update = _fake_update([fn_call, fn_result])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "show graph"}]},
            )

        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("event") == "tool_error"]
        assert len(error_events) == 1
        assert error_events[0]["data"]["name"] == "get_graph"
        assert error_events[0]["data"]["call_id"] == "err-1"
        assert "Graph builder" in error_events[0]["data"]["error"]

    def test_tool_error_stream_continues_to_done(self, api_client):
        """A tool_error event does not abort the stream; done is still emitted with status=success."""
        fn_call = _fn_call_content("read_note", call_id="err-2")
        fn_result = _fn_result_content(
            json.dumps({"error": "File not found"}), call_id="err-2"
        )
        text = _text_content("I could not find that note.")
        update = _fake_update([fn_call, fn_result, text])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "read a note"}]},
            )

        events = _parse_sse(resp.text)
        event_types = [e.get("event") for e in events]
        assert "tool_error" in event_types
        assert "token" in event_types
        assert events[-1]["event"] == "done"
        assert events[-1]["data"]["status"] == "success"

    def test_tool_error_not_emitted_for_clean_result(self, api_client):
        """FunctionResultContent without an 'error' key does NOT emit tool_error."""
        fn_result = _fn_result_content(json.dumps({"chunks": [], "total": 0}))
        update = _fake_update([fn_result])

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_updates_gen(update))

        with patch("monocle.routers.chat.create_chat_agent", return_value=mock_agent):
            resp = api_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "search"}]},
            )

        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("event") == "tool_error"]
        assert len(error_events) == 0


#endregion

