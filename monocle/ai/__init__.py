"""monocle.ai — AI provider abstraction layer.

Public API::

    from monocle.ai import get_provider
    provider = get_provider(settings)   # returns AIProvider for configured backend
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.config import ModelEntry, Settings

from monocle.ai.base import AIProvider  # noqa: F401 — re-export

logger = logging.getLogger(__name__)


def _build_single_provider(
    settings: "Settings",
    chat_entry: "ModelEntry",
    embed_entry: "ModelEntry",
) -> AIProvider:
    """Build a single-backend AIProvider that serves both chat and embed.

    Called when both models share the same ``provider`` and effective base URL,
    or when chat_entry == embed_entry (same model for both roles).

    The returned provider instance is configured with the chat model for chat
    and the embed model for embeddings.
    """
    from monocle.ai.transcription import get_transcription_provider

    provider_name = chat_entry.provider
    transcription_provider = get_transcription_provider(settings)

    if provider_name == "ollama":
        from monocle.ai.ollama_provider import OllamaProvider

        base_url = chat_entry.base_url or settings.ai.ollama_base_url
        return OllamaProvider(
            embed_model=embed_entry.name,
            chat_model=chat_entry.name,
            base_url=base_url,
            transcription_provider=transcription_provider,
        )

    if provider_name == "foundry_local":
        from monocle.ai.foundry_local_provider import FoundryLocalProvider

        base_url = (
            chat_entry.base_url
            or settings.foundry_local_base_url  # type: ignore[attr-defined]
            or settings.ai.foundry_local_base_url
        )
        api_key = settings.foundry_local_api_key or "local"  # type: ignore[attr-defined]
        return FoundryLocalProvider(
            base_url=base_url,
            api_key=api_key,
            embed_model=embed_entry.name,
            chat_model=chat_entry.name,
            transcribe_model=settings.ai.transcribe_model,
            embed_dimensions=settings.ai.embed_dimensions,
            transcription_provider=transcription_provider,
        )

    if provider_name == "azure":
        from monocle.ai.azure_provider import AzureOpenAIProvider

        return AzureOpenAIProvider(
            api_key=settings.azure_openai_api_key,  # type: ignore[arg-type]
            endpoint=settings.azure_openai_endpoint,  # type: ignore[arg-type]
            api_version=settings.azure_openai_api_version,  # type: ignore[arg-type]
            embed_deployment=(
                settings.azure_openai_embed_deployment or embed_entry.name  # type: ignore[attr-defined]
            ),
            chat_deployment=(
                settings.azure_openai_chat_deployment or chat_entry.name  # type: ignore[attr-defined]
            ),
            transcribe_deployment=settings.ai.transcribe_model,
            embed_dimensions=settings.ai.embed_dimensions,
            transcription_provider=transcription_provider,
        )

    raise ValueError(
        f"Unknown provider {provider_name!r} in ai.models. "
        "Expected one of: ollama, foundry_local, azure."
    )


def _build_provider_for_entry(
    settings: "Settings",
    entry: "ModelEntry",
) -> AIProvider:
    """Build a provider instance for a single model entry (used in composite setup)."""
    from monocle.ai.transcription import get_transcription_provider

    provider_name = entry.provider
    transcription_provider = get_transcription_provider(settings)

    if provider_name == "ollama":
        from monocle.ai.ollama_provider import OllamaProvider

        base_url = entry.base_url or settings.ai.ollama_base_url
        # For embed: use entry name for embed_model; for chat: use entry name for chat_model
        return OllamaProvider(
            embed_model=entry.name,
            chat_model=entry.name,
            base_url=base_url,
            transcription_provider=transcription_provider,
        )

    if provider_name == "foundry_local":
        from monocle.ai.foundry_local_provider import FoundryLocalProvider

        base_url = (
            entry.base_url
            or settings.foundry_local_base_url  # type: ignore[attr-defined]
            or settings.ai.foundry_local_base_url
        )
        api_key = settings.foundry_local_api_key or "local"  # type: ignore[attr-defined]
        return FoundryLocalProvider(
            base_url=base_url,
            api_key=api_key,
            embed_model=entry.name,
            chat_model=entry.name,
            transcribe_model=settings.ai.transcribe_model,
            embed_dimensions=settings.ai.embed_dimensions,
            transcription_provider=transcription_provider,
        )

    if provider_name == "azure":
        from monocle.ai.azure_provider import AzureOpenAIProvider

        return AzureOpenAIProvider(
            api_key=settings.azure_openai_api_key,  # type: ignore[arg-type]
            endpoint=settings.azure_openai_endpoint,  # type: ignore[arg-type]
            api_version=settings.azure_openai_api_version,  # type: ignore[arg-type]
            embed_deployment=entry.name,
            chat_deployment=entry.name,
            transcribe_deployment=settings.ai.transcribe_model,
            embed_dimensions=settings.ai.embed_dimensions,
            transcription_provider=transcription_provider,
        )

    raise ValueError(
        f"Unknown provider {provider_name!r} in ai.models. "
        "Expected one of: ollama, foundry_local, azure."
    )


def _effective_base_url(settings: "Settings", entry: "ModelEntry") -> str:
    """Return the resolved base URL for a model entry."""
    if entry.base_url:
        return entry.base_url
    if entry.provider == "ollama":
        return settings.ai.ollama_base_url
    if entry.provider == "foundry_local":
        fl_url = getattr(settings, "foundry_local_base_url", None)
        return fl_url or settings.ai.foundry_local_base_url
    return ""


def get_provider(settings: "Settings") -> AIProvider:
    """Construct and return the configured ``AIProvider`` instance.

    Resolves ``settings.ai.chat_model_key`` and ``settings.ai.embed_model_key``
    to their ``ModelEntry`` records, then:

    * If both models share the same provider and base URL → returns a single
      unified provider (``OllamaProvider``, ``FoundryLocalProvider``, or
      ``AzureOpenAIProvider``).
    * Otherwise → returns a ``CompositeAIProvider`` that delegates chat to the
      chat-model backend and embed to the embed-model backend.

    Raises ``ValueError`` for unknown provider names.
    """
    chat_entry = settings.ai.get_chat_model()
    embed_entry = settings.ai.get_embed_model()

    chat_provider_name = chat_entry.provider
    embed_provider_name = embed_entry.provider
    chat_url = _effective_base_url(settings, chat_entry)
    embed_url = _effective_base_url(settings, embed_entry)

    logger.info(
        "[AI] Initialising provider: chat=%s (%s) embed=%s (%s)",
        chat_entry.name, chat_provider_name,
        embed_entry.name, embed_provider_name,
    )

    if chat_provider_name == embed_provider_name and chat_url == embed_url:
        # Same backend — build a unified provider
        return _build_single_provider(settings, chat_entry, embed_entry)

    # Different backends — build a composite
    from monocle.ai.composite import CompositeAIProvider

    chat_provider = _build_provider_for_entry(settings, chat_entry)
    embed_provider = _build_provider_for_entry(settings, embed_entry)
    return CompositeAIProvider(chat_provider=chat_provider, embed_provider=embed_provider)
