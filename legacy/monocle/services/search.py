"""monocle/services/search.py — Canonical search_vault service."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.index.base import IndexLayer
    from monocle.models import ScoredChunk

logger = logging.getLogger(__name__)

_MAX_SEARCH_RESULTS = 10


async def search_vault(
    index: "IndexLayer",
    ai: "AIProvider | None",
    query: str,
    n_results: int = 5,
    note_type: str | None = None,
    domain: str | None = None,
) -> list["ScoredChunk"]:
    """Semantic search across the vault using embeddings.

    Args:
        index: The index layer to search.
        ai: AI provider for computing the query embedding.
        query: Natural-language search query.
        n_results: Maximum results to return (capped at 10).
        note_type: Optional ChromaDB ``type`` metadata filter.
        domain: Optional ChromaDB ``domain`` metadata filter.

    Returns:
        List of ``ScoredChunk`` objects ordered by similarity (descending).

    Falls back to substring search when *ai* is ``None`` and the backend is
    ``MemoryIndex``. Production backends still require embeddings.
    """
    from monocle.index.memory import MemoryIndex

    n = max(1, min(n_results, _MAX_SEARCH_RESULTS))
    filters: dict[str, str] = {}
    if note_type:
        filters["type"] = note_type
    if domain:
        filters["domain"] = domain

    if ai is None:
        if not isinstance(index, MemoryIndex):
            raise RuntimeError(
                "Semantic search requires an AI provider. Configure ai.provider in config.yaml."
            )
        return await asyncio.to_thread(index.search, [], n, filters or None, query)

    embedding = await ai.embed(query)
    scored = await asyncio.to_thread(
        index.search,
        embedding,
        n,
        filters or None,
        query,
    )
    return scored
