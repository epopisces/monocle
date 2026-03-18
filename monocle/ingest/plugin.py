"""
monocle/ingest/plugin.py — IngestPlugin ABC and IngestPluginRegistry singleton.

Every content-source type is handled by a concrete IngestPlugin subclass that
reports what requests it can handle and extracts plain text from them.

The IngestPluginRegistry singleton holds the ordered list of registered plugins
and resolves the correct plugin for each incoming IngestRequest.  Plugins are
tested in registration order; the first match wins.

Usage::

    from monocle.ingest.plugin import IngestPluginRegistry

    registry = IngestPluginRegistry.get()
    plugin = registry.resolve(request)
    text = await plugin.extract(request, ai=provider)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.models import IngestRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class IngestPlugin(ABC):
    """Abstract base class for all ingest source plugins.

    Class variables
    ---------------
    source_id:    Short machine identifier for the source type (e.g. ``"web"``).
    source_label: Human-readable name for this plugin (e.g. ``"Web / Text"``).
    """

    source_id: ClassVar[str]
    source_label: ClassVar[str]

    @classmethod
    @abstractmethod
    def can_handle(cls, request: "IngestRequest") -> bool:
        """Return True if this plugin should handle *request*.

        Plugins are tested in registration order; first match wins.
        """

    @abstractmethod
    async def extract(
        self,
        request: "IngestRequest",
        ai: "AIProvider | None" = None,
    ) -> str:
        """Extract plain-text content from *request*.

        Args:
            request: The raw ingest request.
            ai:      AIProvider instance (required for audio transcription).

        Returns:
            Plain-text content ready for the routing and extraction steps.
        """


# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------


class IngestPluginRegistry:
    """Singleton registry that holds the ordered list of ingest plugins.

    Use :meth:`get` to obtain the shared instance.

    Example::

        registry = IngestPluginRegistry.get()
        registry.register(MyPlugin())
        plugin = registry.resolve(request)
    """

    _instance: "IngestPluginRegistry | None" = None

    def __init__(self) -> None:
        self._plugins: list[IngestPlugin] = []

    @classmethod
    def get(cls) -> "IngestPluginRegistry":
        """Return the shared singleton instance, creating it if needed."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (used in tests to get a clean registry)."""
        cls._instance = None

    def register(self, plugin: IngestPlugin) -> None:
        """Append *plugin* to the ordered registry.

        Plugins are evaluated in the order they are registered.
        """
        logger.debug(
            "IngestPluginRegistry: registered %s (source_id=%s)",
            type(plugin).__name__,
            getattr(plugin, "source_id", "?"),
        )
        self._plugins.append(plugin)

    def resolve(self, request: "IngestRequest") -> IngestPlugin:
        """Return the first plugin whose :meth:`can_handle` returns True.

        Falls back to :class:`~monocle.ingest.plugins.text_plugin.TextPlugin`
        if no registered plugin matches.

        Raises:
            RuntimeError: If no plugins are registered *and* the default
                TextPlugin cannot be imported.
        """
        for plugin in self._plugins:
            if plugin.can_handle(request):
                logger.debug(
                    "IngestPluginRegistry: resolved %s for source=%s",
                    type(plugin).__name__,
                    request.source,
                )
                return plugin

        # Default fallback — always import fresh so registry.reset() in tests works
        from monocle.ingest.plugins.text_plugin import TextPlugin

        logger.debug(
            "IngestPluginRegistry: no plugin matched, falling back to TextPlugin"
        )
        return TextPlugin()

    @property
    def plugins(self) -> list[IngestPlugin]:
        """Ordered copy of the currently registered plugins."""
        return list(self._plugins)
