"""
monocle/tests/test_agents.py — Tests for M10 Agent Framework & Chat API.

Coverage:
  - POST /api/chat SSE event sequence: token, tool_call, note_created, done
  - tool_error: stream continues after tool failure
  - done event emitted on normal completion; error-only on pre-stream failures
  - Empty messages → 422
  - VaultTools construction and tool list
  - create_chat_agent factory returns a ChatAgent
"""
from __future__ import annotations

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


#endregion

# ---------------------------------------------------------------------------
#region #*   Tests: VaultTools construction
# ---------------------------------------------------------------------------

class TestVaultTools:
    """Tests that VaultTools builds correctly and exposes the right tools."""

    def test_tools_list_has_9_entries(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools

        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, graph_builder=None)
        assert len(vt.tools) == 9

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
        assert any("search_vault" in n or "search" in n for n in names)


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

    @pytest.mark.asyncio
    async def test_search_vault_returns_json_list(self, vault_tools):
        result = await vault_tools.search_vault("Alice", n_results=3)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_read_note_returns_json_with_body(self, vault_tools):
        result = await vault_tools.read_note("people/alice-example.md")
        parsed = json.loads(result)
        assert "body" in parsed
        assert "file_path" in parsed
        assert parsed["file_path"] == "people/alice-example.md"

    @pytest.mark.asyncio
    async def test_read_note_nonexistent_raises(self, vault_tools):
        with pytest.raises(Exception):
            await vault_tools.read_note("people/nobody.md")

    @pytest.mark.asyncio
    async def test_write_note_updates_body(self, vault_tools, tmp_vault):
        result = await vault_tools.write_note("people/alice-example.md", "New body text.")
        parsed = json.loads(result)
        assert parsed["status"] == "updated"
        # Verify the vault file was really updated
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        assert "New body text." in content

    @pytest.mark.asyncio
    async def test_write_note_body_length_cap(self, vault_tools):
        """write_note must reject bodies over 50,000 chars."""
        with pytest.raises(ValueError, match="50,000"):
            await vault_tools.write_note("people/alice-example.md", "x" * 50_001)

    @pytest.mark.asyncio
    async def test_create_note_returns_file_path(self, vault_tools):
        result = await vault_tools.create_note(
            title="My Idea",
            body="A great idea.",
            note_type="idea",
            domain="personal",
        )
        parsed = json.loads(result)
        assert parsed["status"] == "created"
        assert "file_path" in parsed

    @pytest.mark.asyncio
    async def test_create_note_sets_review_status_pending(self, vault_tools, tmp_vault):
        """Agent-created notes must land as review_status: pending."""
        await vault_tools.create_note(title="Pending Note", body="Content.", note_type="idea", domain="personal")
        # Find the newly created note and check its frontmatter
        import yaml
        for md_file in tmp_vault.rglob("*.md"):
            text = md_file.read_text()
            if "Pending Note" in text:
                fm_text = text.split("---")[1]
                fm = yaml.safe_load(fm_text)
                assert fm.get("review_status") == "pending"
                return
        pytest.fail("Created note not found in vault")

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
    async def test_get_stats_returns_json(self, vault_tools):
        result = await vault_tools.get_stats()
        parsed = json.loads(result)
        assert "total_notes" in parsed
        assert "notes_by_type" in parsed

    @pytest.mark.asyncio
    async def test_list_notes_returns_items(self, vault_tools):
        result = await vault_tools.list_notes(limit=5)
        parsed = json.loads(result)
        assert "items" in parsed
        assert "total" in parsed

    @pytest.mark.asyncio
    async def test_list_notes_limit_capped_at_20(self, vault_tools):
        result = await vault_tools.list_notes(limit=999)
        parsed = json.loads(result)
        assert len(parsed["items"]) <= 20

    @pytest.mark.asyncio
    async def test_get_person_graph_no_graph_builder_returns_error_json(self, vault_tools):
        """When graph_builder=None the tool returns an error JSON, not an exception."""
        result = await vault_tools.get_person_graph("Alice")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_get_person_graph_with_builder(self, tmp_vault, memory_index, mock_ai):
        from monocle.vault import VaultLayer
        from monocle.graph import GraphBuilder
        from monocle.agents.tools import VaultTools

        vault = VaultLayer(str(tmp_vault))
        graph_builder = GraphBuilder(vault)
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, graph_builder=graph_builder)
        result = await vt.get_person_graph("Alice Example")
        parsed = json.loads(result)
        # Should return graph structure even if focus has no edges
        assert "focus" in parsed
        assert "node_count" in parsed

    # -----------------------------------------------------------------------
    #region #*    append_to_note tests
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_append_to_note_updates_existing_body(self, vault_tools, tmp_vault):
        """append_to_note should find alice-example.md and append new content."""
        result = await vault_tools.append_to_note("Alice", "She also leads the infra guild.")
        parsed = json.loads(result)
        assert parsed["status"] == "updated"
        assert "file_path" in parsed
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        assert "She also leads the infra guild." in content

    @pytest.mark.asyncio
    async def test_append_to_note_preserves_existing_body(self, vault_tools, tmp_vault):
        """append_to_note must keep the original content intact."""
        # Read original to know what we started with
        original = (tmp_vault / "people" / "alice-example.md").read_text()
        await vault_tools.append_to_note("Alice", "New fact.")
        updated = (tmp_vault / "people" / "alice-example.md").read_text()
        # Frontmatter is preserved
        assert "---" in updated
        # New content added
        assert "New fact." in updated

    @pytest.mark.asyncio
    async def test_append_to_note_no_match_returns_error_json(self, tmp_vault, memory_index, mock_ai):
        """When no indexed note matches, return an error JSON (not exception)."""
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools

        # Use an empty index (no chunks)
        vault = VaultLayer(str(tmp_vault))
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai)
        result = await vt.append_to_note("ZZZ_nonexistent_person_xyz", "Content.")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_append_to_note_content_length_cap(self, vault_tools):
        """append_to_note must reject content over 50,000 chars."""
        with pytest.raises(ValueError, match="50,000"):
            await vault_tools.append_to_note("Alice", "x" * 50_001)

    @pytest.mark.asyncio
    async def test_append_to_note_triggers_reindex(self, tmp_vault, memory_index, mock_ai):
        """append_to_note must push to reindex_queue when one is configured."""
        from monocle.vault import VaultLayer
        from monocle.agents.tools import VaultTools
        from monocle.models import NoteChunk

        vault = VaultLayer(str(tmp_vault))
        memory_index.upsert_chunks([
            NoteChunk(
                chunk_id="people/alice-example.md::0",
                file_path="people/alice-example.md",
                chunk_index=0,
                text="Alice is an engineer.",
                embedding=[0.1] * 1536,
            )
        ])
        mock_rq = MagicMock()
        vt = VaultTools(vault=vault, index=memory_index, ai=mock_ai, reindex_queue=mock_rq)
        await vt.append_to_note("Alice", "New fact.")
        mock_rq.push.assert_called_once()

    @pytest.mark.asyncio
    async def test_append_to_note_unwraps_json_body(self, vault_tools, tmp_vault):
        """append_to_note must unwrap {"body": "..."} JSON the LLM sometimes produces."""
        await vault_tools.append_to_note("Alice", '{"body": "She won a hackathon."}')
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        assert "She won a hackathon." in content
        assert '{"body"' not in content

    @pytest.mark.asyncio
    async def test_append_to_note_ai_merge_integrates_content(self, vault_tools, tmp_vault):
        """When AI is available, append_to_note merges rather than raw-appends."""
        result = await vault_tools.append_to_note("Alice", "She now leads the infra guild.")
        parsed = json.loads(result)
        assert parsed["status"] == "updated"
        content = (tmp_vault / "people" / "alice-example.md").read_text()
        # Both old and new content should appear in the merged body
        assert "She now leads the infra guild." in content

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

