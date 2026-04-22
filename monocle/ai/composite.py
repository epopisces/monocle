"""
monocle/ai/composite.py — Composite AI provider for mixed-backend setups.

When the active chat model and embed model live on *different* providers,
``get_provider()`` returns a ``CompositeAIProvider`` that delegates each
operation to the appropriate underlying provider instance.

If both models share the same provider and base URL, ``get_provider()``
returns a plain single-provider instance instead (no compositing overhead).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator

from monocle.ai.base import AIProvider

if TYPE_CHECKING:
    from monocle.models import ProviderModelsResponse

logger = logging.getLogger(__name__)


class CompositeAIProvider(AIProvider):
    """Delegates chat → ``_chat_provider`` and embed → ``_embed_provider``.

    Transcription is handled by whichever provider has a transcription
    provider configured (chat provider is preferred).

    ``get_model_status()`` merges status from both underlying providers.
    """

    _provider_name = "composite"

    def __init__(
        self,
        chat_provider: AIProvider,
        embed_provider: AIProvider,
    ) -> None:
        self._chat_provider = chat_provider
        self._embed_provider = embed_provider
        logger.info(
            "[AI] CompositeAIProvider: chat=%s embed=%s",
            chat_provider._provider_name,
            embed_provider._provider_name,
        )

    # ------------------------------------------------------------------
    # AIProvider abstract method delegates
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        return await self._embed_provider.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embed_provider.embed_batch(texts)

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
    ) -> str | AsyncIterator[str]:
        return await self._chat_provider.chat(
            messages, stream=stream, tools=tools, tool_choice=tool_choice
        )

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        # Prefer chat provider; fall back to embed provider
        if self._chat_provider._transcription_provider is not None:  # type: ignore[attr-defined]
            return await self._chat_provider.transcribe(audio_bytes, mime_type)
        return await self._embed_provider.transcribe(audio_bytes, mime_type)

    async def get_model_status(self) -> "ProviderModelsResponse":
        """Merge status from both underlying providers."""
        from monocle.models import ProviderModelsResponse

        chat_status = await self._chat_provider.get_model_status()
        embed_status = await self._embed_provider.get_model_status()

        # Combine model lists; mark provider reachable if either is reachable
        return ProviderModelsResponse(
            provider=f"{chat_status.provider}+{embed_status.provider}",
            provider_reachable=chat_status.provider_reachable or embed_status.provider_reachable,
            models=chat_status.models + embed_status.models,
        )

    async def detect_embed_dimensions(self) -> int:
        return await self._embed_provider.detect_embed_dimensions()
