"""monocle/services/ingest.py — Canonical capture_thought services."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.models import IngestResponse, IngestSessionDetailResponse
    from monocle.ingest import IngestPipeline
    from monocle.models import IngestConfidence, Note
    from monocle.services.ingest_prepare import IngestPreparationWorker
    from monocle.services.ingest_sessions import IngestSessionStore
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

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


async def capture_thought_session(
    store: "IngestSessionStore",
    prepare_worker: "IngestPreparationWorker | None",
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    content: str,
    source: str = "mcp",
) -> tuple["IngestResponse", "IngestSessionDetailResponse | None"]:
    """Capture raw text through the persisted ingest-session fast-capture flow."""
    if len(content) > _MAX_BODY_LENGTH:
        raise ValueError(f"content exceeds {_MAX_BODY_LENGTH:,} character limit")

    from monocle.models import IngestRequest
    from monocle.services.ingest_execute import execute_fast_capture_session

    req = IngestRequest(content=content, source=source, fast_capture=True)  # type: ignore[arg-type]
    response = await asyncio.to_thread(store.create_api_session, req)
    if prepare_worker is None:
        return response, None

    detail = await execute_fast_capture_session(
        store,
        prepare_worker,
        vault,
        reindex_queue,
        response.session_id,
    )
    return response, detail
