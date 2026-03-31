"""monocle/tests/test_review.py — Tests for Review queue endpoints (M13)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: create a pending note via the notes API
# ---------------------------------------------------------------------------


def _add_pending_note(client: TestClient, path: str = "inbox/pending-test.md") -> str:
    """Create a note with review_status=pending and return its vault-relative path."""
    r = client.put(
        f"/api/notes/{path}",
        json={
            "title": "Pending Note",
            "body": "Something to review.",
            "metadata": {"review_status": "pending", "confidence": 0.4},
        },
    )
    assert r.status_code in (200, 201), f"Setup PUT failed: {r.status_code} {r.text}"
    return path


# ===========================================================================
# GET /api/review
# ===========================================================================


class TestListReview:
    def test_list_review_returns_200(self, api_client: TestClient) -> None:
        r = api_client.get("/api/review")
        assert r.status_code == 200

    def test_list_review_has_pagination_fields(self, api_client: TestClient) -> None:
        body = api_client.get("/api/review").json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)

    def test_list_review_returns_only_pending_notes(self, api_client: TestClient) -> None:
        _add_pending_note(api_client, "inbox/pending-filter.md")
        body = api_client.get("/api/review").json()
        for item in body["items"]:
            assert item["review_status"] == "pending"

    def test_list_review_excludes_approved_notes(self, api_client: TestClient) -> None:
        # alice.md from the api_client fixture is approved — must not appear
        body = api_client.get("/api/review").json()
        for item in body["items"]:
            assert "alice" not in item["file_path"]

    def test_list_review_includes_newly_pending_note(self, api_client: TestClient) -> None:
        _add_pending_note(api_client, "inbox/new-pending.md")
        body = api_client.get("/api/review").json()
        paths = [item["file_path"] for item in body["items"]]
        assert "inbox/new-pending.md" in paths

    def test_list_review_pagination_limit(self, api_client: TestClient) -> None:
        for i in range(4):
            _add_pending_note(api_client, f"inbox/page-{i}.md")
        body = api_client.get("/api/review?limit=2&offset=0").json()
        assert body["limit"] == 2
        assert len(body["items"]) <= 2

    def test_list_review_pagination_offset(self, api_client: TestClient) -> None:
        for i in range(4):
            _add_pending_note(api_client, f"inbox/offs-{i}.md")
        body_p1 = api_client.get("/api/review?limit=2&offset=0").json()
        body_p2 = api_client.get("/api/review?limit=2&offset=2").json()
        ids_p1 = {item["file_path"] for item in body_p1["items"]}
        ids_p2 = {item["file_path"] for item in body_p2["items"]}
        assert ids_p1.isdisjoint(ids_p2)


# ===========================================================================
# GET /api/review/count
# ===========================================================================


class TestReviewCount:
    def test_count_returns_200(self, api_client: TestClient) -> None:
        assert api_client.get("/api/review/count").status_code == 200

    def test_count_returns_integer(self, api_client: TestClient) -> None:
        body = api_client.get("/api/review/count").json()
        assert "count" in body
        assert isinstance(body["count"], int)

    def test_count_is_zero_when_no_pending_notes(self, api_client: TestClient) -> None:
        # Fresh vault from fixture — only approved notes
        body = api_client.get("/api/review/count").json()
        assert body["count"] == 0

    def test_count_increases_after_pending_note_added(self, api_client: TestClient) -> None:
        before = api_client.get("/api/review/count").json()["count"]
        _add_pending_note(api_client, "inbox/count-adds.md")
        after = api_client.get("/api/review/count").json()["count"]
        assert after == before + 1


# ===========================================================================
# PATCH /api/review/{path}/approve
# ===========================================================================


class TestApproveNote:
    def test_approve_returns_200(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-me.md")
        r = api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "user"})
        assert r.status_code == 200

    def test_approve_sets_review_status_approved(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-status.md")
        api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "alice"})
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["review_status"] == "approved"

    def test_approve_sets_approval_mode_manual(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-mode.md")
        api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "alice"})
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["approval_mode"] == "manual"

    def test_approve_sets_approved_by(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-by.md")
        api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "bob"})
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["approved_by"] == "bob"

    def test_approve_sets_approved_at_timestamp(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-at.md")
        api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "user"})
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["approved_at"] is not None

    def test_approve_response_has_all_fields(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-resp.md")
        body = api_client.patch(
            f"/api/review/{path}/approve", json={"approved_by": "charlie"}
        ).json()
        assert body["review_status"] == "approved"
        assert body["approval_mode"] == "manual"
        assert body["approved_by"] == "charlie"
        assert "approved_at" in body
        assert body["file_path"] == path

    def test_approve_uses_default_approved_by(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-default.md")
        body = api_client.patch(f"/api/review/{path}/approve", json={}).json()
        assert body["approved_by"] == "user"

    def test_approve_404_for_missing_note(self, api_client: TestClient) -> None:
        r = api_client.patch(
            "/api/review/nonexistent/note.md/approve", json={"approved_by": "user"}
        )
        assert r.status_code == 404

    def test_approve_removes_from_review_queue(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-queue.md")
        api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "user"})
        items = api_client.get("/api/review").json()["items"]
        assert not any(item["file_path"] == path for item in items)


# ===========================================================================
# PATCH /api/review/{path}/reject
# ===========================================================================


class TestRejectNote:
    def test_reject_returns_200(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-me.md")
        r = api_client.patch(f"/api/review/{path}/reject")
        assert r.status_code == 200

    def test_reject_sets_review_status_rejected(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-status.md")
        api_client.patch(f"/api/review/{path}/reject")
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["review_status"] == "rejected"

    def test_reject_sets_approval_mode_manual(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-mode.md")
        api_client.patch(f"/api/review/{path}/reject")
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["approval_mode"] == "manual"

    def test_reject_sets_approved_by_as_user(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-by.md")
        api_client.patch(f"/api/review/{path}/reject")
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["approved_by"] == "user"

    def test_reject_sets_approved_at_timestamp(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-at.md")
        api_client.patch(f"/api/review/{path}/reject")
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["approved_at"] is not None

    def test_reject_response_has_all_fields(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-resp.md")
        body = api_client.patch(f"/api/review/{path}/reject").json()
        assert body["review_status"] == "rejected"
        assert body["approval_mode"] == "manual"
        assert body["approved_by"] == "user"
        assert "approved_at" in body
        assert body["file_path"] == path

    def test_reject_404_for_missing_note(self, api_client: TestClient) -> None:
        r = api_client.patch("/api/review/nonexistent/note.md/reject")
        assert r.status_code == 404

    def test_reject_removes_from_review_queue(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-queue.md")
        api_client.patch(f"/api/review/{path}/reject")
        items = api_client.get("/api/review").json()["items"]
        assert not any(item["file_path"] == path for item in items)

    def test_reject_note_not_valid_pydantic_on_read(self, api_client: TestClient) -> None:
        """Verify that rejecting and reading back a note passes Pydantic validation."""
        path = _add_pending_note(api_client, "inbox/reject-pydantic.md")
        api_client.patch(f"/api/review/{path}/reject")
        # This GET should NOT raise a Pydantic validation error
        r = api_client.get(f"/api/notes/{path}")
        assert r.status_code == 200, f"Failed to read rejected note: {r.text}"
        note = r.json()
        assert note["metadata"]["review_status"] == "rejected"

    def test_reject_decrements_pending_count_cache(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-cache.md")
        # Warm the cache
        api_client.get("/api/review/count")
        before = api_client.app.state._review_pending_count
        api_client.patch(f"/api/review/{path}/reject")
        after = api_client.app.state._review_pending_count
        assert after == max(0, before - 1)


# ===========================================================================
# POST /api/review/approve-all
# ===========================================================================


class TestApproveAll:
    def test_approve_all_returns_200(self, api_client: TestClient) -> None:
        r = api_client.post("/api/review/approve-all", json={"approved_by": "user"})
        assert r.status_code == 200

    def test_approve_all_returns_approved_count(self, api_client: TestClient) -> None:
        _add_pending_note(api_client, "inbox/all-1.md")
        _add_pending_note(api_client, "inbox/all-2.md")
        body = api_client.post("/api/review/approve-all", json={"approved_by": "admin"}).json()
        assert "approved" in body
        assert body["approved"] >= 2

    def test_approve_all_clears_review_queue(self, api_client: TestClient) -> None:
        _add_pending_note(api_client, "inbox/clear-1.md")
        _add_pending_note(api_client, "inbox/clear-2.md")
        api_client.post("/api/review/approve-all", json={"approved_by": "user"})
        assert api_client.get("/api/review/count").json()["count"] == 0

    def test_approve_all_when_queue_empty_returns_zero(self, api_client: TestClient) -> None:
        # No pending notes in fresh fixture
        body = api_client.post("/api/review/approve-all", json={}).json()
        assert body["approved"] == 0

    def test_approve_all_sets_notes_as_approved_in_vault(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/all-approved.md")
        api_client.post("/api/review/approve-all", json={"approved_by": "system"})
        note = api_client.get(f"/api/notes/{path}").json()
        assert note["metadata"]["review_status"] == "approved"

    def test_approve_all_sets_all_approval_fields(self, api_client: TestClient) -> None:
        """approve-all must write approved_by, approval_mode, and approved_at (T2)."""
        path = _add_pending_note(api_client, "inbox/all-fields.md")
        api_client.post("/api/review/approve-all", json={"approved_by": "admin"})
        note = api_client.get(f"/api/notes/{path}").json()
        meta = note["metadata"]
        assert meta["approved_by"] == "admin"
        assert meta["approval_mode"] == "manual"
        assert meta["approved_at"] is not None

    def test_approve_all_partial_failure_count(self, api_client: TestClient) -> None:
        """Failed approvals must not be counted in the approved total (T3)."""
        from unittest.mock import patch as _patch

        _add_pending_note(api_client, "inbox/fail-one.md")
        _add_pending_note(api_client, "inbox/ok-one.md")
        _add_pending_note(api_client, "inbox/ok-two.md")

        call_count = [0]
        real_patch_fm = api_client.app.state.vault.patch_frontmatter

        def _sometimes_fail(path, updates, **kw):
            call_count[0] += 1
            if "fail-one" in path:
                raise RuntimeError("simulated vault failure")
            return real_patch_fm(path, updates, **kw)

        with _patch.object(api_client.app.state.vault, "patch_frontmatter", _sometimes_fail):
            body = api_client.post(
                "/api/review/approve-all", json={"approved_by": "user"}
            ).json()

        # 2 of 3 notes approved; the failure must not inflate the count.
        assert body["approved"] == 2


# ===========================================================================
# Pending count cache (P1)
# ===========================================================================


class TestPendingCountCache:
    def test_review_count_uses_cached_value(self, api_client: TestClient) -> None:
        """After GET /review warms the cache, GET /review/count must return O(1)."""
        _add_pending_note(api_client, "inbox/cache-note.md")
        # Warm cache via list endpoint
        api_client.get("/api/review")
        # Manually set cache to a sentinel so we can detect a fresh scan bypassed
        api_client.app.state._review_pending_count = 42
        body = api_client.get("/api/review/count").json()
        assert body["count"] == 42, "Expected cached sentinel value, not a fresh scan result"

    def test_approve_decrements_cache(self, api_client: TestClient) -> None:
        """Approving a note must decrement the count cache by 1 (not trigger rescan)."""
        path = _add_pending_note(api_client, "inbox/decrement-me.md")
        # Warm the cache
        api_client.get("/api/review/count")
        before = api_client.app.state._review_pending_count
        api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "user"})
        after = api_client.app.state._review_pending_count
        assert after == max(0, before - 1)

    def test_approve_all_sets_cache_to_remainder(self, api_client: TestClient) -> None:
        """approve-all must set cache to (total - approved), not None."""
        _add_pending_note(api_client, "inbox/rem-1.md")
        _add_pending_note(api_client, "inbox/rem-2.md")
        api_client.post("/api/review/approve-all", json={"approved_by": "user"})
        cached = api_client.app.state._review_pending_count
        # All approved → remainder is 0
        assert cached == 0


# ===========================================================================
# Pagination edge cases (T4)
# ===========================================================================


class TestPaginationEdgeCases:
    def test_offset_beyond_total_returns_empty_items(self, api_client: TestClient) -> None:
        """offset > total must return empty items list but correct total (T4)."""
        _add_pending_note(api_client, "inbox/pgbound-1.md")
        body = api_client.get("/api/review?limit=10&offset=9999").json()
        assert body["items"] == []
        assert body["total"] >= 1, "Total must still reflect all pending notes"
