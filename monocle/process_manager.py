"""
monocle/process_manager.py — Optional multi-process orchestration.

Phase 1: Not used.  All components run in the unified FastAPI process
         (separate_processes=False, the default).

Phase 3+: Set ``server.separate_processes: true`` in config.yaml (or pass
          ``--separate-processes`` to ``monocle serve`` / ``monocle dev``) to
          extract the inbox watcher and APScheduler into standalone OS processes.
          The main API process becomes the "capture" server only.

When inactive (``separate_processes=False``) this module is a complete no-op — no
changes to M1–M22 core code are required.  ProcessManager is fully opt-in.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.config import Settings

logger = logging.getLogger(__name__)


class SubprocessHandle:
    """Manages a single long-running subprocess with exponential-backoff crash-restart."""

    _MAX_BACKOFF_S: float = 30.0
    _BASE_BACKOFF_S: float = 1.0

    def __init__(self, name: str, args: list[str]) -> None:
        self.name = name
        self.args = args
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._restart_count = 0

    async def start(self) -> None:
        """Spawn the subprocess and begin the supervisor loop."""
        self._running = True
        self._task = asyncio.create_task(self._supervise(), name=f"pm-{self.name}")
        self._task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task) -> None:
        if not task.cancelled():
            exc = task.exception()
            if exc:
                logger.error(
                    "[ProcessManager] Supervisor for %s raised: %s", self.name, exc
                )

    async def stop(self) -> None:
        """Terminate the subprocess and cancel the supervisor task."""
        self._running = False
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "[ProcessManager] %s did not exit cleanly; sending SIGKILL", self.name
                )
                self._proc.kill()
                await self._proc.wait()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _supervise(self) -> None:
        """Supervisor loop: spawn → wait → restart with exponential backoff."""
        backoff = self._BASE_BACKOFF_S
        while self._running:
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *self.args,
                    # Inherit parent stdin/stdout/stderr so log output is visible.
                    stdin=None,
                    stdout=None,
                    stderr=None,
                )
                logger.info(
                    "[ProcessManager] Started subprocess %s (pid=%d)",
                    self.name,
                    self._proc.pid,
                )
                await self._proc.wait()
                if not self._running:
                    break
                exit_code = self._proc.returncode
                self._restart_count += 1
                logger.warning(
                    "[ProcessManager] Subprocess %s exited (code=%s),"
                    " restarting (#%d) in %.0fs",
                    self.name,
                    exit_code,
                    self._restart_count,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._MAX_BACKOFF_S)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "[ProcessManager] Failed to start subprocess %s: %s", self.name, exc
                )
                if self._running:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self._MAX_BACKOFF_S)

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def restart_count(self) -> int:
        return self._restart_count


class ProcessManager:
    """Manages optional separate OS processes for watcher and scheduler.

    Activated by ``server.separate_processes: true`` in ``config.yaml`` or by
    the ``MONOCLE_SEPARATE_PROCESSES=1`` environment variable (set by
    ``monocle serve --separate-processes`` / ``monocle dev --separate-processes``).

    When inactive (the default), all components run inside the unified process
    and this class is a complete no-op — no changes to M1–M22 core code are
    required.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._processes: dict[str, SubprocessHandle] = {}

    def _make_args(self, command: str) -> list[str]:
        """Build subprocess argv for a ``monocle <command>`` subcommand."""
        return [sys.executable, "-m", "monocle", command]

    def _is_separate_processes_enabled(self) -> bool:
        """Compute the effective separate-processes flag.

        Returns True if EITHER:
          - config.server.separate_processes is True, OR
          - MONOCLE_SEPARATE_PROCESSES=1 env var is set
        """
        return self._settings.server.separate_processes or os.environ.get(
            "MONOCLE_SEPARATE_PROCESSES"
        ) == "1"

    async def start_all(self) -> None:
        """Spawn all separable component subprocesses.

        Idempotent: calling start_all() multiple times is safe. If a subprocess
        handle already exists and is running, it will not be respawned.

        No-op when the effective separate-processes flag is False (neither config
        setting nor MONOCLE_SEPARATE_PROCESSES env var is set).
        """
        if not self._is_separate_processes_enabled():
            logger.debug(
                "[ProcessManager] separate_processes disabled — unified mode, no subprocesses"
            )
            return

        logger.info("[ProcessManager] Starting separated component processes")
        for name in ("watch", "scheduler"):
            # Idempotency guard: skip if a handle already exists and is running.
            # This prevents duplicate subprocess spawning on repeated start_all() calls.
            if name in self._processes:
                handle = self._processes[name]
                if handle.is_running:
                    logger.debug(
                        "[ProcessManager] Subprocess %s already running (pid=%d), skipping",
                        name,
                        handle.pid,
                    )
                    continue
                else:
                    # Handle exists but is not running (crashed or stopped).
                    # Clean it up and create a replacement.
                    logger.debug(
                        "[ProcessManager] Subprocess %s was running but exited (code=%s),"
                        " restarting",
                        name,
                        handle._proc.returncode if handle._proc else None,
                    )

            handle = SubprocessHandle(name, self._make_args(name))
            await handle.start()
            self._processes[name] = handle
        logger.info("[ProcessManager] All component subprocesses launched")

    async def stop_all(self) -> None:
        """Terminate all managed subprocesses."""
        for name, handle in list(self._processes.items()):
            logger.info("[ProcessManager] Stopping subprocess: %s", name)
            await handle.stop()
        self._processes.clear()

    def status(self) -> dict:
        """Return a status dict suitable for embedding in the health endpoint.

        The returned ``separate_processes`` field reflects the effective flag
        (config + env var), not just the config value.
        """
        return {
            "separate_processes": self._is_separate_processes_enabled(),
            "processes": {
                name: {
                    "running": handle.is_running,
                    "pid": handle.pid,
                    "restart_count": handle.restart_count,
                }
                for name, handle in self._processes.items()
            },
        }
