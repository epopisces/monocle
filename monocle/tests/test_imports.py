"""
monocle/tests/test_imports.py — M1 smoke tests.

Verifies that all key modules are importable with no side-effects.
No business logic is tested here — that comes in later milestones.
"""
from __future__ import annotations

import pytest


def test_config_import() -> None:
    from monocle.config import Settings  # noqa: F401


def test_models_import() -> None:
    from monocle.models import (  # noqa: F401
        Note,
        BrainStats,
        IngestRequest,
        GraphData,
        LinkRef,
        NoteMetadata,
        Page,
        RoutingDecision,
        GraphNode,
        GraphEdge,
        IndexStats,
        ScoredChunk,
        NoteChunk,
        NoteRef,
        IngestConfidence,
    )


def test_telemetry_import() -> None:
    from monocle.telemetry import configure_telemetry  # noqa: F401


def test_watcher_import() -> None:
    from monocle.watcher import InboxWatcher, ReindexQueue  # noqa: F401


def test_process_manager_import() -> None:
    from monocle.process_manager import ProcessManager  # noqa: F401


def test_agent_stubs_import() -> None:
    from monocle.agents.routing import RoutingAgent  # noqa: F401
    from monocle.agents.reindex import ReindexAgent  # noqa: F401


def test_cli_import() -> None:
    from monocle.cli import app  # noqa: F401


def test_ingest_request_has_allow_duplicate() -> None:
    """FR-ING-11: IngestRequest must carry allow_duplicate from M1."""
    from monocle.models import IngestRequest

    req = IngestRequest()
    assert req.allow_duplicate is False

    req_dup = IngestRequest(allow_duplicate=True)
    assert req_dup.allow_duplicate is True


def test_settings_defaults() -> None:
    """Settings instantiates with all defaults when no config.yaml exists."""
    from monocle.config import Settings

    s = Settings()
    assert s.server.host == "127.0.0.1"
    assert s.server.port == 8000
    assert s.ai.embed_dimensions is None  # None = auto-detect from model
    assert s.review.confidence_weights.template_match == 0.35


def test_server_config_invalid_host_raises() -> None:
    """ServerConfig must reject hosts outside the allowed set."""
    from pydantic import ValidationError

    from monocle.config import ServerConfig

    with pytest.raises(ValidationError):
        ServerConfig(host="192.168.1.1")


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0", "localhost"])
def test_server_config_valid_hosts_accepted(host: str) -> None:
    """All three explicitly allowed hosts must not raise."""
    from monocle.config import ServerConfig

    cfg = ServerConfig(host=host)
    assert cfg.host == host


async def test_inbox_watcher_stub_running_flag(tmp_path) -> None:
    """InboxWatcher.start() sets running=True; stop() clears it."""
    from monocle.watcher import InboxWatcher

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    watcher = InboxWatcher(inbox_path=str(inbox))
    assert watcher.status()["running"] is False
    await watcher.start()
    assert watcher.status()["running"] is True
    await watcher.stop()
    assert watcher.status()["running"] is False


async def test_reindex_queue_stub_does_not_raise() -> None:
    """ReindexQueue stub methods must not raise."""
    from monocle.watcher import ReindexQueue

    q = ReindexQueue()
    await q.start()
    q.push("vault/inbox/test.md")  # no-op but must not raise
    await q.stop()
