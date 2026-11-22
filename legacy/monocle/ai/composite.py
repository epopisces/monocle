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
        """Merge status from both underlying providers.

        Returns exactly one model per role (chat, embed, transcribe) by:
        - Extracting the 'chat' role model from chat_provider
        - Extracting the 'embed' role model from embed_provider
        - Extracting the 'transcribe' role model (preferring chat_provider)

        This ensures no role duplicates and matches the docstring contract:
        "Status of each configured model role."
        """
        from monocle.models import ProviderModelsResponse

        chat_status = await self._chat_provider.get_model_status()
        embed_status = await self._embed_provider.get_model_status()

        # Build a dict of role -> ModelStatus, selecting one per role.
        # The provider_reachable flag is OR'd so we report True if any provider is reachable.
        models_by_role: dict[str, object] = {}

        # Extract chat role from chat_provider
        for model in chat_status.models:
            if model.role == "chat":
                models_by_role["chat"] = model
                break

        # Extract embed role from embed_provider
        for model in embed_status.models:
            if model.role == "embed":
                models_by_role["embed"] = model
                break

        # Extract transcribe role: prefer chat_provider, fall back to embed_provider
        for model in chat_status.models:
            if model.role == "transcribe":
                models_by_role["transcribe"] = model
                break
        if "transcribe" not in models_by_role:
            for model in embed_status.models:
                if model.role == "transcribe":
                    models_by_role["transcribe"] = model
                    break

        # Convert dict values to list, preserving a consistent order
        models = [models_by_role[role] for role in ("chat", "embed", "transcribe") if role in models_by_role]

        return ProviderModelsResponse(
            provider=f"{chat_status.provider}+{embed_status.provider}",
            provider_reachable=chat_status.provider_reachable or embed_status.provider_reachable,
            models=models,
        )

    async def detect_embed_dimensions(self) -> int:
        return await self._embed_provider.detect_embed_dimensions()
