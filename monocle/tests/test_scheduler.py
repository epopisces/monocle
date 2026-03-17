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
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

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
    def test_moocle_alias_is_same_class(self):
        """MoocleScheduler (typo alias) resolves to the same class as MonocleScheduler."""
        from monocle.agents.scheduler import MoocleScheduler, MonocleScheduler

        assert MoocleScheduler is MonocleScheduler
