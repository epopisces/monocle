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

import logging
from typing import TYPE_CHECKING, AsyncIterator

import ollama

from monocle.ai.base import AIProvider, _open_span
from monocle.telemetry import get_meter, span, timed

if TYPE_CHECKING:
    from monocle.ai.transcription import TranscriptionProvider

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
        self._client = ollama.AsyncClient(host=base_url)
        # Track which models have been confirmed / pulled so we only check once
        self._ready_models: set[str] = set()
        # Transcription is handled by a pluggable provider (Ollama has no native API)
        self._transcription_provider = transcription_provider

        meter = get_meter("monocle.ai")
        self._embed_hist = meter.create_histogram("ai.embed_duration", unit="ms")
        self._chat_hist = meter.create_histogram("ai.chat_duration", unit="ms")

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
    ) -> str | AsyncIterator[str]:
        """Send *messages* to the Ollama chat model."""
        attrs = {"ai.provider": self._provider_name, "ai.model": self._chat_model}
        if not stream:
            async with span("ai.chat", **attrs):
                async with timed(self._chat_hist, **{"provider": self._provider_name}):
                    await self._ensure_model(self._chat_model)
                    response = await self._client.chat(
                        model=self._chat_model,
                        messages=messages,
                        stream=False,
                    )
                    return response.message.content  # type: ignore[return-value]
        else:
            return self._stream_chat(messages)

    async def _stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:  # type: ignore[override]
        await self._ensure_model(self._chat_model)
        # Use the synchronous OTel span directly — async context managers are not
        # compatible with async generator functions.
        with _open_span(
            "ai.chat.stream",
            provider=self._provider_name,
            model=self._chat_model,
        ):
            # ollama.AsyncClient.chat() with stream=True is an async generator;
            # it must NOT be awaited — iterate directly.
            async for chunk in self._client.chat(
                model=self._chat_model,
                messages=messages,
                stream=True,
            ):
                content = chunk.message.content
                if content:
                    yield content

    # transcribe() is inherited from AIProvider.transcribe() which delegates to
    # self._transcription_provider.  No override needed here.
