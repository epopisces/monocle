"""
monocle/ingest/plugins/audio_plugin.py — AudioPlugin.

Handles voice/audio ingests by delegating transcription to ``AIProvider``.
This plugin matches requests that include raw audio bytes, regardless of the
``source`` field value.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from monocle.ingest.plugin import IngestPlugin

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.models import IngestRequest

logger = logging.getLogger(__name__)


class AudioPlugin(IngestPlugin):
    """Handle audio/voice ingests via ``AIProvider.transcribe``.

    Matches any request whose ``audio_bytes`` field is non-None.  The
    ``source`` is expected to be ``"voice"`` but is not enforced here so
    that MCP/Teams can also capture audio if needed.
    """

    source_id = "voice"
    source_label = "Audio / Voice"

    @classmethod
    def can_handle(cls, request: "IngestRequest") -> bool:
        return request.audio_bytes is not None

    async def extract(
        self,
        request: "IngestRequest",
        ai: "AIProvider | None" = None,
    ) -> str:
        """Transcribe ``request.audio_bytes`` to plain text.

        Raises:
            RuntimeError: If no AIProvider is supplied (transcription requires
                          a configured transcription back-end).
        """
        if ai is None:
            raise RuntimeError(
                "AudioPlugin.extract() requires an AIProvider for transcription. "
                "Pass ai=provider when calling IngestPipeline.run()."
            )
        mime_type = request.audio_mime_type or "audio/webm"
        logger.debug("AudioPlugin: transcribing %d bytes (%s)", len(request.audio_bytes), mime_type)
        text = await ai.transcribe(request.audio_bytes, mime_type)
        logger.info("[INGEST] Audio transcription produced %d characters", len(text))
        return text
