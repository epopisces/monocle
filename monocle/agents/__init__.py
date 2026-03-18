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


# ---------------------------------------------------------------------------
# BaseChatClient adapter
# ---------------------------------------------------------------------------


@use_function_invocation
class _AIProviderChatClient(BaseChatClient):
    """Thin adapter from ``AIProvider.chat`` to ``BaseChatClient``.

    The ``@use_function_invocation`` decorator wraps ``get_streaming_response``
    to handle the tool-call / tool-result loop automatically, calling
    ``_inner_get_streaming_response`` for each LLM turn.
    """

    OTEL_PROVIDER_NAME = "monocle_ai_provider"

    def __init__(self, ai: "AIProvider") -> None:
        super().__init__()
        self._ai = ai

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
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": content.call_id or "",
                            "content": json.dumps(content.result) if content.result is not None else "",
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
        tools = self._build_openai_tools(chat_options)

        # AIProvider.chat with stream=False returns a str or AsyncIterator.
        # We always pass stream=False for the non-streaming path.
        raw = await self._ai.chat(
            dict_messages,
            stream=False,
            tools=tools,
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
        tools = self._build_openai_tools(chat_options)

        stream = await self._ai.chat(
            dict_messages,
            stream=True,
            tools=tools,
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
                            arguments=json.loads(tc["function"].get("arguments", "{}")),
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
                                arguments=json.loads(tc["function"].get("arguments", "{}")),
                            )],
                        )
                else:
                    yield ChatResponseUpdate(role="assistant", text=chunk)


# ---------------------------------------------------------------------------
# Helper: extract tool calls from raw LLM text output
# ---------------------------------------------------------------------------


def _try_parse_tool_calls(raw: str) -> list[dict] | None:
    """Attempt to extract tool calls from a raw LLM response string.

    Some providers (particularly when accessed via AIProvider.chat with a
    schema-unaware call) embed tool call JSON inline.  This helper tries
    to detect that pattern; returns None if not a tool call response.
    """
    stripped = raw.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
        if isinstance(data, dict) and "tool_calls" in data:
            return data["tool_calls"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_chat_agent(
    ai: "AIProvider",
    vault: "VaultLayer",
    index: "IndexLayer",
    settings: "Settings",
    graph_builder: "GraphBuilder | None" = None,
):
    """Create a ``ChatAgent`` wired with all 7 vault tools.

    Args:
        ai: The configured ``AIProvider`` instance.
        vault: Active ``VaultLayer`` for the vault.
        index: Active ``IndexLayer`` (ChromaDB or MemoryIndex).
        settings: Application settings (used for OTel and model config).
        graph_builder: Optional ``GraphBuilder`` for graph tool support.

    Returns:
        A ready-to-use ``ChatAgent`` with all 7 tools registered.
    """
    from agent_framework import ChatAgent

    from monocle.agents.tools import VaultTools

    _configure_agent_otel(settings)

    tool_registry = VaultTools(vault=vault, index=index, ai=ai, graph_builder=graph_builder)
    client = _AIProviderChatClient(ai=ai)

    agent = ChatAgent(
        chat_client=client,
        instructions=(
            "You are Monocle, a personal knowledge assistant. "
            "You have access to the user's private vault of notes and can search, read, "
            "create, and update notes. Always cite the note file_path when referencing "
            "specific information. When creating notes, choose the most appropriate "
            "note type. Be concise and factual — do not invent details not found in the vault."
        ),
        name="monocle",
        model_id=settings.ai.chat_model,
        tools=tool_registry.tools,
    )
    logger.debug("[AGENT] ChatAgent created with %d tools", len(tool_registry.tools))
    return agent
