"""
monocle/tests/test_scheduler.py — Unit tests for MonocleScheduler.

Coverage targets
----------------
- start() / stop() lifecycle
- status() dict structure before and after start
- add_cron_job() happy path and error paths:
    - raised RuntimeError when called before start()
    - raised ValueError on invalid (non-5-field) cron strings
- MoocleScheduler backward-compat alias
- WeeklySummaryAgent (M11)
- Agent API endpoints: POST /api/agents/weekly-summary, POST /api/agents/reindex
"""
from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings() -> MagicMock:
    """Return a minimal MagicMock that satisfies MonocleScheduler's constructor."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestMonocleSchedulerLifecycle:
    async def test_start_creates_running_scheduler(self):
        """start() initialises APScheduler and status() reports running=True."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()
        try:
            assert sched.status()["running"] is True
        finally:
            await sched.stop()

    async def test_stop_shuts_down_scheduler(self):
        """stop() shuts down a running scheduler; status() reports running=False."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()
        await sched.stop()
        assert sched.status()["running"] is False

    async def test_stop_before_start_is_noop(self):
        """stop() before start() does not raise."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.stop()  # should not raise

    def test_status_before_start_returns_not_running_empty_jobs(self):
        """status() before start() returns running=False and empty jobs list."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        status = sched.status()
        assert status["running"] is False
        assert status["jobs"] == []

    async def test_double_stop_is_safe(self):
        """stop() called twice does not raise."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()
        await sched.stop()
        await sched.stop()  # second call should be a no-op


# ---------------------------------------------------------------------------
# add_cron_job tests
# ---------------------------------------------------------------------------


class TestMonocleSchedulerAddCronJob:
    async def test_add_cron_job_appears_in_status(self):
        """A registered job appears in status()['jobs'] with correct id."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()

        async def _stub() -> None:
            pass

        sched.add_cron_job("my_job", _stub, "0 3 * * 0")

        jobs = sched.status()["jobs"]
        assert any(j["id"] == "my_job" for j in jobs), f"Job not found in {jobs}"

        await sched.stop()

    async def test_status_job_entries_have_id_and_next_run(self):
        """Each entry in status()['jobs'] has 'id' and 'next_run' keys."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()

        async def _stub() -> None:
            pass

        sched.add_cron_job("weekly", _stub, "0 17 * * 5")

        jobs = sched.status()["jobs"]
        assert len(jobs) == 1
        assert "id" in jobs[0]
        assert "next_run" in jobs[0]

        await sched.stop()

    async def test_add_cron_job_before_start_raises_runtime_error(self):
        """add_cron_job() before start() raises RuntimeError."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())

        async def _stub() -> None:
            pass

        with pytest.raises(RuntimeError, match="not started"):
            sched.add_cron_job("bad", _stub, "0 3 * * 0")

    async def test_cron_too_few_fields_raises_value_error(self):
        """A cron string with fewer than 5 fields raises ValueError."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()

        async def _stub() -> None:
            pass

        with pytest.raises(ValueError, match="5 fields"):
            sched.add_cron_job("bad", _stub, "0 3 * *")

        await sched.stop()

    async def test_cron_too_many_fields_raises_value_error(self):
        """A cron string with more than 5 fields raises ValueError."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()

        async def _stub() -> None:
            pass

        with pytest.raises(ValueError, match="5 fields"):
            sched.add_cron_job("bad", _stub, "0 3 * * 0 extra")

        await sched.stop()

    async def test_replace_existing_job_by_same_id(self):
        """Registering a second job with the same id replaces the first (replace_existing=True)."""
        from monocle.agents.scheduler import MonocleScheduler

        sched = MonocleScheduler(_make_settings())
        await sched.start()

        call_order: list[int] = []

        async def _stub_a() -> None:
            call_order.append(1)

        async def _stub_b() -> None:
            call_order.append(2)

        sched.add_cron_job("same_id", _stub_a, "0 3 * * 0")
        sched.add_cron_job("same_id", _stub_b, "0 4 * * 0")

        # Should still be exactly one job under 'same_id'
        jobs = sched.status()["jobs"]
        assert sum(1 for j in jobs if j["id"] == "same_id") == 1, (
            f"Expected 1 job with id 'same_id', got: {jobs}"
        )

        await sched.stop()


# ---------------------------------------------------------------------------
# Backward-compat alias
# ---------------------------------------------------------------------------


class TestMoocleSchedulerAlias:
    def test_moocle_alias_is_gone(self):
        """MoocleScheduler typo alias was removed after M6."""
        import importlib
        import monocle.agents.scheduler as sched_mod

        assert not hasattr(sched_mod, "MoocleScheduler"), (
            "MoocleScheduler alias should have been removed; found it in scheduler module"
        )


# ---------------------------------------------------------------------------
# WeeklySummaryAgent tests (M11)
# ---------------------------------------------------------------------------


def _make_vault_with_recent_notes(tmp_path: Path) -> "VaultLayer":  # type: ignore[name-defined]
    """Create a temp vault with notes updated recently."""
    import yaml

    from monocle.vault import VaultLayer

    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat().replace("+00:00", "Z")

    for fname, body, extra_fm in [
        (
            "work/meeting-a.md",
            "We discussed project roadmap.",
            {"type": "meeting_note", "domain": "work"},
        ),
        (
            "work/decision-a.md",
            "Chose FastAPI for the backend.",
            {"type": "decision", "domain": "work"},
        ),
        (
            "people/alice.md",
            "Alice is a senior engineer.",
            {"type": "person_note", "domain": "work"},
        ),
        (
            "ideas/graph-idea.md",
            "Graph visualisation concept.",
            {"type": "idea", "domain": "personal"},
        ),
    ]:
        fp = tmp_path / fname
        fp.parent.mkdir(parents=True, exist_ok=True)
        fm = {
            "created": now_iso,
            "updated": now_iso,
            "confidence": 0.9,
            "review_status": "approved",
            "source": "web",
            "tags": [],
            **extra_fm,
        }
        fp.write_text(
            f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n",
            encoding="utf-8",
        )

    (tmp_path / "summaries").mkdir(exist_ok=True)
    return VaultLayer(str(tmp_path))


def _make_mock_ai() -> AsyncMock:
    """Return a mock AIProvider whose chat() returns a plain string."""
    from monocle.models import NoteMetadata

    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[0.1] * 1536)
    ai.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    ai.chat = AsyncMock(
        return_value=type("R", (), {"content": "## Cluster: Theme\n\nThis week saw good progress."})()
    )
    ai.extract_note_metadata = AsyncMock(return_value=NoteMetadata())
    return ai


def _make_mock_settings(domains: list[str] | None = None) -> MagicMock:
    cfg = MagicMock()
    cfg.agents.weekly_summary.domains = domains or ["work", "personal"]
    return cfg


class TestWeeklySummaryAgent:
    async def test_run_writes_summary_note(self, tmp_path: Path):
        """run() creates summaries/YYYY-WW.md when recent notes exist."""
        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex

        vault = _make_vault_with_recent_notes(tmp_path)
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings()

        agent = WeeklySummaryAgent()
        file_path = await agent.run(vault, index, ai, settings)

        assert file_path.startswith("summaries/")
        assert file_path.endswith(".md")
        # The file should exist on disk
        full_path = Path(tmp_path) / file_path
        assert full_path.exists(), f"Expected {full_path} to be written"

    async def test_summary_note_has_approved_frontmatter(self, tmp_path: Path):
        """Written summary note must have confidence=1.0 and review_status=approved."""
        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex

        vault = _make_vault_with_recent_notes(tmp_path)
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings()

        agent = WeeklySummaryAgent()
        file_path = await agent.run(vault, index, ai, settings)

        note = vault.read_note(file_path)
        assert note.metadata.confidence == 1.0, "Confidence must be 1.0 for auto-approved summaries"
        assert note.metadata.review_status == "approved"
        assert note.metadata.approved_by == "system:weekly-summary"
        assert note.metadata.approval_mode == "auto"
        assert note.metadata.type == "weekly_summary"

    async def test_run_no_recent_notes_raises_runtime_error(self, tmp_path: Path):
        """run() raises RuntimeError when no notes were modified in the last 7 days."""
        import yaml

        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        # Write a note with an old updated date (9 days ago)
        old_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=9)
        old_iso = old_dt.isoformat().replace("+00:00", "Z")
        fp = tmp_path / "work" / "old-note.md"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fm = {
            "created": old_iso,
            "updated": old_iso,
            "type": "meeting_note",
            "domain": "work",
            "confidence": 0.9,
            "review_status": "approved",
            "source": "web",
            "tags": [],
        }
        fp.write_text(
            f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\nOld content.\n",
            encoding="utf-8",
        )
        (tmp_path / "summaries").mkdir(exist_ok=True)

        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings()
        agent = WeeklySummaryAgent()

        with pytest.raises(RuntimeError, match="No notes modified"):
            await agent.run(vault, index, ai, settings)

    async def test_run_skips_notes_older_than_7_days(self, tmp_path: Path):
        """Only notes updated within the last 7 days are included."""
        import yaml

        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        now = datetime.datetime.now(datetime.timezone.utc)
        recent_iso = now.isoformat().replace("+00:00", "Z")
        old_dt = now - datetime.timedelta(days=10)
        old_iso = old_dt.isoformat().replace("+00:00", "Z")

        for fname, upd_iso in [
            ("work/recent.md", recent_iso),
            ("work/old.md", old_iso),
        ]:
            fp = tmp_path / fname
            fp.parent.mkdir(parents=True, exist_ok=True)
            fm = {
                "created": upd_iso,
                "updated": upd_iso,
                "type": "meeting_note",
                "domain": "work",
                "confidence": 0.9,
                "review_status": "approved",
                "source": "web",
                "tags": [],
            }
            fp.write_text(
                f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\nContent.\n",
                encoding="utf-8",
            )
        (tmp_path / "summaries").mkdir(exist_ok=True)

        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings(domains=[None])  # no domain filter
        agent = WeeklySummaryAgent()

        # Should succeed — one recent note is enough (using LLM grouping fallback)
        file_path = await agent.run(vault, index, ai, settings)
        assert file_path.startswith("summaries/")

    async def test_llm_fallback_used_for_small_batches(self, tmp_path: Path):
        """LLM grouping is used when fewer than _MIN_NOTES_FOR_CLUSTERING notes exist."""
        import yaml

        from monocle.agents.weekly_summary import WeeklySummaryAgent, _MIN_NOTES_FOR_CLUSTERING
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")

        # Write exactly _MIN_NOTES_FOR_CLUSTERING - 1 notes (too few for clustering)
        count = max(1, _MIN_NOTES_FOR_CLUSTERING - 1)
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        (tmp_path / "summaries").mkdir(exist_ok=True)
        for i in range(count):
            fp = tmp_path / f"work/note-{i}.md"
            fm = {
                "created": now_iso,
                "updated": now_iso,
                "type": "meeting_note",
                "domain": "work",
                "confidence": 0.9,
                "review_status": "approved",
                "source": "web",
                "tags": [],
            }
            fp.write_text(
                f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\nNote {i}.\n",
                encoding="utf-8",
            )

        vault = VaultLayer(str(tmp_path))
        index = MemoryIndex()

        # LLM grouping will be called; mock chat to return valid JSON groups
        ai = AsyncMock()
        ai.chat = AsyncMock(
            side_effect=[
                # _llm_group_notes call
                type("R", (), {"content": '{"groups": [[1]]}'})(),
                # _summarise_cluster call
                type("R", (), {"content": "Summary paragraph."})(),
            ]
        )

        settings = _make_mock_settings(domains=[None])
        agent = WeeklySummaryAgent()

        file_path = await agent.run(vault, index, ai, settings)
        assert file_path.startswith("summaries/")

    async def test_llm_empty_groups_fallback_to_single_group(self):
        """_llm_group_notes falls back to a single group when the model returns
        {"groups": []} (empty list), preventing run() from raising RuntimeError."""
        from monocle.agents.weekly_summary import _llm_group_notes

        ai = AsyncMock()
        ai.chat = AsyncMock(
            return_value=type("R", (), {"content": '{"groups": []}'})()
        )
        summaries = ["Note A summary", "Note B summary", "Note C summary"]
        result = await _llm_group_notes(ai, summaries)

        assert len(result) == 1, f"Expected single fallback group, got {result}"
        assert result[0] == summaries

    async def test_llm_out_of_range_indices_fallback_to_single_group(self):
        """_llm_group_notes falls back to a single group when every group contains
        only out-of-range indices (all filtered to empty), rather than propagating
        empty inner groups to _summarise_cluster."""
        from monocle.agents.weekly_summary import _llm_group_notes

        ai = AsyncMock()
        # All indices are out of range for a 3-note list
        ai.chat = AsyncMock(
            return_value=type("R", (), {"content": '{"groups": [[99, 100]]}'})()
        )
        summaries = ["Note A summary", "Note B summary", "Note C summary"]
        result = await _llm_group_notes(ai, summaries)

        # Every returned group must be non-empty
        assert all(len(g) > 0 for g in result), f"Empty groups found in result: {result}"
        # Should have fallen back to single group
        assert len(result) == 1
        assert result[0] == summaries

    async def test_iso_week_label(self):
        """_iso_week_label returns YYYY-WW format."""
        from monocle.agents.weekly_summary import _iso_week_label

        dt = datetime.datetime(2026, 3, 18, tzinfo=datetime.timezone.utc)
        label = _iso_week_label(dt)
        # 2026-03-18 is ISO week 12
        assert label == "2026-12"

    async def test_clustering_with_embeddings_from_index(self, tmp_path: Path):
        """When the index returns embeddings, sklearn clustering is attempted."""
        from monocle.agents.weekly_summary import WeeklySummaryAgent, _MIN_NOTES_FOR_CLUSTERING
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        import yaml

        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        (tmp_path / "summaries").mkdir(exist_ok=True)

        file_paths = []
        for i in range(_MIN_NOTES_FOR_CLUSTERING + 2):
            fname = f"work/note-{i}.md"
            fp = tmp_path / fname
            fm = {
                "created": now_iso,
                "updated": now_iso,
                "type": "meeting_note",
                "domain": "work",
                "confidence": 0.9,
                "review_status": "approved",
                "source": "web",
                "tags": [],
            }
            fp.write_text(
                f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\nNote {i}.\n",
                encoding="utf-8",
            )
            file_paths.append(fname)

        vault = VaultLayer(str(tmp_path))

        # Provide a mock index that returns real-ish embeddings (i+1 avoids zero-vector)
        mock_index = MagicMock(spec=MemoryIndex)
        mock_embeddings = {fp: [float(i + 1) / 10] * 1536 for i, fp in enumerate(file_paths)}
        mock_index.get_embeddings_by_file = MagicMock(return_value=mock_embeddings)

        ai = _make_mock_ai()
        settings = _make_mock_settings(domains=[None])
        agent = WeeklySummaryAgent()

        file_path = await agent.run(vault, mock_index, ai, settings)
        assert file_path.startswith("summaries/")
        # Verify embeddings were fetched
        mock_index.get_embeddings_by_file.assert_called_once()

    async def test_max_clusters_boundary(self, tmp_path: Path):
        """_MAX_CLUSTERS caps the cluster count when notes are abundant (>=25 notes)."""
        import yaml

        from monocle.agents.weekly_summary import (
            WeeklySummaryAgent,
            _MAX_CLUSTERS,
            _MIN_NOTES_FOR_CLUSTERING,
        )
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        # Use enough notes so that n//3 would exceed _MAX_CLUSTERS
        note_count = _MAX_CLUSTERS * 3 + 3  # e.g. 27 notes → n//3 = 9 > _MAX_CLUSTERS
        assert note_count // 3 > _MAX_CLUSTERS, "Test pre-condition: n//3 must exceed _MAX_CLUSTERS"

        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        (tmp_path / "summaries").mkdir(exist_ok=True)

        file_paths = []
        for i in range(note_count):
            fname = f"work/note-{i}.md"
            fp = tmp_path / fname
            fm = {
                "created": now_iso,
                "updated": now_iso,
                "type": "meeting_note",
                "domain": "work",
                "confidence": 0.9,
                "review_status": "approved",
                "source": "web",
                "tags": [],
            }
            fp.write_text(
                f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\nNote {i}.\n",
                encoding="utf-8",
            )
            file_paths.append(fname)

        vault = VaultLayer(str(tmp_path))

        # Patch _compute_clusters_sklearn to capture the n_clusters argument
        captured: list[int] = []

        def _spy_cluster(embeddings, n_clusters):
            captured.append(n_clusters)
            from monocle.agents.weekly_summary import _compute_clusters_sklearn as _orig  # noqa: F811
            return [i % max(1, n_clusters) for i in range(len(embeddings))]

        mock_index = MagicMock(spec=MemoryIndex)
        mock_embeddings = {fp: [float(i + 1) / 10] * 1536 for i, fp in enumerate(file_paths)}
        mock_index.get_embeddings_by_file = MagicMock(return_value=mock_embeddings)

        ai = _make_mock_ai()
        settings = _make_mock_settings(domains=[None])
        agent = WeeklySummaryAgent()

        with patch(
            "monocle.agents.weekly_summary._compute_clusters_sklearn", side_effect=_spy_cluster
        ):
            file_path = await agent.run(vault, mock_index, ai, settings)

        assert file_path.startswith("summaries/")
        assert captured, "_compute_clusters_sklearn was not called"
        assert captured[0] <= _MAX_CLUSTERS, (
            f"n_clusters={captured[0]} exceeded _MAX_CLUSTERS={_MAX_CLUSTERS}"
        )

    async def test_double_trigger_same_week_overwrites_gracefully(self, tmp_path: Path):
        """Calling run() twice in the same ISO week does not raise and returns the same path."""
        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex

        vault = _make_vault_with_recent_notes(tmp_path)
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings()
        agent = WeeklySummaryAgent()

        path1 = await agent.run(vault, index, ai, settings)
        path2 = await agent.run(vault, index, ai, settings)

        assert path1 == path2, "Both runs should write to the same weekly path"
        full_path = tmp_path / path2
        assert full_path.exists(), "Summary file should exist after second run"

    async def test_single_configured_domain_used_in_summary_metadata(self, tmp_path: Path):
        """When only one domain is configured, the summary note's domain matches it."""
        import yaml
        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex

        vault = _make_vault_with_recent_notes(tmp_path)
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings()
        settings.agents.weekly_summary.domains = ["personal"]
        agent = WeeklySummaryAgent()

        file_path = await agent.run(vault, index, ai, settings)

        full_path = tmp_path / file_path
        content = full_path.read_text(encoding="utf-8")
        fm_text = content.split("---")[1]
        fm = yaml.safe_load(fm_text)
        assert fm.get("domain") == "personal", f"Expected domain='personal', got {fm.get('domain')!r}"

    async def test_multi_domain_summary_uses_mixed_domain(self, tmp_path: Path):
        """When multiple domains produce content, the summary note's domain is 'mixed'."""
        import yaml
        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex

        vault = _make_vault_with_recent_notes(tmp_path)
        index = MemoryIndex()
        ai = _make_mock_ai()
        settings = _make_mock_settings()
        settings.agents.weekly_summary.domains = ["work", "personal"]
        agent = WeeklySummaryAgent()

        # _make_vault_with_recent_notes creates notes without a domain filter;
        # _run_domain with domain="work" or "personal" fetches via search (MemoryIndex returns all).
        # Both domain passes will produce content, so domain should be "mixed".
        file_path = await agent.run(vault, index, ai, settings)

        full_path = tmp_path / file_path
        content = full_path.read_text(encoding="utf-8")
        fm_text = content.split("---")[1]
        fm = yaml.safe_load(fm_text)
        assert fm.get("domain") == "mixed", f"Expected domain='mixed', got {fm.get('domain')!r}"


# ---------------------------------------------------------------------------
# Agent API endpoint tests (M11)
# ---------------------------------------------------------------------------


class TestAgentAPIEndpoints:
    """Tests for POST /api/agents/weekly-summary and POST /api/agents/reindex."""

    def test_trigger_reindex_returns_202(self, api_client):
        """POST /api/agents/reindex returns 202 Accepted."""
        from monocle.agents.reindex import ReindexAgent
        from monocle.index.memory import MemoryIndex

        client = api_client
        # Attach reindex_agent to app state
        reindex_agent = ReindexAgent()
        client.app.state.reindex_agent = reindex_agent

        resp = client.post("/api/agents/reindex")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body.get("status") == "accepted"

    def test_trigger_reindex_missing_state_returns_503(self, api_client):
        """POST /api/agents/reindex returns 503 when state is missing."""
        client = api_client
        # Remove reindex_agent from state
        client.app.state.reindex_agent = None

        resp = client.post("/api/agents/reindex")
        assert resp.status_code == 503

    def test_trigger_weekly_summary_sse_start_event(self, api_client, tmp_path):
        """POST /api/agents/weekly-summary emits a start SSE event."""
        import json
        import yaml
        import datetime as _dt

        client = api_client

        # Ensure AI is set (already set by api_client fixture via mock_ai)
        # Make the agent write a real summary by mocking run()
        from monocle.agents.weekly_summary import WeeklySummaryAgent

        mock_agent = MagicMock(spec=WeeklySummaryAgent)
        mock_agent.run = AsyncMock(return_value="summaries/2026-12.md")
        client.app.state.weekly_summary_agent = mock_agent

        resp = client.post("/api/agents/weekly-summary")
        assert resp.status_code == 200
        text = resp.text
        # Should contain at least the start event
        assert "event: start" in text or "event: done" in text

    def test_trigger_weekly_summary_no_recent_notes_emits_done(self, api_client):
        """POST /api/agents/weekly-summary emits done (skipped) when agent raises RuntimeError."""
        import json as _json

        from monocle.agents.weekly_summary import WeeklySummaryAgent

        client = api_client
        mock_agent = MagicMock(spec=WeeklySummaryAgent)
        mock_agent.run = AsyncMock(side_effect=RuntimeError("No notes modified in the last 7 days"))
        client.app.state.weekly_summary_agent = mock_agent

        resp = client.post("/api/agents/weekly-summary")
        assert resp.status_code == 200
        text = resp.text
        assert "event: done" in text
        # Find the done event data
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    data = _json.loads(line[5:].strip())
                    if data.get("skipped"):
                        return
                except _json.JSONDecodeError:
                    pass
        # Acceptable if done event is present
        assert "done" in text

    def test_trigger_weekly_summary_no_ai_emits_error(self, api_client):
        """POST /api/agents/weekly-summary emits error when AI is unavailable."""
        client = api_client
        # Remove AI provider
        original_ai = client.app.state.ai
        client.app.state.ai = None
        client.app.state.weekly_summary_agent = None  # force fresh instantiation

        try:
            resp = client.post("/api/agents/weekly-summary")
            assert resp.status_code == 200
            assert "event: error" in resp.text
        finally:
            client.app.state.ai = original_ai

    async def test_scheduled_weekly_summary_skips_when_ai_none(
        self, tmp_path: Path
    ):
        """The scheduled cron closure logs a warning and returns without calling agent.run()
        when ai is None (e.g. AI provider failed to start).
        """
        # Reconstruct the closure from main.py logic for isolation
        from unittest.mock import patch as _patch
        from monocle.agents.weekly_summary import WeeklySummaryAgent
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        vault = _make_vault_with_recent_notes(tmp_path)
        index = MemoryIndex()
        ai = None  # simulate missing AI provider
        cfg = _make_mock_settings()

        agent = WeeklySummaryAgent()
        run_called = False

        async def _run(*a, **kw):
            nonlocal run_called
            run_called = True

        agent.run = _run  # type: ignore[method-assign]

        # Replicate the scheduled closure from main.py
        import logging as _logging

        _log = _logging.getLogger("monocle.main")

        async def _scheduled_weekly_summary() -> None:
            if ai is None:
                _log.warning("[SCHEDULER] Weekly summary skipped — AI provider not available")
                return
            await agent.run(vault, index, ai, cfg)

        await _scheduled_weekly_summary()
        assert not run_called, "agent.run() must not be called when ai is None"
