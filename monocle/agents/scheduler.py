"""
monocle/agents/scheduler.py — APScheduler integration for Monocle.

Phase 1: Runs as an integrated component of the unified FastAPI process.
         The ``AsyncIOScheduler`` is started inside the app lifespan context
         and shares the running event loop.

Scheduled tasks
---------------
weekly_summary
    Cron expression from ``agents.weekly_summary.cron`` (default: Fridays 17:00).
    Calls the ``WeeklySummaryAgent`` (implemented in M11 — job is a no-op stub
    until then).

reindex
    Cron expression from ``agents.reindex.cron`` (default: Sundays 03:00).
    Calls ``ReindexAgent.run(vault, index)`` for incremental re-indexing.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from monocle.config import Settings

logger = logging.getLogger(__name__)


class MonocleScheduler:
    """Thin wrapper around APScheduler's ``AsyncIOScheduler``.

    Responsibilities:
    -  Start / stop the scheduler in the app lifespan.
    -  Register cron jobs for periodic tasks.
    -  Provide a ``status()`` dict for the health endpoint.

    Job functions are injected as callables at registration time so this
    class has no direct dependency on VaultLayer, IndexLayer, or agent
    implementations — keeping it testable in isolation.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._scheduler = None  # lazy: created in start()

    async def start(self) -> None:
        """Create and start the ``AsyncIOScheduler``."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "apscheduler is required for scheduled jobs. "
                "Install it with: uv add apscheduler"
            ) from exc

        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        logger.info("[SCHEDULER] APScheduler started")

    async def stop(self) -> None:
        """Shut down the scheduler without waiting for running jobs."""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None  # status() uses None-check; clear so running=False
            logger.info("[SCHEDULER] APScheduler stopped")

    def status(self) -> dict:
        """Return a dict suitable for embedding in the health endpoint."""
        if self._scheduler is None:
            return {"running": False, "jobs": []}
        return {
            "running": self._scheduler.running,
            "jobs": [
                {"id": job.id, "next_run": str(job.next_run_time)}
                for job in self._scheduler.get_jobs()
            ],
        }

    def add_cron_job(
        self,
        job_id: str,
        func: Callable,
        cron_expression: str,
        *args,
        **kwargs,
    ) -> None:
        """Register a cron job from a 5-field cron string.

        Parameters
        ----------
        job_id:
            Unique string identifier (used for logging and status).
        func:
            Async callable to invoke.
        cron_expression:
            Standard 5-field cron string, e.g. ``"0 17 * * 5"`` (Fri 17:00).
        *args / **kwargs:
            Passed through to *func* when the job fires.
        """
        if self._scheduler is None:
            raise RuntimeError("Scheduler not started — call start() first")

        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(
                f"cron_expression must have 5 fields, got {len(parts)}: {cron_expression!r}"
            )
        minute, hour, day, month, day_of_week = parts

        self._scheduler.add_job(
            func,
            trigger="cron",
            id=job_id,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            args=args,
            kwargs=kwargs,
            replace_existing=True,
            misfire_grace_time=3600,  # 1-hour grace window for missed fires
        )
        logger.info(
            "[SCHEDULER] Registered job '%s' with cron '%s'", job_id, cron_expression
        )


# Backward-compat alias — the double-o variant was a typo introduced in M5.
# Remove after M6.
MoocleScheduler = MonocleScheduler
