"""
monocle/ai/ollama_provider.py — AIProvider implementation backed by Ollama.

Uses ``ollama.AsyncClient`` for embeddings and chat.  Auto-pulls models on
first use if they are not available locally.

Transcription:
    Ollama has no built-in transcription API.  Audio transcription is handled
    by a pluggable ``TranscriptionProvider`` (set via ``ai.transcribe_backend``
    in config.yaml).  The recommended default is a local whisper.cpp HTTP server
    (``transcribe_backend: whisper_cpp``); ``subprocess`` is available as a
    fallback.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, AsyncIterator, Literal

import ollama

from monocle.ai.base import AIProvider, _open_span
from monocle.telemetry import get_meter, span, timed

if TYPE_CHECKING:
    from monocle.ai.transcription import TranscriptionProvider
    from monocle.models import ProviderModelsResponse

logger = logging.getLogger(__name__)

class OllamaProvider(AIProvider):
    """AIProvider backed by a locally running Ollama instance.

    Parameters
    ----------
    embed_model:
        Name of the Ollama model used for embeddings (default: nomic-embed-text).
    chat_model:
        Name of the Ollama model used for chat completions (default: llama3.2).
    base_url:
        Base URL of the Ollama HTTP API (default: http://localhost:11434).
    """

    _provider_name = "ollama"

    def __init__(
        self,
        embed_model: str = "nomic-embed-text",
        chat_model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        transcription_provider: "TranscriptionProvider | None" = None,
    ) -> None:
        self._embed_model = embed_model
        self._chat_model = chat_model
        self._base_url = base_url
        # Do NOT set timeout here. For streaming responses, a hard HTTP timeout prevents
        # legitimate slow responses (e.g., 2-3 min LLM generations). Instead, the chat
        # router wraps streaming in asyncio.timeout(300) for timeout control at the app level.
        # httpx default is 5 minutes, which provides a safety net.
        self._client = ollama.AsyncClient(host=base_url)
        # Track which models have been confirmed / pulled so we only check once
        self._ready_models: set[str] = set()
        # Transcription is handled by a pluggable provider (Ollama has no native API)
        self._transcription_provider = transcription_provider

        meter = get_meter("monocle.ai")
        self._embed_hist = meter.create_histogram("ai.embed_duration", unit="ms")
        self._chat_hist = meter.create_histogram("ai.chat_duration", unit="ms")
        self._transcribe_hist = meter.create_histogram("ai.transcribe_duration", unit="ms")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_model(self, model: str) -> None:
        """Pull *model* from the Ollama registry if it is not available locally."""
        if model in self._ready_models:
            return
        try:
            await self._client.show(model)
            self._ready_models.add(model)
        except ollama.ResponseError as exc:
            if "not found" in str(exc).lower() or getattr(exc, "status_code", None) == 404:
                logger.info("[AI] Ollama model '%s' not found locally — pulling...", model)
                await self._client.pull(model)
                logger.info("[AI] Ollama model '%s' pull complete.", model)
                self._ready_models.add(model)
            else:
                raise

    # ------------------------------------------------------------------
    # AIProvider implementation
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for *text*."""
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_model}
        async with span("ai.embed", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                await self._ensure_model(self._embed_model)
                response = await self._client.embed(
                    model=self._embed_model, input=text
                )
                return response.embeddings[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per item in *texts* (preserves order)."""
        if not texts:
            return []
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_model}
        async with span("ai.embed_batch", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                await self._ensure_model(self._embed_model)
                response = await self._client.embed(
                    model=self._embed_model, input=texts
                )
                return response.embeddings

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
    ) -> str | AsyncIterator[str]:
        """Send *messages* to the Ollama chat model."""
        # Ollama doesn't support tool_choice natively; enforce first-turn policy via
        # schema filtering — expose only the hinted tool so the model must call it.
        effective_tools = tools
        if tool_choice and isinstance(tool_choice, dict) and tools:
            hint_name = (tool_choice.get("function") or {}).get("name")
            if hint_name:
                filtered = [t for t in tools if (t.get("function") or {}).get("name") == hint_name]
                if filtered:
                    effective_tools = filtered
                    logger.debug("[AI] Ollama first-turn: exposing only tool [%s]", hint_name)

        attrs = {"ai.provider": self._provider_name, "ai.model": self._chat_model}
        if not stream:
            async with span("ai.chat", **attrs):
                async with timed(self._chat_hist, **{"provider": self._provider_name}):
                    await self._ensure_model(self._chat_model)
                    kwargs: dict = {"model": self._chat_model, "messages": messages, "stream": False}
                    if effective_tools:
                        kwargs["tools"] = effective_tools
                    response = await self._client.chat(**kwargs)
                    if response.message.tool_calls:
                        return json.dumps({
                            "tool_calls": [
                                {
                                    "id": str(i),
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": (
                                            json.dumps(dict(tc.function.arguments))
                                            if hasattr(tc.function.arguments, "items")
                                            else tc.function.arguments or "{}"
                                        ),
                                    },
                                }
                                for i, tc in enumerate(response.message.tool_calls)
                            ]
                        })
                    return response.message.content or ""  # type: ignore[return-value]
        else:
            return self._stream_chat(messages, effective_tools)

    async def _stream_chat(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[str]:  # type: ignore[override]
        await self._ensure_model(self._chat_model)
        # Use the synchronous OTel span directly — async context managers are not
        # compatible with async generator functions.
        with _open_span(
            "ai.chat.stream",
            provider=self._provider_name,
            model=self._chat_model,
        ):
            # ollama.AsyncClient.chat() with stream=True returns a coroutine yielding an async generator.
            chat_kwargs: dict = {"model": self._chat_model, "messages": messages, "stream": True}
            if tools:
                chat_kwargs["tools"] = tools
            tool_calls_buf: list = []
            response = await self._client.chat(**chat_kwargs)
            async for chunk in response:
                content = chunk.message.content
                if content:
                    yield content
                if chunk.message.tool_calls:
                    tool_calls_buf.extend(chunk.message.tool_calls)
            # Emit accumulated tool calls as a single JSON chunk (non-streaming
            # detection via _try_parse_tool_calls in the adapter layer).
            if tool_calls_buf:
                yield json.dumps({
                    "tool_calls": [
                        {
                            "id": str(i),
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": (
                                    dict(tc.function.arguments)
                                    if hasattr(tc.function.arguments, "items")
                                    else json.loads(tc.function.arguments or "{}")
                                ),
                            },
                        }
                        for i, tc in enumerate(tool_calls_buf)
                    ]
                })

    # transcribe() is inherited from AIProvider.transcribe() which delegates to
    # self._transcription_provider.  No override needed here.

    async def get_model_status(self) -> "ProviderModelsResponse":  # type: ignore[override]
        """Query Ollama for available and loaded models."""
        from monocle.models import ModelStatus, ProviderModelsResponse

        # Attempt to reach the Ollama instance
        try:
            list_response = await self._client.list()
        except Exception as exc:
            logger.debug("[AI] Ollama list() failed: %s", exc)
            return ProviderModelsResponse(
                provider=self._provider_name,
                provider_reachable=False,
                models=[],
            )

        # Collect names of locally available models (strip :latest tag for matching)
        available_names: set[str] = set()
        for m in list_response.models:
            raw = getattr(m, "model", "") or ""
            available_names.add(raw)
            available_names.add(raw.split(":")[0])

        # Collect names of currently loaded models from the PS API
        loaded_names: set[str] = set()
        try:
            ps_response = await self._client.ps()
            for m in ps_response.models:
                raw = getattr(m, "model", "") or ""
                loaded_names.add(raw)
                loaded_names.add(raw.split(":")[0])
        except Exception as exc:
            logger.debug("[AI] Ollama ps() failed (no loaded models info): %s", exc)

        def _status(name: str, role: "Literal['chat', 'embed', 'transcribe']") -> ModelStatus:
            avail = name in available_names or name.split(":")[0] in available_names
            loaded = name in loaded_names or name.split(":")[0] in loaded_names
            return ModelStatus(name=name, role=role, available=avail, loaded=loaded)

        models = [
            _status(self._chat_model, "chat"),
            _status(self._embed_model, "embed"),
        ]
        return ProviderModelsResponse(
            provider=self._provider_name,
            provider_reachable=True,
            models=models,
        )
