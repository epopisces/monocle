"""
monocle/process_manager.py — Optional multi-process orchestration.

Phase 1: Not used.  All components run in the unified FastAPI process.
Phase 3+: Set server.separate_processes=true to enable.

Stubbed here so imports resolve cleanly in M1.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages optional separate OS processes for watcher/scheduler.

    Wired in M23.
    """

    async def start_all(self) -> None:
        logger.debug("ProcessManager.start_all() — stub (wired in M23)")

    async def stop_all(self) -> None:
        pass

    def status(self) -> dict:
        return {"separate_processes": False}
