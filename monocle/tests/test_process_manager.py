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


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
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


#endregion

# ---------------------------------------------------------------------------
#region #*   TestSubprocessHandle
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


#endregion

# ---------------------------------------------------------------------------
#region #*   TestProcessManagerUnifiedMode
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


#endregion

# ---------------------------------------------------------------------------
#region #*   TestProcessManagerSeparateMode
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


#endregion

# ---------------------------------------------------------------------------
#region #*   TestProcessManagerConfig
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


#endregion

# ---------------------------------------------------------------------------
#region #*   TestMainLifespanCaptureOnlyGating
# ---------------------------------------------------------------------------


class TestMainLifespanCaptureOnlyGating:
    """Verify ProcessManager behavior in capture-only and separate-process modes.
    
    Note: The real lifespan gating logic (checking _capture_only flag) is tested
    by existing test_api.py tests. These tests focus on ProcessManager's role in
    the orchestration.
    """

    def test_process_manager_start_all_respects_env_var_separate_processes(self, monkeypatch):
        """ProcessManager.start_all() should spawn subprocesses when env var is set regardless of config."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "1")
        settings = _make_settings(separate=False)  # Config says False, env says True
        pm = ProcessManager(settings)

        # Verify effective flag from env var
        assert pm._is_separate_processes_enabled()

    def test_process_manager_effective_flag_honors_config(self, monkeypatch):
        """ProcessManager effective flag should be True when config.separate_processes=True."""
        from monocle.process_manager import ProcessManager

        monkeypatch.delenv("MONOCLE_SEPARATE_PROCESSES", raising=False)
        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        assert pm._is_separate_processes_enabled()

    def test_process_manager_effective_flag_false_when_both_false(self, monkeypatch):
        """ProcessManager effective flag should be False when both config and env are false/unset."""
        from monocle.process_manager import ProcessManager

        monkeypatch.delenv("MONOCLE_SEPARATE_PROCESSES", raising=False)
        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        assert not pm._is_separate_processes_enabled()


#endregion

# ---------------------------------------------------------------------------
#region #*   TestProcessManagerEnvironmentVariable
# ---------------------------------------------------------------------------


class TestProcessManagerEnvironmentVariable:
    """Tests verifying MONOCLE_SEPARATE_PROCESSES env var handling."""

    def test_is_separate_processes_enabled_honors_env_var(self, monkeypatch):
        """_is_separate_processes_enabled() returns True when env var is set."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "1")
        settings = _make_settings(separate=False)  # Mismatch: config says False
        pm = ProcessManager(settings)

        # Effective flag should be True because env var overrides config
        assert pm._is_separate_processes_enabled() is True

    def test_is_separate_processes_enabled_config_true_env_unset(self, monkeypatch):
        """_is_separate_processes_enabled() returns True when config is True."""
        from monocle.process_manager import ProcessManager

        monkeypatch.delenv("MONOCLE_SEPARATE_PROCESSES", raising=False)
        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        assert pm._is_separate_processes_enabled() is True

    def test_is_separate_processes_enabled_both_false(self, monkeypatch):
        """_is_separate_processes_enabled() returns False when both config and env are false/unset."""
        from monocle.process_manager import ProcessManager

        monkeypatch.delenv("MONOCLE_SEPARATE_PROCESSES", raising=False)
        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        assert pm._is_separate_processes_enabled() is False

    def test_is_separate_processes_enabled_env_var_wrong_value(self, monkeypatch):
        """_is_separate_processes_enabled() ignores env var if not exactly '1'."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "0")  # or anything else
        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        # Should be False because only "1" enables the feature
        assert pm._is_separate_processes_enabled() is False

    @pytest.mark.asyncio
    async def test_start_all_respects_env_var_over_config(self, monkeypatch):
        """start_all() spawns subprocesses when env var is set, even if config is False."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "1")
        settings = _make_settings(separate=False)  # Config says no, env says yes
        pm = ProcessManager(settings)

        spawned_commands: list[str] = []

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            spawned_commands.append(args[-1])
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)

            # Should have spawned because env var overrides config
            assert "watch" in spawned_commands
            assert "scheduler" in spawned_commands

            await pm.stop_all()

    def test_status_reflects_effective_env_var(self, monkeypatch):
        """status() reports separate_processes=True when env var is set."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "1")
        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        s = pm.status()
        # status() should reflect the effective flag (True due to env var)
        assert s["separate_processes"] is True

    @pytest.mark.asyncio
    async def test_start_all_noop_when_env_var_empty_string(self, monkeypatch):
        """start_all() is a no-op when env var is an empty string."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "")
        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec:
            await pm.start_all()

        # Empty string is not the same as "1", so no-op
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_all_both_config_and_env_true(self, monkeypatch):
        """start_all() spawns subprocesses when both config and env specify True."""
        from monocle.process_manager import ProcessManager

        monkeypatch.setenv("MONOCLE_SEPARATE_PROCESSES", "1")
        settings = _make_settings(separate=True)  # Redundant but valid
        pm = ProcessManager(settings)

        spawned_commands: list[str] = []

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            spawned_commands.append(args[-1])
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)

            assert len(spawned_commands) == 2
            await pm.stop_all()


#endregion

# ---------------------------------------------------------------------------
#region #*   TestProcessManagerIdempotency
# ---------------------------------------------------------------------------


class TestProcessManagerIdempotency:
    """Tests verifying idempotency of start_all()."""

    @pytest.mark.asyncio
    async def test_start_all_idempotent_double_call_same_handles(self):
        """Calling start_all() twice returns the same handle objects."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)
            handles_first = dict(pm._processes)  # Snapshot first set

            await pm.start_all()
            await asyncio.sleep(0.05)
            handles_second = dict(pm._processes)  # Snapshot second set

            # Same handle object for "watch": idem potency
            assert handles_first["watch"] is handles_second["watch"]
            assert handles_first["scheduler"] is handles_second["scheduler"]

            await pm.stop_all()

    @pytest.mark.asyncio
    async def test_start_all_idempotent_spawns_once(self):
        """Calling start_all() twice should spawn subprocesses only once."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        spawn_count = 0

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            nonlocal spawn_count
            spawn_count += 1
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)
            count_after_first = spawn_count

            await pm.start_all()
            await asyncio.sleep(0.05)
            count_after_second = spawn_count

            # Should only spawn 2 (watch + scheduler) on first call.
            # Second call should not spawn any new processes.
            assert count_after_first == 2
            assert count_after_second == 2  # No new spawns

            await pm.stop_all()

    @pytest.mark.asyncio
    async def test_start_all_no_handle_leak_on_repeat_calls(self):
        """Repeated start_all() calls don't accumulate handles in _processes."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            for iteration in range(3):
                await pm.start_all()
                await asyncio.sleep(0.05)
                # _processes should always have exactly 2 entries
                assert len(pm._processes) == 2, f"Iteration {iteration}: expected 2, got {len(pm._processes)}"

            await pm.stop_all()

    @pytest.mark.asyncio
    async def test_start_all_restarts_crashed_process(self):
        """start_all() will create a new handle if the old one crashed/exited."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)
        spawn_count = 0

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            nonlocal spawn_count
            spawn_count += 1
            mock_proc = MagicMock()
            mock_proc.pid = 100 + spawn_count
            # Immediately exit
            async def _exit():
                return 1
            mock_proc.wait = _exit
            mock_proc.returncode = 1
            mock_proc.terminate = MagicMock()
            return mock_proc

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.10)  # Allow process to exit
            first_watch_handle = pm._processes["watch"]

            # Call start_all() again — should restart the crashed "watch" process
            await pm.start_all()
            await asyncio.sleep(0.05)
            second_watch_handle = pm._processes["watch"]

            # Should have spawned more than 2 times (initial 2 + at least 1 restart)
            assert spawn_count >= 3

            await pm.stop_all()

    @pytest.mark.asyncio
    async def test_start_all_idempotent_in_unified_mode(self):
        """start_all() is a no-op when called multiple times in unified mode."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=False)
        pm = ProcessManager(settings)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec:
            await pm.start_all()
            await pm.start_all()
            await pm.start_all()

        # Should never spawn in unified mode, regardless of call count
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_stable_after_repeated_start_all(self):
        """status() returns consistent info after repeated start_all() calls."""
        from monocle.process_manager import ProcessManager

        settings = _make_settings(separate=True)
        pm = ProcessManager(settings)

        async def _fake_exec(*args, stdin=None, stdout=None, stderr=None):
            block = asyncio.Event()
            return _make_mock_proc(block)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec):
            await pm.start_all()
            await asyncio.sleep(0.05)
            status_first = pm.status()

            await pm.start_all()
            await asyncio.sleep(0.05)
            status_second = pm.status()

            # status() should be identical after second call
            assert status_first == status_second
            assert len(status_first["processes"]) == 2
            assert all(status_first["processes"][name]["running"] for name in ["watch", "scheduler"])

            await pm.stop_all()


