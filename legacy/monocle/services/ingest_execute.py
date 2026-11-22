"""Compatibility wrappers for consolidated ingest workflow execution."""
from __future__ import annotations

from monocle.services.ingest_workflow import execute_fast_capture_session, execute_review_session

__all__ = ["execute_fast_capture_session", "execute_review_session"]
