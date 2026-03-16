"""
monocle/tests/test_api.py — M2 acceptance tests.

Verifies that every registered route returns 200 or 501 and never 404 or 500.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from monocle.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health (must return 200)
# ---------------------------------------------------------------------------


def test_health_200():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "version" in body
    assert "ai_reachable" in body
    assert "index_status" in body


# ---------------------------------------------------------------------------
# All stub routes must return exactly 501
# ---------------------------------------------------------------------------

STUB_ROUTES: list[tuple[str, str]] = [
    # notes
    ("GET", "/api/notes"),
    ("GET", "/api/notes/people/test.md"),
    ("PUT", "/api/notes/people/test.md"),
    ("PATCH", "/api/notes/people/test.md"),
    ("DELETE", "/api/notes/people/test.md"),
    ("POST", "/api/notes/people/test.md/move"),
    ("GET", "/api/notes/people/test.md/backlinks"),
    ("GET", "/api/templates"),
    # search
    ("GET", "/api/search"),
    ("GET", "/api/search/keyword"),
    # ingest
    ("POST", "/api/ingest"),
    ("POST", "/api/ingest/stream"),
    # ingest failures
    ("GET", "/api/ingest/failures"),
    ("POST", "/api/ingest/failures/retry"),
    ("DELETE", "/api/ingest/failures/abc123"),
    # transcribe
    ("POST", "/api/transcribe"),
    # graph
    ("GET", "/api/graph"),
    # stats
    ("GET", "/api/stats"),
    # chat
    ("POST", "/api/chat"),
    # agents
    ("POST", "/api/agents/weekly-summary"),
    ("POST", "/api/agents/reindex"),
    # review
    ("GET", "/api/review"),
    ("GET", "/api/review/count"),
    ("PATCH", "/api/review/people/test.md/approve"),
    ("POST", "/api/review/approve-all"),
    # settings
    ("GET", "/api/settings"),
    ("PATCH", "/api/settings"),
    ("POST", "/api/settings/rotate-mcp-key"),
    # teams
    ("POST", "/api/teams/messages"),
]


@pytest.mark.parametrize("method,path", STUB_ROUTES, ids=[f"{m} {p}" for m, p in STUB_ROUTES])
def test_stub_returns_501(method: str, path: str):
    r = client.request(method, path)
    assert r.status_code == 501, (
        f"{method} {path} returned {r.status_code}, expected 501"
    )


# ---------------------------------------------------------------------------
# No route returns 404 or 500
# ---------------------------------------------------------------------------


def test_no_route_returns_404_or_500():
    """Composite guard: none of the registered routes should be missing or broken."""
    for method, path in STUB_ROUTES:
        r = client.request(method, path)
        assert r.status_code not in (404, 500), (
            f"{method} {path} returned unexpected {r.status_code}"
        )
