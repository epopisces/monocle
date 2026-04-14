"""monocle/services/ingest.py — Canonical capture_thought service."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.ingest import IngestPipeline
    from monocle.models import IngestConfidence, Note

logger = logging.getLogger(__name__)

_MAX_BODY_LENGTH = 50_000


async def capture_thought(
    pipeline: "IngestPipeline",
    content: str,
    source: str = "mcp",
) -> tuple["Note", "IngestConfidence | None"]:
    """Ingest raw text through the full 8-step pipeline.

    Routing, metadata extraction, note construction, file write, reindex, and
    confidence scoring are all handled by the pipeline.

    Args:
        pipeline: The ``IngestPipeline`` instance.
        content: Raw text content to ingest (max 50,000 characters).
        source: Source identifier, e.g. ``"mcp"``, ``"web"``, ``"voice"``.

    Returns:
        Tuple of ``(note, confidence)`` — confidence may be ``None`` on failure.

    Raises:
        ValueError: If *content* exceeds the character limit.
    """
    if len(content) > _MAX_BODY_LENGTH:
        raise ValueError(f"content exceeds {_MAX_BODY_LENGTH:,} character limit")

    from monocle.models import IngestRequest

    req = IngestRequest(content=content, source=source)  # type: ignore[arg-type]
    return await pipeline.run(req)
