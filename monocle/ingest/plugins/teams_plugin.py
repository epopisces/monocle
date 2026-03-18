"""
monocle/ingest/plugins/teams_plugin.py — TeamsPlugin.

Handles Microsoft Teams message ingests.  Teams messages arrive via
``POST /api/teams/messages`` (Bot Framework) which assembles an
``IngestRequest`` with ``source="teams"`` and the message body in
``content``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from monocle.ingest.plugin import IngestPlugin

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.models import IngestRequest


class TeamsPlugin(IngestPlugin):
    """Handle Microsoft Teams message ingests.

    Matches requests where ``source == "teams"``.  The Bot Framework router
    already strips HTML and assembles plain text before calling the pipeline,
    so this plugin simply returns ``content`` unchanged.
    """

    source_id = "teams"
    source_label = "Microsoft Teams"

    @classmethod
    def can_handle(cls, request: "IngestRequest") -> bool:
        return request.source == "teams"

    async def extract(
        self,
        request: "IngestRequest",
        ai: "AIProvider | None" = None,
    ) -> str:
        """Return the Teams message body as-is."""
        return request.content or ""
