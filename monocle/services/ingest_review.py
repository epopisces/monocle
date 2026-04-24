"""Ingest review orchestration for M36."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from monocle.models import DiffPreview, DiffPreviewHunk, IngestSessionDetailResponse, ProposedAction

if TYPE_CHECKING:
    from monocle.services.ingest_sessions import IngestSessionStore
    from monocle.vault import VaultLayer


def _excerpt(text: str | None, limit: int = 240) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if not compact:
        return None
    return compact[:limit].strip()


async def load_review_session(
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
    return await load_review_session(store, vault, session_id)


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
    return await load_review_session(store, vault, session_id)


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
    return await load_review_session(store, vault, session_id)


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
    return await load_review_session(store, vault, session_id)


async def approve_all_review_actions(
    store: "IngestSessionStore",
    vault: "VaultLayer",
    session_id: str,
) -> IngestSessionDetailResponse | None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return None
    await asyncio.to_thread(store.approve_all_proposed_actions, session_id)
    return await load_review_session(store, vault, session_id)


async def sync_review_state(
    store: "IngestSessionStore",
    session_id: str,
) -> None:
    await _sync_review_state(store, session_id)


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


async def _sync_review_state(store: "IngestSessionStore", session_id: str) -> None:
    detail = await asyncio.to_thread(store.get_session, session_id)
    if detail is None:
        return

    questions = detail.session.open_questions
    actions = detail.session.proposed_actions

    if any(not str(item.get("answer") or "").strip() for item in questions):
        next_state = "awaiting_user"
    elif actions and all(item.approval_state in {"approved", "rejected"} for item in actions):
        next_state = (
            "approved_pending_execution"
            if any(item.approval_state == "approved" for item in actions)
            else "proposal_ready"
        )
    else:
        next_state = "in_review"

    await asyncio.to_thread(store.set_session_state, session_id, next_state)
