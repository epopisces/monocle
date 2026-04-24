from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from monocle.models import IngestRequest
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