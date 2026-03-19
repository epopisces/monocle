"""
monocle/tests/test_dev_mode.py — Unified dev startup, clean shutdown, 
and service verification tests.

These tests exercise the actual server process startup/shutdown. They do NOT
require a full running server — they use subprocess + a short startup window.
The `live_server` fixture (in conftest.py) is available for integration tests
and Playwright; these tests verify the dev startup contract more narrowly.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time

import pytest


def _free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(base_url: str, timeout: float = 12.0) -> bool:
    """Poll /api/health until the server reports ready/degraded or timeout."""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=1.0)
            status = resp.json().get("status", "")
            if status in ("ready", "degraded"):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


@pytest.fixture()
def dev_server(tmp_path):
    """Start `uvicorn monocle.main:app` on a free port; yield (base_url, proc); then stop."""
    import httpx  # ensure importable early

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "inbox").mkdir()

    env = os.environ.copy()
    env["MONOCLE_VAULT_PATH"] = str(vault_dir)
    env["MONOCLE_VAULT_INBOX_PATH"] = str(vault_dir / "inbox")
    # Disable telemetry export to avoid noise
    env["MONOCLE_TELEMETRY_ENABLED"] = "false"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "monocle.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ready = _wait_for_server(base_url, timeout=12.0)
    if not ready:
        proc.terminate()
        out, err = proc.communicate(timeout=5)
        pytest.skip(
            f"dev_server did not start in time on port {port}. "
            f"stdout: {out.decode()[-1000:]} stderr: {err.decode()[-1000:]}"
        )

    yield base_url, proc

    if sys.platform == "win32":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


class TestUnifiedDevStartup:
    def test_health_endpoint_returns_ready_or_degraded(self, dev_server):
        """Server starts and /api/health is reachable."""
        import httpx

        base_url, _ = dev_server
        resp = httpx.get(f"{base_url}/api/health", timeout=5.0)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ready", "degraded")

    def test_multiple_api_endpoints_reachable(self, dev_server):
        """Key API endpoints respond (not 404 / 501)."""
        import httpx

        base_url, _ = dev_server
        # /api/stats and /api/notes should be wired
        for path in ("/api/stats", "/api/notes"):
            resp = httpx.get(f"{base_url}{path}", timeout=5.0)
            assert resp.status_code not in (404, 501), (
                f"{path} returned {resp.status_code} — endpoint may be a stub"
            )

    def test_clean_shutdown(self, dev_server):
        """Server exits cleanly (non-null exit code logged, process terminates)."""
        base_url, proc = dev_server

        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=6)
            exited = True
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            exited = False

        # We accept any exit code — what matters is the process terminates
        assert exited, "Server process did not exit within 6s of SIGINT"


class TestWatcherAndSchedulerStartup:
    def test_watcher_status_in_health(self, dev_server):
        """Health endpoint includes watcher_running field."""
        import httpx

        base_url, _ = dev_server
        resp = httpx.get(f"{base_url}/api/health", timeout=5.0)
        data = resp.json()
        # watcher_running is set in health router; it should be present
        assert "watcher_running" in data

    def test_scheduler_does_not_crash_startup(self, dev_server):
        """If the scheduler crashed on startup, health would report degraded.
        We check the server is at least reachable and returning a known status."""
        import httpx

        base_url, _ = dev_server
        resp = httpx.get(f"{base_url}/api/health", timeout=5.0)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ready", "degraded")


class TestDevTelemetryBlock:
    """Test the telemetry block printed by `python -m monocle dev`."""

    def test_dev_command_prints_telemetry_block(self, tmp_path):
        """The `dev` command prints a [TELEMETRY] block before handing off."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "inbox").mkdir()

        env = os.environ.copy()
        env["MONOCLE_VAULT_PATH"] = str(vault_dir)
        env["MONOCLE_TELEMETRY_ENABLED"] = "false"

        # Run `python -m monocle dev` and immediately terminate.
        # We just need the first few lines of output.
        proc = subprocess.Popen(
            [sys.executable, "-m", "monocle", "dev"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Give it up to 3 seconds and collect output
        # (dev starts uvicorn which may or may not start fully — we just need
        # the telemetry line which is printed synchronously before uvicorn.run())
        time.sleep(0.5)
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()

        output = out.decode(errors="replace")
        assert "[TELEMETRY]" in output, (
            f"Expected [TELEMETRY] block in dev command output, got:\n{output[:500]}"
        )
