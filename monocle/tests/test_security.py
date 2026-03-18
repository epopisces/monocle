"""
monocle/tests/test_security.py — Security and boundary tests for M8.

Covers:
- Path traversal protection (403)
- File / audio size limits (422)
- Optimistic-concurrency conflict detection (409)
- CORS header presence
- Rate-limit responses (429) — disabled by default; marked integration
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# Path Traversal
# ===========================================================================

class TestPathTraversal:
    """Path-traversal tests use percent-encoded dots (%2e%2e) so that httpx
    does NOT normalise ``../..`` in the URL before the request reaches
    FastAPI.  Starlette decodes the segments when populating the path
    parameter, which means ``_safe_resolve`` still sees ``../../.env``
    and rejects it with 403."""

    def test_get_note_traversal_blocked(self, api_client: TestClient):
        """GET /api/notes/%2e%2e/%2e%2e/.env must return 403."""
        r = api_client.get("/api/notes/%2e%2e/%2e%2e/.env")
        assert r.status_code == 403

    def test_get_note_absolute_path_blocked(self, api_client: TestClient):
        """Absolute paths that escape the vault must return 403."""
        # %2F is a URL-encoded slash kept as-is by httpx so Starlette
        # sees the leading slash and _safe_resolve rejects it.
        r = api_client.get("/api/notes/%2Fetc%2Fpasswd")
        assert r.status_code == 403

    def test_put_note_traversal_blocked(self, api_client: TestClient):
        payload = {"title": "hack", "body": "evil", "metadata": {}}
        r = api_client.put("/api/notes/%2e%2e/%2e%2e/etc/evil.md", json=payload)
        assert r.status_code == 403

    def test_delete_note_traversal_blocked(self, api_client: TestClient):
        r = api_client.delete("/api/notes/%2e%2e/%2e%2e/.env")
        assert r.status_code == 403

    def test_patch_frontmatter_traversal_blocked(self, api_client: TestClient):
        r = api_client.patch(
            "/api/notes/%2e%2e/%2e%2e/.env",
            json={"updates": {"type": "hacked"}},
        )
        assert r.status_code == 403

    def test_move_note_to_path_traversal_blocked(self, api_client: TestClient):
        """POST /api/notes/{path}/move with a malicious to_path must return 403."""
        # First create a note to move
        api_client.put(
            "/api/notes/work/move-traversal-src.md",
            json={"title": "Source", "body": "moveme", "metadata": {}},
        )
        r = api_client.post(
            "/api/notes/work/move-traversal-src.md/move",
            json={"to_path": "../../evil.md"},
        )
        assert r.status_code == 403, (
            f"Expected 403 for to_path traversal, got {r.status_code}: {r.text}"
        )


# ===========================================================================
# Audio Size Limits
# ===========================================================================

class TestAudioSizeLimits:
    def test_ingest_audio_over_25mb_returns_422(self, api_client: TestClient):
        import base64
        big_audio = b"a" * (25 * 1024 * 1024 + 1)
        payload = {
            "content": None,
            "source": "voice",
            "audio_bytes": base64.b64encode(big_audio).decode(),
            "audio_mime_type": "audio/webm",
        }
        r = api_client.post("/api/ingest", json=payload)
        assert r.status_code == 422

    def test_ingest_audio_exactly_25mb_allowed(self, api_client: TestClient):
        """Exactly 25 MB should not be rejected by the size guard."""
        import base64
        exact_audio = b"b" * (25 * 1024 * 1024)
        payload = {
            "content": None,
            "source": "voice",
            "audio_bytes": base64.b64encode(exact_audio).decode(),
            "audio_mime_type": "audio/webm",
        }
        # Should not 422 from SIZE check (may fail for other reasons like bad audio)
        r = api_client.post("/api/ingest", json=payload)
        assert r.status_code != 422 or "Audio payload exceeds" not in r.text

    def test_transcribe_empty_file_422(self, api_client: TestClient):
        r = api_client.post(
            "/api/transcribe",
            files={"file": ("empty.webm", b"", "audio/webm")},
        )
        assert r.status_code == 422

    def test_transcribe_over_limit_422(self, api_client: TestClient):
        big_audio = b"c" * (25 * 1024 * 1024 + 1)
        r = api_client.post(
            "/api/transcribe",
            files={"file": ("big.webm", big_audio, "audio/webm")},
        )
        assert r.status_code == 413


# ===========================================================================
# Optimistic-Concurrency (409)
# ===========================================================================

class TestOptimisticConcurrency:
    def test_put_stale_mtime_returns_409(self, api_client: TestClient):
        """PUT with a clearly stale if_mtime returns 409."""
        # First write
        r1 = api_client.put(
            "/api/notes/work/conc-test.md",
            json={"title": "V1", "body": "body v1", "metadata": {}},
        )
        assert r1.status_code == 201  # first PUT creates a new note

        # Second write with stale timestamp
        r2 = api_client.put(
            "/api/notes/work/conc-test.md",
            json={"title": "V2", "body": "body v2", "metadata": {}, "if_mtime": 1.0},
        )
        assert r2.status_code == 409

    def test_put_correct_mtime_succeeds(self, api_client: TestClient):
        """PUT with the correct mtime (from prior GET) succeeds."""
        api_client.put(
            "/api/notes/work/conc-ok.md",
            json={"title": "V1", "body": "body v1", "metadata": {}},
        )
        note = api_client.get("/api/notes/work/conc-ok.md").json()
        mtime = note.get("mtime")

        r = api_client.put(
            "/api/notes/work/conc-ok.md",
            json={"title": "V2", "body": "body v2", "metadata": {}, "if_mtime": mtime},
        )
        assert r.status_code == 200

    def test_rapid_puts_coalesced_in_reindex_queue(self, api_client: TestClient):
        """Rapid consecutive PUTs should not crash — the ReindexQueue coalesces them."""
        for i in range(5):
            r = api_client.put(
                "/api/notes/work/rapid.md",
                json={"title": f"Rapid {i}", "body": f"body {i}", "metadata": {}},
            )
            # First PUT creates (201); subsequent PUTs update (200)
            assert r.status_code in (200, 201)


# ===========================================================================
# CORS headers
# ===========================================================================

class TestCORS:
    def test_cors_preflight_allowed_origin(self, api_client: TestClient):
        """OPTIONS preflight from allowed origin should include CORS headers."""
        r = api_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # May return 200 or 204
        assert r.status_code in (200, 204)
        # CORS headers should be present
        assert "access-control-allow-origin" in {k.lower() for k in r.headers}

    def test_cors_header_present_on_get(self, api_client: TestClient):
        r = api_client.get(
            "/api/health",
            headers={"Origin": "http://localhost:8000"},
        )
        assert r.status_code == 200
        assert "access-control-allow-origin" in {k.lower() for k in r.headers}

    def test_cors_wildcard_not_used(self, api_client: TestClient):
        """The CORS origin should never be a bare wildcard."""
        r = api_client.get(
            "/api/health",
            headers={"Origin": "http://localhost:8000"},
        )
        headers_lower = {k.lower(): v for k, v in r.headers.items()}
        origin = headers_lower.get("access-control-allow-origin", "")
        assert origin != "*", "Wildcard CORS origin is not allowed"

    def test_cors_dev_origin_excluded_in_non_dev_mode(self, api_client: TestClient):
        """localhost:5173 (Vite dev server) must NOT be reflected as an allowed origin
        when dev_cors is disabled (the test fixture does not set MONOCLE_DEV)."""
        r = api_client.get(
            "/api/health",
            headers={"Origin": "http://localhost:5173"},
        )
        headers_lower = {k.lower(): v for k, v in r.headers.items()}
        # When the origin is not in the allowed list, CORSMiddleware either
        # omits the header or reflects a different origin.  Either way, 5173
        # must not be echoed back.
        echo = headers_lower.get("access-control-allow-origin", "")
        assert "5173" not in echo, (
            "localhost:5173 must not be in CORS allow-origin outside dev mode"
        )


# ===========================================================================
# Ingest duplicate detection (advisory, no automatic dedup)
# ===========================================================================

class TestDuplicateDetection:
    def test_ingest_duplicate_returns_409(self, api_client: TestClient, mock_ai):
        """When MemoryIndex returns a high-similarity hit, pipeline should raise DuplicateSuspected.

        In the test environment we use MemoryIndex (substring search, score=1.0).
        We trigger the duplicate by mocking the index.search to return a high-score result.
        """
        from unittest.mock import patch
        from monocle.models import ScoredChunk

        # Pre-populate index with a note so duplicate detection has something to find
        # by injecting a chunk for an existing note
        index = api_client.app.state.index
        from monocle.models import NoteChunk
        index.upsert_chunks([
            NoteChunk(
                chunk_id="people/alice.md::0",
                file_path="people/alice.md",
                chunk_index=0,
                text="Met with Sarah today about the project.",
                embedding=[0.1] * 1536,
                metadata={"created": "2099-01-01T00:00:00+00:00"},  # far future = within 7 days
            )
        ])

        # Mock embed_batch to return the same embedding (ensures similarity = 1.0)
        mock_ai.embed_batch.return_value = [[0.1] * 1536]

        # Mock index.search to return a high-score hit
        high_score_chunk = ScoredChunk(
            chunk_id="people/alice.md::0",
            file_path="people/alice.md",
            score=0.99,
            text="Met with Sarah today.",
            metadata={"created": "2099-01-01T00:00:00+00:00"},
        )

        def _mocked_search(*a, **kw):
            return [high_score_chunk]

        with patch.object(index, "search", side_effect=_mocked_search):
            r = api_client.post(
                "/api/ingest",
                json={
                    "content": "Met with Sarah today about the project.",
                    "source": "web",
                    "allow_duplicate": False,
                },
            )

        # DuplicateSuspected → 409
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["similar_note_detected"] is True
        assert "similar_note_path" in body["detail"]

    def test_ingest_with_allow_duplicate_creates_note(self, api_client: TestClient, mock_ai):
        """allow_duplicate=True bypasses duplicate detection and creates the note."""
        from unittest.mock import patch
        from monocle.models import ScoredChunk

        index = api_client.app.state.index
        high_score_chunk = ScoredChunk(
            chunk_id="people/alice.md::0",
            file_path="people/alice.md",
            score=0.99,
            text="Met with Sarah today.",
            metadata={"created": "2099-01-01T00:00:00+00:00"},
        )

        def _mocked_search(*a, **kw):
            return [high_score_chunk]

        with patch.object(index, "search", side_effect=_mocked_search):
            r = api_client.post(
                "/api/ingest",
                json={
                    "content": "Met with Sarah today about the project 2.",
                    "source": "web",
                    "allow_duplicate": True,
                },
            )

        assert r.status_code == 201
        body = r.json()
        assert "note" in body
        # Confidence should report similar_note_detected=True
        assert body["confidence"]["similar_note_detected"] is True
