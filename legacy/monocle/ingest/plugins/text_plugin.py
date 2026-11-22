"""
monocle/ingest/plugins/text_plugin.py — TextPlugin.

Handles plain-text, web, MCP, and import ingests — any request that carries
content directly as a string and does not require audio transcription.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from monocle.ingest.plugin import IngestPlugin

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.models import IngestRequest


class TextPlugin(IngestPlugin):
    """Handle plain-text / web / MCP / import ingests.

    ``can_handle`` returns True for any request that:
    - Has no audio_bytes (not an audio capture), AND
    - Has a source that is neither ``"voice"`` nor ``"teams"``
      (those have dedicated plugins).

    As a defensive fallback the pipeline also uses this plugin when no other
    plugin matches.
    """

    source_id = "web"
    source_label = "Web / Text"

    @classmethod
    def can_handle(cls, request: "IngestRequest") -> bool:
        return request.audio_bytes is None and request.source not in ("voice", "teams")

    async def extract(
        self,
        request: "IngestRequest",
        ai: "AIProvider | None" = None,
    ) -> str:
        """Return the ``content`` field as-is (or empty string if absent)."""
        return request.content or ""
