"""
monocle/tests/test_watcher.py — Unit tests for InboxWatcher and ReindexQueue.

Design notes
------------
- ``ReindexQueue`` tests run end-to-end using asyncio with a very short idle
  window (50 ms) to verify coalescing without waiting 10 seconds.
- ``InboxWatcher`` tests exercise the handler's ``dispatch()`` / debounce
  logic directly (synthetic watchdog events) to avoid depending on real
  filesystem events and OS-level timing.
- The watcher's ingest callback is always a mock so no real IngestPipeline is
  required (IngestPipeline is M7).
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monocle.watcher import (
    InboxWatcher,
    ReindexQueue,
    _InboxEventHandler,
    _write_error_sidecar,
)


# ---------------------------------------------------------------------------
# ReindexQueue tests
# ---------------------------------------------------------------------------


class TestReindexQueue:
    """Coalescing queue tests running with short idle windows."""

    async def test_single_push_fires_callback(self):
        """A single push fires the callback after the idle window."""
        fired: list[str] = []

        async def cb(fp: str) -> None:
            fired.append(fp)

        q = ReindexQueue()
        q.IDLE_WINDOW_S = 0.05
        await q.start()
        q.set_callback(cb)

        q.push("/vault/note.md")
        await asyncio.sleep(0.15)

        assert fired == ["/vault/note.md"]
        await q.stop()

    async def test_multiple_pushes_coalesce_to_one_call(self):
        """Three rapid pushes for the same path produce exactly one callback."""
        fired: list[str] = []

        async def cb(fp: str) -> None:
            fired.append(fp)

        q = ReindexQueue()
        q.IDLE_WINDOW_S = 0.05
        await q.start()
        q.set_callback(cb)

        q.push("/vault/note.md")
        q.push("/vault/note.md")
        q.push("/vault/note.md")
        await asyncio.sleep(0.15)

        assert len(fired) == 1, f"Expected 1 callback, got {len(fired)}"
        await q.stop()

    async def test_different_files_fire_independently(self):
        """Pushes for different paths each fire their own callback."""
        fired: list[str] = []

        async def cb(fp: str) -> None:
            fired.append(fp)

        q = ReindexQueue()
        q.IDLE_WINDOW_S = 0.05
        await q.start()
        q.set_callback(cb)

        q.push("/vault/a.md")
        q.push("/vault/b.md")
        await asyncio.sleep(0.15)

        assert sorted(fired) == ["/vault/a.md", "/vault/b.md"]
        await q.stop()

    async def test_stop_cancels_all_pending_tasks(self):
        """Stopping the queue before the idle window prevents callbacks from firing."""
        fired: list[str] = []

        async def cb(fp: str) -> None:
            fired.append(fp)

        q = ReindexQueue()
        q.IDLE_WINDOW_S = 0.5  # long enough for stop() to cancel
        await q.start()
        q.set_callback(cb)

        q.push("/vault/note.md")
        # Stop immediately — callback should never fire
        await q.stop()
        await asyncio.sleep(0.1)

        assert fired == [], "Callback should not fire after stop()"

    async def test_push_before_start_is_ignored(self):
        """push() before start() does not crash and produces no callback."""
        fired: list[str] = []

        async def cb(fp: str) -> None:
            fired.append(fp)

        q = ReindexQueue()
        q.set_callback(cb)
        q.push("/vault/note.md")  # loop is None — should be silently ignored
        await asyncio.sleep(0.1)
        assert fired == []

    async def test_no_callback_set_does_not_crash(self):
        """push() with no callback registered should not raise."""
        q = ReindexQueue()
        q.IDLE_WINDOW_S = 0.05
        await q.start()
        q.push("/vault/note.md")
        await asyncio.sleep(0.15)  # fires without crashing
        await q.stop()

    async def test_callback_exception_is_logged_not_silenced(self, caplog):
        """When the re-index callback raises, the exception is logged at ERROR
        level rather than silently swallowed or crashing the queue."""
        import logging

        async def raising_cb(fp: str) -> None:
            raise RuntimeError("index write failure")

        q = ReindexQueue()
        q.IDLE_WINDOW_S = 0.05
        await q.start()
        q.set_callback(raising_cb)

        with caplog.at_level(logging.ERROR, logger="monocle.watcher"):
            q.push("/vault/note.md")
            await asyncio.sleep(0.2)

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            f"Expected at least one ERROR log for callback exception; "
            f"got records: {[r.message for r in caplog.records]}"
        )
        combined = " ".join(r.message for r in error_records)
        assert "index write failure" in combined or "callback raised" in combined
        await q.stop()


# ---------------------------------------------------------------------------
# InboxWatcher — _on_stable_file logic
# ---------------------------------------------------------------------------


class TestInboxWatcherOnStableFile:
    """Test _on_stable_file without running a real watchdog observer."""

    async def test_stable_file_calls_ingest_callback(self, tmp_path: Path):
        """A stable .md file in the inbox triggers the ingest callback once."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        md_file = inbox / "capture.md"
        md_file.write_text("# Note\nContent", encoding="utf-8")

        calls: list[str] = []

        async def mock_ingest(fp: str) -> None:
            calls.append(fp)

        watcher = InboxWatcher(inbox_path=str(inbox), ingest_callback=mock_ingest)
        await watcher._on_stable_file(str(md_file))

        assert calls == [str(md_file)]

    async def test_no_callback_logs_warning_does_not_crash(
        self, tmp_path: Path, caplog
    ):
        """When no callback is set, _on_stable_file logs a warning and returns."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        md_file = inbox / "capture.md"
        md_file.write_text("# Note", encoding="utf-8")

        watcher = InboxWatcher(inbox_path=str(inbox))
        await watcher._on_stable_file(str(md_file))  # should not raise

    async def test_ingest_failure_writes_error_sidecar(self, tmp_path: Path):
        """A failing ingest callback causes a .error.md sidecar to be written."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        md_file = inbox / "capture.md"
        md_file.write_text("# Note\nContent", encoding="utf-8")

        async def failing_ingest(fp: str) -> None:
            raise ValueError("Routing pipeline failure")

        watcher = InboxWatcher(inbox_path=str(inbox), ingest_callback=failing_ingest)
        await watcher._on_stable_file(str(md_file))

        sidecar = Path(str(md_file) + ".error.md")
        assert sidecar.exists(), ".error.md sidecar should be written on ingest failure"
        content = sidecar.read_text(encoding="utf-8")
        assert "Routing pipeline failure" in content


# ---------------------------------------------------------------------------
# InboxWatcher — _InboxEventHandler dispatch + debounce
# ---------------------------------------------------------------------------


class TestInboxEventHandlerDispatch:
    """Test the watchdog event handler's file-filtering and debounce logic."""

    def _make_handler(
        self,
        inbox_path: str,
        on_stable: "AsyncMock",
        loop: asyncio.AbstractEventLoop,
        debounce_s: float = 0.05,
    ) -> _InboxEventHandler:
        timers: dict = {}
        timer_lock = threading.Lock()
        return _InboxEventHandler(
            inbox_path=inbox_path,
            on_stable_file=on_stable,
            debounce_s=debounce_s,
            timers=timers,
            timer_lock=timer_lock,
            loop=loop,
        )

    async def test_created_event_in_inbox_triggers_callback(self, tmp_path: Path):
        """FileCreatedEvent for .md in inbox fires the stable-file callback."""
        try:
            from watchdog.events import FileCreatedEvent
        except ImportError:
            pytest.skip("watchdog not installed")

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        md_file = inbox / "note.md"
        md_file.write_text("# Content", encoding="utf-8")

        loop = asyncio.get_running_loop()
        fired: list[str] = []

        async def on_stable(fp: str) -> None:
            fired.append(fp)

        handler = self._make_handler(str(inbox), on_stable, loop, debounce_s=0.05)
        handler.dispatch(FileCreatedEvent(str(md_file)))

        await asyncio.sleep(0.2)
        assert str(md_file) in fired

    async def test_non_md_file_ignored(self, tmp_path: Path):
        """Non-.md files (e.g., .txt, .pdf) are ignored by the handler."""
        try:
            from watchdog.events import FileCreatedEvent
        except ImportError:
            pytest.skip("watchdog not installed")

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        txt_file = inbox / "note.txt"
        txt_file.write_text("content", encoding="utf-8")

        loop = asyncio.get_running_loop()
        fired: list[str] = []

        async def on_stable(fp: str) -> None:
            fired.append(fp)

        handler = self._make_handler(str(inbox), on_stable, loop, debounce_s=0.05)
        handler.dispatch(FileCreatedEvent(str(txt_file)))

        await asyncio.sleep(0.2)
        assert fired == [], "Non-.md files should be ignored"

    async def test_file_outside_inbox_ignored(self, tmp_path: Path):
        """Files in vault subdirs outside inbox do NOT trigger the handler."""
        try:
            from watchdog.events import FileCreatedEvent
        except ImportError:
            pytest.skip("watchdog not installed")

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        people_dir = tmp_path / "people"
        people_dir.mkdir()
        other_file = people_dir / "note.md"
        other_file.write_text("# Person", encoding="utf-8")

        loop = asyncio.get_running_loop()
        fired: list[str] = []

        async def on_stable(fp: str) -> None:
            fired.append(fp)

        handler = self._make_handler(str(inbox), on_stable, loop, debounce_s=0.05)
        handler.dispatch(FileCreatedEvent(str(other_file)))

        await asyncio.sleep(0.2)
        assert fired == [], "Files outside inbox should be ignored"

    async def test_two_rapid_creates_coalesce_to_one_callback(self, tmp_path: Path):
        """Two rapid FileCreatedEvents for the same path produce one callback."""
        try:
            from watchdog.events import FileCreatedEvent
        except ImportError:
            pytest.skip("watchdog not installed")

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        md_file = inbox / "note.md"
        md_file.write_text("# Content", encoding="utf-8")

        loop = asyncio.get_running_loop()
        fired: list[str] = []

        async def on_stable(fp: str) -> None:
            fired.append(fp)

        handler = self._make_handler(str(inbox), on_stable, loop, debounce_s=0.05)
        # Fire two events in rapid succession
        handler.dispatch(FileCreatedEvent(str(md_file)))
        handler.dispatch(FileCreatedEvent(str(md_file)))

        await asyncio.sleep(0.2)
        assert len(fired) == 1, f"Expected 1 callback, got {len(fired)}: {fired}"

    async def test_moved_event_uses_dest_path(self, tmp_path: Path):
        """FileMovedEvent (atomic editor save) triggers callback with dest_path.

        Editors such as VS Code and Obsidian perform atomic saves by writing to
        a temp path then renaming to the final path, which produces a
        FileMovedEvent rather than a FileCreatedEvent.
        """
        try:
            from watchdog.events import FileMovedEvent
        except ImportError:
            pytest.skip("watchdog not installed")

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        dest_file = inbox / "note.md"
        dest_file.write_text("# Moved", encoding="utf-8")
        src_tmp = inbox / "note.md.tmp"  # temp path used during atomic save

        loop = asyncio.get_running_loop()
        fired: list[str] = []

        async def on_stable(fp: str) -> None:
            fired.append(fp)

        handler = self._make_handler(str(inbox), on_stable, loop, debounce_s=0.05)
        handler.dispatch(FileMovedEvent(str(src_tmp), str(dest_file)))

        await asyncio.sleep(0.2)
        assert str(dest_file) in fired, (
            f"Expected dest_path {dest_file!r} in fired; got {fired}"
        )
        assert str(src_tmp) not in fired, "src_path should not be in fired list"

    async def test_error_sidecar_not_dispatched(self, tmp_path: Path):
        """A FileCreatedEvent for a .error.md sidecar is silently dropped.

        When an ingest fails, _write_error_sidecar writes a .error.md file in
        the inbox.  That write generates a watchdog FileCreatedEvent.  If the
        handler processed it, the ingest would fail again, writing another
        sidecar — an infinite cascade.  The filter must break the loop by
        ignoring any .error.md file.
        """
        try:
            from watchdog.events import FileCreatedEvent
        except ImportError:
            pytest.skip("watchdog not installed")

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        sidecar = inbox / "capture.md.error.md"
        sidecar.write_text("---\ntype: ingest_error\n---\n", encoding="utf-8")

        loop = asyncio.get_running_loop()
        fired: list[str] = []

        async def on_stable(fp: str) -> None:
            fired.append(fp)

        handler = self._make_handler(str(inbox), on_stable, loop, debounce_s=0.05)
        handler.dispatch(FileCreatedEvent(str(sidecar)))

        await asyncio.sleep(0.2)
        assert fired == [], (
            f".error.md sidecar should be ignored to prevent cascade; fired={fired}"
        )


# ---------------------------------------------------------------------------
# _write_error_sidecar helper
# ---------------------------------------------------------------------------


class TestWriteErrorSidecar:
    def test_writes_sidecar_file(self, tmp_path: Path):
        """_write_error_sidecar creates a .error.md file alongside the source."""
        md_file = tmp_path / "capture.md"
        md_file.write_text("# Note", encoding="utf-8")

        _write_error_sidecar(str(md_file), ValueError("Something went wrong"))

        sidecar = Path(str(md_file) + ".error.md")
        assert sidecar.exists()
        content = sidecar.read_text(encoding="utf-8")
        assert "Something went wrong" in content
        assert "capture.md" in content

    def test_sidecar_contains_frontmatter_type(self, tmp_path: Path):
        """The sidecar has YAML frontmatter with type: ingest_error."""
        md_file = tmp_path / "note.md"
        md_file.write_text("# Note", encoding="utf-8")

        _write_error_sidecar(str(md_file), RuntimeError("boom"))

        sidecar = Path(str(md_file) + ".error.md")
        content = sidecar.read_text(encoding="utf-8")
        assert "type: ingest_error" in content


# ---------------------------------------------------------------------------
# InboxWatcher integration (start/stop lifecycle)
# ---------------------------------------------------------------------------


class TestInboxWatcherLifecycle:
    async def test_start_creates_inbox_dir(self, tmp_path: Path):
        """start() creates the inbox directory if it does not exist."""
        inbox = tmp_path / "new_inbox"
        assert not inbox.exists()

        watcher = InboxWatcher(inbox_path=str(inbox))
        await watcher.start()
        assert inbox.exists()
        await watcher.stop()

    async def test_status_running(self, tmp_path: Path):
        """status() reports running=True after start and False baseline."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()

        watcher = InboxWatcher(inbox_path=str(inbox))
        assert watcher.status()["running"] is False

        await watcher.start()
        assert watcher.status()["running"] is True

        await watcher.stop()
        assert watcher.status()["running"] is False
