"""monocle/tests/test_settings.py — Tests for Settings endpoints (M13)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Module-scoped autouse fixture: redirect config writes to a temp file
# so tests never mutate the real config.yaml.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _temp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MONOCLE_CONFIG at a temp file for every test in this module."""
    cfg = tmp_path / "test_config.yaml"
    cfg.write_text("{}\n")
    monkeypatch.setenv("MONOCLE_CONFIG", str(cfg))
    return cfg


# ===========================================================================
# GET /api/settings
# ===========================================================================


class TestGetSettings:
    def test_get_settings_200(self, api_client: TestClient) -> None:
        r = api_client.get("/api/settings")
        assert r.status_code == 200

    def test_get_settings_has_expected_sections(self, api_client: TestClient) -> None:
        body = api_client.get("/api/settings").json()
        for section in ("ai", "vault", "review", "server", "telemetry", "ui"):
            assert section in body, f"Missing section: {section}"

    def test_get_settings_mcp_key_masked_last4(
        self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_ACCESS_KEY", "supersecretABCD")
        body = api_client.get("/api/settings").json()
        assert "mcp_key_last4" in body
        assert body["mcp_key_last4"] == "****ABCD"

    def test_get_settings_full_key_not_in_response(
        self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_ACCESS_KEY", "topsecrettoken9999")
        body_str = str(api_client.get("/api/settings").json())
        assert "topsecrettoken9999" not in body_str

    def test_get_settings_no_mcp_key_returns_null(
        self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MCP_ACCESS_KEY", raising=False)
        body = api_client.get("/api/settings").json()
        assert body["mcp_key_last4"] is None

    def test_get_settings_no_azure_secrets_leaked(self, api_client: TestClient) -> None:
        body_str = str(api_client.get("/api/settings").json())
        for secret_key in ("azure_openai_api_key", "foundry_local_api_key"):
            assert secret_key not in body_str


# ===========================================================================
# PATCH /api/settings
# ===========================================================================


class TestPatchSettings:
    def test_patch_review_queue_threshold(self, api_client: TestClient) -> None:
        r = api_client.patch("/api/settings", json={"review": {"queue_threshold": 0.75}})
        assert r.status_code == 200
        assert r.json()["review"]["queue_threshold"] == 0.75

    def test_patch_review_auto_approve_threshold(self, api_client: TestClient) -> None:
        r = api_client.patch(
            "/api/settings", json={"review": {"auto_approve_threshold_pct": 90}}
        )
        assert r.status_code == 200
        assert r.json()["review"]["auto_approve_threshold_pct"] == 90

    def test_patch_review_both_fields(self, api_client: TestClient) -> None:
        r = api_client.patch(
            "/api/settings",
            json={"review": {"queue_threshold": 0.75, "auto_approve_threshold_pct": 90}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["review"]["queue_threshold"] == 0.75
        assert body["review"]["auto_approve_threshold_pct"] == 90

    def test_patch_takes_effect_on_subsequent_get(self, api_client: TestClient) -> None:
        """PATCH must mutate app.state.settings so GET reflects the new value."""
        api_client.patch("/api/settings", json={"review": {"queue_threshold": 0.6}})
        body = api_client.get("/api/settings").json()
        assert body["review"]["queue_threshold"] == 0.6

    def test_patch_empty_body_returns_200(self, api_client: TestClient) -> None:
        r = api_client.patch("/api/settings", json={})
        assert r.status_code == 200

    def test_patch_returns_mcp_key_masked(self, api_client: TestClient) -> None:
        r = api_client.patch("/api/settings", json={})
        body = r.json()
        assert "mcp_key_last4" in body

    def test_patch_writes_to_config_yaml(
        self, api_client: TestClient, _temp_config: Path
    ) -> None:
        api_client.patch("/api/settings", json={"review": {"queue_threshold": 0.55}})
        content = _temp_config.read_text()
        assert "queue_threshold" in content
        assert "0.55" in content

    def test_patch_ai_provider_no_crash(self, api_client: TestClient) -> None:
        """Patching ai.chat_model should succeed without hot-reloading the provider
        (provider field unchanged)."""
        r = api_client.patch("/api/settings", json={"ai": {"chat_model": "llama3.3"}})
        assert r.status_code == 200
        assert r.json()["ai"]["chat_model"] == "llama3.3"


# ===========================================================================
# POST /api/settings/rotate-mcp-key
# ===========================================================================


class TestRotateMcpKey:
    def test_rotate_returns_200(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONOCLE_ENV_FILE", str(tmp_path / ".env"))
        r = api_client.post("/api/settings/rotate-mcp-key")
        assert r.status_code == 200

    def test_rotate_returns_masked_key(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONOCLE_ENV_FILE", str(tmp_path / ".env"))
        body = api_client.post("/api/settings/rotate-mcp-key").json()
        assert "mcp_key_last4" in body
        assert body["mcp_key_last4"].startswith("****")
        # token_hex(32) gives 64-char hex; masked = "****" + last 4 → 8 chars
        assert len(body["mcp_key_last4"]) == 8

    def test_rotate_writes_key_to_env_file(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setenv("MONOCLE_ENV_FILE", str(env_file))
        api_client.post("/api/settings/rotate-mcp-key")
        assert env_file.exists()
        assert "MCP_ACCESS_KEY=" in env_file.read_text()

    def test_rotate_replaces_existing_key_in_env_file(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("MCP_ACCESS_KEY=oldkey1234\nOTHER_VAR=keep\n")
        monkeypatch.setenv("MONOCLE_ENV_FILE", str(env_file))
        api_client.post("/api/settings/rotate-mcp-key")
        content = env_file.read_text()
        assert "MCP_ACCESS_KEY=oldkey1234" not in content
        assert "OTHER_VAR=keep" in content

    def test_rotate_updates_os_environ(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONOCLE_ENV_FILE", str(tmp_path / ".env"))
        api_client.post("/api/settings/rotate-mcp-key")
        assert "MCP_ACCESS_KEY" in os.environ

    def test_rotate_replaces_old_key_in_os_environ(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Old key value must be gone from os.environ after rotation (T5)."""
        old_key = "oldfixedvalue00001111"
        monkeypatch.setenv("MCP_ACCESS_KEY", old_key)
        monkeypatch.setenv("MONOCLE_ENV_FILE", str(tmp_path / ".env"))
        api_client.post("/api/settings/rotate-mcp-key")
        new_key = os.environ.get("MCP_ACCESS_KEY", "")
        assert new_key != old_key, "Key was not rotated — old value still set"
        assert len(new_key) > 4, "Rotated key should be non-trivially long"


# ===========================================================================
# Input validation (B1 — provider Literal, B2 — range validators)
# ===========================================================================


class TestInputValidation:
    def test_patch_invalid_provider_returns_422(self, api_client: TestClient) -> None:
        """AIPatch.provider must be a Literal — arbitrary strings return 422 (B1)."""
        r = api_client.patch("/api/settings", json={"ai": {"provider": "bad_provider"}})
        assert r.status_code == 422

    def test_patch_invalid_transcribe_backend_returns_422(self, api_client: TestClient) -> None:
        """AIPatch.transcribe_backend must be a Literal — arbitrary strings return 422 (B1)."""
        r = api_client.patch("/api/settings", json={"ai": {"transcribe_backend": "ftp"}})
        assert r.status_code == 422

    def test_patch_queue_threshold_too_high_returns_422(self, api_client: TestClient) -> None:
        """queue_threshold > 1.0 must return 422 (B2)."""
        r = api_client.patch("/api/settings", json={"review": {"queue_threshold": 1.5}})
        assert r.status_code == 422

    def test_patch_queue_threshold_negative_returns_422(self, api_client: TestClient) -> None:
        """queue_threshold < 0 must return 422 (B2)."""
        r = api_client.patch("/api/settings", json={"review": {"queue_threshold": -0.1}})
        assert r.status_code == 422

    def test_patch_auto_approve_pct_over_100_returns_422(self, api_client: TestClient) -> None:
        """auto_approve_threshold_pct > 100 must return 422 (B2)."""
        r = api_client.patch("/api/settings", json={"review": {"auto_approve_threshold_pct": 101}})
        assert r.status_code == 422

    def test_patch_auto_approve_pct_negative_returns_422(self, api_client: TestClient) -> None:
        """auto_approve_threshold_pct < 0 must return 422 (B2)."""
        r = api_client.patch("/api/settings", json={"review": {"auto_approve_threshold_pct": -1}})
        assert r.status_code == 422

    def test_patch_boundary_values_accepted(self, api_client: TestClient) -> None:
        """Boundary values (0.0, 1.0, 0, 100) must be accepted."""
        r = api_client.patch(
            "/api/settings",
            json={"review": {"queue_threshold": 0.0, "auto_approve_threshold_pct": 100}},
        )
        assert r.status_code == 200


# ===========================================================================
# AI provider hot-reload (B3)
# ===========================================================================


class TestAIProviderHotReload:
    def test_patch_ai_provider_triggers_hot_reload(self, api_client: TestClient) -> None:
        """Changing ai.provider must call get_provider and update app.state.ai (B3)."""
        from unittest.mock import MagicMock, patch

        mock_new_ai = MagicMock()
        with patch("monocle.ai.get_provider", return_value=mock_new_ai) as mock_get:
            r = api_client.patch("/api/settings", json={"ai": {"provider": "foundry_local"}})
        assert r.status_code == 200
        assert r.json()["ai"]["provider"] == "foundry_local"
        assert mock_get.call_count == 1, "get_provider must be called on provider change"

    def test_patch_ai_model_only_does_not_trigger_hot_reload(
        self, api_client: TestClient
    ) -> None:
        """Changing ai.chat_model (no provider change) must NOT re-initialise the provider."""
        from unittest.mock import patch

        with patch("monocle.ai.get_provider") as mock_get:
            r = api_client.patch("/api/settings", json={"ai": {"chat_model": "mistral"}})
        assert r.status_code == 200
        mock_get.assert_not_called()
