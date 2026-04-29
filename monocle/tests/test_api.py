"""
monocle/tests/test_api.py — M8 API integration tests.

Uses the `api_client` fixture (MemoryIndex + mock AIProvider) to test the
wired implementations of notes, search, ingest, failures, transcribe,
health, and stats endpoints.

Routes NOT implemented in M8 (graph, chat, agents, review, settings, teams)
continue to return 501 and are tested in the stub section at the bottom.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from monocle.models import ProposedAction


def _prepare_review_session(
    api_client: TestClient,
    *,
    open_questions: list[dict] | None = None,
    contradictions: list[dict] | None = None,
    proposed_actions: list[ProposedAction] | None = None,
) -> str:
    seed = api_client.put(
        "/api/notes/people/alice.md",
        json={
            "title": "Alice",
            "body": "Original meeting notes.",
            "metadata": {"type": "person_note", "domain": "work", "review_status": "approved"},
        },
    )
    assert seed.status_code in (200, 201)

    created = api_client.post(
        "/api/ingest",
        json={"content": "Prepared session for review workflow.", "source": "web"},
    )
    assert created.status_code == 202
    session_id = created.json()["session_id"]

    store = api_client.app.state.ingest_session_store
    job = store.claim_prepare_jobs(limit=1)[0]
    store.complete_prepare_job(
        job.job_id,
        session_id,
        title="Prepared review",
        digest="Review digest",
        open_questions=(
            open_questions
            if open_questions is not None
            else [{"id": "oq_1", "question": "What changed?", "reason": "Clarify the update."}]
        ),
        related_notes=[],
        contradictions=(
            contradictions
            if contradictions is not None
            else [{"file_path": "people/alice.md", "summary": "Existing note may be stale.", "severity": "warning"}]
        ),
        proposed_actions=(
            proposed_actions
            if proposed_actions is not None
            else [
                ProposedAction(
                    action_id="act_1",
                    action_type="update_note",
                    approval_state="draft",
                    target_file_path="people/alice.md",
                    target_note_type="person_note",
                    rationale="Refresh the person note.",
                    proposed_content={"title": "Alice", "body": "Updated meeting notes."},
                )
            ]
        ),
        artifact_payload={"digest": "Review digest"},
    )
    return session_id

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

    def test_health_models_200(self, api_client: TestClient):
        r = api_client.get("/api/health/models")
        assert r.status_code == 200
        body = _json(r)
        assert "provider" in body
        assert "provider_reachable" in body
        assert "models" in body
        assert isinstance(body["models"], list)

    def test_health_models_structure(self, api_client: TestClient):
        """Each model entry must have the expected fields."""
        r = api_client.get("/api/health/models")
        body = _json(r)
        for m in body["models"]:
            assert "name" in m
            assert "role" in m
            assert "available" in m
            assert "loaded" in m
            assert m["role"] in ("chat", "embed", "transcribe")


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

    def test_note_history_diff_and_restore_flow(self, api_client: TestClient):
        payload = {
            "title": "Versioned",
            "body": "Original body",
            "metadata": {"type": "observation", "domain": "work"},
        }
        created = api_client.put("/api/notes/work/versioned.md", json=payload)
        assert created.status_code == 201

        updated = api_client.put(
            "/api/notes/work/versioned.md",
            json={
                **payload,
                "body": "Updated body",
                "metadata": {**payload["metadata"], "review_status": "pending"},
            },
        )
        assert updated.status_code == 200

        history = api_client.get("/api/notes/work/versioned.md/history")
        assert history.status_code == 200
        entries = history.json()
        assert len(entries) == 1
        timestamp = entries[0]["timestamp"]

        version = api_client.get(f"/api/notes/work/versioned.md/history/{timestamp}")
        assert version.status_code == 200
        assert version.json()["note"]["body"] == "Original body"

        diff = api_client.get(f"/api/notes/work/versioned.md/history/{timestamp}/diff")
        assert diff.status_code == 200
        diff_body = diff.json()
        assert diff_body["diff_preview"]["kind"] == "history"
        assert {hunk["section"] for hunk in diff_body["diff_preview"]["hunks"]} >= {"body", "frontmatter"}

        restored = api_client.post(
            f"/api/notes/work/versioned.md/history/{timestamp}/restore",
            json={"if_mtime": updated.json()["mtime"]},
        )
        assert restored.status_code == 200
        assert restored.json()["body"] == "Original body"

    def test_note_history_restore_rejects_stale_mtime(self, api_client: TestClient):
        payload = {
            "title": "Versioned",
            "body": "Original body",
            "metadata": {"type": "observation", "domain": "work"},
        }
        api_client.put("/api/notes/work/versioned-stale.md", json=payload)
        updated = api_client.put(
            "/api/notes/work/versioned-stale.md",
            json={
                **payload,
                "body": "Updated body",
                "metadata": {**payload["metadata"], "review_status": "pending"},
            },
        )
        assert updated.status_code == 200
        stale_mtime = updated.json()["mtime"]
        timestamp = api_client.get("/api/notes/work/versioned-stale.md/history").json()[0]["timestamp"]

        newest = api_client.put(
            "/api/notes/work/versioned-stale.md",
            json={
                **payload,
                "body": "Newest body",
                "metadata": {**payload["metadata"], "review_status": "pending"},
                "if_mtime": stale_mtime,
            },
        )
        assert newest.status_code == 200

        restored = api_client.post(
            f"/api/notes/work/versioned-stale.md/history/{timestamp}/restore",
            json={"if_mtime": stale_mtime},
        )
        assert restored.status_code == 409

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
# Omni Search
# ===========================================================================

class TestOmniSearch:
    def test_omni_search_requires_min_3_chars(self, api_client: TestClient):
        r = api_client.get("/api/search/omni?q=ab")
        assert r.status_code == 422

    def test_omni_search_trims_query_before_min_length_check(self, api_client: TestClient):
        r = api_client.get("/api/search/omni", params={"q": " ab "})
        assert r.status_code == 422

    def test_omni_search_requires_q(self, api_client: TestClient):
        r = api_client.get("/api/search/omni")
        assert r.status_code == 422

    def test_omni_search_filename_match(self, api_client: TestClient):
        api_client.put(
            "/api/notes/work/omni_fname_test.md",
            json={"title": "Omni Fname", "body": "some content", "metadata": {}},
        )
        r = api_client.get("/api/search/omni?q=omni_fname")
        assert r.status_code == 200
        results = r.json()
        assert isinstance(results, list)
        matches = [item for item in results if "omni_fname" in item["file_path"]]
        assert matches, "Expected at least one filename match"
        assert matches[0]["match_location"] == "filename"

    def test_omni_search_frontmatter_match(self, api_client: TestClient):
        api_client.put(
            "/api/notes/work/omni_fm_note.md",
            json={
                "title": "xfmtag_unique_title",
                "body": "body without the keyword",
                "metadata": {"tags": ["xfmtag_unique_title"]},
            },
        )
        r = api_client.get("/api/search/omni?q=xfmtag_unique")
        assert r.status_code == 200
        results = r.json()
        fm_matches = [
            item for item in results
            if "omni_fm_note" in item["file_path"] and item["match_location"] in ("filename", "frontmatter")
        ]
        assert fm_matches

    def test_omni_search_people_frontmatter_match(self, api_client: TestClient):
        api_client.put(
            "/api/notes/work/team-sync.md",
            json={
                "title": "Weekly team sync",
                "body": "Discussed open review items.",
                "metadata": {"people": ["Sarah Chen", "Taylor Reed"]},
            },
        )
        r = api_client.get("/api/search/omni?q=sarah")
        assert r.status_code == 200
        results = r.json()
        matches = [
            item for item in results
            if item["file_path"] == "work/team-sync.md"
        ]
        assert matches
        assert matches[0]["match_location"] == "frontmatter"

    def test_omni_search_body_match(self, api_client: TestClient):
        api_client.put(
            "/api/notes/work/omni_body_note.md",
            json={"title": "Ordinary Title", "body": "xbodyterm_unique_789 found here", "metadata": {}},
        )
        r = api_client.get("/api/search/omni?q=xbodyterm_unique")
        assert r.status_code == 200
        results = r.json()
        body_matches = [item for item in results if "omni_body_note" in item["file_path"]]
        assert body_matches
        assert body_matches[0]["match_location"] == "body"

    def test_omni_search_priority_order(self, api_client: TestClient):
        """Filename matches must appear before frontmatter, frontmatter before body."""
        api_client.put(
            "/api/notes/work/orderprio_filename.md",
            json={"title": "orderprio title", "body": "orderprio content", "metadata": {}},
        )
        r = api_client.get("/api/search/omni?q=orderprio")
        assert r.status_code == 200
        results = r.json()
        assert results, "Expected results for 'orderprio'"
        # First result for this query should be the filename match
        first = results[0]
        assert first["match_location"] == "filename"

    def test_omni_search_result_fields(self, api_client: TestClient):
        r = api_client.get("/api/search/omni?q=test")
        assert r.status_code == 200
        for item in r.json():
            assert "file_path" in item
            assert "title" in item
            assert "excerpt" in item
            assert "match_location" in item
            assert item["match_location"] in ("filename", "frontmatter", "body")

    def test_omni_search_reuses_cached_catalog_until_invalidated(self, api_client: TestClient):
        api_client.put(
            "/api/notes/work/cache-target.md",
            json={"title": "cache target", "body": "cache needle", "metadata": {}},
        )
        catalog = api_client.app.state.omni_search_catalog

        with patch.object(catalog, "_build_full_catalog", wraps=catalog._build_full_catalog) as build_catalog:
            first = api_client.get("/api/search/omni?q=cache")
            second = api_client.get("/api/search/omni?q=cache")

        assert first.status_code == 200
        assert second.status_code == 200
        assert build_catalog.call_count == 1

    def test_omni_search_refreshes_invalidated_entry(self, api_client: TestClient):
        api_client.put(
            "/api/notes/work/cache-refresh.md",
            json={
                "title": "Weekly sync",
                "body": "Original body text.",
                "metadata": {"people": ["Sarah Chen"]},
            },
        )
        catalog = api_client.app.state.omni_search_catalog

        warm = api_client.get("/api/search/omni?q=sarah")
        assert warm.status_code == 200
        assert any(item["file_path"] == "work/cache-refresh.md" for item in warm.json())

        api_client.put(
            "/api/notes/work/cache-refresh.md",
            json={
                "title": "Weekly sync",
                "body": "Original body text.",
                "metadata": {"people": ["Jordan Ellis"]},
            },
        )
        catalog.invalidate("work/cache-refresh.md")

        stale = api_client.get("/api/search/omni?q=sarah")
        refreshed = api_client.get("/api/search/omni?q=jordan")

        assert stale.status_code == 200
        assert refreshed.status_code == 200
        assert all(item["file_path"] != "work/cache-refresh.md" for item in stale.json())
        assert any(item["file_path"] == "work/cache-refresh.md" for item in refreshed.json())


# ===========================================================================
# Ingest
# ===========================================================================

class TestIngest:
    def test_ingest_text_returns_202_with_session_summary(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest",
            json={"content": "Met with Sarah today about the project.", "source": "web"},
        )
        assert r.status_code == 202
        body = _json(r)
        assert body["origin"] == "api"
        assert body["state"] == "queued"
        assert body["session_id"].startswith("ing_")
        assert len(body["source_ids"]) == 1
        assert body["source_ids"][0].startswith("src_")
        assert body["notification"]["kind"] == "ingest_captured"

    def test_ingest_forces_origin_to_api(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest",
            json={"content": "Client tries to spoof origin.", "source": "web", "origin": "chat"},
        )
        assert r.status_code == 202
        body = _json(r)
        assert body["origin"] == "api"

        detail = api_client.get(f"/api/ingest/sessions/{body['session_id']}")
        assert detail.status_code == 200
        assert detail.json()["session"]["origin"] == "api"

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

    def test_ingest_session_can_be_loaded_after_creation(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest",
            json={"content": "I decided to refactor the pipeline.", "source": "web"},
        )
        assert r.status_code == 202
        session_id = r.json()["session_id"]

        detail = api_client.get(f"/api/ingest/sessions/{session_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["session"]["session_id"] == session_id
        assert body["session"]["state"] == "queued"
        assert body["session"]["proposed_actions"] == []
        assert len(body["sources"]) == 1
        assert body["sources"][0]["status"] == "archived"

    def test_list_ingest_sessions_returns_created_session(self, api_client: TestClient):
        created = api_client.post(
            "/api/ingest",
            json={"content": "Queue this for later review.", "source": "web"},
        )
        assert created.status_code == 202
        session_id = created.json()["session_id"]

        listed = api_client.get("/api/ingest/sessions")
        assert listed.status_code == 200
        sessions = listed.json()
        assert any(item["session_id"] == session_id for item in sessions)

    def test_fast_capture_executes_clean_session_without_review_handoff(self, api_client: TestClient):
        created = api_client.post(
            "/api/ingest",
            json={
                "content": "Capture this directly into the vault as a clean fast-capture note.",
                "source": "voice",
                "fast_capture": True,
            },
        )
        assert created.status_code == 202
        body = created.json()
        assert body["state"] == "completed"

        detail = api_client.get(f"/api/ingest/sessions/{body['session_id']}")
        assert detail.status_code == 200
        session = detail.json()["session"]
        assert session["fast_capture"] is True
        assert session["state"] == "completed"
        assert session["execution_summary"]["succeeded"] == 1
        assert session["execution_summary"]["failed"] == 0
        assert session["proposed_actions"][0]["approval_state"] == "executed"
        written_path = session["proposed_actions"][0]["execution_result"]["file_path"]

        note = api_client.get(f"/api/notes/{written_path}")
        assert note.status_code == 200
        note_body = note.json()
        assert note_body["metadata"]["sources"][0]["session_id"] == body["session_id"]

    def test_fast_capture_falls_back_to_review_when_open_questions_exist(self, api_client: TestClient):
        async def _chat_with_fast_capture_blockers(messages, **kwargs):
            content = messages[-1].get("content", "") if messages else ""
            if '"routing_decision"' in content and '"source_excerpt"' in content:
                return json.dumps(
                    {
                        "title": "Needs clarification",
                        "digest": "Fast capture surfaced an unanswered question.",
                        "open_questions": [{"question": "Who owns this follow-up?", "reason": "Missing owner."}],
                        "contradictions": [],
                        "proposed_actions": [
                            {
                                "action_type": "create_note",
                                "target_note_type": "observation",
                                "rationale": "Prepared for manual review.",
                                "proposed_content": {"title": "Needs clarification", "body": "Question remains open."},
                            }
                        ],
                    }
                )
            return '{"type": "other", "domain": "personal", "tags": []}'

        api_client.app.state.ai.chat = AsyncMock(side_effect=_chat_with_fast_capture_blockers)

        created = api_client.post(
            "/api/ingest",
            json={
                "content": "Fast capture should stop and ask a question here.",
                "source": "voice",
                "fast_capture": True,
            },
        )
        assert created.status_code == 202
        body = created.json()
        assert body["state"] == "awaiting_user"

        detail = api_client.get(f"/api/ingest/sessions/{body['session_id']}")
        assert detail.status_code == 200
        session = detail.json()["session"]
        assert session["fast_capture"] is True
        assert session["state"] == "awaiting_user"
        assert session["open_questions"][0]["question"] == "Who owns this follow-up?"

    def test_fast_capture_preserves_failed_prepare_state(self, api_client: TestClient):
        api_client.app.state.ingest_prepare_worker._build_prepared_session = AsyncMock(
            side_effect=RuntimeError("prep exploded")
        )

        created = api_client.post(
            "/api/ingest",
            json={
                "content": "This fast capture should stay failed when preparation explodes.",
                "source": "voice",
                "fast_capture": True,
            },
        )
        assert created.status_code == 202
        body = created.json()
        assert body["state"] == "failed"

        detail = api_client.get(f"/api/ingest/sessions/{body['session_id']}")
        assert detail.status_code == 200
        session = detail.json()["session"]
        assert session["fast_capture"] is True
        assert session["state"] == "failed"
        assert session["proposed_actions"] == []

    def test_fast_capture_returns_to_proposal_ready_when_execution_fails(
        self,
        api_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from monocle import mcp_server

        original_create_note = mcp_server.create_note
        vault = api_client.app.state.vault

        async def corrupting_create_note(*args, **kwargs):
            result = await original_create_note(*args, **kwargs)
            created = json.loads(result)
            note = vault.read_note(created["file_path"])
            note.body = "Corrupted after write."
            vault.write_note(created["file_path"], note)
            return result

        monkeypatch.setattr(mcp_server, "create_note", corrupting_create_note)

        created = api_client.post(
            "/api/ingest",
            json={
                "content": "This fast capture should recover into proposal review after execution failure.",
                "source": "voice",
                "fast_capture": True,
            },
        )
        assert created.status_code == 202
        body = created.json()
        assert body["state"] == "proposal_ready"

        detail = api_client.get(f"/api/ingest/sessions/{body['session_id']}")
        assert detail.status_code == 200
        session = detail.json()["session"]
        assert session["state"] == "proposal_ready"
        assert session["execution_summary"]["succeeded"] == 0
        assert session["execution_summary"]["failed"] == 1
        assert session["proposed_actions"][0]["approval_state"] == "failed"
        assert "validation failed" in session["proposed_actions"][0]["execution_result"]["message"].lower()

    def test_ingest_session_true_up_requeues_prepared_session(self, api_client: TestClient):
        created = api_client.post(
            "/api/ingest",
            json={"content": "Make this ready, then refresh it.", "source": "web"},
        )
        assert created.status_code == 202
        session_id = created.json()["session_id"]
        store = api_client.app.state.ingest_session_store
        job = store.claim_prepare_jobs(limit=1)[0]
        store.complete_prepare_job(
            job.job_id,
            session_id,
            title="Prepared",
            digest="Digest",
            open_questions=[],
            related_notes=[],
            contradictions=[],
            proposed_actions=[],
            artifact_payload={"digest": "Digest"},
        )

        response = api_client.post(f"/api/ingest/sessions/{session_id}/true-up")
        assert response.status_code == 202
        body = response.json()
        assert body["session_id"] == session_id
        assert body["state"] == "queued"

        detail = api_client.get(f"/api/ingest/sessions/{session_id}")
        assert detail.status_code == 200
        assert detail.json()["session"]["state"] == "queued"

    def test_ingest_review_flow_supports_questions_edits_diffs_and_individual_approval_handoff(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client)

        detail = api_client.get(f"/api/ingest/sessions/{session_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["session"]["contradictions"][0]["title"] == "Alice"
        assert body["session"]["proposed_actions"][0]["diff_preview"]["kind"] == "update"
        assert body["session"]["proposed_actions"][0]["diff_preview"]["hunks"][0]["section"] in {"title", "body"}

        started = api_client.post(f"/api/ingest/sessions/{session_id}/start-review")
        assert started.status_code == 200
        assert started.json()["session"]["state"] == "in_review"

        answered = api_client.patch(
            f"/api/ingest/sessions/{session_id}/questions/oq_1",
            json={"answer": "It now includes the new meeting outcome."},
        )
        assert answered.status_code == 200
        answered_body = answered.json()
        assert answered_body["session"]["state"] == "proposal_ready"
        assert answered_body["session"]["open_questions"][0]["answer"] == "It now includes the new meeting outcome."

        patched = api_client.patch(
            f"/api/ingest/sessions/{session_id}/actions/act_1",
            json={
                "rationale": "Refresh the person note with the clarified outcome.",
                "proposed_content": {"body": "Edited meeting notes with clarified outcome."},
            },
        )
        assert patched.status_code == 200
        patched_body = patched.json()
        assert patched_body["session"]["proposed_actions"][0]["rationale"] == "Refresh the person note with the clarified outcome."
        assert patched_body["session"]["proposed_actions"][0]["diff_preview"]["after_excerpt"] == "Edited meeting notes with clarified outcome."

        approved = api_client.post(f"/api/ingest/sessions/{session_id}/actions/act_1/approve")
        assert approved.status_code == 200
        approved_body = approved.json()
        assert approved_body["session"]["state"] == "approved_pending_execution"
        assert approved_body["session"]["proposed_actions"][0]["approval_state"] == "approved"

    def test_ingest_review_answering_last_question_without_actions_enters_proposal_ready(self, api_client: TestClient):
        session_id = _prepare_review_session(
            api_client,
            contradictions=[],
            proposed_actions=[],
        )

        started = api_client.post(f"/api/ingest/sessions/{session_id}/start-review")
        assert started.status_code == 200
        assert started.json()["session"]["state"] == "in_review"

        answered = api_client.patch(
            f"/api/ingest/sessions/{session_id}/questions/oq_1",
            json={"answer": "There are no follow-up note actions for this capture."},
        )
        assert answered.status_code == 200
        answered_body = answered.json()
        assert answered_body["session"]["state"] == "proposal_ready"
        assert answered_body["session"]["proposed_actions"] == []

    def test_ingest_review_approve_all_does_not_promote_rejected_only_session(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client, open_questions=[])

        rejected = api_client.post(f"/api/ingest/sessions/{session_id}/actions/act_1/reject")
        assert rejected.status_code == 200
        rejected_body = rejected.json()
        assert rejected_body["session"]["state"] == "proposal_ready"
        assert rejected_body["session"]["proposed_actions"][0]["approval_state"] == "rejected"

        approve_all = api_client.post(f"/api/ingest/sessions/{session_id}/approve-all")
        assert approve_all.status_code == 200
        approve_all_body = approve_all.json()
        assert approve_all_body["session"]["state"] == "proposal_ready"
        assert approve_all_body["session"]["proposed_actions"][0]["approval_state"] == "rejected"

    def test_ingest_review_patch_rejects_target_path_traversal(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client, open_questions=[])

        patched = api_client.patch(
            f"/api/ingest/sessions/{session_id}/actions/act_1",
            json={"target_file_path": "../../.env"},
        )

        assert patched.status_code == 403

    def test_ingest_review_diff_preview_preserves_explicit_body_clear(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client, open_questions=[])

        patched = api_client.patch(
            f"/api/ingest/sessions/{session_id}/actions/act_1",
            json={"proposed_content": {"body": ""}},
        )

        assert patched.status_code == 200
        patched_body = patched.json()
        body_hunk = next(
            hunk
            for hunk in patched_body["session"]["proposed_actions"][0]["diff_preview"]["hunks"]
            if hunk["section"] == "body"
        )
        assert body_hunk["before"] == "Original meeting notes."
        assert body_hunk["after"] is None

    def test_ingest_review_patch_rejects_approval_state_in_patch_payload(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client, open_questions=[])

        patched = api_client.patch(
            f"/api/ingest/sessions/{session_id}/actions/act_1",
            json={"approval_state": "approved"},
        )

        assert patched.status_code == 422

    def test_ingest_review_patch_rejects_invalid_target_note_type(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client, open_questions=[])

        patched = api_client.patch(
            f"/api/ingest/sessions/{session_id}/actions/act_1",
            json={"target_note_type": "totally_invalid_type"},
        )

        assert patched.status_code == 422

    def test_ingest_review_execute_runs_approved_actions_through_mcp_and_validates_result(self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch):
        session_id = _prepare_review_session(api_client, open_questions=[])

        approved = api_client.post(f"/api/ingest/sessions/{session_id}/actions/act_1/approve")
        assert approved.status_code == 200

        from monocle import mcp_server

        original_update_note = mcp_server.update_note
        update_spy = AsyncMock(side_effect=original_update_note)
        monkeypatch.setattr(mcp_server, "update_note", update_spy)

        executed = api_client.post(f"/api/ingest/sessions/{session_id}/execute")
        assert executed.status_code == 200
        body = executed.json()
        assert body["session"]["state"] == "completed"
        assert body["session"]["execution_summary"]["succeeded"] == 1
        assert body["session"]["execution_summary"]["failed"] == 0
        assert body["session"]["execution_summary"]["skipped"] == 0
        assert body["session"]["execution_summary"]["completed_at"] is not None
        assert body["session"]["proposed_actions"][0]["approval_state"] == "executed"
        assert body["session"]["proposed_actions"][0]["execution_result"]["status"] == "succeeded"
        assert update_spy.await_count == 1

        note = api_client.get("/api/notes/people/alice.md")
        assert note.status_code == 200
        note_body = note.json()
        assert note_body["title"] == "Alice"
        assert note_body["body"] == "Updated meeting notes."
        assert note_body["metadata"]["sources"][0]["source_id"].startswith("src_")

    def test_ingest_review_execute_rejects_sessions_not_ready_for_execution(self, api_client: TestClient):
        session_id = _prepare_review_session(api_client, open_questions=[])

        executed = api_client.post(f"/api/ingest/sessions/{session_id}/execute")
        assert executed.status_code == 409
        assert "approved_pending_execution" in executed.json()["detail"]

    def test_ingest_review_execute_rolls_back_when_post_apply_validation_fails(self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch):
        session_id = _prepare_review_session(api_client, open_questions=[])

        approved = api_client.post(f"/api/ingest/sessions/{session_id}/actions/act_1/approve")
        assert approved.status_code == 200

        from monocle import mcp_server

        original_update_note = mcp_server.update_note
        vault = api_client.app.state.vault

        async def corrupting_update_note(*args, **kwargs):
            result = await original_update_note(*args, **kwargs)
            note = vault.read_note(kwargs["file_path"])
            note.body = "Corrupted after write."
            vault.write_note(kwargs["file_path"], note)
            return result

        monkeypatch.setattr(mcp_server, "update_note", corrupting_update_note)

        executed = api_client.post(f"/api/ingest/sessions/{session_id}/execute")
        assert executed.status_code == 200
        body = executed.json()
        assert body["session"]["state"] == "failed"
        assert body["session"]["execution_summary"]["succeeded"] == 0
        assert body["session"]["execution_summary"]["failed"] == 1
        assert body["session"]["proposed_actions"][0]["approval_state"] == "failed"
        assert "validation failed" in body["session"]["proposed_actions"][0]["execution_result"]["message"].lower()

        note = api_client.get("/api/notes/people/alice.md")
        assert note.status_code == 200
        note_body = note.json()
        assert note_body["body"] == "Original meeting notes."

    def test_archived_source_endpoints_list_and_read_text_content(self, api_client: TestClient):
        created = api_client.post(
            "/api/ingest",
            json={"content": "Captured source body.", "source": "web"},
        )
        assert created.status_code == 202

        listed = api_client.get("/api/ingest/sources")
        assert listed.status_code == 200
        sources = listed.json()
        assert len(sources) >= 1
        source_id = sources[0]["source_id"]

        source = api_client.get(f"/api/ingest/sources/{source_id}")
        assert source.status_code == 200
        assert source.json()["source_id"] == source_id

        content = api_client.get(f"/api/ingest/sources/{source_id}/content")
        assert content.status_code == 200
        body = content.json()
        assert body["source"]["source_id"] == source_id
        assert "Captured source body." in body["text"]

    def test_archived_source_content_rejects_binary_sources_but_download_allows_them(self, api_client: TestClient):
        created = api_client.post(
            "/api/ingest",
            json={
                "source": "voice",
                "audio_bytes": "AQIDBA==",
                "audio_mime_type": "audio/wav",
            },
        )
        assert created.status_code == 202

        listed = api_client.get("/api/ingest/sources")
        assert listed.status_code == 200
        source_id = next(source["source_id"] for source in listed.json() if source["kind"] == "audio")

        content = api_client.get(f"/api/ingest/sources/{source_id}/content")
        assert content.status_code == 415

        download = api_client.get(f"/api/ingest/sources/{source_id}/download")
        assert download.status_code == 200
        assert download.content == b"\x01\x02\x03\x04"

    def test_archived_source_content_truncates_large_text_payloads(self, api_client: TestClient):
        from monocle.routers import ingest as ingest_router

        created = api_client.post(
            "/api/ingest",
            json={
                "content": "x" * (ingest_router._MAX_SOURCE_TEXT_BYTES + 10),
                "source": "web",
            },
        )
        assert created.status_code == 202

        listed = api_client.get("/api/ingest/sources")
        assert listed.status_code == 200
        source_id = listed.json()[0]["source_id"]

        content = api_client.get(f"/api/ingest/sources/{source_id}/content")
        assert content.status_code == 200
        body = content.json()
        assert body["truncated"] is True
        assert len(body["text"]) == ingest_router._MAX_SOURCE_TEXT_BYTES

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

    def test_ingest_stream_forces_origin_to_api(self, api_client: TestClient):
        r = api_client.post(
            "/api/ingest/stream",
            json={"content": "SSE origin spoof attempt", "source": "web", "origin": "inbox"},
        )
        assert r.status_code == 200

        done_payload = None
        event_name = None
        for line in r.text.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
            elif event_name == "done" and line.startswith("data: "):
                import json as _json

                done_payload = _json.loads(line[len("data: "):])
                break

        assert done_payload is not None
        assert done_payload["origin"] == "api"

        detail = api_client.get(f"/api/ingest/sessions/{done_payload['session_id']}")
        assert detail.status_code == 200
        assert detail.json()["session"]["origin"] == "api"
        assert "session_id" in done_payload
        assert "state" in done_payload
        assert "elapsed_ms" in done_payload


# ===========================================================================
# Ingest Failures
# ===========================================================================

class TestIngestFailures:
    def test_delete_failure_404_for_missing(self, api_client: TestClient):
        r = api_client.delete("/api/ingest/failures/nonexistent-id-xyz")
        assert r.status_code == 404

    def test_retry_failure_404_for_missing(self, api_client: TestClient):
        r = api_client.post("/api/ingest/failures/retry", json={"id": "nonexistent-id-xyz"})
        assert r.status_code == 404

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
        assert registry.get(record_id) is None
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
        assert registry.get(record_id)["status"] == "retried"


# ===========================================================================
# Capture Workbench
# ===========================================================================

class TestCaptureWorkbench:
    def test_capture_workbench_aggregates_prepared_pending_and_failures(self, api_client: TestClient):
        prepared_session_id = _prepare_review_session(api_client, open_questions=[])

        pending = api_client.put(
            "/api/notes/work/pending-workbench.md",
            json={
                "title": "Pending workbench note",
                "body": "Needs explicit approval.",
                "metadata": {
                    "type": "observation",
                    "domain": "work",
                    "review_status": "pending",
                    "confidence": 0.42,
                },
            },
        )
        assert pending.status_code in (200, 201)

        failed_created = api_client.post(
            "/api/ingest",
            json={"content": "This prepared session should fail.", "source": "web"},
        )
        assert failed_created.status_code == 202
        failed_session_id = failed_created.json()["session_id"]

        store = api_client.app.state.ingest_session_store
        failed_job = store.claim_prepare_job_for_session(failed_session_id)
        assert failed_job is not None
        store.fail_prepare_job(failed_job.job_id, failed_session_id, "prep exploded")

        registry = api_client.app.state.failed_registry
        registry.add(
            source="web",
            content_preview="URL capture timed out.",
            error_message="summary timed out",
            sidecar_path=None,
            step=4,
        )

        response = api_client.get("/api/capture-workbench?limit_per_section=10")
        assert response.status_code == 200
        body = response.json()

        assert body["actionable_count"] == 4
        assert body["counts"] == {
            "prepared": 1,
            "pending_review": 1,
            "failures": 2,
        }

        sections = {section["section"]: section for section in body["sections"]}
        assert sections["prepared"]["count"] == 1
        assert sections["prepared"]["items"][0]["session_id"] == prepared_session_id

        assert sections["pending_review"]["count"] == 1
        assert sections["pending_review"]["items"][0]["file_path"] == "work/pending-workbench.md"

        assert sections["failures"]["count"] == 2
        failure_types = {item["item_type"] for item in sections["failures"]["items"]}
        assert failure_types == {"failed_session", "failed_ingest"}
        assert any(item.get("session_id") == failed_session_id for item in sections["failures"]["items"])

    def test_capture_workbench_failure_section_merges_by_newest_item_before_limit(self, api_client: TestClient):
        registry = api_client.app.state.failed_registry
        record_id = registry.add(
            source="web",
            content_preview="Older failed URL capture.",
            error_message="summary timed out",
            sidecar_path=None,
            step=4,
        )
        registry_record = registry.get(record_id)
        assert registry_record is not None
        registry_record["timestamp"] = "2026-04-29T10:00:00+00:00"
        registry._save()

        failed_created = api_client.post(
            "/api/ingest",
            json={"content": "This prepared session should fail later.", "source": "web"},
        )
        assert failed_created.status_code == 202
        failed_session_id = failed_created.json()["session_id"]

        store = api_client.app.state.ingest_session_store
        failed_job = store.claim_prepare_job_for_session(failed_session_id)
        assert failed_job is not None
        store.fail_prepare_job(failed_job.job_id, failed_session_id, "prep exploded")

        with store._connect() as conn:
            conn.execute(
                "UPDATE ingest_sessions SET updated_at = ? WHERE session_id = ?",
                ("2026-04-29T10:00:01Z", failed_session_id),
            )

        response = api_client.get("/api/capture-workbench?limit_per_section=1")
        assert response.status_code == 200
        body = response.json()

        failures = next(section for section in body["sections"] if section["section"] == "failures")
        assert failures["count"] == 2
        assert len(failures["items"]) == 1
        assert failures["items"][0]["item_type"] == "failed_session"
        assert failures["items"][0]["session_id"] == failed_session_id

    def test_capture_workbench_applies_queue_threshold_to_pending_review_items(
        self,
        api_client: TestClient,
    ):
        settings = api_client.app.state.settings
        settings.review.queue_threshold = 0.5

        low = api_client.put(
            "/api/notes/work/pending-low.md",
            json={
                "title": "Low confidence pending note",
                "body": "Should stay visible in the workbench.",
                "metadata": {
                    "type": "observation",
                    "domain": "work",
                    "review_status": "pending",
                    "confidence": 0.4,
                },
            },
        )
        high = api_client.put(
            "/api/notes/work/pending-high.md",
            json={
                "title": "High confidence pending note",
                "body": "Should remain in legacy review but not the workbench count.",
                "metadata": {
                    "type": "observation",
                    "domain": "work",
                    "review_status": "pending",
                    "confidence": 0.9,
                },
            },
        )
        assert low.status_code in (200, 201)
        assert high.status_code in (200, 201)

        workbench = api_client.get("/api/capture-workbench")
        assert workbench.status_code == 200
        workbench_body = workbench.json()
        assert workbench_body["queue_threshold"] == 0.5
        assert workbench_body["counts"]["pending_review"] == 1
        pending_items = next(section for section in workbench_body["sections"] if section["section"] == "pending_review")["items"]
        assert [item["file_path"] for item in pending_items] == ["work/pending-low.md"]


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
# Inbox callback helpers (_is_monocle_note, _strip_frontmatter)
# ===========================================================================

class TestInboxCallbackHelpers:
    """Unit tests for the helpers used inside _inbox_ingest_callback.

    These helpers prevent double-ingest of notes that were already written by
    the Monocle pipeline or agent tools (the root cause of the spurious
    ``people/person.md`` duplicate when an agent creates a note).
    """

    def test_is_monocle_note_detects_approval_mode(self):
        from monocle.main import _is_monocle_note
        raw = "---\ntitle: Foo\napproval_mode: null\n---\nBody text"
        assert _is_monocle_note(raw) is True

    def test_is_monocle_note_false_for_plain_obsidian(self):
        from monocle.main import _is_monocle_note
        raw = "---\ntitle: Foo\ntags: [work]\n---\nBody text"
        assert _is_monocle_note(raw) is False

    def test_is_monocle_note_false_for_raw_text_no_frontmatter(self):
        from monocle.main import _is_monocle_note
        assert _is_monocle_note("I met Sarah today at the conference.") is False

    def test_is_monocle_note_true_for_realistic_agent_note(self):
        from monocle.main import _is_monocle_note
        # Mirrors the exact frontmatter written by create_from_template
        raw = (
            "---\n"
            "action_items: []\n"
            "approval_mode: null\n"
            "approved_at: null\n"
            "approved_by: null\n"
            "confidence: 1.0\n"
            "review_status: pending\n"
            "title: Grayson Gallagher\n"
            "---\n"
            "Grayson is a 4 year old who loves Legos.\n"
        )
        assert _is_monocle_note(raw) is True

    def test_strip_frontmatter_removes_yaml_block(self):
        from monocle.main import _strip_frontmatter
        raw = "---\ntitle: Foo\n---\nBody text here"
        assert _strip_frontmatter(raw) == "Body text here"

    def test_strip_frontmatter_returns_original_when_no_frontmatter(self):
        from monocle.main import _strip_frontmatter
        raw = "Just raw text, no frontmatter."
        assert _strip_frontmatter(raw) == raw

    def test_strip_frontmatter_returns_original_when_no_closing_delimiter(self):
        from monocle.main import _strip_frontmatter
        raw = "---\ntitle: Foo\nno closing delimiter"
        assert _strip_frontmatter(raw) == raw


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
