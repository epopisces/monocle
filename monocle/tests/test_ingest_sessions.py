from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from monocle.models import IngestRequest, ProposedAction
from monocle.services.ingest_sessions import IngestSessionStore


def _make_settings():
    from monocle.config import Settings

    defaults = {
        "ai": {"provider": "ollama"},
        "vault": {"path": "/tmp/vault", "watch": False},
    }
    with patch("monocle.config._find_config_file", return_value=Path("/nonexistent")), patch(
        "monocle.config._load_yaml", return_value=defaults
    ):
        return Settings()


class TestIngestSessionStore:
    def test_create_api_session_archives_text_and_survives_restart(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )

        created = store.create_api_session(
            IngestRequest(content="Archived outside the vault", source="web")
        )

        detail = store.get_session(created.session_id)
        assert detail is not None
        assert detail.session.origin == "api"
        assert detail.session.state == "queued"
        assert len(detail.sources) == 1

        source = detail.sources[0]
        payload_path = tmp_path / "data" / "sources" / source.archive_path
        assert payload_path.read_text(encoding="utf-8") == "Archived outside the vault"

        restarted = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        restarted_detail = restarted.get_session(created.session_id)
        assert restarted_detail is not None
        assert restarted_detail.session.session_id == created.session_id
        assert restarted_detail.sources[0].checksum_sha256 == source.checksum_sha256

    def test_create_inbox_session_preserves_original_file_metadata(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        inbox_file = tmp_path / "vault" / "inbox" / "capture.webm"
        inbox_file.parent.mkdir(parents=True, exist_ok=True)
        inbox_file.write_bytes(b"audio-bytes")

        created = store.create_inbox_session(str(inbox_file), request_source="voice")
        detail = store.get_session(created.session_id)

        assert detail is not None
        assert detail.session.origin == "inbox"
        assert detail.sources[0].kind == "file"
        assert detail.sources[0].mime_type == "audio/webm"
        assert detail.sources[0].provenance["original_path"] == str(inbox_file)

    def test_list_sessions_can_filter_by_origin(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        inbox_file = tmp_path / "vault" / "inbox" / "capture.md"
        inbox_file.parent.mkdir(parents=True, exist_ok=True)
        inbox_file.write_text("hello", encoding="utf-8")

        api_session = store.create_api_session(IngestRequest(content="via api", source="web"))
        store.create_inbox_session(str(inbox_file), request_source="web")

        api_sessions = store.list_sessions(origin="api")
        assert [session.session_id for session in api_sessions] == [api_session.session_id]

    def test_list_sessions_preloads_sources_and_actions_in_constant_queries(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        first = store.create_api_session(IngestRequest(content="first", source="web"))
        second = store.create_api_session(IngestRequest(content="second", source="web"))

        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO proposed_actions (
                    action_id, session_id, action_type, approval_state,
                    target_file_path, target_note_type, rationale, proposed_content_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "act_first",
                    first.session_id,
                    "update_note",
                    "draft",
                    "people/alice.md",
                    "person_note",
                    "Needs review before applying.",
                    '{"title":"Alice"}',
                ),
            )

        original_connect = store._connect
        selects: list[str] = []

        @contextmanager
        def counted_connect():
            with original_connect() as conn:
                conn.set_trace_callback(
                    lambda sql: selects.append(sql)
                    if sql.lstrip().upper().startswith("SELECT")
                    else None
                )
                yield conn

        store._connect = counted_connect  # type: ignore[method-assign]
        try:
            sessions = store.list_sessions(limit=10)
        finally:
            store._connect = original_connect  # type: ignore[method-assign]

        assert len(selects) == 3
        assert [session.session_id for session in sessions] == [second.session_id, first.session_id]
        assert sessions[0].source_ids == [second.source_ids[0]]
        assert sessions[0].proposed_actions == []
        assert sessions[1].source_ids == [first.source_ids[0]]
        assert [action.action_id for action in sessions[1].proposed_actions] == ["act_first"]

    def test_get_session_reuses_preloaded_sources(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        created = store.create_api_session(IngestRequest(content="detail", source="web"))

        original_connect = store._connect
        selects: list[str] = []

        @contextmanager
        def counted_connect():
            with original_connect() as conn:
                conn.set_trace_callback(
                    lambda sql: selects.append(sql)
                    if sql.lstrip().upper().startswith("SELECT")
                    else None
                )
                yield conn

        store._connect = counted_connect  # type: ignore[method-assign]
        try:
            detail = store.get_session(created.session_id)
        finally:
            store._connect = original_connect  # type: ignore[method-assign]

        assert detail is not None
        assert len(selects) == 3
        assert detail.session.source_ids == [detail.sources[0].source_id]

    def test_update_proposed_action_persists_edit_and_marks_session_in_review(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        created = store.create_api_session(IngestRequest(content="review me", source="web"))
        job = store.claim_prepare_jobs(limit=1)[0]
        store.complete_prepare_job(
            job.job_id,
            created.session_id,
            title="Prepared review",
            digest="Digest",
            open_questions=[],
            related_notes=[],
            contradictions=[],
            proposed_actions=[
                ProposedAction(
                    action_id="act_1",
                    action_type="update_note",
                    approval_state="draft",
                    target_file_path="people/alice.md",
                    target_note_type="person_note",
                    rationale="Capture new context.",
                    proposed_content={"title": "Alice", "body": "Original draft"},
                )
            ],
            artifact_payload={"digest": "Digest"},
        )

        updated = store.update_proposed_action(
            created.session_id,
            "act_1",
            approval_state="edited",
            rationale="Capture the clarified meeting details.",
            proposed_content={"title": "Alice", "body": "Edited draft"},
        )

        assert updated is not None
        assert updated.approval_state == "edited"
        assert updated.proposed_content["body"] == "Edited draft"

        detail = store.get_session(created.session_id)
        assert detail is not None
        assert detail.session.state == "in_review"
        assert detail.session.proposed_actions[0].rationale == "Capture the clarified meeting details."

    def test_complete_prepare_job_rejects_mismatched_job_and_session(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        first = store.create_api_session(IngestRequest(content="first", source="web"))
        second = store.create_api_session(IngestRequest(content="second", source="web"))
        jobs = store.claim_prepare_jobs(limit=2)
        first_job = next(job for job in jobs if job.session_id == first.session_id)

        with pytest.raises(ValueError, match="does not belong"):
            store.complete_prepare_job(
                first_job.job_id,
                second.session_id,
                title="Prepared review",
                digest="Digest",
                open_questions=[],
                related_notes=[],
                contradictions=[],
                proposed_actions=[],
                artifact_payload={"digest": "Digest"},
            )

        first_detail = store.get_session(first.session_id)
        second_detail = store.get_session(second.session_id)
        assert first_detail is not None
        assert second_detail is not None
        assert first_detail.session.state == "preparing"
        assert second_detail.session.state == "preparing"

        with store._connect() as conn:
            row = conn.execute(
                "SELECT status FROM background_prepare_jobs WHERE job_id = ?",
                (first_job.job_id,),
            ).fetchone()
        assert row is not None
        assert row["status"] == "running"

    def test_fail_prepare_job_rejects_mismatched_job_and_session(self, tmp_path: Path):
        settings = _make_settings()
        store = IngestSessionStore(
            settings,
            db_path=tmp_path / "data" / "ingest" / "sessions.db",
            ingest_root=tmp_path / "data" / "ingest",
            sources_root=tmp_path / "data" / "sources",
        )
        first = store.create_api_session(IngestRequest(content="first", source="web"))
        second = store.create_api_session(IngestRequest(content="second", source="web"))
        jobs = store.claim_prepare_jobs(limit=2)
        first_job = next(job for job in jobs if job.session_id == first.session_id)

        with pytest.raises(ValueError, match="does not belong"):
            store.fail_prepare_job(first_job.job_id, second.session_id, "boom")

        first_detail = store.get_session(first.session_id)
        second_detail = store.get_session(second.session_id)
        assert first_detail is not None
        assert second_detail is not None
        assert first_detail.session.state == "preparing"
        assert second_detail.session.state == "preparing"

        with store._connect() as conn:
            row = conn.execute(
                "SELECT status FROM background_prepare_jobs WHERE job_id = ?",
                (first_job.job_id,),
            ).fetchone()
            failed_notifications = conn.execute(
                "SELECT COUNT(*) AS count FROM ingest_notifications WHERE kind = 'ingest_prepare_failed'",
            ).fetchone()
        assert row is not None
        assert row["status"] == "running"
        assert failed_notifications is not None
        assert failed_notifications["count"] == 0