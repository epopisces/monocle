"""monocle/tests/test_review.py — Tests for active review action endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient


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


class TestApproveNote:
    def test_approve_sets_expected_metadata(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-note.md")

        response = api_client.patch(f"/api/review/{path}/approve", json={"approved_by": "alice"})
        assert response.status_code == 200
        body = response.json()
        assert body["file_path"] == path
        assert body["review_status"] == "approved"
        assert body["approval_mode"] == "manual"
        assert body["approved_by"] == "alice"
        assert body["approved_at"] is not None

        note = api_client.get(f"/api/notes/{path}").json()
        meta = note["metadata"]
        assert meta["review_status"] == "approved"
        assert meta["approval_mode"] == "manual"
        assert meta["approved_by"] == "alice"
        assert meta["approved_at"] is not None

    def test_approve_uses_default_approved_by(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/approve-default.md")
        body = api_client.patch(f"/api/review/{path}/approve", json={}).json()
        assert body["approved_by"] == "user"

    def test_approve_404_for_missing_note(self, api_client: TestClient) -> None:
        r = api_client.patch(
            "/api/review/nonexistent/note.md/approve",
            json={"approved_by": "user"},
        )
        assert r.status_code == 404


class TestRejectNote:
    def test_reject_sets_expected_metadata(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-note.md")

        response = api_client.patch(f"/api/review/{path}/reject")
        assert response.status_code == 200
        body = response.json()
        assert body["file_path"] == path
        assert body["review_status"] == "rejected"
        assert body["approval_mode"] == "manual"
        assert body["approved_by"] == "user"
        assert body["approved_at"] is not None

        note = api_client.get(f"/api/notes/{path}").json()
        meta = note["metadata"]
        assert meta["review_status"] == "rejected"
        assert meta["approval_mode"] == "manual"
        assert meta["approved_by"] == "user"
        assert meta["approved_at"] is not None

    def test_reject_404_for_missing_note(self, api_client: TestClient) -> None:
        r = api_client.patch("/api/review/nonexistent/note.md/reject")
        assert r.status_code == 404

    def test_reject_note_remains_readable(self, api_client: TestClient) -> None:
        path = _add_pending_note(api_client, "inbox/reject-readable.md")
        api_client.patch(f"/api/review/{path}/reject")

        r = api_client.get(f"/api/notes/{path}")
        assert r.status_code == 200
        assert r.json()["metadata"]["review_status"] == "rejected"
