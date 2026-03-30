"""
monocle/tests/test_api.py — M8 API integration tests.

Uses the `api_client` fixture (MemoryIndex + mock AIProvider) to test the
wired implementations of notes, search, ingest, failures, transcribe,
health, and stats endpoints.

Routes NOT implemented in M8 (graph, chat, agents, review, settings, teams)
continue to return 501 and are tested in the stub section at the bottom.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#endregion

# ---------------------------------------------------------------------------
#region #*   Module-level client for stub 501 checks (uses main app with real lifespan
# suppressed via raise_server_exceptions=False)
# ---------------------------------------------------------------------------

from monocle.main import app

_stub_client = TestClient(app, raise_server_exceptions=False)


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper
# ---------------------------------------------------------------------------

def _json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {}


# ===========================================================================
# Health
# ===========================================================================

class TestHealth:
    def test_health_200(self, api_client: TestClient):
        r = api_client.get("/api/health")
        assert r.status_code == 200
        body = _json(r)
        assert "status" in body
        assert "version" in body
        assert "ai_reachable" in body
        assert "index_status" in body

    def test_health_has_telemetry_endpoint_field(self, api_client: TestClient):
        r = api_client.get("/api/health")
        body = _json(r)
        # field exists (may be null if telemetry disabled)
        assert "telemetry_endpoint" in body

    def test_health_watcher_field(self, api_client: TestClient):
        r = api_client.get("/api/health")
        body = _json(r)
        assert "watcher_running" in body
        # watcher is None in test fixture → False
        assert body["watcher_running"] is False


# ===========================================================================
# Notes
# ===========================================================================

class TestNotes:
    def test_list_notes_returns_paginated(self, api_client: TestClient):
        r = api_client.get("/api/notes")
        assert r.status_code == 200
        body = _json(r)
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)

    def test_list_notes_default_params(self, api_client: TestClient):
        r = api_client.get("/api/notes?sort=updated&limit=10&offset=0")
        assert r.status_code == 200
        body = _json(r)
        assert body["offset"] == 0
        assert body["limit"] == 10

    def test_get_note_404_for_missing(self, api_client: TestClient):
        r = api_client.get("/api/notes/nonexistent/note.md")
        assert r.status_code == 404

    def test_put_creates_note(self, api_client: TestClient):
        payload = {
            "title": "Test Note",
            "body": "This is a test note body.",
            "metadata": {},
        }
        r = api_client.put("/api/notes/people/test-note.md", json=payload)
        assert r.status_code == 201  # RFC 7231 §4.3.4: 201 Created for new resource
        body = _json(r)
        assert body["title"] == "Test Note"
        assert body["file_path"] == "people/test-note.md"

    def test_put_returns_note_with_mtime(self, api_client: TestClient):
        payload = {"title": "MT Note", "body": "Has mtime.", "metadata": {}}
        r = api_client.put("/api/notes/work/mt-note.md", json=payload)
        assert r.status_code == 201  # new note
        body = _json(r)
        assert "mtime" in body

    def test_put_update_returns_200(self, api_client: TestClient):
        """PUT on an already-existing note must return 200, not 201."""
        payload = {"title": "Existing", "body": "v1", "metadata": {}}
        r_create = api_client.put("/api/notes/work/existing.md", json=payload)
        assert r_create.status_code == 201
        r_update = api_client.put("/api/notes/work/existing.md", json={**payload, "body": "v2"})
        assert r_update.status_code == 200

    def test_get_existing_note(self, api_client: TestClient):
        # First create
        api_client.put("/api/notes/people/alice2.md", json={"title": "Alice2", "body": "Body", "metadata": {}})
        r = api_client.get("/api/notes/people/alice2.md")
        assert r.status_code == 200
        body = _json(r)
        assert body["title"] == "Alice2"

    def test_patch_note_updates_frontmatter(self, api_client: TestClient):
        api_client.put("/api/notes/work/patch-me.md", json={"title": "PatchMe", "body": "Body", "metadata": {}})
        r = api_client.patch(
            "/api/notes/work/patch-me.md",
            json={"updates": {"custom_field": "custom_value"}},
        )
        assert r.status_code == 200

    def test_delete_note(self, api_client: TestClient):
        api_client.put("/api/notes/work/to-delete.md", json={"title": "Del", "body": "b", "metadata": {}})
        r = api_client.delete("/api/notes/work/to-delete.md")
        assert r.status_code == 204
        # Note should be gone
        r2 = api_client.get("/api/notes/work/to-delete.md")
        assert r2.status_code == 404

    def test_move_note(self, api_client: TestClient):
        api_client.put("/api/notes/work/moveme.md", json={"title": "Move", "body": "b", "metadata": {}})
        r = api_client.post(
            "/api/notes/work/moveme.md/move",
            json={"to_path": "people/moved.md"},
        )
        assert r.status_code == 200
        body = _json(r)
        assert body["to_path"] == "people/moved.md"

    def test_list_templates(self, api_client: TestClient):
        r = api_client.get("/api/templates")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) > 0

    def test_put_conflict_stale_mtime(self, api_client: TestClient):
        payload = {"title": "Conflict", "body": "v1", "metadata": {}}
        r1 = api_client.put("/api/notes/work/conflict.md", json=payload)
        assert r1.status_code == 201  # new resource created
        # Use a clearly stale mtime
        stale_payload = {"title": "Conflict updated", "body": "v2", "metadata": {}, "if_mtime": 1.0}
        r2 = api_client.put("/api/notes/work/conflict.md", json=stale_payload)
        assert r2.status_code == 409

    def test_backlinks_returns_list(self, api_client: TestClient):
        # create two notes where note2 wikilinks to note1
        api_client.put(
            "/api/notes/people/backlink-target.md",
            json={"title": "Target", "body": "Target note", "metadata": {}},
        )
        api_client.put(
            "/api/notes/work/linker.md",
            json={"title": "Linker", "body": "See [[backlink-target]] for details.", "metadata": {}},
        )
        r = api_client.get("/api/notes/people/backlink-target.md/backlinks")
        assert r.status_code == 200
        results = r.json()
        assert isinstance(results, list)
        # linker.md should appear in the results
        sources = [item["source"] for item in results]
        assert "work/linker.md" in sources

    def test_backlinks_structured_link(self, api_client: TestClient):
        """Notes with structured frontmatter links should appear in backlinks."""
        api_client.put(
            "/api/notes/people/structured-target.md",
            json={"title": "Structured Target", "body": "Target body", "metadata": {}},
        )
        api_client.put(
            "/api/notes/work/structured-linker.md",
            json={
                "title": "Structured Linker",
                "body": "Body without wikilinks.",
                "metadata": {
                    "links": [{"target": "structured-target", "relation": "discusses", "metadata": {}}]
                },
            },
        )
        r = api_client.get("/api/notes/people/structured-target.md/backlinks")
        assert r.status_code == 200
        results = r.json()
        sources = [item["source"] for item in results]
        assert "work/structured-linker.md" in sources
        # Relation and context should be populated
        match = next(i for i in results if i["source"] == "work/structured-linker.md")
        assert match["relation"] == "discusses"

    def test_backlinks_people_co_mention(self, api_client: TestClient):
        """Notes with a matching people co-mention should appear in backlinks."""
        # Target note: people/alice-comention.md  (slug: alice-comention)
        api_client.put(
            "/api/notes/people/alice-comention.md",
            json={"title": "Alice Comention", "body": "Alice's profile.", "metadata": {}},
        )
        # Linker: mentions "alice-comention" in people list
        api_client.put(
            "/api/notes/work/meeting-comention.md",
            json={
                "title": "Meeting",
                "body": "We met to discuss the roadmap.",
                "metadata": {"people": ["alice-comention"]},
            },
        )
        r = api_client.get("/api/notes/people/alice-comention.md/backlinks")
        assert r.status_code == 200
        results = r.json()
        sources = [item["source"] for item in results]
        assert "work/meeting-comention.md" in sources
        match = next(i for i in results if i["source"] == "work/meeting-comention.md")
        assert match["relation"] == "mentions"


# ===========================================================================
# Search
# ===========================================================================

class TestSearch:
    def test_semantic_search_requires_q(self, api_client: TestClient):
        r = api_client.get("/api/search")
        # FastAPI will return 422 for missing required query param
        assert r.status_code == 422

    def test_semantic_search_returns_list(self, api_client: TestClient):
        r = api_client.get("/api/search?q=test+query")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_keyword_search_requires_q(self, api_client: TestClient):
        r = api_client.get("/api/search/keyword")
        assert r.status_code == 422

    def test_keyword_search_returns_results(self, api_client: TestClient):
        # Create a searchable note
        api_client.put(
            "/api/notes/work/searchable.md",
            json={"title": "Searchable", "body": "uniquekeyword123 content here", "metadata": {}},
        )
        r = api_client.get("/api/search/keyword?q=uniquekeyword123")
        assert r.status_code == 200
        results = r.json()
        assert isinstance(results, list)
        assert any("searchable" in item["file_path"] for item in results)

    def test_keyword_search_no_match(self, api_client: TestClient):
        r = api_client.get("/api/search/keyword?q=xyznotfound999")
        assert r.status_code == 200
        assert r.json() == []

    def test_semantic_search_type_filter(self, api_client: TestClient):
        """?type= filter param is forwarded to the index; request must not error."""
        r = api_client.get("/api/search?q=test&type=person_note")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_semantic_search_domain_filter(self, api_client: TestClient):
        r = api_client.get("/api/search?q=test&domain=work")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_semantic_search_source_filter(self, api_client: TestClient):
        r = api_client.get("/api/search?q=test&source=web")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_keyword_search_domain_filter(self, api_client: TestClient):
        """?domain= filter is accepted and narrows the scan without error."""
        r = api_client.get("/api/search/keyword?q=engineer&domain=work")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ===========================================================================
# Ingest
# ===========================================================================

class TestIngest:
    def test_ingest_text_returns_201(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest",
            json={"content": "Met with Sarah today about the project.", "source": "web"},
        )
        assert r.status_code == 201
        body = _json(r)
        assert "note" in body
        assert "confidence" in body
        assert "file_path" in body["note"]

    def test_ingest_requires_content_or_audio(self, api_client: TestClient):
        # Empty content is valid for text (pipeline handles it)
        r = api_client.post("/api/ingest", json={"content": "", "source": "web"})
        # Should succeed or fail gracefully — not 501
        assert r.status_code != 501

    def test_ingest_audio_too_large_returns_422(self, api_client: TestClient):
        import base64
        big_audio = b"x" * (25 * 1024 * 1024 + 1)
        r = api_client.post(
            "/api/ingest",
            json={
                "content": None,
                "source": "voice",
                "audio_bytes": base64.b64encode(big_audio).decode(),
                "audio_mime_type": "audio/webm",
            },
        )
        assert r.status_code == 422

    def test_ingest_confidence_fields_present(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest",
            json={"content": "I decided to refactor the pipeline.", "source": "web"},
        )
        assert r.status_code == 201
        body = _json(r)
        conf = body["confidence"]
        assert "score" in conf
        assert "template_match" in conf
        assert "similar_note_detected" in conf

    def test_ingest_stream_returns_streaming(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest/stream",
            json={"content": "Stream test content", "source": "web"},
        )
        # SSE returns 200 or might stream
        assert r.status_code in (200, 201)

    def test_ingest_stream_emits_step_and_done_events(self, api_client: TestClient):
        """SSE stream must include at least one step_complete event and a done event."""
        r = api_client.post(
            "/api/ingest/stream",
            json={"content": "Stream event content for SSE test", "source": "web"},
        )
        assert r.status_code == 200
        raw_text = r.text

        # Parse SSE lines: event: <name>
        event_names = [
            line[len("event: "):].strip()
            for line in raw_text.splitlines()
            if line.startswith("event: ")
        ]
        assert "step_complete" in event_names, f"No step_complete events found. Events: {event_names}"
        assert "done" in event_names, f"No done event found. Events: {event_names}"

        # Parse done event data
        done_data_lines = []
        capture = False
        for line in raw_text.splitlines():
            if line.startswith("event: done"):
                capture = True
            elif capture and line.startswith("data: "):
                done_data_lines.append(line[len("data: "):])
                break

        assert done_data_lines, "done event has no data line"
        import json as _json
        done_payload = _json.loads(done_data_lines[0])
        assert "note_path" in done_payload
        assert "confidence" in done_payload
        assert "elapsed_ms" in done_payload


# ===========================================================================
# Ingest Failures
# ===========================================================================

class TestIngestFailures:
    def test_list_failures_initially_empty(self, api_client: TestClient):
        r = api_client.get("/api/ingest/failures")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_failure_404_for_missing(self, api_client: TestClient):
        r = api_client.delete("/api/ingest/failures/nonexistent-id-xyz")
        assert r.status_code == 404

    def test_retry_failure_404_for_missing(self, api_client: TestClient):
        r = api_client.post("/api/ingest/failures/retry", json={"id": "nonexistent-id-xyz"})
        assert r.status_code == 404

    def test_failures_newest_first(self, api_client: TestClient):
        """After creating a failure entry manually, it should appear in the list."""
        registry = api_client.app.state.failed_registry
        registry.add(
            source="web",
            content_preview="Test content",
            error_message="Test error",
            sidecar_path=None,
            step=3,
        )
        r = api_client.get("/api/ingest/failures")
        assert r.status_code == 200
        failures = r.json()
        assert len(failures) >= 1

    def test_delete_removes_record(self, api_client: TestClient):
        registry = api_client.app.state.failed_registry
        record_id = registry.add(
            source="web",
            content_preview="Delete me",
            error_message="error",
            sidecar_path=None,
            step=3,
        )
        r = api_client.delete(f"/api/ingest/failures/{record_id}")
        assert r.status_code == 204
        # Should be gone
        r2 = api_client.delete(f"/api/ingest/failures/{record_id}")
        assert r2.status_code == 404

    def test_retry_success_creates_note(self, api_client: TestClient):
        """A valid retry must succeed: return status=ok, note_path, and content_truncated flag."""
        registry = api_client.app.state.failed_registry
        record_id = registry.add(
            source="web",
            content_preview="Met with Sarah today to discuss Q2 plans.",
            error_message="routing failed",
            sidecar_path=None,
            step=3,
        )
        r = api_client.post("/api/ingest/failures/retry", json={"id": record_id})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "note_path" in body
        assert "confidence" in body
        # content_truncated field must be present (False for short preview)
        assert "content_truncated" in body
        assert body["content_truncated"] is False  # 40-char preview < 200

        # Record should now be marked retried — verify it still appears (mark_retried ≠ delete)
        r2 = api_client.get("/api/ingest/failures")
        assert r2.status_code == 200


# ===========================================================================
# Transcribe
# ===========================================================================

class TestTranscribe:
    def test_transcribe_audio(self, api_client: TestClient):
        fake_audio = b"fake-audio-data"
        r = api_client.post(
            "/api/transcribe",
            files={"file": ("test.webm", fake_audio, "audio/webm")},
        )
        assert r.status_code == 200
        body = _json(r)
        assert "transcript" in body
        assert body["transcript"] == "transcribed audio content"

    def test_transcribe_empty_file_422(self, api_client: TestClient):
        r = api_client.post(
            "/api/transcribe",
            files={"file": ("empty.webm", b"", "audio/webm")},
        )
        assert r.status_code == 422


# ===========================================================================
# Stats
# ===========================================================================

class TestStats:
    def test_stats_returns_brain_stats(self, api_client: TestClient):
        r = api_client.get("/api/stats")
        assert r.status_code == 200
        body = _json(r)
        assert "total_notes" in body
        assert "total_chunks" in body
        assert "notes_by_type" in body
        assert "notes_by_domain" in body
        assert "pending_review" in body
        assert "failed_ingests" in body
        assert "index" in body
        assert "latency_p50_ms" in body
        assert "latency_p95_ms" in body

    def test_stats_counts_notes(self, api_client: TestClient):
        # Notes were created in the fixture
        r = api_client.get("/api/stats")
        body = _json(r)
        assert body["total_notes"] >= 2  # alice.md + decision-one.md from fixture


# ===========================================================================
# Stub routes still return 501 (routes not yet implemented in M8)
# ===========================================================================

STILL_STUB_ROUTES: list[tuple[str, str]] = [
    # teams (M21)
    ("POST", "/api/teams/messages"),
]


@pytest.mark.parametrize(
    "method,path",
    STILL_STUB_ROUTES,
    ids=[f"{m} {p}" for m, p in STILL_STUB_ROUTES],
)
def test_stub_still_returns_501(method: str, path: str):
    r = _stub_client.request(method, path)
    assert r.status_code == 501, (
        f"{method} {path} returned {r.status_code}, expected 501"
    )
