"""monocle/routers/stats.py — Brain stats endpoint."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request

from monocle.models import BrainStats, IndexStats

router = APIRouter(tags=["stats"])
logger = logging.getLogger(__name__)


@router.get("/stats", response_model=BrainStats)
async def get_stats(request: Request) -> BrainStats:
    """Return aggregate vault and index statistics."""
    vault = getattr(request.app.state, "vault", None)
    index = getattr(request.app.state, "index", None)
    failed_registry = getattr(request.app.state, "failed_registry", None)

    # -- Index stats --
    index_stats = IndexStats()
    if index is not None:
        try:
            index_stats = await asyncio.to_thread(index.get_stats)
        except Exception as exc:
            logger.warning("Could not fetch index stats: %s", exc)

    # -- Vault note counts --
    total_notes = 0
    notes_by_type: dict[str, int] = {}
    notes_by_domain: dict[str, int] = {}
    pending_review = 0

    if vault is not None:
        def _count_notes() -> tuple[int, dict, dict, int]:
            page = vault.list_notes(limit=100_000)
            _total = page.total
            _by_type: dict[str, int] = {}
            _by_domain: dict[str, int] = {}
            _pending = 0
            for ref in page.items:
                _by_type[ref.type] = _by_type.get(ref.type, 0) + 1
                _by_domain[ref.domain] = _by_domain.get(ref.domain, 0) + 1
                if ref.review_status == "pending":
                    _pending += 1
            return _total, _by_type, _by_domain, _pending

        try:
            total_notes, notes_by_type, notes_by_domain, pending_review = await asyncio.to_thread(
                _count_notes
            )
        except Exception as exc:
            logger.warning("Could not count vault notes: %s", exc)

    # -- Failed ingests --
    failed_ingests = 0
    if failed_registry is not None:
        try:
            failed_ingests = failed_registry.count_failed()
        except Exception as exc:
            logger.warning("Could not count failed ingests: %s", exc)

    return BrainStats(
        total_notes=total_notes,
        total_chunks=index_stats.total_chunks,
        notes_by_type=notes_by_type,
        notes_by_domain=notes_by_domain,
        pending_review=pending_review,
        failed_ingests=failed_ingests,
        index=index_stats,
        # Latency percentiles from OTel histogram snapshots — not yet
        # implemented (requires in-process MetricReader readback).
        latency_p50_ms={},
        latency_p95_ms={},
    )
