"""monocle.ai — AI provider abstraction layer.

Public API::

    from monocle.ai import get_provider
    provider = get_provider(settings)   # returns AIProvider for configured backend
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.config import Settings

from monocle.ai.base import AIProvider  # noqa: F401 — re-export

logger = logging.getLogger(__name__)


def get_provider(settings: "Settings") -> AIProvider:
    """Construct and return the configured ``AIProvider`` instance.

    Provider selection is governed by ``settings.ai.provider``:

    * ``"ollama"``        → ``OllamaProvider``
    * ``"foundry_local"`` → ``FoundryLocalProvider``
    * ``"azure"``         → ``AzureOpenAIProvider``

    Raises ``ValueError`` for unknown provider names.
    """
    provider_name = settings.ai.provider
    logger.info("[AI] Initialising provider: %s", provider_name)

    # Build the configured transcription provider once; pass to all AI providers.
    # "native" returns None, letting each provider use its built-in (Foundry/Azure)
    # or raise a clear error (Ollama) when transcription is attempted without config.
    from monocle.ai.transcription import get_transcription_provider

    transcription_provider = get_transcription_provider(settings)

    if provider_name == "ollama":
        from monocle.ai.ollama_provider import OllamaProvider

        return OllamaProvider(
            embed_model=settings.ai.embed_model,
            chat_model=settings.ai.chat_model,
            base_url=settings.ai.ollama_base_url,
            transcription_provider=transcription_provider,
        )

    if provider_name == "foundry_local":
        from monocle.ai.foundry_local_provider import FoundryLocalProvider

        base_url = (
            settings.foundry_local_base_url
            or settings.ai.foundry_local_base_url
        )
        api_key = settings.foundry_local_api_key or "local"
        return FoundryLocalProvider(
            base_url=base_url,
            api_key=api_key,
            embed_model=settings.ai.embed_model,
            chat_model=settings.ai.chat_model,
            transcribe_model=settings.ai.transcribe_model,
            embed_dimensions=settings.ai.embed_dimensions,
            transcription_provider=transcription_provider,  # None = use native
        )

    if provider_name == "azure":
        from monocle.ai.azure_provider import AzureOpenAIProvider

        # Required — model_validator in Settings already raised if missing
        return AzureOpenAIProvider(
            api_key=settings.azure_openai_api_key,  # type: ignore[arg-type]
            endpoint=settings.azure_openai_endpoint,  # type: ignore[arg-type]
            api_version=settings.azure_openai_api_version,  # type: ignore[arg-type]
            embed_deployment=(
                settings.azure_openai_embed_deployment or settings.ai.embed_model
            ),
            chat_deployment=(
                settings.azure_openai_chat_deployment or settings.ai.chat_model
            ),
            transcribe_deployment=settings.ai.transcribe_model,
            embed_dimensions=settings.ai.embed_dimensions,
            transcription_provider=transcription_provider,  # None = use native
        )

    raise ValueError(
        f"Unknown ai.provider value: {provider_name!r}. "
        "Expected one of: ollama, foundry_local, azure."
    )
