"""Aggregated backend contract for the unified capture workbench."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from monocle.models import (
    CaptureWorkbenchCounts,
    CaptureWorkbenchItem,
    CaptureWorkbenchResponse,
    CaptureWorkbenchSection,
    FailedIngestRecord,
    IngestSession,
    NoteRef,
)

if TYPE_CHECKING:
    from monocle.config import Settings
    from monocle.ingest.failed_registry import FailedIngestRegistry
    from monocle.services.ingest_sessions import IngestSessionStore
    from monocle.vault import VaultLayer


async def list_pending_review_notes(
    vault: "VaultLayer",
    *,
    threshold: float | None,
    limit: int,
    offset: int,
) -> tuple[list[NoteRef], int]:
    pending = await _get_all_pending_notes(vault, threshold=threshold)
    total = len(pending)
    return pending[offset : offset + limit], total


def list_failed_ingest_records(
    registry: "FailedIngestRegistry",
    *,
    actionable_only: bool,
) -> list[FailedIngestRecord]:
    records: list[FailedIngestRecord] = []
    for raw in registry.get_all():
        status = str(raw.get("status") or "failed")
        if actionable_only and status != "failed":
            continue
        preview = str(raw.get("content_preview") or "")
        step = raw.get("step")
        records.append(
            FailedIngestRecord(
                id=str(raw.get("id") or ""),
                source=str(raw.get("source") or "web"),
                content_preview=preview,
                content_truncated=len(preview) >= 200,
                error_message=str(raw.get("error_message") or "Unknown ingest failure"),
                failed_at=str(raw.get("timestamp") or ""),
                sidecar_path=(str(raw.get("sidecar_path")) if raw.get("sidecar_path") is not None else None),
                step=int(step) if isinstance(step, int) or (isinstance(step, str) and step.isdigit()) else None,
                retried=status == "retried",
            )
        )
    return records


async def build_capture_workbench_response(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    failed_registry: "FailedIngestRegistry",
    settings: "Settings",
    *,
    limit_per_section: int,
) -> CaptureWorkbenchResponse:
    queue_threshold = settings.review.queue_threshold
    prepared_task = asyncio.to_thread(store.list_sessions, ready_only=True, limit=limit_per_section, offset=0)
    prepared_count_task = asyncio.to_thread(store.count_sessions, ready_only=True)
    failed_sessions_task = asyncio.to_thread(
        store.list_sessions,
        state="failed",
        sort_by="updated_at",
        limit=limit_per_section,
        offset=0,
    )
    failed_session_count_task = asyncio.to_thread(store.count_sessions, state="failed")
    pending_task = list_pending_review_notes(
        vault,
        threshold=queue_threshold,
        limit=limit_per_section,
        offset=0,
    )

    prepared_sessions, prepared_count, failed_sessions, failed_session_count, pending_result = await asyncio.gather(
        prepared_task,
        prepared_count_task,
        failed_sessions_task,
        failed_session_count_task,
        pending_task,
    )
    pending_notes, pending_count = pending_result

    failed_ingests = list_failed_ingest_records(failed_registry, actionable_only=True)
    failure_items = _build_failure_items(
        failed_ingests[:limit_per_section],
        failed_sessions[:limit_per_section],
        limit_per_section=limit_per_section,
    )

    counts = CaptureWorkbenchCounts(
        prepared=prepared_count,
        pending_review=pending_count,
        failures=failed_session_count + len(failed_ingests),
    )
    return CaptureWorkbenchResponse(
        actionable_count=counts.prepared + counts.pending_review + counts.failures,
        queue_threshold=queue_threshold,
        counts=counts,
        sections=[
            CaptureWorkbenchSection(
                section="prepared",
                count=prepared_count,
                items=[_prepared_session_to_item(session) for session in prepared_sessions],
            ),
            CaptureWorkbenchSection(
                section="pending_review",
                count=pending_count,
                items=[_pending_note_to_item(note) for note in pending_notes],
            ),
            CaptureWorkbenchSection(
                section="failures",
                count=counts.failures,
                items=failure_items,
            ),
        ],
    )


async def _get_all_pending_notes(
    vault: "VaultLayer",
    *,
    threshold: float | None,
) -> list[NoteRef]:
    # Fetch all notes in a single call to avoid repeated full vault scans.
    # Use a large limit (100k) to practically cover all personal vaults in one scan.
    # list_notes() returns page.total, so we can detect if we need a second call
    # (unlikely for typical vault sizes).
    page = await asyncio.to_thread(vault.list_notes, limit=100000, offset=0)

    # Filter for pending notes matching the threshold, in-memory.
    pending: list[NoteRef] = []
    for ref in page.items:
        if ref.review_status != "pending":
            continue
        if threshold is not None and ref.confidence > threshold:
            continue
        pending.append(ref)

    pending.sort(key=_pending_note_sort_key)
    return pending


def _pending_note_sort_key(ref: NoteRef) -> tuple[float, float, str]:
    return (ref.confidence, -_note_timestamp(ref), ref.file_path)


def _note_timestamp(ref: NoteRef) -> float:
    dt = ref.updated or ref.created
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _pending_note_to_item(ref: NoteRef) -> CaptureWorkbenchItem:
    return CaptureWorkbenchItem(
        item_id=ref.file_path,
        section="pending_review",
        item_type="pending_note",
        title=ref.title,
        summary=ref.file_path,
        confidence=ref.confidence,
        file_path=ref.file_path,
        note_type=ref.type,
        created_at=ref.created.isoformat() if ref.created else None,
        updated_at=ref.updated.isoformat() if ref.updated else None,
    )


def _prepared_session_to_item(session: IngestSession) -> CaptureWorkbenchItem:
    return CaptureWorkbenchItem(
        item_id=session.session_id,
        section="prepared",
        item_type="ingest_session",
        title=_session_title(session),
        summary=session.digest,
        source=session.origin,
        state=session.state,
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        open_questions_count=len(session.open_questions),
        contradictions_count=len(session.contradictions),
        proposed_actions_count=len(session.proposed_actions),
    )


def _failed_session_to_item(session: IngestSession) -> CaptureWorkbenchItem:
    return CaptureWorkbenchItem(
        item_id=session.session_id,
        section="failures",
        item_type="failed_session",
        title=_session_title(session),
        summary=session.digest or "Ingest session failed during preparation.",
        source=session.origin,
        state=session.state,
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        open_questions_count=len(session.open_questions),
        contradictions_count=len(session.contradictions),
        proposed_actions_count=len(session.proposed_actions),
    )


def _failed_ingest_to_item(record: FailedIngestRecord) -> CaptureWorkbenchItem:
    return CaptureWorkbenchItem(
        item_id=record.id,
        section="failures",
        item_type="failed_ingest",
        title=f"Failed {record.source} capture",
        summary=record.content_preview,
        source=record.source,
        failure_id=record.id,
        created_at=record.failed_at,
        updated_at=record.failed_at,
        error_message=record.error_message,
        retryable=not record.retried,
    )


def _build_failure_items(
    failed_ingests: list[FailedIngestRecord],
    failed_sessions: list[IngestSession],
    *,
    limit_per_section: int,
) -> list[CaptureWorkbenchItem]:
    items = [
        *(_failed_ingest_to_item(record) for record in failed_ingests),
        *(_failed_session_to_item(session) for session in failed_sessions),
    ]
    items.sort(key=_failure_item_sort_key, reverse=True)
    return items[:limit_per_section]


def _failure_item_sort_key(item: CaptureWorkbenchItem) -> tuple[float, str]:
    return (_workbench_timestamp(item.updated_at or item.created_at), item.item_id)


def _workbench_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _session_title(session: IngestSession) -> str:
    if session.title:
        return session.title
    return session.session_id


__all__ = [
    "build_capture_workbench_response",
    "list_failed_ingest_records",
    "list_pending_review_notes",
]