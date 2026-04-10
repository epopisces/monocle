"""
monocle/agents/__init__.py — Agent factory for the chat endpoint.

Provides ``create_chat_agent(provider, vault, index, settings)`` which returns
a ``ChatAgent`` backed by the configured ``AIProvider`` via a thin
``BaseChatClient`` adapter.

The adapter translates between:
  - The agent framework's ``ChatMessage`` list + ``ChatOptions`` (with tools)
  - The existing ``AIProvider.chat()`` OpenAI-style dict-message interface

OTel providers are configured once per agent construction via
``agent_framework.observability.configure_otel_providers``.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, AsyncIterable

from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
    use_function_invocation,
)

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.config import Settings
    from monocle.graph import GraphBuilder
    from monocle.index.base import IndexLayer
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

logger = logging.getLogger(__name__)

# Flag to ensure OTel configuration is called only once per process lifetime
_otel_configured = False


def _configure_agent_otel(settings: "Settings") -> None:
    """Configure agent framework OTel providers (idempotent within a process)."""
    global _otel_configured
    if _otel_configured:
        return
    try:
        from agent_framework.observability import configure_otel_providers
        from urllib.parse import urlparse

        port = None
        if settings.telemetry.enabled:
            try:
                parsed = urlparse(settings.telemetry.otlp_endpoint)
                if parsed.port == 4317:
                    port = 4317
            except Exception:
                pass
        configure_otel_providers(
            enable_sensitive_data=settings.telemetry.enable_sensitive_data,
            vs_code_extension_port=port,
        )
        _otel_configured = True
        logger.debug("[AGENT] Agent framework OTel providers configured (port=%s)", port)
    except Exception as exc:  # pragma: no cover
        logger.debug("[AGENT] Agent framework OTel configuration skipped: %s", exc)


#endregion

# ---------------------------------------------------------------------------
#region #*   BaseChatClient adapter
# ---------------------------------------------------------------------------


@use_function_invocation
class _AIProviderChatClient(BaseChatClient):
    """Thin adapter from ``AIProvider.chat`` to ``BaseChatClient``.

    The ``@use_function_invocation`` decorator wraps ``get_streaming_response``
    to handle the tool-call / tool-result loop automatically, calling
    ``_inner_get_streaming_response`` for each LLM turn.
    """

    OTEL_PROVIDER_NAME = "monocle_ai_provider"

    def __init__(self, ai: "AIProvider", tool_hint: str | None = None) -> None:
        super().__init__()
        self._ai = ai
        self._tool_hint = tool_hint

    @staticmethod
    def _normalize_tool_call_arguments(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize tool call arguments from JSON strings to dicts.

        The agent framework may serialize tool call arguments as JSON strings,
        but providers (Ollama, Azure, Foundry) expect them as dicts in their
        Pydantic models. This normalizes them for all providers uniformly.
        """
        normalized = []
        for msg in messages:
            msg_copy = dict(msg)
            if "tool_calls" in msg_copy:
                normalized_calls = []
                for tc in msg_copy.get("tool_calls", []):
                    tc_copy = dict(tc)
                    if "function" in tc_copy:
                        func_copy = dict(tc_copy["function"])
                        args = func_copy.get("arguments")
                        if isinstance(args, str):
                            try:
                                func_copy["arguments"] = json.loads(args)
                            except (json.JSONDecodeError, ValueError):
                                pass  # Keep as string if not valid JSON; provider will validate
                        tc_copy["function"] = func_copy
                    normalized_calls.append(tc_copy)
                msg_copy["tool_calls"] = normalized_calls
            normalized.append(msg_copy)
        return normalized

    # ------------------------------------------------------------------
    # Convert agent-framework ChatMessage list → dict-list for AIProvider.chat
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert agent framework ChatMessage objects to OpenAI-style dicts."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            role: str = msg.role.value if msg.role is not None else "user"
            # Collect all content into a single string for simple text messages
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []

            for content in msg.contents:
                if isinstance(content, TextContent):
                    text_parts.append(content.text)
                elif isinstance(content, FunctionCallContent):
                    # Tool call from assistant
                    call_args = content.arguments
                    if isinstance(call_args, dict):
                        call_args_str = json.dumps(call_args)
                    else:
                        call_args_str = str(call_args) if call_args is not None else "{}"
                    tool_calls.append(
                        {
                            "id": content.call_id or "",
                            "type": "function",
                            "function": {
                                "name": content.function_name if hasattr(content, "function_name") else (content.name or ""),
                                "arguments": call_args_str,
                            },
                        }
                    )
                elif isinstance(content, FunctionResultContent):
                    # Tool result — becomes a "tool" role message
                    # Avoid double-encoding: if result is already a string, use as-is;
                    # otherwise JSON-serialize it
                    if isinstance(content.result, str):
                        result_content = content.result
                    elif content.result is not None:
                        result_content = json.dumps(content.result)
                    else:
                        result_content = ""
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": content.call_id or "",
                            "content": result_content,
                        }
                    )

            if tool_results:
                result.extend(tool_results)
            elif tool_calls:
                entry: dict[str, Any] = {"role": role, "tool_calls": tool_calls}
                if text_parts:
                    entry["content"] = "".join(text_parts)
                result.append(entry)
            else:
                result.append({"role": role, "content": "".join(text_parts)})

        return result

    @staticmethod
    def _build_openai_tools(chat_options: ChatOptions) -> list[dict[str, Any]] | None:
        """Convert ChatOptions tools → OpenAI-compatible tool schema list."""
        if not chat_options.tools:
            return None
        schemas: list[dict[str, Any]] = []
        for tool in chat_options.tools:
            if hasattr(tool, "to_json_schema_spec"):
                schemas.append(tool.to_json_schema_spec())
            elif isinstance(tool, dict):
                schemas.append(tool)
        return schemas or None

    # ------------------------------------------------------------------
    # Non-streaming (full response)
    # ------------------------------------------------------------------

    async def _inner_get_response(
        self,
        *,
        messages: list[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        dict_messages = self._to_dict_messages(messages)
        normalized_messages = self._normalize_tool_call_arguments(dict_messages)
        tools = self._build_openai_tools(chat_options)

        # AIProvider.chat with stream=False returns a str or AsyncIterator.
        # We always pass stream=False for the non-streaming path.
        tool_choice: dict | None = None
        if self._tool_hint and tools and _is_first_tool_call_turn(messages):
            tool_choice = {"type": "function", "function": {"name": self._tool_hint}}
            logger.debug("[AGENT] First-turn tool policy: tool_choice=%s", self._tool_hint)
        raw = await self._ai.chat(
            normalized_messages,
            stream=False,
            tools=tools,
            tool_choice=tool_choice,
        )

        # raw is either a plain str or (fallback) an AsyncIterator — consume it
        if not isinstance(raw, str):
            # Drain async iterator to get full text
            parts: list[str] = []
            async for chunk in raw:
                parts.append(chunk)
            raw = "".join(parts)

        # Detect if the model returned a tool call (JSON with tool_calls key)
        parsed_tool_calls = _try_parse_tool_calls(raw)
        if parsed_tool_calls is not None:
            contents = [
                FunctionCallContent(
                    call_id=tc.get("id", ""),
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"].get("arguments", "{}")),
                )
                for tc in parsed_tool_calls
            ]
            return ChatResponse(
                messages=[ChatMessage(role="assistant", contents=contents)]
            )

        return ChatResponse(
            messages=[ChatMessage(role="assistant", text=raw)]
        )

    # ------------------------------------------------------------------
    # Streaming (token-by-token)
    # ------------------------------------------------------------------

    async def _inner_get_streaming_response(
        self,
        *,
        messages: list[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        dict_messages = self._to_dict_messages(messages)
        normalized_messages = self._normalize_tool_call_arguments(dict_messages)
        tools = self._build_openai_tools(chat_options)

        tool_choice: dict | None = None
        if self._tool_hint and tools and _is_first_tool_call_turn(messages):
            tool_choice = {"type": "function", "function": {"name": self._tool_hint}}
            logger.debug("[AGENT] First-turn tool policy: tool_choice=%s", self._tool_hint)
        stream = await self._ai.chat(
            normalized_messages,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
        )

        if isinstance(stream, str):
            # Provider returned full text synchronously
            parsed_tc = _try_parse_tool_calls(stream)
            if parsed_tc is not None:
                for tc in parsed_tc:
                    yield ChatResponseUpdate(
                        role="assistant",
                        contents=[FunctionCallContent(
                            call_id=tc.get("id", ""),
                            name=tc["function"]["name"],
                            arguments=_parse_arguments(tc["function"].get("arguments")),
                        )],
                    )
            else:
                yield ChatResponseUpdate(role="assistant", text=stream)
            return

        # Yield token deltas as they arrive; detect tool-call JSON chunks emitted
        # by the provider at the end of the stream.
        async for chunk in stream:
            if chunk:
                parsed_tc = _try_parse_tool_calls(chunk)
                if parsed_tc is not None:
                    for tc in parsed_tc:
                        yield ChatResponseUpdate(
                            role="assistant",
                            contents=[FunctionCallContent(
                                call_id=tc.get("id", ""),
                                name=tc["function"]["name"],
                                arguments=_parse_arguments(tc["function"].get("arguments")),
                            )],
                        )
                else:
                    yield ChatResponseUpdate(role="assistant", text=chunk)


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: extract tool calls from raw LLM text output
# ---------------------------------------------------------------------------


def _parse_arguments(args: dict | str | None) -> dict:
    """Parse tool call arguments from either dict or JSON string."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            return json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _try_parse_tool_calls(raw: str) -> list[dict] | None:
    """Attempt to extract tool calls from a raw LLM response string.

    Handles several formats local models emit:

    1. Clean JSON:        {"tool_calls": [...]}
    2. Fenced code block: ```json\n{"tool_calls": [...]}\n```
    3. Embedded in prose: "Sure! {"tool_calls": [...]} Let me know."

    Returns None if no tool call structure is detected.
    Logs a warning when a ``tool_calls`` pattern is present but unparseable
    so that silent failures are visible in logs.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    # Strategy 1: direct clean JSON — fast path
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "tool_calls" in data:
                return data["tool_calls"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Strategy 2: fenced code block (```json ... ``` or ``` ... ```)
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        try:
            data = json.loads(fenced_match.group(1))
            if isinstance(data, dict) and "tool_calls" in data:
                return data["tool_calls"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Strategy 3: JSON object embedded in prose — find '{"tool_calls"' by scanning
    brace_pos = stripped.find('{"tool_calls"')
    if brace_pos != -1:
        depth = 0
        for i, ch in enumerate(stripped[brace_pos:], brace_pos):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[brace_pos : i + 1]
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, dict) and "tool_calls" in data:
                            logger.debug("_try_parse_tool_calls: extracted tool calls from embedded JSON")
                            return data["tool_calls"]
                    except (json.JSONDecodeError, KeyError):
                        pass
                    break

    # Warn if the keyword appears but nothing could be extracted
    if "tool_calls" in stripped:
        logger.warning(
            "_try_parse_tool_calls: response contains 'tool_calls' but could not be parsed; "
            "preview: %.120s",
            stripped,
        )

    return None


def _is_first_tool_call_turn(messages: list["ChatMessage"]) -> bool:
    """Return True if no tool invocations have occurred yet in this conversation.

    The adapter uses this to decide whether to enforce the first-turn tool policy.
    ``tool_choice`` is only passed to the provider on the very first LLM call;
    subsequent turns (after at least one FunctionCallContent) are unconstrained.
    """
    for msg in messages:
        for content in msg.contents:
            if isinstance(content, (FunctionCallContent, FunctionResultContent)):
                return False
    return True


#endregion

# ---------------------------------------------------------------------------
#region #*   Public factory
# ---------------------------------------------------------------------------


# Allowed tool_hint values — must match VaultTools method names (canonical MCP names)
_ALLOWED_TOOL_HINTS = frozenset({
    "search_vault",
    "read_note",
    "update_note",
    "create_note",
    "create_reference_from_url",
    "get_graph",
})


def create_chat_agent(
    ai: "AIProvider",
    vault: "VaultLayer",
    index: "IndexLayer",
    settings: "Settings",
    graph_builder: "GraphBuilder | None" = None,
    reindex_queue: "ReindexQueue | None" = None,
    tool_hint: str | None = None,
):
    """Create a ``ChatAgent`` wired with all 6 vault tools (canonical MCP names).

    Args:
        ai: The configured ``AIProvider`` instance.
        vault: Active ``VaultLayer`` for the vault.
        index: Active ``IndexLayer`` (ChromaDB or MemoryIndex).
        settings: Application settings (used for OTel and model config).
        graph_builder: Optional ``GraphBuilder`` for graph tool support.
        reindex_queue: Optional ``ReindexQueue`` for triggering re-indexing when notes are created/updated.

    Returns:
        A ready-to-use ``ChatAgent`` with all 6 tools registered.
    """
    from agent_framework import ChatAgent

    from monocle.agents.tools import VaultTools

    _configure_agent_otel(settings)

    tool_registry = VaultTools(vault=vault, index=index, ai=ai, graph_builder=graph_builder, reindex_queue=reindex_queue)
    client = _AIProviderChatClient(ai=ai, tool_hint=tool_hint)

    base_instructions = (
            "You are Monocle, a personal knowledge assistant. "
            "You have access to the user's private vault of notes and can search, read, "
            "create, and update notes. Always cite the note file_path when referencing "
            "specific information. When creating notes, choose the most appropriate "
            "note type. Be concise and factual — do not invent details not found in the vault.\n\n"
            "TOOL SELECTION GUIDE:\n"
            "- To RETRIEVE or LOOK UP notes (e.g. 'What are my notes on X?', "
            "'What do I know about Y?', 'Tell me about Z'): use search_vault, "
            "then read_note to get full details of the most relevant result.\n"
            "- To ADD, APPEND, or MODIFY information in an existing note "
            "(e.g. 'add to my note on X', 'update my note about Y with <new info>'): "
            "use update_note — pass 'body' (the new text, never as JSON) and either "
            "'file_path' (preferred, from a prior search_vault/read_note result) or "
            "'query' (the note name/topic to find). The tool intelligently merges new "               "content with the existing note body using AI.\n"
            "- To CREATE a brand-new note: use create_note.\n"
            "- For person relationship graphs: use get_graph.\n"
            "- To CREATE A REFERENCE NOTE FROM A URL: use create_reference_from_url. "
            "Never use create_note with made-up content. "
            "The tool fetches the page, generates an AI summary, and creates a reference note. "
            "The tool returns file_path, title, and summary (the AI-generated note body). "
            "Inform the user that a reference note has been created and saved to that file path, "
            "optionally highlighting key takeaways from the summary."
        )

    # Inject tool hint directive when provided and valid
    if tool_hint and tool_hint in _ALLOWED_TOOL_HINTS:
        base_instructions += (
            f"\n\nREQUIRED: The user selected a guided action. "
            f"You MUST call the `{tool_hint}` tool first for this request."
        )

    agent = ChatAgent(
        chat_client=client,
        instructions=base_instructions,
        name="monocle",
        model_id=settings.ai.chat_model,
        tools=tool_registry.tools,
    )
    logger.debug("[AGENT] ChatAgent created with %d tools", len(tool_registry.tools))
    return agent
