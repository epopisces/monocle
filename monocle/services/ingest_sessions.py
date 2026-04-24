"""Persistent ingest-session storage and immutable source archival."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import mimetypes
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, get_args

from monocle.models import (
    IngestNotificationSummary,
    IngestNotification,
    IngestRequest,
    IngestResponse,
    IngestSession,
    IngestSessionDetailResponse,
    IngestTrueUpResponse,
    IngestSessionOrigin,
    IngestSessionState,
    ProposedAction,
    SourceRecord,
    SourceRecordKind,
)

if TYPE_CHECKING:
    from monocle.config import Settings
    from monocle.models import NoteSource


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _guess_mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


_INGEST_SESSION_STATES = frozenset(get_args(IngestSessionState))


@dataclass(frozen=True)
class BackgroundPrepareJob:
    job_id: str
    session_id: str
    job_type: str
    status: str
    run_after: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class IngestSessionPrepareContext:
    session: IngestSession
    sources: list[SourceRecord]
    request_source: str
    template_hint: str | None
    artifact_dir: Path


def _normalise_inbox_mime_type(mime_type: str, request_source: "NoteSource", path: Path) -> str:
    if request_source != "voice":
        return mime_type
    suffix = path.suffix.lower()
    if suffix == ".webm":
        return "audio/webm"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".flac":
        return "audio/flac"
    return mime_type


class IngestSessionStore:
    """SQLite-backed ingest-session store with file-system source archives."""

    def __init__(
        self,
        settings: "Settings",
        *,
        db_path: Path | None = None,
        ingest_root: Path | None = None,
        sources_root: Path | None = None,
    ) -> None:
        data_root = Path(settings.index.chroma_persist_path).resolve().parent
        self._ingest_root = Path(ingest_root or (data_root / "ingest")).resolve()
        self._sources_root = Path(sources_root or (data_root / "sources")).resolve()
        self._db_path = Path(db_path or (self._ingest_root / "sessions.db")).resolve()

        self._ingest_root.mkdir(parents=True, exist_ok=True)
        self._sources_root.mkdir(parents=True, exist_ok=True)
        (self._ingest_root / "artifacts").mkdir(parents=True, exist_ok=True)
        self._initialise()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def ingest_root(self) -> Path:
        return self._ingest_root

    @property
    def sources_root(self) -> Path:
        return self._sources_root

    def create_api_session(self, request: IngestRequest) -> IngestResponse:
        if request.audio_bytes is not None:
            payload = request.audio_bytes
            kind: SourceRecordKind = "audio"
            mime_type = request.audio_mime_type or "application/octet-stream"
            source_name = self._default_source_name(request.source, kind, mime_type)
        else:
            payload = (request.content or "").encode("utf-8")
            kind = "text"
            mime_type = request.content_type or "text/plain"
            source_name = self._default_source_name(request.source, kind, mime_type)

        provenance = {
            "captured_via": "api",
            "request_source": request.source,
            "content_type": request.content_type,
            "audio_mime_type": request.audio_mime_type,
            "template_hint": request.template_hint,
        }

        return self._create_session(
            origin=request.origin,
            request_source=request.source,
            source_kind=kind,
            source_name=source_name,
            mime_type=mime_type,
            payload=payload,
            template_hint=request.template_hint,
            allow_duplicate=request.allow_duplicate,
            fast_capture=request.fast_capture,
            provenance=provenance,
        )

    def create_inbox_session(self, file_path: str, *, request_source: "NoteSource" = "web") -> IngestResponse:
        source_path = Path(file_path)
        payload = source_path.read_bytes()
        mime_type = _normalise_inbox_mime_type(_guess_mime_type(source_path), request_source, source_path)
        provenance = {
            "captured_via": "inbox_watcher",
            "original_path": str(source_path),
            "request_source": request_source,
        }
        return self._create_session(
            origin="inbox",
            request_source=request_source,
            source_kind="file",
            source_name=source_path.name,
            mime_type=mime_type,
            payload=payload,
            template_hint=None,
            allow_duplicate=False,
            fast_capture=False,
            provenance=provenance,
        )

    def list_sessions(
        self,
        *,
        state: str | None = None,
        origin: str | None = None,
        ready_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IngestSession]:
        clauses: list[str] = []
        params: list[Any] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if origin:
            clauses.append("origin = ?")
            params.append(origin)
        if ready_only:
            clauses.append("state IN ('dormant_ready','in_review','awaiting_user','proposal_ready')")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([max(1, min(limit, 200)), max(offset, 0)])

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT session_id, origin, state, fast_capture, title, digest,
                       open_questions_json, related_notes_json, contradictions_json,
                       created_at, updated_at, prepared_at, last_true_up_at,
                       execution_summary_json
                FROM ingest_sessions
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

            session_ids = [row["session_id"] for row in rows]
            sources_by_session = self._get_sources_for_sessions(conn, session_ids)
            actions_by_session = self._get_actions_for_sessions(conn, session_ids)
            sessions = [
                self._build_session(
                    row,
                    sources=sources_by_session.get(row["session_id"], []),
                    actions=actions_by_session.get(row["session_id"], []),
                )
                for row in rows
            ]

        return sessions

    def get_session(self, session_id: str) -> IngestSessionDetailResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, origin, state, fast_capture, title, digest,
                       open_questions_json, related_notes_json, contradictions_json,
                       created_at, updated_at, prepared_at, last_true_up_at,
                       execution_summary_json
                FROM ingest_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None

            sources = self._get_sources_for_sessions(conn, [session_id]).get(session_id, [])
            actions = self._get_actions_for_sessions(conn, [session_id]).get(session_id, [])
            session = self._build_session(row, sources=sources, actions=actions)
            return IngestSessionDetailResponse(session=session, sources=sources)

    def get_prepare_context(self, session_id: str) -> IngestSessionPrepareContext | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, origin, state, fast_capture, title, digest,
                       open_questions_json, related_notes_json, contradictions_json,
                       created_at, updated_at, prepared_at, last_true_up_at,
                       execution_summary_json,
                       request_source, template_hint, artifact_dir
                FROM ingest_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None

            sources = self._get_sources_for_sessions(conn, [session_id]).get(session_id, [])
            actions = self._get_actions_for_sessions(conn, [session_id]).get(session_id, [])
            session = self._build_session(row, sources=sources, actions=actions)
            return IngestSessionPrepareContext(
                session=session,
                sources=sources,
                request_source=row["request_source"],
                template_hint=row["template_hint"],
                artifact_dir=(self._ingest_root / (row["artifact_dir"] or f"artifacts/{session_id}")).resolve(),
            )

    def claim_prepare_jobs(self, *, limit: int = 1, run_after: str | None = None) -> list[BackgroundPrepareJob]:
        due_at = run_after or _utcnow_iso()
        max_jobs = max(1, min(limit, 8))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT job_id, session_id, job_type, status, run_after, created_at, updated_at
                FROM background_prepare_jobs
                WHERE status = 'queued' AND run_after <= ?
                ORDER BY run_after ASC, created_at ASC
                LIMIT ?
                """,
                (due_at, max_jobs),
            ).fetchall()
            job_ids = [row["job_id"] for row in rows]
            now = _utcnow_iso()
            for job_id in job_ids:
                conn.execute(
                    """
                    UPDATE background_prepare_jobs
                    SET status = 'running', updated_at = ?
                    WHERE job_id = ?
                    """,
                    (now, job_id),
                )
                conn.execute(
                    """
                    UPDATE ingest_sessions
                    SET state = 'preparing', updated_at = ?
                    WHERE session_id = (SELECT session_id FROM background_prepare_jobs WHERE job_id = ?)
                    """,
                    (now, job_id),
                )

            return [
                BackgroundPrepareJob(
                    job_id=row["job_id"],
                    session_id=row["session_id"],
                    job_type=row["job_type"],
                    status="running",
                    run_after=row["run_after"],
                    created_at=row["created_at"],
                    updated_at=now,
                )
                for row in rows
            ]

    def claim_prepare_job_for_session(self, session_id: str) -> BackgroundPrepareJob | None:
        now = _utcnow_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT job_id, session_id, job_type, status, run_after, created_at, updated_at
                FROM background_prepare_jobs
                WHERE session_id = ? AND status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None

            conn.execute(
                """
                UPDATE background_prepare_jobs
                SET status = 'running', updated_at = ?
                WHERE job_id = ?
                """,
                (now, row["job_id"]),
            )
            conn.execute(
                """
                UPDATE ingest_sessions
                SET state = 'preparing', updated_at = ?
                WHERE session_id = ?
                """,
                (now, session_id),
            )

            return BackgroundPrepareJob(
                job_id=row["job_id"],
                session_id=row["session_id"],
                job_type=row["job_type"],
                status="running",
                run_after=row["run_after"],
                created_at=row["created_at"],
                updated_at=now,
            )

    def complete_prepare_job(
        self,
        job_id: str,
        session_id: str,
        *,
        title: str | None,
        digest: str | None,
        open_questions: list[dict[str, Any]],
        related_notes: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        proposed_actions: list[ProposedAction],
        artifact_payload: dict[str, Any],
    ) -> str:
        now = _utcnow_iso()
        notification_id = _new_id("notif")
        artifact_dir = self._ingest_root / "artifacts" / session_id

        with self._connect() as conn:
            self._assert_prepare_job_matches_session(conn, job_id, session_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "prepare_result.json").write_text(
                _json_dumps(artifact_payload),
                encoding="utf-8",
            )
            conn.execute(
                """
                UPDATE ingest_sessions
                SET state = 'dormant_ready',
                    title = ?,
                    digest = ?,
                    open_questions_json = ?,
                    related_notes_json = ?,
                    contradictions_json = ?,
                    updated_at = ?,
                    prepared_at = ?
                WHERE session_id = ?
                """,
                (
                    title,
                    digest,
                    _json_dumps(open_questions),
                    _json_dumps(related_notes),
                    _json_dumps(contradictions),
                    now,
                    now,
                    session_id,
                ),
            )
            conn.execute(
                """
                UPDATE background_prepare_jobs
                SET status = 'completed', updated_at = ?
                WHERE job_id = ?
                """,
                (now, job_id),
            )
            conn.execute(
                """
                UPDATE source_records
                SET status = 'ready'
                WHERE session_id = ? AND status IN ('archived', 'queued', 'processing')
                """,
                (session_id,),
            )
            conn.execute("DELETE FROM proposed_actions WHERE session_id = ?", (session_id,))
            for action in proposed_actions:
                conn.execute(
                    """
                    INSERT INTO proposed_actions (
                        action_id, session_id, action_type, approval_state,
                        target_file_path, target_note_type, rationale, diff_preview_json,
                        proposed_content_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action.action_id,
                        session_id,
                        action.action_type,
                        action.approval_state,
                        action.target_file_path,
                        action.target_note_type,
                        action.rationale,
                        _json_dumps(
                            action.diff_preview.model_dump(mode="json")
                            if hasattr(action.diff_preview, "model_dump")
                            else action.diff_preview
                        )
                        if action.diff_preview is not None
                        else None,
                        _json_dumps(action.proposed_content),
                    ),
                )
            conn.execute(
                """
                UPDATE ingest_notifications
                SET status = 'read'
                WHERE session_id = ? AND kind = 'ingest_captured' AND status = 'unread'
                """,
                (session_id,),
            )
            conn.execute(
                """
                INSERT INTO ingest_notifications (
                    notification_id, session_id, kind, status, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    session_id,
                    'ingest_ready',
                    'unread',
                    now,
                    _json_dumps(
                        {
                            'open_questions_count': len(open_questions),
                            'contradictions_count': len(contradictions),
                            'proposed_actions_count': len(proposed_actions),
                        }
                    ),
                ),
            )
        return notification_id

    def fail_prepare_job(self, job_id: str, session_id: str, error_message: str) -> str:
        now = _utcnow_iso()
        notification_id = _new_id("notif")
        with self._connect() as conn:
            self._assert_prepare_job_matches_session(conn, job_id, session_id)
            conn.execute(
                """
                UPDATE background_prepare_jobs
                SET status = 'failed', updated_at = ?
                WHERE job_id = ?
                """,
                (now, job_id),
            )
            conn.execute(
                """
                UPDATE ingest_sessions
                SET state = 'failed', updated_at = ?
                WHERE session_id = ?
                """,
                (now, session_id),
            )
            conn.execute(
                """
                INSERT INTO ingest_notifications (
                    notification_id, session_id, kind, status, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    session_id,
                    'ingest_prepare_failed',
                    'unread',
                    now,
                    _json_dumps({'error': error_message}),
                ),
            )
        return notification_id

    def list_notifications(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[IngestNotificationSummary]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("n.status = ?")
            params.append(status)
        if kind:
            clauses.append("n.kind = ?")
            params.append(kind)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([max(1, min(limit, 200)), max(offset, 0)])

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT n.notification_id, n.session_id, n.kind, n.status, n.created_at,
                       n.payload_json, s.state AS session_state, s.title AS session_title,
                       s.digest AS session_digest, s.open_questions_json,
                       s.contradictions_json
                FROM ingest_notifications n
                JOIN ingest_sessions s ON s.session_id = n.session_id
                {where_sql}
                ORDER BY n.created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
            session_ids = [row["session_id"] for row in rows]
            sources_by_session = self._get_sources_for_sessions(conn, session_ids)
            actions_by_session = self._get_actions_for_sessions(conn, session_ids)

        summaries: list[IngestNotificationSummary] = []
        for row in rows:
            sources = sources_by_session.get(row["session_id"], [])
            actions = actions_by_session.get(row["session_id"], [])
            payload = _json_loads(row["payload_json"], {})
            summaries.append(
                IngestNotificationSummary(
                    notification_id=row["notification_id"],
                    session_id=row["session_id"],
                    kind=row["kind"],
                    status=row["status"],
                    created_at=row["created_at"],
                    session_state=row["session_state"],
                    session_title=row["session_title"],
                    session_digest=row["session_digest"],
                    source_names=[source.source_name for source in sources],
                    open_questions_count=len(_json_loads(row["open_questions_json"], [])),
                    contradictions_count=len(_json_loads(row["contradictions_json"], [])),
                    proposed_actions_count=payload.get("proposed_actions_count", len(actions)),
                )
            )
        return summaries

    def count_notifications(self, *, status: str | None = None, kind: str | None = None) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM ingest_notifications {where_sql}",
                params,
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def set_notification_status(self, notification_id: str, status: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE ingest_notifications SET status = ? WHERE notification_id = ?",
                (status, notification_id),
            )
            return row.rowcount > 0

    def set_session_notification_status(self, session_id: str, kind: str, status: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE ingest_notifications SET status = ? WHERE session_id = ? AND kind = ?",
                (status, session_id, kind),
            )
            return int(row.rowcount)

    def enqueue_true_up(self, session_id: str) -> IngestTrueUpResponse | None:
        now = _utcnow_iso()
        job_id = _new_id("job")
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT session_id FROM ingest_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if exists is None:
                return None

            existing_job = conn.execute(
                """
                SELECT job_id FROM background_prepare_jobs
                WHERE session_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if existing_job is not None:
                job_id = existing_job["job_id"]
            else:
                conn.execute(
                    """
                    INSERT INTO background_prepare_jobs (
                        job_id, session_id, job_type, status, run_after, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, session_id, 'prepare_session', 'queued', now, now, now),
                )

            conn.execute(
                """
                UPDATE ingest_sessions
                SET state = 'queued', updated_at = ?, last_true_up_at = ?
                WHERE session_id = ?
                """,
                (now, now, session_id),
            )
            conn.execute(
                """
                UPDATE ingest_notifications
                SET status = 'dismissed'
                WHERE session_id = ? AND kind = 'ingest_ready' AND status != 'dismissed'
                """,
                (session_id,),
            )

        return IngestTrueUpResponse(
            session_id=session_id,
            job_id=job_id,
            state='queued',
            last_true_up_at=now,
        )

    def set_session_state(self, session_id: str, state: IngestSessionState) -> bool:
        if state not in _INGEST_SESSION_STATES:
            raise ValueError(f"Invalid ingest session state: {state}")
        now = _utcnow_iso()
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE ingest_sessions SET state = ?, updated_at = ? WHERE session_id = ?",
                (state, now, session_id),
            )
            return row.rowcount > 0

    def set_session_execution_summary(
        self,
        session_id: str,
        summary: dict[str, Any],
        *,
        state: IngestSessionState | None = None,
    ) -> bool:
        now = _utcnow_iso()
        updates = ["execution_summary_json = ?", "updated_at = ?"]
        params: list[Any] = [_json_dumps(summary), now]
        if state is not None:
            if state not in _INGEST_SESSION_STATES:
                raise ValueError(f"Invalid ingest session state: {state}")
            updates.insert(0, "state = ?")
            params.insert(0, state)

        with self._connect() as conn:
            row = conn.execute(
                f"UPDATE ingest_sessions SET {', '.join(updates)} WHERE session_id = ?",
                (*params, session_id),
            )
            return row.rowcount > 0

    def answer_open_question(
        self,
        session_id: str,
        question_id: str,
        answer: str,
    ) -> list[dict[str, Any]] | None:
        now = _utcnow_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT open_questions_json FROM ingest_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None

            questions = _json_loads(row["open_questions_json"], [])
            updated = False
            for item in questions:
                if str(item.get("id")) != question_id:
                    continue
                item["answer"] = answer
                item["answered_at"] = now
                updated = True
                break

            if not updated:
                return None

            next_state = "proposal_ready"
            if any(not str(item.get("answer") or "").strip() for item in questions):
                next_state = "awaiting_user"

            conn.execute(
                """
                UPDATE ingest_sessions
                SET open_questions_json = ?, state = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (_json_dumps(questions), next_state, now, session_id),
            )
            return questions

    def update_proposed_action(
        self,
        session_id: str,
        action_id: str,
        *,
        approval_state: str | None = None,
        target_file_path: str | None = None,
        target_note_type: str | None = None,
        rationale: str | None = None,
        diff_preview: dict[str, Any] | None = None,
        proposed_content: dict[str, Any] | None = None,
        execution_result: dict[str, Any] | None = None,
    ) -> ProposedAction | None:
        updates: list[str] = []
        params: list[Any] = []

        if approval_state is not None:
            updates.append("approval_state = ?")
            params.append(approval_state)
        if target_file_path is not None:
            updates.append("target_file_path = ?")
            params.append(target_file_path)
        if target_note_type is not None:
            updates.append("target_note_type = ?")
            params.append(target_note_type)
        if rationale is not None:
            updates.append("rationale = ?")
            params.append(rationale)
        if diff_preview is not None:
            updates.append("diff_preview_json = ?")
            params.append(_json_dumps(diff_preview))
        if proposed_content is not None:
            updates.append("proposed_content_json = ?")
            params.append(_json_dumps(proposed_content))
        if execution_result is not None:
            updates.append("execution_result_json = ?")
            params.append(_json_dumps(execution_result))

        if not updates:
            with self._connect() as conn:
                return self._get_action(conn, session_id, action_id)

        now = _utcnow_iso()
        with self._connect() as conn:
            result = conn.execute(
                f"""
                UPDATE proposed_actions
                SET {', '.join(updates)}
                WHERE session_id = ? AND action_id = ?
                """,
                (*params, session_id, action_id),
            )
            if result.rowcount == 0:
                return None
            conn.execute(
                """
                UPDATE ingest_sessions
                SET state = 'in_review', updated_at = ?
                WHERE session_id = ? AND state IN ('dormant_ready', 'awaiting_user', 'proposal_ready')
                """,
                (now, session_id),
            )
            return self._get_action(conn, session_id, action_id)

    def set_proposed_action_approval_state(
        self,
        session_id: str,
        action_id: str,
        approval_state: str,
    ) -> ProposedAction | None:
        return self.update_proposed_action(
            session_id,
            action_id,
            approval_state=approval_state,
        )

    def list_source_records(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SourceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_id, session_id, kind, status, source_name, mime_type,
                       archive_path, checksum_sha256, captured_at, byte_size, provenance_json
                FROM source_records
                ORDER BY captured_at DESC
                LIMIT ? OFFSET ?
                """,
                (max(1, min(limit, 500)), max(offset, 0)),
            ).fetchall()
        return [
            SourceRecord(
                source_id=row["source_id"],
                session_id=row["session_id"],
                kind=row["kind"],
                status=row["status"],
                source_name=row["source_name"],
                mime_type=row["mime_type"],
                archive_path=row["archive_path"],
                checksum_sha256=row["checksum_sha256"],
                captured_at=row["captured_at"],
                byte_size=row["byte_size"],
                provenance=_json_loads(row["provenance_json"], {}),
            )
            for row in rows
        ]

    def get_source_record(self, source_id: str) -> SourceRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source_id, session_id, kind, status, source_name, mime_type,
                       archive_path, checksum_sha256, captured_at, byte_size, provenance_json
                FROM source_records
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        return SourceRecord(
            source_id=row["source_id"],
            session_id=row["session_id"],
            kind=row["kind"],
            status=row["status"],
            source_name=row["source_name"],
            mime_type=row["mime_type"],
            archive_path=row["archive_path"],
            checksum_sha256=row["checksum_sha256"],
            captured_at=row["captured_at"],
            byte_size=row["byte_size"],
            provenance=_json_loads(row["provenance_json"], {}),
        )

    def resolve_source_path(self, source_id: str) -> Path | None:
        source = self.get_source_record(source_id)
        if source is None:
            return None
        resolved = (self._sources_root / source.archive_path).resolve()
        if not resolved.is_relative_to(self._sources_root):
            raise ValueError(f"Archived source path escapes sources_root: {source.archive_path}")
        if not resolved.exists():
            return None
        return resolved

    def approve_all_proposed_actions(self, session_id: str) -> list[ProposedAction]:
        now = _utcnow_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE proposed_actions
                SET approval_state = 'approved'
                WHERE session_id = ? AND approval_state IN ('draft', 'edited')
                """,
                (session_id,),
            )
            actions = self._get_actions(conn, session_id)
            if actions and all(action.approval_state in ('approved', 'rejected') for action in actions):
                next_state = 'approved_pending_execution' if any(
                    action.approval_state == 'approved' for action in actions
                ) else 'proposal_ready'
                conn.execute(
                    """
                    UPDATE ingest_sessions
                    SET state = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (next_state, now, session_id),
                )
            return actions

    def _create_session(
        self,
        *,
        origin: IngestSessionOrigin,
        request_source: "NoteSource",
        source_kind: SourceRecordKind,
        source_name: str,
        mime_type: str | None,
        payload: bytes,
        template_hint: str | None,
        allow_duplicate: bool,
        fast_capture: bool,
        provenance: dict[str, Any],
    ) -> IngestResponse:
        now = _utcnow_iso()
        session_id = _new_id("ing")
        source_id = _new_id("src")
        notification_id = _new_id("notif")
        job_id = _new_id("job")

        archive_rel_path = Path(source_id) / "payload"
        archive_abs_path = self._sources_root / archive_rel_path
        archive_abs_path.parent.mkdir(parents=True, exist_ok=True)
        archive_abs_path.write_bytes(payload)

        checksum = hashlib.sha256(payload).hexdigest()
        source_record = SourceRecord(
            source_id=source_id,
            session_id=session_id,
            kind=source_kind,
            status="archived",
            source_name=source_name,
            mime_type=mime_type,
            archive_path=archive_rel_path.as_posix(),
            checksum_sha256=checksum,
            captured_at=now,
            byte_size=len(payload),
            provenance=provenance,
        )
        metadata_path = archive_abs_path.parent / "metadata.json"
        metadata_path.write_text(
            _json_dumps(source_record.model_dump(mode="json")),
            encoding="utf-8",
        )

        artifact_dir = self._ingest_root / "artifacts" / session_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO ingest_sessions (
                        session_id, origin, state, title, digest,
                        open_questions_json, related_notes_json, contradictions_json,
                        created_at, updated_at, prepared_at, last_true_up_at,
                        request_source, template_hint, allow_duplicate, fast_capture,
                        artifact_dir
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        origin,
                        "queued",
                        None,
                        None,
                        "[]",
                        "[]",
                        "[]",
                        now,
                        now,
                        None,
                        None,
                        request_source,
                        template_hint,
                        1 if allow_duplicate else 0,
                        1 if fast_capture else 0,
                        artifact_dir.relative_to(self._ingest_root).as_posix(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO source_records (
                        source_id, session_id, kind, status, source_name, mime_type,
                        archive_path, checksum_sha256, captured_at, byte_size, provenance_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_record.source_id,
                        source_record.session_id,
                        source_record.kind,
                        source_record.status,
                        source_record.source_name,
                        source_record.mime_type,
                        source_record.archive_path,
                        source_record.checksum_sha256,
                        source_record.captured_at,
                        source_record.byte_size,
                        _json_dumps(source_record.provenance),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO ingest_notifications (
                        notification_id, session_id, kind, status, created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        notification_id,
                        session_id,
                        "ingest_captured",
                        "unread",
                        now,
                        _json_dumps({"source_id": source_id}),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO background_prepare_jobs (
                        job_id, session_id, job_type, status, run_after, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        session_id,
                        "prepare_session",
                        "queued",
                        now,
                        now,
                        now,
                    ),
                )
        except Exception:
            shutil.rmtree(archive_abs_path.parent, ignore_errors=True)
            shutil.rmtree(artifact_dir, ignore_errors=True)
            raise

        return IngestResponse(
            session_id=session_id,
            origin=origin,
            state="queued",
            source_ids=[source_id],
            created_at=now,
            updated_at=now,
            notification=IngestNotification(
                id=notification_id,
                kind="ingest_captured",
                status="unread",
                created_at=now,
            ),
        )

    def _build_session(
        self,
        row: sqlite3.Row,
        *,
        sources: list[SourceRecord],
        actions: list[ProposedAction],
    ) -> IngestSession:
        session_id = row["session_id"]
        return IngestSession(
            session_id=session_id,
            origin=row["origin"],
            state=row["state"],
            fast_capture=bool(row["fast_capture"]),
            source_ids=[source.source_id for source in sources],
            title=row["title"],
            digest=row["digest"],
            open_questions=_json_loads(row["open_questions_json"], []),
            related_notes=_json_loads(row["related_notes_json"], []),
            contradictions=_json_loads(row["contradictions_json"], []),
            proposed_actions=actions,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            prepared_at=row["prepared_at"],
            last_true_up_at=row["last_true_up_at"],
            execution_summary=_json_loads(row["execution_summary_json"], None),
        )

    def _get_sources_for_sessions(
        self,
        conn: sqlite3.Connection,
        session_ids: list[str],
    ) -> dict[str, list[SourceRecord]]:
        session_ids = list(dict.fromkeys(session_ids))
        grouped: dict[str, list[SourceRecord]] = {session_id: [] for session_id in session_ids}
        if not session_ids:
            return grouped

        placeholders = ", ".join("?" for _ in session_ids)
        rows = conn.execute(
            f"""
            SELECT source_id, session_id, kind, status, source_name, mime_type,
                   archive_path, checksum_sha256, captured_at, byte_size, provenance_json
            FROM source_records
            WHERE session_id IN ({placeholders})
            ORDER BY session_id ASC, captured_at ASC
            """,
            tuple(session_ids),
        ).fetchall()
        for row in rows:
            grouped[row["session_id"]].append(
                SourceRecord(
                    source_id=row["source_id"],
                    session_id=row["session_id"],
                    kind=row["kind"],
                    status=row["status"],
                    source_name=row["source_name"],
                    mime_type=row["mime_type"],
                    archive_path=row["archive_path"],
                    checksum_sha256=row["checksum_sha256"],
                    captured_at=row["captured_at"],
                    byte_size=row["byte_size"],
                    provenance=_json_loads(row["provenance_json"], {}),
                )
            )
        return grouped

    def _get_sources(self, conn: sqlite3.Connection, session_id: str) -> list[SourceRecord]:
        return self._get_sources_for_sessions(conn, [session_id]).get(session_id, [])

    def _assert_prepare_job_matches_session(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        session_id: str,
    ) -> None:
        row = conn.execute(
            "SELECT session_id FROM background_prepare_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Background prepare job not found: {job_id}")
        if row["session_id"] != session_id:
            raise ValueError(
                f"Background prepare job {job_id} does not belong to session {session_id}"
            )

    def _get_actions_for_sessions(
        self,
        conn: sqlite3.Connection,
        session_ids: list[str],
    ) -> dict[str, list[ProposedAction]]:
        session_ids = list(dict.fromkeys(session_ids))
        grouped: dict[str, list[ProposedAction]] = {session_id: [] for session_id in session_ids}
        if not session_ids:
            return grouped

        placeholders = ", ".join("?" for _ in session_ids)
        rows = conn.execute(
            f"""
            SELECT session_id, action_id, action_type, approval_state, target_file_path,
                 target_note_type, rationale, diff_preview_json, proposed_content_json,
                 execution_result_json
            FROM proposed_actions
            WHERE session_id IN ({placeholders})
            ORDER BY session_id ASC, created_at ASC
            """,
            tuple(session_ids),
        ).fetchall()
        for row in rows:
            grouped[row["session_id"]].append(
                ProposedAction(
                    action_id=row["action_id"],
                    action_type=row["action_type"],
                    approval_state=row["approval_state"],
                    target_file_path=row["target_file_path"],
                    target_note_type=row["target_note_type"],
                    rationale=row["rationale"],
                    diff_preview=_json_loads(row["diff_preview_json"], None),
                    proposed_content=_json_loads(row["proposed_content_json"], {}),
                    execution_result=_json_loads(row["execution_result_json"], None),
                )
            )
        return grouped

    def _get_actions(self, conn: sqlite3.Connection, session_id: str) -> list[ProposedAction]:
        return self._get_actions_for_sessions(conn, [session_id]).get(session_id, [])

    def _get_action(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        action_id: str,
    ) -> ProposedAction | None:
        row = conn.execute(
            """
            SELECT session_id, action_id, action_type, approval_state, target_file_path,
                   target_note_type, rationale, diff_preview_json, proposed_content_json,
                   execution_result_json
            FROM proposed_actions
            WHERE session_id = ? AND action_id = ?
            """,
            (session_id, action_id),
        ).fetchone()
        if row is None:
            return None
        return ProposedAction(
            action_id=row["action_id"],
            action_type=row["action_type"],
            approval_state=row["approval_state"],
            target_file_path=row["target_file_path"],
            target_note_type=row["target_note_type"],
            rationale=row["rationale"],
            diff_preview=_json_loads(row["diff_preview_json"], None),
            proposed_content=_json_loads(row["proposed_content_json"], {}),
            execution_result=_json_loads(row["execution_result_json"], None),
        )

    def _default_source_name(
        self,
        request_source: "NoteSource",
        source_kind: SourceRecordKind,
        mime_type: str | None,
    ) -> str:
        extension = mimetypes.guess_extension(mime_type or "") or (
            ".txt" if source_kind == "text" else ".bin"
        )
        return f"{request_source}-capture{extension}"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_sessions (
                    session_id TEXT PRIMARY KEY,
                    origin TEXT NOT NULL,
                    state TEXT NOT NULL,
                    title TEXT,
                    digest TEXT,
                    open_questions_json TEXT NOT NULL DEFAULT '[]',
                    related_notes_json TEXT NOT NULL DEFAULT '[]',
                    contradictions_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    prepared_at TEXT,
                    last_true_up_at TEXT,
                    execution_summary_json TEXT,
                    request_source TEXT NOT NULL,
                    template_hint TEXT,
                    allow_duplicate INTEGER NOT NULL DEFAULT 0,
                    fast_capture INTEGER NOT NULL DEFAULT 0,
                    artifact_dir TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_records (
                    source_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    mime_type TEXT,
                    archive_path TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    byte_size INTEGER NOT NULL DEFAULT 0,
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES ingest_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proposed_actions (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    target_file_path TEXT,
                    target_note_type TEXT,
                    rationale TEXT NOT NULL,
                    diff_preview_json TEXT,
                    proposed_content_json TEXT NOT NULL DEFAULT '{}',
                    execution_result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES ingest_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_notifications (
                    notification_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES ingest_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS background_prepare_jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    run_after TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES ingest_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_column(conn, "ingest_sessions", "execution_summary_json", "TEXT")
            self._ensure_column(conn, "proposed_actions", "execution_result_json", "TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingest_sessions_state_created ON ingest_sessions(state, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingest_sessions_origin_created ON ingest_sessions(origin, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_records_session_id ON source_records(session_id, captured_at ASC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_proposed_actions_session_id ON proposed_actions(session_id, created_at ASC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notifications_status_created ON ingest_notifications(status, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prepare_jobs_status_run_after ON background_prepare_jobs(status, run_after ASC)"
            )

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")