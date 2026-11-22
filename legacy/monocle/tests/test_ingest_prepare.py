from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from monocle.ingest import IngestPipeline
from monocle.index.memory import MemoryIndex
from monocle.models import IngestRequest, NoteMetadata, RoutingDecision
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

    @pytest.mark.asyncio
    async def test_run_once_fails_job_when_archive_path_escapes_sources_root(self, prep_fixture):
        store, worker, _activity = prep_fixture
        created = store.create_api_session(IngestRequest(content="Tampered source path.", source="web"))
        escaped_path = store.sources_root.parent / "escaped.txt"
        escaped_path.write_text("outside the sources root", encoding="utf-8")

        with store._connect() as conn:
            conn.execute(
                "UPDATE source_records SET archive_path = ? WHERE session_id = ?",
                ("../escaped.txt", created.session_id),
            )

        processed = await worker.run_once()

        assert processed == 1
        detail = store.get_session(created.session_id)
        assert detail is not None
        assert detail.session.state == "failed"

        notifications = store.list_notifications(kind="ingest_prepare_failed")
        assert len(notifications) == 1
        assert notifications[0].session_id == created.session_id

    @pytest.mark.asyncio
    async def test_prepare_session_now_waits_for_running_job_completion(self, prep_fixture):
        store, worker, _activity = prep_fixture
        created = store.create_api_session(IngestRequest(content="Wait for the running prepare job.", source="web"))
        job = store.claim_prepare_jobs(limit=1)[0]

        original_build = worker._build_prepared_session
        started = asyncio.Event()
        release = asyncio.Event()

        async def _delayed_build(context):
            started.set()
            await release.wait()
            return await original_build(context)

        worker._build_prepared_session = AsyncMock(side_effect=_delayed_build)

        prepare_task = asyncio.create_task(worker._prepare_job(job))
        await started.wait()

        detail_task = asyncio.create_task(worker.prepare_session_now(created.session_id))
        await asyncio.sleep(0)
        assert detail_task.done() is False
        release.set()

        detail = await detail_task
        await prepare_task

        assert detail is not None
        assert detail.session.state == "dormant_ready"
        assert detail.session.digest == "Met with Alice and captured follow-up work."

    @pytest.mark.asyncio
    async def test_generate_prep_payload_uses_local_prompt_override_without_frontmatter(
        self,
        prep_fixture,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import monocle.prompts as prompts_module

        store, worker, _activity = prep_fixture
        created = store.create_api_session(IngestRequest(content="Prompt override session.", source="web"))
        context = store.get_prepare_context(created.session_id)
        assert context is not None

        prompts_root = tmp_path / "prompts"
        (prompts_root / "local").mkdir(parents=True, exist_ok=True)
        (prompts_root / "ingest_prepare.md").write_text(
            "---\nname: ingest_prepare\n---\nDEFAULT PROMPT",
            encoding="utf-8",
        )
        (prompts_root / "local" / "ingest_prepare.md").write_text(
            "---\nname: ingest_prepare_local\n---\nLOCAL PREP PROMPT",
            encoding="utf-8",
        )
        monkeypatch.setattr(prompts_module, "_PROMPTS_DIR", prompts_root)

        worker._ai.chat.reset_mock()

        payload = await worker._generate_prep_payload(
            source_text="Prompt override session.",
            routing_decision=RoutingDecision(template="blank", note_type="observation", confidence=1.0, fast_path=True),
            note_metadata=NoteMetadata(title="Prompt Override", type="observation"),
            related_notes=[],
            context=context,
        )

        assert payload["title"] == "Alice sync"
        messages = worker._ai.chat.await_args.args[0]
        assert messages[0]["content"] == "LOCAL PREP PROMPT"
        assert "name:" not in messages[0]["content"]
        assert "---" not in messages[0]["content"]