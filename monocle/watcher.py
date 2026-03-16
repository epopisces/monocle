"""
monocle/watcher.py — InboxWatcher and ReindexQueue.

Phase 1: InboxWatcher runs as an integrated async task inside the unified
         FastAPI process (started/stopped in main.py lifespan).
Phase 3+: Can be extracted as a standalone OS process when
          server.separate_processes = true (via ProcessManager).

Wired in M5.  This stub is importable with no side-effects in M1.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ReindexQueue:
    """Asyncio-based per-file coalescing re-index queue.

    push(file_path) schedules a background re-index with a 10-second idle
    window per file — multiple pushes within the window collapse into one job.

    Wired in M5.
    """

    def push(self, file_path: str) -> None:  # noqa: D401
        """Schedule a re-index for file_path (no-op in M1 stub)."""
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class InboxWatcher:
    """Watches vault/inbox/ for new files and triggers the ingest pipeline.

    Wired in M5.
    """

    def __init__(self) -> None:
        self._running = False

    async def start(self) -> None:
        """Start watching the inbox (no-op stub in M1)."""
        self._running = True
        logger.debug("InboxWatcher.start() — stub (wired in M5)")

    async def stop(self) -> None:
        """Stop watching the inbox."""
        self._running = False

    def status(self) -> dict:
        return {"running": self._running}
