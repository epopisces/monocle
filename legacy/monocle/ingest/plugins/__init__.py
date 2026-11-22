"""
monocle/ingest/plugins/__init__.py — Plugin package.

Importing this module registers the three built-in plugins with the
``IngestPluginRegistry`` singleton in the correct priority order:

1. AudioPlugin    — matches first when audio_bytes is present
2. TeamsPlugin    — matches requests with source="teams"
3. TextPlugin     — default catch-all for web/mcp/import text
"""
from monocle.ingest.plugin import IngestPluginRegistry
from monocle.ingest.plugins.audio_plugin import AudioPlugin
from monocle.ingest.plugins.teams_plugin import TeamsPlugin
from monocle.ingest.plugins.text_plugin import TextPlugin

__all__ = ["AudioPlugin", "TeamsPlugin", "TextPlugin"]


def register_default_plugins(registry: IngestPluginRegistry | None = None) -> None:
    """Register the three built-in plugins in priority order.

    Idempotent — if a plugin with the same ``source_id`` is already present
    in *registry* it is skipped so calling this multiple times is safe.

    Args:
        registry: Registry instance to populate.  Defaults to the singleton.
    """
    if registry is None:
        registry = IngestPluginRegistry.get()
    existing_ids = {p.source_id for p in registry.plugins}
    for plugin in (AudioPlugin(), TeamsPlugin(), TextPlugin()):
        if plugin.source_id not in existing_ids:
            registry.register(plugin)


# Auto-register on import as documented in the module docstring.
register_default_plugins()
