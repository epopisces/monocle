from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from monocle.ingest import IngestPipeline
from monocle.index.memory import MemoryIndex
from monocle.models import IngestRequest, NoteMetadata
from monocle.services.activity import ActivityMonitor
from monocle.services.ingest_prepare import IngestPreparationWorker
from monocle.services.ingest_sessions import IngestSessionStore
from monocle.vault import VaultLayer


def _make_settings(tmp_path: Path):
    from monocle.config import Settings

    defaults = {
        "ai": {
            "chat_model_key": "llama3.2",
            "embed_model_key": "nomic-embed",
            "models": [
                {"key": "llama3.2", "name": "llama3.2", "role": "chat", "provider": "ollama"},
                {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
            ],
        },
        "vault": {"path": str(tmp_path / "vault"), "watch": False},
        "index": {"backend": "chroma", "chroma_persist_path": str(tmp_path / "data" / "chroma")},
        "ingest": {"prepare_poll_interval_s": 1.0, "max_idle_prepare_jobs": 1},
    }
    with patch("monocle.config._find_config_file", return_value=Path("/nonexistent")), patch(
        "monocle.config._load_yaml", return_value=defaults
    ):
        return Settings()


@pytest.fixture
def prep_fixture(tmp_path: Path):
    settings = _make_settings(tmp_path)
    vault_path = tmp_path / "vault"
    vault_path.mkdir(parents=True, exist_ok=True)
    vault = VaultLayer(str(vault_path))
    index = MemoryIndex()

    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[0.1] * 1536)
    ai.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    ai.transcribe = AsyncMock(return_value="transcribed audio content")
    ai.extract_note_metadata = AsyncMock(return_value=NoteMetadata(title="Alice sync", domain="work"))
    ai.chat = AsyncMock(
        return_value=json.dumps(
            {
                "title": "Alice sync",
                "digest": "Met with Alice and captured follow-up work.",
                "open_questions": [{"question": "Should this become a project note?"}],
                "contradictions": [],
                "proposed_actions": [
                    {
                        "action_type": "create_note",
                        "target_note_type": "observation",
                        "rationale": "Capture the meeting outcome.",
                        "proposed_content": {"title": "Alice sync", "body": "Met with Alice about the Q2 rollout."},
                    }
                ],
            }
        )
    )

    pipeline = IngestPipeline(vault=vault, index=index, ai=ai, settings=settings)
    store = IngestSessionStore(
        settings,
        db_path=tmp_path / "data" / "ingest" / "sessions.db",
        ingest_root=tmp_path / "data" / "ingest",
        sources_root=tmp_path / "data" / "sources",
    )
    activity = ActivityMonitor()
    worker = IngestPreparationWorker(
        store=store,
        pipeline=pipeline,
        vault=vault,
        index=index,
        ai=ai,
        settings=settings,
        activity=activity,
    )
    return store, worker, activity


class TestIngestPreparationWorker:
    @pytest.mark.asyncio
    async def test_run_once_prepares_queued_session_and_emits_ready_notification(self, prep_fixture):
        store, worker, _activity = prep_fixture
        created = store.create_api_session(IngestRequest(content="Met with Alice about the Q2 rollout.", source="web"))

        processed = await worker.run_once()

        assert processed == 1
        detail = store.get_session(created.session_id)
        assert detail is not None
        assert detail.session.state == "dormant_ready"
        assert detail.session.digest == "Met with Alice and captured follow-up work."
        assert detail.session.open_questions[0]["question"] == "Should this become a project note?"
        assert len(detail.session.proposed_actions) == 1

        notifications = store.list_notifications(kind="ingest_ready")
        assert len(notifications) == 1
        assert notifications[0].session_id == created.session_id
        assert notifications[0].status == "unread"

    @pytest.mark.asyncio
    async def test_run_once_skips_background_work_when_activity_is_busy(self, prep_fixture):
        store, worker, activity = prep_fixture
        created = store.create_api_session(IngestRequest(content="Busy state should defer prep.", source="web"))

        with activity.track_chat_stream():
            processed = await worker.run_once()

        assert processed == 0
        detail = store.get_session(created.session_id)
        assert detail is not None
        assert detail.session.state == "queued"

    @pytest.mark.asyncio
    async def test_true_up_requeues_prepared_session(self, prep_fixture):
        store, worker, _activity = prep_fixture
        created = store.create_api_session(IngestRequest(content="Refresh this prepared session.", source="web"))
        await worker.run_once()

        refreshed = store.enqueue_true_up(created.session_id)

        assert refreshed is not None
        assert refreshed.state == "queued"
        detail = store.get_session(created.session_id)
        assert detail is not None
        assert detail.session.state == "queued"
        assert detail.session.last_true_up_at == refreshed.last_true_up_at