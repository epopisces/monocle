"""Compatibility wrappers for the consolidated ingest workflow owner."""
from __future__ import annotations

from monocle.services.ingest_workflow import (
    answer_review_question,
    approve_all_review_actions,
    load_session_detail as load_review_session,
    set_review_action_approval,
    start_review_session,
    sync_review_state,
    update_review_action,
)

__all__ = [
    "answer_review_question",
    "approve_all_review_actions",
    "load_review_session",
    "set_review_action_approval",
    "start_review_session",
    "sync_review_state",
    "update_review_action",
]
