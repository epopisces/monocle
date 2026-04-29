"""Consolidated ingest workflow ownership for prepare, review, and execution."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from monocle.models import (
    DiffPreview,
    DiffPreviewHunk,
    IngestExecutionSummary,
    IngestExecutionValidation,
    IngestSessionDetailResponse,
    ProposedAction,
)

if TYPE_CHECKING:
    from monocle.services.ingest_prepare import IngestPreparationWorker
    from monocle.services.ingest_sessions import IngestSessionStore
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _excerpt(text: str | None, limit: int = 240) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if not compact:
        return None
    return compact[:limit].strip()


def _has_unanswered_questions(questions: list[dict[str, Any]]) -> bool:
    return any(not str(item.get("answer") or "").strip() for item in questions)


def _all_actions_resolved(actions: list[ProposedAction]) -> bool:
    return bool(actions) and all(item.approval_state in {"approved", "rejected"} for item in actions)


def _resolved_actions_state(actions: list[ProposedAction]) -> str:
    return "approved_pending_execution" if any(item.approval_state == "approved" for item in actions) else "proposal_ready"


async def load_session_detail(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None
    return await _hydrate_detail(vault, detail)


async def start_review_session(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None
    if detail.session.state in {"dormant_ready", "awaiting_user", "proposal_ready"}:
        await asyncio.to_thread(store.set_session_state, session_id, "in_review")
    return await load_session_detail(store, vault, session_id)


async def answer_review_question(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
    question_id: str,
    answer: str,
) -> IngestSessionDetailResponse | None:
    questions = await asyncio.to_thread(store.answer_open_question, session_id, question_id, answer)
    if questions is None:
        return None
    await _sync_state_after_question_answer(store, session_id)
    return await load_session_detail(store, vault, session_id)


async def update_review_action(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
    action_id: str,
    *,
    approval_state: str | None = None,
    target_file_path: str | None = None,
    target_note_type: str | None = None,
    rationale: str | None = None,
    proposed_content: dict[str, Any] | None = None,
) -> IngestSessionDetailResponse | None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None

    current = next((item for item in detail.session.proposed_actions if item.action_id == action_id), None)
    if current is None:
        return None

    next_content = dict(current.proposed_content)
    if proposed_content:
        next_content.update(proposed_content)

    next_target_file_path = (
        _normalise_target_file_path(vault, target_file_path)
        if target_file_path is not None
        else current.target_file_path
    )
    next_target_note_type = target_note_type if target_note_type is not None else current.target_note_type
    next_rationale = rationale if rationale is not None else current.rationale

    preview = await _build_diff_preview(
        vault,
        current.model_copy(
            update={
                "approval_state": approval_state or current.approval_state,
                "target_file_path": next_target_file_path,
                "target_note_type": next_target_note_type,
                "rationale": next_rationale,
                "proposed_content": next_content,
            }
        ),
    )
    updated = await asyncio.to_thread(
        store.update_proposed_action,
        session_id,
        action_id,
        approval_state=approval_state,
        target_file_path=next_target_file_path if target_file_path is not None else None,
        target_note_type=target_note_type,
        rationale=rationale,
        diff_preview=preview.model_dump(mode="json") if preview is not None else None,
        proposed_content=next_content if proposed_content is not None else None,
    )
    if updated is None:
        return None

    await _sync_review_state(store, session_id)
    return await load_session_detail(store, vault, session_id)


async def set_review_action_approval(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
    action_id: str,
    approval_state: str,
) -> IngestSessionDetailResponse | None:
    updated = await asyncio.to_thread(
        store.set_proposed_action_approval_state,
        session_id,
        action_id,
        approval_state,
    )
    if updated is None:
        return None

    await _sync_review_state(store, session_id)
    return await load_session_detail(store, vault, session_id)


async def approve_all_review_actions(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None
    await asyncio.to_thread(store.approve_all_proposed_actions, session_id)
    await _sync_review_state(store, session_id)
    return await load_session_detail(store, vault, session_id)


async def sync_review_state(
    store: "IngestSessionStore",
    session_id: str,
) -> None:
    await _sync_review_state(store, session_id)


async def execute_review_session(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    from monocle import mcp_server

    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None

    if detail.session.state != "approved_pending_execution":
        raise ValueError("Only sessions in approved_pending_execution can be executed.")

    approved_actions = [action for action in detail.session.proposed_actions if action.approval_state == "approved"]
    if not approved_actions:
        raise ValueError("This ingest session has no approved actions to execute.")

    await asyncio.to_thread(store.set_session_state, session_id, "executing")
    detail = await load_session_detail(store, vault, session_id)
    if detail is None:
        return None

    source_links = _build_source_links(detail)
    request_source = _session_request_source(detail)
    expected_source_ids = {str(item["source_id"]) for item in source_links}
    touched_paths: list[str] = []
    succeeded = 0
    failed = 0
    skipped = 0

    for action in detail.session.proposed_actions:
        if action.approval_state != "approved":
            skipped += 1
            await asyncio.to_thread(
                store.update_proposed_action,
                session_id,
                action.action_id,
                execution_result={
                    "status": "skipped",
                    "message": "Action was not approved for execution.",
                },
            )
            continue

        file_path: str | None = action.target_file_path
        previous_note: Any | None = None
        try:
            expected_body = str(action.proposed_content.get("body") or "")
            if action.action_type == "create_note":
                expected_title = _default_title(detail, action)
                created = json.loads(
                    await mcp_server.create_note(
                        title=expected_title,
                        body=expected_body,
                        note_type=action.target_note_type or "observation",
                        metadata_updates={
                            "sources": source_links,
                            **({"source": request_source} if request_source else {}),
                        },
                    )
                )
                file_path = str(created["file_path"])
            else:
                if not action.target_file_path:
                    raise ValueError("Approved update action is missing target_file_path.")
                existing_note = await asyncio.to_thread(vault.read_note, action.target_file_path)
                previous_note = existing_note.model_copy(deep=True)
                expected_title = str(action.proposed_content.get("title") or existing_note.title)
                file_path = action.target_file_path
                await mcp_server.update_note(
                    file_path=file_path,
                    body=expected_body,
                    title=expected_title,
                    metadata_updates={"sources": _merge_source_links(existing_note, source_links)},
                )

            actual_note = await asyncio.to_thread(vault.read_note, file_path)
            validation = _build_validation(actual_note, expected_title, expected_body, expected_source_ids)
            if not (validation.title_match and validation.body_match and validation.sources_attached):
                raise ValueError("Post-apply validation failed for the written note.")

            succeeded += 1
            touched_paths.append(file_path)
            await asyncio.to_thread(
                store.update_proposed_action,
                session_id,
                action.action_id,
                approval_state="executed",
                target_file_path=file_path,
                execution_result={
                    "status": "succeeded",
                    "file_path": file_path,
                    "executed_at": actual_note.metadata.updated.isoformat() if actual_note.metadata.updated else None,
                    "validation": validation.model_dump(mode="json"),
                },
            )
        except Exception as exc:
            failed += 1
            rollback_message: str | None = None
            try:
                await _rollback_write(
                    vault,
                    reindex_queue,
                    action_type=action.action_type,
                    file_path=file_path,
                    previous_note=previous_note,
                )
            except Exception as rollback_exc:
                rollback_message = f" Rollback failed: {rollback_exc}"
            await asyncio.to_thread(
                store.update_proposed_action,
                session_id,
                action.action_id,
                approval_state="failed",
                execution_result={
                    "status": "failed",
                    "message": f"{exc}{rollback_message or ''}",
                },
            )

    if reindex_queue is not None:
        for file_path in dict.fromkeys(touched_paths):
            reindex_queue.push(file_path)

    summary = IngestExecutionSummary(
        total_actions=len(detail.session.proposed_actions),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        affected_file_paths=list(dict.fromkeys(touched_paths)),
        completed_at=_utcnow_iso(),
    )
    await asyncio.to_thread(
        store.set_session_execution_summary,
        session_id,
        summary.model_dump(mode="json"),
        state="failed" if failed else "completed",
    )
    return await load_session_detail(store, vault, session_id)


async def execute_fast_capture_session(
    store: "IngestSessionStore",
    prepare_worker: "IngestPreparationWorker",
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    detail = await prepare_worker.prepare_session_now(session_id)
    if detail is None:
        return None

    if detail.session.state in {"failed", "completed", "executing"}:
        return detail

    if detail.session.state == "preparing":
        return detail

    if detail.session.open_questions or detail.session.contradictions or not detail.session.proposed_actions:
        await sync_review_state(store, session_id)
        return await load_session_detail(store, vault, session_id)

    detail = await approve_all_review_actions(store, vault, session_id)
    if detail is None:
        return None

    detail = await execute_review_session(store, vault, reindex_queue, session_id)
    if detail is None:
        return None

    if detail.session.state == "completed":
        await asyncio.to_thread(store.set_session_notification_status, session_id, "ingest_ready", "dismissed")
        return await load_session_detail(store, vault, session_id)

    if detail.session.state == "failed":
        await asyncio.to_thread(store.set_session_state, session_id, "proposal_ready")
        return await load_session_detail(store, vault, session_id)

    return detail


async def _hydrate_detail(
    vault: "VaultLayer",
    detail: IngestSessionDetailResponse,
) -> IngestSessionDetailResponse:
    contradictions: list[dict[str, Any]] = []
    for item in detail.session.contradictions:
        enriched = dict(item)
        file_path = item.get("file_path")
        if isinstance(file_path, str) and file_path:
            try:
                note = await asyncio.to_thread(vault.read_note, file_path)
            except Exception:
                note = None
            if note is not None:
                enriched.setdefault("title", note.title)
                enriched.setdefault("excerpt", _excerpt(note.body, 200))
        contradictions.append(enriched)

    actions: list[ProposedAction] = []
    for action in detail.session.proposed_actions:
        preview = await _build_diff_preview(vault, action)
        actions.append(action.model_copy(update={"diff_preview": preview or action.diff_preview}))

    detail.session.contradictions = contradictions
    detail.session.proposed_actions = actions
    return detail


def _normalise_target_file_path(
    vault: "VaultLayer",
    target_file_path: str,
) -> str | None:
    candidate = target_file_path.strip()
    if not candidate:
        return None
    resolved = vault._safe_resolve(candidate)
    return vault._to_relative(resolved)


async def _build_diff_preview(vault: "VaultLayer", action: ProposedAction) -> DiffPreview | None:
    has_proposed_title = "title" in action.proposed_content
    has_proposed_body = "body" in action.proposed_content
    proposed_title = str(action.proposed_content.get("title") or "") if has_proposed_title else ""
    proposed_body = str(action.proposed_content.get("body") or "") if has_proposed_body else ""

    if action.action_type == "create_note":
        hunks: list[DiffPreviewHunk] = []
        if proposed_title:
            hunks.append(DiffPreviewHunk(section="title", before=None, after=proposed_title))
        if proposed_body:
            hunks.append(
                DiffPreviewHunk(
                    section="body",
                    before=None,
                    after=_excerpt(proposed_body, 500),
                )
            )
        return DiffPreview(
            kind="create",
            before_excerpt=None,
            after_excerpt=_excerpt(proposed_body or proposed_title),
            hunks=hunks,
        )

    note = None
    if action.target_file_path:
        try:
            note = await asyncio.to_thread(vault.read_note, action.target_file_path)
        except Exception:
            note = None

    before_title = note.title if note is not None else None
    before_body = note.body if note is not None else None
    after_title = proposed_title if has_proposed_title else before_title
    after_body = proposed_body if has_proposed_body else before_body

    hunks: list[DiffPreviewHunk] = []
    if before_title != after_title:
        hunks.append(DiffPreviewHunk(section="title", before=before_title, after=after_title))
    if before_body != after_body:
        hunks.append(
            DiffPreviewHunk(
                section="body",
                before=_excerpt(before_body, 500),
                after=_excerpt(after_body, 500),
            )
        )

    return DiffPreview(
        kind="update",
        before_excerpt=_excerpt(before_body),
        after_excerpt=_excerpt(after_body),
        hunks=hunks,
    )


async def _sync_state_after_question_answer(store: "IngestSessionStore", session_id: str) -> None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return

    questions = detail.session.open_questions
    actions = detail.session.proposed_actions

    if _has_unanswered_questions(questions):
        next_state = "awaiting_user"
    elif _all_actions_resolved(actions):
        next_state = _resolved_actions_state(actions)
    else:
        next_state = "proposal_ready"

    await asyncio.to_thread(store.set_session_state, session_id, next_state)


async def _sync_review_state(store: "IngestSessionStore", session_id: str) -> None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return

    questions = detail.session.open_questions
    actions = detail.session.proposed_actions

    if _has_unanswered_questions(questions):
        next_state = "awaiting_user"
    elif _all_actions_resolved(actions):
        next_state = _resolved_actions_state(actions)
    else:
        next_state = "in_review"

    await asyncio.to_thread(store.set_session_state, session_id, next_state)


def _build_source_links(detail: IngestSessionDetailResponse) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for source in detail.sources:
        author = source.provenance.get("author") if isinstance(source.provenance, dict) else None
        links.append(
            {
                "source_id": source.source_id,
                "session_id": source.session_id,
                "source_name": source.source_name,
                "archive_path": source.archive_path,
                "kind": source.kind,
                "mime_type": source.mime_type,
                "captured_at": source.captured_at,
                "author": author,
            }
        )
    return links


def _session_request_source(detail: IngestSessionDetailResponse) -> str | None:
    for source in detail.sources:
        if isinstance(source.provenance, dict):
            request_source = source.provenance.get("request_source")
            if isinstance(request_source, str) and request_source:
                return request_source
    return None


def _merge_source_links(note: Any, new_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_links: list[dict[str, Any]] = []
    for item in getattr(note.metadata, "sources", []) or []:
        if hasattr(item, "model_dump"):
            existing_links.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            existing_links.append(dict(item))

    merged: dict[str, dict[str, Any]] = {}
    for item in existing_links + new_links:
        source_id = str(item.get("source_id") or "")
        if source_id:
            merged[source_id] = item
    return list(merged.values())


def _default_title(detail: IngestSessionDetailResponse, action: ProposedAction) -> str:
    proposed_title = str(action.proposed_content.get("title") or "").strip()
    if proposed_title:
        return proposed_title
    if action.target_file_path:
        return Path(action.target_file_path).stem.replace("-", " ").strip().title() or "Captured Note"
    if detail.session.title:
        return detail.session.title
    if detail.sources:
        return Path(detail.sources[0].source_name).stem.replace("-", " ").strip().title() or "Captured Note"
    return "Captured Note"


def _build_validation(
    actual_note: Any,
    expected_title: str | None,
    expected_body: str,
    expected_source_ids: set[str],
) -> IngestExecutionValidation:
    actual_source_ids = {
        str(item.source_id)
        for item in getattr(actual_note.metadata, "sources", []) or []
        if getattr(item, "source_id", None)
    }
    return IngestExecutionValidation(
        title_match=(expected_title is None or actual_note.title == expected_title),
        body_match=actual_note.body == expected_body,
        sources_attached=expected_source_ids.issubset(actual_source_ids),
    )


async def _rollback_write(
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    *,
    action_type: str,
    file_path: str | None,
    previous_note: Any | None,
) -> None:
    if not file_path:
        return

    if action_type == "create_note":
        try:
            await asyncio.to_thread(vault.delete_note, file_path)
        except Exception:
            pass
    elif previous_note is not None:
        await asyncio.to_thread(vault.write_note, file_path, previous_note)

    if reindex_queue is not None:
        reindex_queue.push(file_path)


__all__ = [
    "answer_review_question",
    "approve_all_review_actions",
    "execute_fast_capture_session",
    "execute_review_session",
    "load_session_detail",
    "set_review_action_approval",
    "start_review_session",
    "sync_review_state",
    "update_review_action",
]