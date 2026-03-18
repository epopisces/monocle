"""
monocle/ai/foundry_local_provider.py — AIProvider backed by Foundry Local.

Foundry Local exposes an OpenAI-compatible HTTP API, so this provider uses
``openai.AsyncOpenAI`` with a custom ``base_url``.

Configuration (from Settings / env vars):
    ``foundry_local_base_url``  — e.g. "http://localhost:5272"
    ``foundry_local_api_key``   — optional; defaults to "local"
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator

from monocle.ai.base import AIProvider, _open_span
from monocle.telemetry import get_meter, span, timed

if TYPE_CHECKING:
    from monocle.ai.transcription import TranscriptionProvider

logger = logging.getLogger(__name__)


class FoundryLocalProvider(AIProvider):
    """AIProvider backed by a Foundry Local OpenAI-compatible endpoint.

    Parameters
    ----------
    base_url:
        Base URL of the Foundry Local API (e.g. ``http://localhost:5272``).
    api_key:
        API key — pass ``"local"`` if no auth is required.
    embed_model:
        Model name for embeddings.
    chat_model:
        Model name for chat completions.
    transcribe_model:
        Model name for audio transcription (default: ``"whisper"``).
    embed_dimensions:
        Requested embedding dimensions (used where the API supports it).
    """

    _provider_name = "foundry_local"

    def __init__(
        self,
        base_url: str = "http://localhost:5272",
        api_key: str = "local",
        embed_model: str = "nomic-embed-text",
        chat_model: str = "llama3.2",
        transcribe_model: str = "whisper",
        embed_dimensions: int | None = None,
        transcription_provider: "TranscriptionProvider | None" = None,
    ) -> None:
        import openai

        self._embed_model = embed_model
        self._chat_model = chat_model
        self._transcribe_model = transcribe_model
        self._embed_dimensions = embed_dimensions

        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "local",
        )
        # Default: use the native OpenAI-compatible transcription endpoint.
        # Overridable at construction time to swap in any TranscriptionProvider.
        if transcription_provider is None:
            from monocle.ai.transcription import NativeOpenAITranscriptionProvider

            transcription_provider = NativeOpenAITranscriptionProvider(
                self._client, model=transcribe_model
            )
        self._transcription_provider = transcription_provider

        meter = get_meter("monocle.ai")
        self._embed_hist = meter.create_histogram("ai.embed_duration", unit="ms")
        self._chat_hist = meter.create_histogram("ai.chat_duration", unit="ms")
        self._transcribe_hist = meter.create_histogram("ai.transcribe_duration", unit="ms")

    # ------------------------------------------------------------------
    # AIProvider implementation
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_model}
        async with span("ai.embed", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                kwargs: dict = {"model": self._embed_model, "input": text}
                if self._embed_dimensions:
                    kwargs["dimensions"] = self._embed_dimensions
                response = await self._client.embeddings.create(**kwargs)
                return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_model}
        async with span("ai.embed_batch", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                kwargs: dict = {"model": self._embed_model, "input": texts}
                if self._embed_dimensions:
                    kwargs["dimensions"] = self._embed_dimensions
                response = await self._client.embeddings.create(**kwargs)
                # Preserve order — OpenAI returns items in the same order as input
                return [item.embedding for item in response.data]

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        attrs = {"ai.provider": self._provider_name, "ai.model": self._chat_model}
        if not stream:
            async with span("ai.chat", **attrs):
                async with timed(self._chat_hist, **{"provider": self._provider_name}):
                    response = await self._client.chat.completions.create(
                        model=self._chat_model,
                        messages=messages,  # type: ignore[arg-type]
                        stream=False,
                    )
                    return response.choices[0].message.content or ""
        else:
            return self._stream_chat(messages)

    async def _stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:  # type: ignore[override]
        # Use the synchronous OTel span directly — async context managers are not
        # compatible with async generator functions.
        with _open_span(
            "ai.chat.stream",
            provider=self._provider_name,
            model=self._chat_model,
        ):
            stream = await self._client.chat.completions.create(
                model=self._chat_model,
                messages=messages,  # type: ignore[arg-type]
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

    # transcribe() is inherited from AIProvider.transcribe() which delegates to
    # self._transcription_provider (NativeOpenAITranscriptionProvider by default).
