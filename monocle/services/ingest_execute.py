"""Execution of approved ingest proposals through the canonical MCP tool plane."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from monocle.models import IngestExecutionSummary, IngestExecutionValidation, IngestSessionDetailResponse, ProposedAction

if TYPE_CHECKING:
    from monocle.services.ingest_prepare import IngestPreparationWorker
    from monocle.services.ingest_sessions import IngestSessionStore
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _build_validation(actual_note: Any, expected_title: str | None, expected_body: str, expected_source_ids: set[str]) -> IngestExecutionValidation:
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


async def execute_review_session(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    from monocle import mcp_server
    from monocle.services.ingest_review import load_review_session

    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None

    if detail.session.state != "approved_pending_execution":
        raise ValueError("Only sessions in approved_pending_execution can be executed.")

    approved_actions = [action for action in detail.session.proposed_actions if action.approval_state == "approved"]
    if not approved_actions:
        raise ValueError("This ingest session has no approved actions to execute.")

    await asyncio.to_thread(store.set_session_state, session_id, "executing")
    detail = await load_review_session(store, vault, session_id)
    if detail is None:
        return None

    source_links = _build_source_links(detail)
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
                        metadata_updates={"sources": source_links},
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
    return await load_review_session(store, vault, session_id)


async def execute_fast_capture_session(
    store: "IngestSessionStore",
    prepare_worker: "IngestPreparationWorker",
    vault: "VaultLayer",
    reindex_queue: "ReindexQueue | None",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    from monocle.services.ingest_review import approve_all_review_actions, load_review_session, sync_review_state

    detail = await prepare_worker.prepare_session_now(session_id)
    if detail is None:
        return None

    if detail.session.state in {"failed", "completed", "executing"}:
        return detail

    if detail.session.state == "preparing":
        return detail

    if detail.session.open_questions or detail.session.contradictions or not detail.session.proposed_actions:
        await sync_review_state(store, session_id)
        return await load_review_session(store, vault, session_id)

    detail = await approve_all_review_actions(store, vault, session_id)
    if detail is None:
        return None

    detail = await execute_review_session(store, vault, reindex_queue, session_id)
    if detail is None:
        return None

    if detail.session.state == "completed":
        await asyncio.to_thread(store.set_session_notification_status, session_id, "ingest_ready", "dismissed")
        return await load_review_session(store, vault, session_id)

    if detail.session.state == "failed":
        await asyncio.to_thread(store.set_session_state, session_id, "proposal_ready")
        return await load_review_session(store, vault, session_id)

    return detail
