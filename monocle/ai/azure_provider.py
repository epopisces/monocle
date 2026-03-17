"""
monocle/ai/azure_provider.py — AIProvider backed by Azure OpenAI.

Uses ``openai.AsyncAzureOpenAI`` for embeddings, chat completions, and audio
transcription.  Credentials are injected from ``Settings`` env fields:

    AZURE_OPENAI_API_KEY
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_API_VERSION
    AZURE_OPENAI_EMBED_DEPLOYMENT   (optional; falls back to ai.embed_model)
    AZURE_OPENAI_CHAT_DEPLOYMENT    (optional; falls back to ai.chat_model)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator

from monocle.ai.base import AIProvider, _open_span
from monocle.telemetry import get_meter, span, timed

if TYPE_CHECKING:
    from monocle.ai.transcription import TranscriptionProvider

logger = logging.getLogger(__name__)


class AzureOpenAIProvider(AIProvider):
    """AIProvider backed by Azure OpenAI.

    Parameters
    ----------
    api_key:
        Azure OpenAI API key (``AZURE_OPENAI_API_KEY``).
    endpoint:
        Azure OpenAI endpoint URL (``AZURE_OPENAI_ENDPOINT``).
    api_version:
        API version string (``AZURE_OPENAI_API_VERSION``).
    embed_deployment:
        Deployment name for the embeddings model.
    chat_deployment:
        Deployment name for the chat model.
    transcribe_deployment:
        Deployment name for Whisper transcription model (default: ``"whisper"``).
    embed_dimensions:
        Requested embedding dimensions — passed to ``text-embedding-3-*`` models.
    """

    _provider_name = "azure"

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        api_version: str,
        embed_deployment: str = "text-embedding-3-large",
        chat_deployment: str = "gpt-4o",
        transcribe_deployment: str = "whisper",
        embed_dimensions: int | None = 1536,
        transcription_provider: "TranscriptionProvider | None" = None,
    ) -> None:
        import openai

        self._embed_deployment = embed_deployment
        self._chat_deployment = chat_deployment
        self._transcribe_deployment = transcribe_deployment
        self._embed_dimensions = embed_dimensions

        self._client = openai.AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        # Default: use the native Azure OpenAI Whisper deployment.
        # Overridable at construction time to swap in any TranscriptionProvider.
        if transcription_provider is None:
            from monocle.ai.transcription import NativeOpenAITranscriptionProvider

            transcription_provider = NativeOpenAITranscriptionProvider(
                self._client, model=transcribe_deployment
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
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_deployment}
        async with span("ai.embed", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                kwargs: dict = {"model": self._embed_deployment, "input": text}
                if self._embed_dimensions:
                    kwargs["dimensions"] = self._embed_dimensions
                response = await self._client.embeddings.create(**kwargs)
                return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_deployment}
        async with span("ai.embed_batch", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                kwargs: dict = {"model": self._embed_deployment, "input": texts}
                if self._embed_dimensions:
                    kwargs["dimensions"] = self._embed_dimensions
                response = await self._client.embeddings.create(**kwargs)
                # Preserve order — Azure returns items in the same order as input
                return [item.embedding for item in response.data]

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        attrs = {"ai.provider": self._provider_name, "ai.model": self._chat_deployment}
        if not stream:
            async with span("ai.chat", **attrs):
                async with timed(self._chat_hist, **{"provider": self._provider_name}):
                    response = await self._client.chat.completions.create(
                        model=self._chat_deployment,
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
            model=self._chat_deployment,
        ):
            stream = await self._client.chat.completions.create(
                model=self._chat_deployment,
                messages=messages,  # type: ignore[arg-type]
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

    # transcribe() is inherited from AIProvider.transcribe() which delegates to
    # self._transcription_provider (NativeOpenAITranscriptionProvider by default).
