"""
monocle/watcher.py — InboxWatcher and ReindexQueue.

Phase 1: InboxWatcher runs as an integrated async task inside the unified
         FastAPI process (started/stopped in main.py lifespan via the
         asynccontextmanager).
Phase 3+: Can be extracted as a standalone OS process when
          server.separate_processes = true (via ProcessManager).

Architecture
------------
InboxWatcher
  - watchdog.Observer thread watches vault/inbox/ (non-recursive).
  - 2-second per-file debounce collapses rapid multi-write saves (e.g. partial
    writes, editor temp files) into a single ingest trigger.
  - On trigger: schedules the configured ingest_callback coroutine on the
    running asyncio event loop via asyncio.run_coroutine_threadsafe().
  - On ingest failure: writes a .error.md sidecar alongside the source file.

ReindexQueue
  - asyncio-based per-file coalescing queue (10-second idle window).
  - push(file_path) cancels any pending task for that path and starts a new
    10-second countdown; only the last push within the window fires the
    re-index callback.
  - push() is thread-safe via loop.call_soon_threadsafe().
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   ReindexQueue
# ---------------------------------------------------------------------------


class ReindexQueue:
    """Asyncio-based per-file coalescing re-index queue.

    ``push(file_path)`` schedules a background re-index with a 10-second idle
    window per file — multiple pushes for the same path within the window
    collapse into one re-index job.

    Thread-safe: ``push()`` may be called from the watchdog observer thread or
    any other non-async thread.
    """

    IDLE_WINDOW_S: float = 10.0

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._callback: Callable[[str], Coroutine[Any, Any, None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_callback(self, cb: Callable[[str], Coroutine[Any, Any, None]]) -> None:
        """Register the coroutine function called when a coalesced re-index fires.

        The callback receives the ``file_path`` as its only argument.
        """
        self._callback = cb

    async def start(self) -> None:
        """Capture the running event loop so push() can schedule across threads."""
        self._loop = asyncio.get_running_loop()
        logger.debug("[WATCHER] ReindexQueue started (idle_window=%.1fs)", self.IDLE_WINDOW_S)

    async def stop(self) -> None:
        """Cancel all pending coalescing tasks and await their cleanup.

        Gathering the cancelled tasks ensures each one has surfaced its
        ``CancelledError`` and completed any ``finally`` / ``__aexit__``
        cleanup before this coroutine returns.  Without the gather, the loop
        may be torn down while the tasks are still pending, triggering
        ``Task was destroyed but it is pending!`` warnings and potentially
        allowing callbacks to run during teardown.
        """
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug("[WATCHER] ReindexQueue stopped")

    def push(self, file_path: str) -> None:
        """Schedule a coalesced re-index for *file_path*.

        Thread-safe.  If the loop is not running (e.g. before startup or after
        shutdown) the call is silently ignored.

        **Trust boundary:** callers are responsible for validating *file_path*
        against the vault root before calling ``push()``.  This method applies
        no path filtering — it schedules whatever path it receives.  Route
        handlers (M8) must ensure *file_path* is a vault-relative string that
        has already passed ``VaultLayer._safe_resolve()`` before enqueueing.
        """
        if self._loop is None or not self._loop.is_running():
            logger.debug(
                "[WATCHER] ReindexQueue.push ignored (loop not running): %s", file_path
            )
            return
        # Reschedule from the event loop thread to safely manipulate asyncio tasks
        self._loop.call_soon_threadsafe(self._reschedule, file_path)

    def _reschedule(self, file_path: str) -> None:
        """Cancel any existing task for *file_path* and start a fresh countdown.

        Must run on the event loop thread.
        """
        existing = self._tasks.pop(file_path, None)
        if existing is not None and not existing.done():
            existing.cancel()

        task = asyncio.ensure_future(self._debounced_reindex(file_path))
        self._tasks[file_path] = task

    async def _debounced_reindex(self, file_path: str) -> None:
        try:
            await asyncio.sleep(self.IDLE_WINDOW_S)
            self._tasks.pop(file_path, None)
            logger.debug("[WATCHER] ReindexQueue firing re-index: %s", file_path)
            if self._callback is not None:
                await self._callback(file_path)
        except asyncio.CancelledError:
            logger.debug("[WATCHER] ReindexQueue: coalesced task cancelled for %s", file_path)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[WATCHER] ReindexQueue: callback raised for %s: %s",
                file_path,
                exc,
                exc_info=True,
            )


#endregion

# ---------------------------------------------------------------------------
#region #*   InboxWatcher
# ---------------------------------------------------------------------------


class InboxWatcher:
    """Watches ``vault/inbox/`` for new files and triggers the ingest pipeline.

    Uses ``watchdog.Observer`` (non-recursive) to detect file-system events on
    the inbox directory.  A per-file debounce (default 2 s, configurable via
    ``debounce_s`` constructor argument or ``settings.vault.debounce_ms``) prevents
    double-triggering when editors write files in multiple partial steps.

    The watcher is designed for Phase 1 (integrated async task) and Phase 3+
    (optional standalone process).  The ``start()`` / ``stop()`` / ``status()``
    interface is compatible with the future ProcessManager API.
    """

    DEBOUNCE_S: float = 2.0  # class-level default; override via constructor

    def __init__(
        self,
        inbox_path: str,
        ingest_callback: (
            Callable[[str], Coroutine[Any, Any, None]] | None
        ) = None,
        debounce_s: float | None = None,
    ) -> None:
        """Initialise the watcher.

        Parameters
        ----------
        inbox_path:
            Absolute or relative path to the inbox directory to watch.
        ingest_callback:
            Async callable ``(file_path: str) -> None`` invoked when a new or
            modified ``.md`` file is stable in the inbox.  When ``None`` the
            watcher logs the event but does not process it (useful during
            development before the ingest pipeline is wired in M7).
        debounce_s:
            Per-file debounce window in seconds.  When ``None`` the class
            default ``DEBOUNCE_S`` (2.0 s) is used.  Pass
            ``settings.vault.debounce_ms / 1000`` at construction time so the
            live value always matches the user's config and configuration drift
            between the class constant and ``vault.debounce_ms`` is impossible.
        """
        self._inbox_path = os.path.realpath(inbox_path)
        self._ingest_callback = ingest_callback
        self._debounce_s: float = debounce_s if debounce_s is not None else self.DEBOUNCE_S
        self._running = False
        self._observer: Any = None  # watchdog.Observer; lazy import
        self._loop: asyncio.AbstractEventLoop | None = None

        # Per-file debounce: file_path -> threading.Timer
        self._timers: dict[str, threading.Timer] = {}
        self._timer_lock = threading.Lock()

    def set_ingest_callback(
        self, cb: Callable[[str], Coroutine[Any, Any, None]]
    ) -> None:
        """Register (or replace) the ingest coroutine function."""
        self._ingest_callback = cb

    async def start(self) -> None:
        """Start the watchdog observer on the inbox directory.

        Creates the inbox directory if it does not exist.  Captures the running
        event loop for thread-safe scheduling of async callbacks.
        """
        try:
            from watchdog.observers import Observer
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "watchdog is required for InboxWatcher. "
                "Install it with: uv add watchdog"
            ) from exc

        self._loop = asyncio.get_running_loop()
        os.makedirs(self._inbox_path, exist_ok=True)

        handler = _InboxEventHandler(
            inbox_path=self._inbox_path,
            on_stable_file=self._on_stable_file,
            debounce_s=self._debounce_s,
            timers=self._timers,
            timer_lock=self._timer_lock,
            loop=self._loop,
        )

        self._observer = Observer()
        self._observer.schedule(handler, self._inbox_path, recursive=False)
        self._observer.start()
        self._running = True
        logger.info("[WATCHER] InboxWatcher started — watching %s", self._inbox_path)

    async def stop(self) -> None:
        """Stop the watchdog observer and cancel any pending debounce timers."""
        self._running = False

        # Cancel pending debounce timers
        with self._timer_lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

        if self._observer is not None:
            self._observer.stop()
            # join() is blocking; run in executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._observer.join)
            self._observer = None

        logger.info("[WATCHER] InboxWatcher stopped")

    def status(self) -> dict:
        """Return a dict describing current watcher state."""
        with self._timer_lock:
            pending = list(self._timers.keys())
        return {
            "running": self._running,
            "inbox_path": self._inbox_path,
            "pending_debounce": pending,
        }

    async def _on_stable_file(self, file_path: str) -> None:
        """Called when a file in the inbox has been stable for DEBOUNCE_S seconds."""
        logger.info("[WATCHER] Stable file detected: %s", file_path)

        if self._ingest_callback is None:
            logger.warning(
                "[WATCHER] No ingest callback configured — skipping %s "
                "(ingest pipeline will be wired in M7)",
                file_path,
            )
            return

        try:
            await self._ingest_callback(file_path)
            # Delete inbox source file after successful ingest (FR-WTCH-02)
            from pathlib import Path as _Path
            try:
                await asyncio.to_thread(_Path(file_path).unlink)
                logger.info("[WATCHER] Deleted inbox file after successful ingest: %s", file_path)
            except FileNotFoundError:
                logger.debug("[WATCHER] Inbox file already deleted: %s", file_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("[WATCHER] Ingest failed for %s: %s", file_path, exc, exc_info=True)
            _write_error_sidecar(file_path, exc)


#endregion

# ---------------------------------------------------------------------------
#region #*   watchdog event handler
# ---------------------------------------------------------------------------


class _InboxEventHandler:
    """watchdog FileSystemEventHandler that debounces file creation/modification.

    Only ``.md`` files directly inside the inbox (not in subdirs) are handled.

    This class dynamically inherits from watchdog's ``FileSystemEventHandler``
    at instantiation time so the watchdog dependency is not imported at module
    load (keeping the module importable in test environments without watchdog).
    """

    def __init__(
        self,
        inbox_path: str,
        on_stable_file: Callable[[str], Coroutine[Any, Any, None]],
        debounce_s: float,
        timers: dict[str, threading.Timer],
        timer_lock: threading.Lock,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._inbox_path = inbox_path
        self._on_stable_file = on_stable_file
        self._debounce_s = debounce_s
        self._timers = timers
        self._timer_lock = timer_lock
        self._loop = loop

        # Dynamically inherit watchdog base class so dispatch() is recognised
        try:
            from watchdog.events import FileSystemEventHandler as _Base

            self.__class__ = type(
                "_InboxEventHandlerImpl",
                (_InboxEventHandler, _Base),
                {},
            )
            _Base.__init__(self)  # type: ignore[call-arg]
        except ImportError:
            pass

    def dispatch(self, event: Any) -> None:  # type: ignore[override]
        """Filter and debounce watchdog events."""
        try:
            from watchdog.events import (
                FileCreatedEvent,
                FileModifiedEvent,
                FileMovedEvent,
            )
        except ImportError:
            return

        if not isinstance(event, (FileCreatedEvent, FileModifiedEvent, FileMovedEvent)):
            return

        # For moved/renamed events (atomic saves) use the destination path
        src_path: str = (
            event.dest_path  # type: ignore[attr-defined]
            if isinstance(event, FileMovedEvent)
            else event.src_path
        )

        # Only handle .md files directly in the inbox directory (no subdirs).
        # Explicitly exclude .error.md sidecars to prevent a cascade loop where
        # writing the sidecar fires a new ingest event, which fails, which writes
        # another sidecar, and so on.
        if not src_path.endswith(".md") or src_path.endswith(".error.md"):
            return
        if os.path.dirname(os.path.realpath(src_path)) != self._inbox_path:
            return

        self._schedule_debounce(src_path)

    def _schedule_debounce(self, file_path: str) -> None:
        with self._timer_lock:
            existing = self._timers.pop(file_path, None)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(
                interval=self._debounce_s,
                function=self._fire,
                args=(file_path,),
            )
            self._timers[file_path] = timer
            timer.start()

    def _fire(self, file_path: str) -> None:
        """Called by the timer thread after the debounce window expires."""
        with self._timer_lock:
            self._timers.pop(file_path, None)

        if not os.path.isfile(file_path):
            logger.debug("[WATCHER] Debounced file no longer exists: %s", file_path)
            return

        # Guard: if the event loop is no longer running (e.g. stop() was called
        # between the timer firing and this point) there is nothing to schedule.
        if not self._loop.is_running():
            logger.debug(
                "[WATCHER] Event loop stopped before ingest could be scheduled: %s",
                file_path,
            )
            return

        # Create the coroutine first so we can close() it on a RuntimeError
        # (avoids a "coroutine was never awaited" ResourceWarning in that path).
        coro = self._on_stable_file(file_path)
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except RuntimeError:
            # TOCTOU: loop closed between the is_running() check and here.
            coro.close()
            logger.debug(
                "[WATCHER] Event loop closed before ingest could be scheduled: %s",
                file_path,
            )
            return

        # Observe the Future so any unexpected exception that escapes
        # _on_stable_file's own try/except is logged rather than silently dropped.
        future.add_done_callback(_log_future_exception)


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _log_future_exception(future: concurrent.futures.Future) -> None:  # type: ignore[type-arg]
    """Done-callback for run_coroutine_threadsafe futures.

    Retrieves the result so that any exception stored on the future is logged
    rather than silently swallowed.  ``CancelledError`` is ignored — it means
    the event loop shut down cleanly while the coroutine was in flight.
    """
    try:
        future.result()
    except concurrent.futures.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[WATCHER] Unhandled exception in _on_stable_file future: %s",
            exc,
            exc_info=True,
        )


def _write_error_sidecar(source_path: str, exc: Exception) -> None:
    """Write a ``.error.md`` sidecar alongside *source_path* describing *exc*."""
    import yaml  # lazy import — mirrors the watchdog lazy-import pattern

    sidecar_path = source_path + ".error.md"
    try:
        # Use yaml.dump to safely quote the filename and avoid YAML injection
        # when a filename contains special characters (colons, newlines, etc.).
        basename = os.path.basename(source_path)
        fm = {
            "type": "ingest_error",
            "source_file": basename,
        }
        content = (
            f"---\n{yaml.dump(fm, default_flow_style=False)}"
            "---\n\n"
            f"Ingest failed for `{basename}`:\n\n"
            f"```\n{exc}\n```\n"
        )
        Path(sidecar_path).write_text(content, encoding="utf-8")
        logger.info("[WATCHER] Wrote error sidecar: %s", sidecar_path)
    except OSError as write_exc:
        logger.error(
            "[WATCHER] Failed to write error sidecar %s: %s", sidecar_path, write_exc
        )
