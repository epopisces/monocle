"""
monocle/tests/conftest.py — Shared pytest fixtures for M1 and beyond.
"""
from __future__ import annotations

import datetime
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from monocle.models import Note, NoteMetadata


#endregion

# ---------------------------------------------------------------------------
#region #*   Fixture: tmp_vault
# ---------------------------------------------------------------------------

_FIXTURE_NOTES: list[dict] = [
    {
        "path": "people/alice-example.md",
        "frontmatter": {
            "type": "person_note",
            "domain": "work",
            "people": ["Alice Example"],
            "tags": ["colleague"],
            "source": "web",
            "confidence": 0.9,
            "review_status": "approved",
        },
        "body": "Alice is a senior engineer on the platform team.",
    },
    {
        "path": "work/decide-python-stack.md",
        "frontmatter": {
            "type": "decision",
            "domain": "work",
            "tags": ["architecture", "python"],
            "source": "web",
            "confidence": 0.85,
            "review_status": "approved",
        },
        "body": "We decided to use Python 3.12 + FastAPI for the backend.",
    },
    {
        "path": "work/kickoff-meeting.md",
        "frontmatter": {
            "type": "meeting_note",
            "domain": "work",
            "people": ["Alice Example", "Bob Smith"],
            "tags": ["kickoff"],
            "source": "web",
            "confidence": 0.8,
            "review_status": "approved",
        },
        "body": "Discussed project timeline and assigned initial tasks.",
    },
    {
        "path": "technologies/idea-graph-viz.md",
        "frontmatter": {
            "type": "idea",
            "domain": "personal",
            "tags": ["graph", "visualization"],
            "source": "web",
            "confidence": 0.7,
            "review_status": "pending",
        },
        "body": "What if we visualised note connections as a force-directed graph?",
    },
    {
        "path": "inbox/raw-capture.md",
        "frontmatter": {
            "type": "other",
            "domain": "personal",
            "tags": [],
            "source": "voice",
            "confidence": 0.35,
            "review_status": "pending",
        },
        "body": "Unprocessed voice capture — needs routing.",
    },
]


def _write_note(vault_root: Path, path: str, frontmatter: dict, body: str) -> None:
    """Write a minimal Obsidian-compatible Markdown note."""
    import yaml

    note_path = vault_root / path
    note_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    fm = {"created": now, "updated": now, **frontmatter}
    content = f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n"
    note_path.write_text(content, encoding="utf-8")


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Temporary vault directory with one fixture note per template type."""
    try:
        import yaml  # noqa: F401 — ensure it's available
    except ImportError:
        pytest.skip("pyyaml not installed")

    for note in _FIXTURE_NOTES:
        _write_note(tmp_path, note["path"], note["frontmatter"], note["body"])

    # Create expected vault subdirectories
    for subdir in ("inbox", "people", "work", "technologies", "summaries", ".templates"):
        (tmp_path / subdir).mkdir(exist_ok=True)

    return tmp_path


#endregion

# ---------------------------------------------------------------------------
#region #*   Fixture: memory_index
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_index():
    """Fresh MemoryIndex instance (no embeddings, substring search).

    The MemoryIndex class is created in M4; this fixture returns None in M1
    and is replaced with a real instance when monocle.index.memory is wired.
    """
    try:
        from monocle.index.memory import MemoryIndex

        return MemoryIndex()
    except ImportError:
        return None


#endregion

# ---------------------------------------------------------------------------
#region #*   Fixture: mock_ai
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ai():
    """AsyncMock AIProvider with sensible default return values for unit tests."""
    from monocle.models import NoteMetadata

    async def _chat_side_effect(messages, **kwargs):
        """Return merge-compatible content for merge calls; JSON for all others."""
        content = messages[-1].get("content", "") if messages else ""
        if "EXISTING:" in content and "NEW INFORMATION:" in content:
            # Simulate a coherent merge: concatenate both sections
            _, rest = content.split("EXISTING:", 1)
            existing_part, new_part = rest.split("NEW INFORMATION:", 1)
            return f"{existing_part.strip()}\n\n{new_part.strip()}"
        return '{"type": "other", "domain": "personal", "tags": []}'

    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[0.1] * 1536)
    ai.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    ai.transcribe = AsyncMock(return_value="transcribed audio content")
    ai.chat = AsyncMock(side_effect=_chat_side_effect)
    ai.extract_note_metadata = AsyncMock(return_value=NoteMetadata())
    from monocle.models import ProviderModelsResponse
    ai.get_model_status = AsyncMock(return_value=ProviderModelsResponse(
        provider="ollama",
        provider_reachable=True,
        models=[],
    ))
    return ai


#endregion

# ---------------------------------------------------------------------------
#region #*   Fixture: api_client
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(tmp_path: Path, mock_ai):
    """TestClient with a real VaultLayer, MemoryIndex, and mock AIProvider.

    Uses a patched lifespan so no real ChromaDB / AI / watcher is started.
    """
    from unittest.mock import patch
    from fastapi.testclient import TestClient

    from monocle.index.memory import MemoryIndex
    from monocle.ingest.failed_registry import FailedIngestRegistry
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    (vault_path / "inbox").mkdir()

    vault = VaultLayer(str(vault_path))
    index = MemoryIndex()
    failed_reg = FailedIngestRegistry(path=tmp_path / "failed_ingests.json")

    # Write a couple of fixture notes so list_notes returns real data
    import yaml, datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    for fname, body, fm in [
        ("people/alice.md", "Alice is an engineer.", {
            "title": "Alice", "type": "person_note", "domain": "work",
            "source": "web", "created": now, "updated": now,
            "confidence": 0.9, "review_status": "approved", "tags": ["colleague"],
        }),
        ("work/decision-one.md", "We chose FastAPI.", {
            "title": "Fast API Decision", "type": "decision", "domain": "work",
            "source": "web", "created": now, "updated": now,
            "confidence": 0.85, "review_status": "approved", "tags": [],
        }),
    ]:
        note_file = vault_path / fname
        note_file.parent.mkdir(parents=True, exist_ok=True)
        note_file.write_text(
            f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n",
            encoding="utf-8",
        )

    @asynccontextmanager
    async def _test_lifespan(app):
        from monocle.config import Settings
        from monocle.ingest import IngestPipeline
        from monocle.ingest.plugin import IngestPluginRegistry
        from monocle.ingest.plugins import register_default_plugins

        _reg = IngestPluginRegistry.get()
        if not _reg.plugins:
            register_default_plugins(_reg)

        # Use default Settings but they won't be used for vault/index operations
        # since those come directly from the vault/index objects we pass.
        settings = Settings()

        rq = ReindexQueue()
        await rq.start()

        pipeline = IngestPipeline(
            vault=vault,
            index=index,
            ai=mock_ai,
            settings=settings,
            registry=_reg,
            failed_registry=failed_reg,
        )

        app.state.vault = vault
        app.state.index = index
        app.state.ai = mock_ai
        app.state.settings = settings
        app.state.reindex_queue = rq
        app.state.ingest_pipeline = pipeline
        app.state.failed_registry = failed_reg
        app.state.watcher = None
        app.state._review_pending_count = None  # lazy count cache; see review.py

        from monocle.graph import GraphBuilder
        app.state.graph_builder = GraphBuilder(vault)

        yield

        await rq.stop()

    from monocle.main import create_app

    with patch("monocle.main.lifespan", new=_test_lifespan):
        test_app = create_app()
        with TestClient(test_app, raise_server_exceptions=False) as client:
            yield client


#endregion

# ---------------------------------------------------------------------------
#region #*   Fixture: live_server  (session-scoped; used by integration tests + Playwright)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Start a real Monocle server on a random available port.

    Polls ``GET /api/health`` until the server reports ``ready`` (or
    ``degraded``) — times out after 15 seconds.

    Yields
    ------
    str
        Base URL of the running server, e.g. ``http://127.0.0.1:54321``.

    Cleanup
    -------
    Sends SIGINT (Ctrl-C equivalent) and waits up to 5 seconds for the process
    to exit cleanly.  On Windows, ``subprocess.terminate()`` is used instead
    because SIGINT is not available for subprocesses.
    """
    import signal
    import socket
    import subprocess
    import sys
    import time

    import httpx

    # Pick a random available port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"

    # Start the server in a subprocess.  Use a temp vault so tests are isolated.
    vault_dir = tmp_path_factory.mktemp("live_vault")
    (vault_dir / "inbox").mkdir(exist_ok=True)

    env = os.environ.copy()
    env["MONOCLE_DEV"] = "false"
    env["MONOCLE_VAULT_PATH"] = str(vault_dir)
    env["MONOCLE_VAULT_INBOX_PATH"] = str(vault_dir / "inbox")
    env["MONOCLE_TELEMETRY_ENABLED"] = "false"  # avoid gRPC noise when AI Toolkit isn't running

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "monocle.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + 15.0
    ready = False
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=1.0)
            status = resp.json().get("status", "")
            if status in ("ready", "degraded"):
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.25)

    if not ready:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        pytest.fail(
            f"live_server did not become ready within 15s on port {port}. "
            f"(stdout/stderr redirected to DEVNULL; check server logs separately if needed)"
        )

    yield base_url

    # Graceful shutdown
    if sys.platform == "win32":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

#endregion