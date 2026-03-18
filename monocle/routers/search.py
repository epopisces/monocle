"""monocle/routers/search.py — Search endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from monocle.models import ScoredChunk

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    chunk_id: str
    file_path: str
    score: float
    text: str
    metadata: dict = Field(default_factory=dict)


class KeywordResult(BaseModel):
    file_path: str
    title: str
    excerpt: str  # first 200 chars of matching body


@router.get("/search", response_model=list[SearchResult])
async def semantic_search(
    request: Request,
    q: str = Query(..., description="Search query"),
    n: int = Query(10, ge=1, le=100),
    type: str | None = Query(None, description="Filter by note type"),
    domain: str | None = Query(None, description="Filter by domain"),
    source: str | None = Query(None, description="Filter by source"),
) -> list[SearchResult]:
    ai = request.app.state.ai
    index = request.app.state.index

    if ai is None:
        raise HTTPException(status_code=503, detail="AI provider not available")
    if index is None:
        raise HTTPException(status_code=503, detail="Index not available")

    embedding = await ai.embed(q)

    filters: dict = {}
    if type:
        filters["type"] = type
    if domain:
        filters["domain"] = domain
    if source:
        filters["source"] = source

    chunks: list[ScoredChunk] = await asyncio.to_thread(
        index.search,
        query_embedding=embedding,
        n_results=n,
        filters=filters or None,
        query_text=q,
    )

    return [
        SearchResult(
            chunk_id=c.chunk_id,
            file_path=c.file_path,
            score=c.score,
            text=c.text,
            metadata=c.metadata,
        )
        for c in chunks
    ]


@router.get("/search/keyword", response_model=list[KeywordResult])
async def keyword_search(
    request: Request,
    q: str = Query(..., description="Keyword(s) to search for"),
    n: int = Query(20, ge=1, le=200),
    domain: str | None = Query(None),
) -> list[KeywordResult]:
    """Scan vault notes for keyword matches (case-insensitive)."""
    vault = request.app.state.vault

    if not q:
        return []

    q_lower = q.lower()

    def _scan() -> list[KeywordResult]:
        page = vault.list_notes(domain=domain, limit=10000)
        results: list[KeywordResult] = []
        for ref in page.items:
            try:
                note = vault.read_note(ref.file_path)
            except Exception:
                continue
            body_lower = (note.body or "").lower()
            title_lower = note.title.lower()
            if q_lower in body_lower or q_lower in title_lower:
                # Find excerpt around first occurrence
                idx = body_lower.find(q_lower)
                if idx >= 0:
                    start = max(0, idx - 60)
                    excerpt = (note.body or "")[start : start + 200]
                else:
                    excerpt = (note.body or "")[:200]
                results.append(
                    KeywordResult(
                        file_path=ref.file_path,
                        title=note.title,
                        excerpt=excerpt,
                    )
                )
            if len(results) >= n:
                break
        return results

    return await asyncio.to_thread(_scan)
