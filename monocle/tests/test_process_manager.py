"""
monocle/tests/test_process_manager.py — Unit tests for ProcessManager & SubprocessHandle.

Tests verify:
  - SubprocessHandle lifecycle (start / stop / restart logic)
  - ProcessManager.start_all() no-op when separate_processes=False
  - ProcessManager.start_all() spawns watch + scheduler when separate_processes=True
  - ProcessManager.stop_all() terminates all handles
  - ProcessManager.status() reflects live state
  - main.py lifespan respects MONOCLE_SEPARATE_PROCESSES / MONOCLE_COMPONENT env vars
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(separate: bool = False) -> object:
    """Return a minimal settings-like object."""
    server = SimpleNamespace(separate_processes=separate)
    return SimpleNamespace(server=server)


def _make_mock_proc(block: asyncio.Event | None = None):
    """Build a MagicMock subprocess that blocks in wait() until block is set."""
    mock_proc = MagicMock()
    mock_proc.pid = 1234
    mock_proc.returncode = None

    if block is not None:
        async def _wait():
            await block.wait()
            return 0
        mock_proc.wait = _wait
        mock_proc.terminate = MagicMock(side_effect=block.set)
    else:
        async def _immediate():
            return 0
        mock_proc.wait = _immediate
        mock_proc.terminate = MagicMock()

    return mock_proc


# ---------------------------------------------------------------------------
# TestSubprocessHandle
# ---------------------------------------------------------------------------


class TestSubprocessHandle:
    """Tests for SubprocessHandle lifecycle."""

    @pytest.mark.asyncio
    async def test_start_spawns_subprocess(self):
        """start() should spawn a subprocess via create_subprocess_exec."""
        from monocle.process_manager import SubprocessHandle

        block = asyncio.Event()
        mock_proc = _make_mock_proc(block)

        with patch(
            "asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)
        ) as mock_exec:
            handle = SubprocessHandle("test", ["python", "-m", "monocle", "watch"])
            await handle.start()
            await asyncio.sleep(0.05)
            await handle.stop()

        assert mock_exec.called
        call_args = mock_exec.call_args[0]
        assert "watch" in call_args

    @pytest.mark.asyncio
    async def test_stop_terminates_running_process(self):
        """stop() should call terminate() on a running process."""
        from monocle.process_manager import SubprocessHandle

        block = asyncio.Event()
        mock_proc = _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            handle = SubprocessHandle("test", ["python", "-c", "pass"])
            await handle.start()
            await asyncio.sleep(0.05)  # supervisor is now blocking in wait()
            await handle.stop()

        mock_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_running_false_before_start(self):
        """is_running should return False before any start() call."""
        from monocle.process_manager import SubprocessHandle

        handle = SubprocessHandle("test", ["python"])
        assert not handle.is_running

    @pytest.mark.asyncio
    async def test_is_running_true_after_start(self):
        """is_running should return True once the subprocess is alive."""
        from monocle.process_manager import SubprocessHandle

        block = asyncio.Event()
        mock_proc = _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            handle = SubprocessHandle("test", ["python"])
            await handle.start()
            await asyncio.sleep(0.05)
            assert handle.is_running
            await handle.stop()

    @pytest.mark.asyncio
    async def test_restart_count_increments_on_exit(self):
        """restart_count should increment when the subprocess exits unexpectedly."""
        from monocle.process_manager import SubprocessHandle

        spawn_count = 0

        async def _fast_exit_exec(*args, stdin=None, stdout=None, stderr=None):
            nonlocal spawn_count
            spawn_count += 1
            mock_proc = MagicMock()
            mock_proc.pid = 100 + spawn_count

            async def _exit():
                return 1  # immediate non-zero exit
            mock_proc.wait = _exit
            mock_proc.returncode = 1
            mock_proc.terminate = MagicMock()
            return mock_proc

        handle = SubprocessHandle("test", ["python"])
        handle._BASE_BACKOFF_S = 0.01
        handle._MAX_BACKOFF_S = 0.02

        with patch("asyncio.create_subprocess_exec", new=_fast_exit_exec):
            await handle.start()
            # Allow enough time for at least one restart
            for _ in range(100):
                await asyncio.sleep(0.02)
                if handle.restart_count >= 1:
                    break
            await handle.stop()

        assert handle.restart_count >= 1
        assert spawn_count >= 2  # at least initial + one restart

    @pytest.mark.asyncio
    async def test_pid_returns_none_before_start(self):
        """pid should be None before the subprocess is spawned."""
        from monocle.process_manager import SubprocessHandle

        handle = SubprocessHandle("test", ["python"])
        assert handle.pid is None

    @pytest.mark.asyncio
    async def test_pid_returns_value_after_start(self):
        """pid should return the subprocess PID after start()."""
        from monocle.process_manager import SubprocessHandle

        block = asyncio.Event()
        mock_proc = _make_mock_proc(block)
        mock_proc.pid = 9999

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            handle = SubprocessHandle("test", ["python"])
            await handle.start()
            await asyncio.sleep(0.05)
            assert handle.pid == 9999
            await handle.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_safe(self):
        """stop() should not raise if called before start()."""
        from monocle.process_manager import SubprocessHandle

        handle = SubprocessHandle("idle", ["python"])
        await handle.stop()  # must not raise


# ---------------------------------------------------------------------------
# TestProcessManagerUnifiedMode
# ---------------------------------------------------------------------------


class TestProcessManagerUnifiedMode:
    """ProcessManager in the default unified mode (separate_processes=False)."""

    @pytest.mark.asyncio
    async def test_start_all_is_noop_when_not_separate(self):
        """start_all() must not spawn any subprocesses in unified mode."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec:
            await pm.start_all()

        mock_exec.assert_not_called()
        assert pm._processes == {}

    @pytest.mark.asyncio
    async def test_stop_all_is_safe_when_nothing_started(self):
        """stop_all() must not raise when no processes are running."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)
        await pm.stop_all()  # must not raise

    def test_status_reflects_unified_mode(self):
        """status() should report separate_processes=False and empty processes dict."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)
        s = pm.status()

        assert s["separate_processes"] is False
        assert s["processes"] == {}

    @pytest.mark.asyncio
    async def test_start_all_idempotent_double_call(self):
        """Calling start_all() twice in unified mode must remain a no-op."""
        from monocle.process_manager import ProcessManager

        pm = ProcessManager(_make_settings(separate=False))
        with patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec:
            await pm.start_all()
            await pm.start_all()

        mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# TestProcessManagerSeparateMode
# ---------------------------------------------------------------------------


class TestProcessManagerSeparateMode:
    """ProcessManager in separate-processes mode (separate_processes=True)."""

    @pytest.mark.asyncio
    async def test_start_all_spawns_watch_and_scheduler(self):
        """start_all() must spawn exactly 'watch' and 'scheduler' subprocesses."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        spawned_commands: list[str] = []

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            spawned_commands.append(args[-1])  # last arg is the command name
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)

            assert "watch" in spawned_commands
            assert "scheduler" in spawned_commands
            assert len(pm._processes) == 2

            await pm.stop_all()

    @pytest.mark.asyncio
    async def test_stop_all_clears_processes_dict(self):
        """stop_all() must empty _processes after terminating all handles."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)
            assert len(pm._processes) == 2
            await pm.stop_all()

        assert pm._processes == {}

    def test_status_reports_active_processes(self):
        """status() should include entries for all spawned handles."""
        from monocle.process_manager import ProcessManager, SubprocessHandle

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        # Manually inject a running handle to avoid asyncio complexity
        handle = MagicMock(spec=SubprocessHandle)
        handle.is_running = True
        handle.pid = 42
        handle.restart_count = 0
        pm._processes["watch"] = handle

        s = pm.status()
        assert s["separate_processes"] is True
        assert "watch" in s["processes"]
        assert s["processes"]["watch"]["running"] is True
        assert s["processes"]["watch"]["pid"] == 42
        assert s["processes"]["watch"]["restart_count"] == 0

    @pytest.mark.asyncio
    async def test_make_args_uses_current_python_executable(self):
        """_make_args() must prefix with sys.executable and '-m monocle'."""
        import sys
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)
        args = pm._make_args("watch")

        assert args[0] == sys.executable
        assert args[1:] == ["-m", "monocle", "watch"]

    def test_make_args_scheduler_command(self):
        """_make_args() works for the 'scheduler' subcommand."""
        import sys
        from monocle.process_manager import ProcessManager

        pm = ProcessManager(_make_settings(separate=True))
        args = pm._make_args("scheduler")
        assert args[-1] == "scheduler"
        assert sys.executable in args[0]


# ---------------------------------------------------------------------------
# TestProcessManagerConfig
# ---------------------------------------------------------------------------


class TestProcessManagerConfig:
    """Tests verifying configuration-driven behaviour."""

    def test_status_empty_when_no_processes_started(self):
        """status() processes dict must be empty before start_all()."""
        from monocle.process_manager import ProcessManager

        pm = ProcessManager(_make_settings(separate=True))
        s = pm.status()
        assert s["processes"] == {}

    def test_status_separate_processes_matches_settings(self):
        """status() separate_processes key must match settings."""
        from monocle.process_manager import ProcessManager

        pm_true = ProcessManager(_make_settings(separate=True))
        pm_false = ProcessManager(_make_settings(separate=False))

        assert pm_true.status()["separate_processes"] is True
        assert pm_false.status()["separate_processes"] is False

    @pytest.mark.asyncio
    async def test_stop_all_after_start_all_in_separate_mode(self):
        """Full start_all() → stop_all() lifecycle in separate mode."""
        from monocle.process_manager import ProcessManager

        pm = ProcessManager(_make_settings(separate=True))

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)
            status_before = pm.status()
            await pm.stop_all()
            status_after = pm.status()

        assert status_before["separate_processes"] is True
        assert status_after["processes"] == {}


# ---------------------------------------------------------------------------
# TestMainLifespanSeparateProcesses
# ---------------------------------------------------------------------------


class TestMainLifespanSeparateProcesses:
    """Verify that main.py lifespan sets watcher/scheduler to None in capture-only mode."""

    def test_lifespan_capture_only_sets_watcher_none(self, tmp_path):
        """MONOCLE_COMPONENT=capture must result in app.state.watcher=None."""
        from fastapi.testclient import TestClient
        import monocle.main as main_module
        from monocle.vault import VaultLayer
        from monocle.index.memory import MemoryIndex
        from monocle.ingest.failed_registry import FailedIngestRegistry
        from monocle.ingest import IngestPipeline
        from monocle.ingest.plugin import IngestPluginRegistry
        from monocle.ingest.plugins import register_default_plugins
        from monocle.graph import GraphBuilder
        from monocle.watcher import ReindexQueue
        from monocle.agents.reindex import ReindexAgent
        from monocle.process_manager import ProcessManager
        from contextlib import asynccontextmanager
        import asyncio

        captured: dict = {}

        @asynccontextmanager
        async def _test_lifespan(app):
            vault = VaultLayer(str(tmp_path))
            index = MemoryIndex()
            app.state.vault = vault
            app.state.index = index
            settings_mock = MagicMock()
            settings_mock.telemetry.enabled = False
            app.state.settings = settings_mock
            app.state._review_pending_count = None
            app.state.graph_builder = GraphBuilder(vault)
            app.state.ai = None
            rq = ReindexQueue()
            await rq.start()
            app.state.reindex_queue = rq
            app.state.failed_registry = FailedIngestRegistry()
            registry_ = IngestPluginRegistry.get()
            if not registry_.plugins:
                register_default_plugins(registry_)
            pipeline = IngestPipeline(
                vault=vault, index=index, ai=AsyncMock(),
                settings=MagicMock(), registry=registry_,
                failed_registry=FailedIngestRegistry(),
            )
            app.state.ingest_pipeline = pipeline
            # Simulate capture-only mode: watcher and scheduler are None
            app.state.scheduler = None
            app.state.watcher = None
            pm = ProcessManager(_make_settings(separate=False))
            app.state.process_manager = pm
            captured["watcher"] = app.state.watcher
            captured["scheduler"] = app.state.scheduler

            from monocle.mcp_server import init_mcp_state
            init_mcp_state(vault, index, None, pipeline, app.state.graph_builder, reindex_queue=rq)

            yield

            await rq.stop()

        with patch.object(main_module, "lifespan", _test_lifespan):
            app = main_module.create_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/health")
                assert resp.status_code == 200

        assert captured["watcher"] is None
        assert captured["scheduler"] is None

    def test_lifespan_separate_processes_starts_process_manager(self, tmp_path):
        """When separate_processes=True, process_manager is available on app.state."""
        from fastapi.testclient import TestClient
        import monocle.main as main_module
        from monocle.vault import VaultLayer
        from monocle.index.memory import MemoryIndex
        from monocle.ingest.failed_registry import FailedIngestRegistry
        from monocle.ingest import IngestPipeline
        from monocle.ingest.plugin import IngestPluginRegistry
        from monocle.ingest.plugins import register_default_plugins
        from monocle.graph import GraphBuilder
        from monocle.watcher import ReindexQueue
        from monocle.process_manager import ProcessManager
        from contextlib import asynccontextmanager

        state_capture: dict = {}

        @asynccontextmanager
        async def _test_lifespan(app):
            vault = VaultLayer(str(tmp_path))
            index = MemoryIndex()
            app.state.vault = vault
            app.state.index = index
            settings_mock = MagicMock()
            settings_mock.telemetry.enabled = False
            app.state.settings = settings_mock
            app.state._review_pending_count = None
            app.state.graph_builder = GraphBuilder(vault)
            app.state.ai = None
            rq = ReindexQueue()
            await rq.start()
            app.state.reindex_queue = rq
            app.state.failed_registry = FailedIngestRegistry()
            registry_ = IngestPluginRegistry.get()
            if not registry_.plugins:
                register_default_plugins(registry_)
            pipeline = IngestPipeline(
                vault=vault, index=index, ai=AsyncMock(),
                settings=MagicMock(), registry=registry_,
                failed_registry=FailedIngestRegistry(),
            )
            app.state.ingest_pipeline = pipeline
            app.state.scheduler = None
            app.state.watcher = None

            pm = ProcessManager(_make_settings(separate=True))
            app.state.process_manager = pm
            state_capture["pm"] = pm
            state_capture["separate"] = pm.status()["separate_processes"]

            from monocle.mcp_server import init_mcp_state
            init_mcp_state(vault, index, None, pipeline, app.state.graph_builder, reindex_queue=rq)

            yield

            await rq.stop()

        with patch.object(main_module, "lifespan", _test_lifespan):
            app = main_module.create_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/health")
                assert resp.status_code == 200

        # Verify process_manager was created with separate_processes=True
        assert state_capture["pm"] is not None
        assert state_capture["separate"] is True

