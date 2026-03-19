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

    def test_patch_preserves_other_review_fields(self, api_client: TestClient) -> None:
        """Patching review.queue_threshold must not affect auto_approve_threshold_pct."""
        # First set auto_approve_threshold_pct
        api_client.patch(
            "/api/settings", json={"review": {"auto_approve_threshold_pct": 50}}
        )
        # Then patch queue_threshold
        r = api_client.patch("/api/settings", json={"review": {"queue_threshold": 0.75}})
        body = r.json()
        # Both fields must still be present and correct
        assert body["review"]["queue_threshold"] == 0.75
        assert body["review"]["auto_approve_threshold_pct"] == 50


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

    def test_patch_ollama_with_native_transcribe_returns_422(self, api_client: TestClient) -> None:
        """Patching provider='ollama' + transcribe_backend='native' must fail (invalid combo).
        
        Ollama has no built-in transcription API. Validators should reject this.
        """
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "provider": "ollama",
                    "transcribe_backend": "native",
                }
            },
        )
        assert r.status_code == 422, "Invalid ollama+native combo should be rejected"

    def test_patch_to_ollama_preserves_valid_transcribe_backend(
        self, api_client: TestClient
    ) -> None:
        """Patching provider='ollama' alone should auto-adjust transcribe_backend if needed."""
        # First ensure we start with a non-ollama provider
        api_client.patch("/api/settings", json={"ai": {"provider": "foundry_local"}})
        
        # Patch to ollama (no transcribe_backend specified)
        r = api_client.patch("/api/settings", json={"ai": {"provider": "ollama"}})
        assert r.status_code == 200
        body = r.json()
        # transcribe_backend should be set to subprocess (default for ollama)
        assert body["ai"]["transcribe_backend"] in ["subprocess", "whisper_cpp"]


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

    def test_patch_ai_provider_hot_reload_failure_rejects_entire_patch(
        self, api_client: TestClient, _temp_config: Path
    ) -> None:
        """If hot-reload fails, the entire patch must be rejected (no partial state).
        
        Config file must not be updated, and app.state must not be changed.
        """
        from unittest.mock import patch
        from monocle.config import _load_yaml

        # Record initial config state
        initial_config = _load_yaml(_temp_config)
        initial_chat_model = api_client.get("/api/settings").json()["ai"]["chat_model"]

        # Attempt patch with provider change, but mock get_provider to fail
        with patch("monocle.ai.get_provider", side_effect=RuntimeError("Provider init failed")):
            r = api_client.patch(
                "/api/settings",
                json={"ai": {"provider": "foundry_local", "chat_model": "meta-llama"}},
            )

        # Must return 500 due to hot-reload failure
        assert r.status_code == 500

        # Config file must NOT have been updated
        current_config = _load_yaml(_temp_config)
        assert current_config == initial_config, "Config should not be written on hot-reload failure"

        # app.state.settings must NOT have been updated
        current_chat_model = api_client.get("/api/settings").json()["ai"]["chat_model"]
        assert (
            current_chat_model == initial_chat_model
        ), "Settings should not be persisted on hot-reload failure"

    def test_patch_ai_provider_success_updates_app_state_consistently(
        self, api_client: TestClient
    ) -> None:
        """On successful provider change, app.state.ai and returned provider must match."""
        from unittest.mock import MagicMock, patch

        mock_new_ai = MagicMock()
        with patch("monocle.ai.get_provider", return_value=mock_new_ai):
            r = api_client.patch(
                "/api/settings", json={"ai": {"provider": "foundry_local"}}
            )

        assert r.status_code == 200
        response_provider = r.json()["ai"]["provider"]

        # Get current settings from a subsequent request
        state_provider = api_client.get("/api/settings").json()["ai"]["provider"]

        # Response and app state must be consistent
        assert response_provider == state_provider == "foundry_local"


# ===========================================================================
# save_config_patch() deep-merge behavior
# ===========================================================================


class TestSaveConfigPatchDeepMerge:
    """Test that save_config_patch() properly performs deep merging of nested dicts,
    not shallow replacement (which would lose nested config structures)."""

    def test_deep_merge_nested_dicts(self, _temp_config: Path) -> None:
        """Patching a nested dict field must preserve sibling nested fields."""
        from monocle.config import save_config_patch, _load_yaml

        # Write initial config with nested structure
        _temp_config.write_text(
            """
review:
  queue_threshold: 1.0
  confidence_weights:
    template_match: 0.35
    metadata_coverage: 0.30
    tag_plausibility: 0.20
    entity_match: 0.15
"""
        )

        # Patch only template_match within confidence_weights
        save_config_patch(
            {"review": {"confidence_weights": {"template_match": 0.5}}}
        )

        # Verify the patch was applied AND siblings were preserved
        config = _load_yaml(_temp_config)
        assert config["review"]["queue_threshold"] == 1.0
        assert config["review"]["confidence_weights"]["template_match"] == 0.5
        assert config["review"]["confidence_weights"]["metadata_coverage"] == 0.30
        assert config["review"]["confidence_weights"]["tag_plausibility"] == 0.20
        assert config["review"]["confidence_weights"]["entity_match"] == 0.15

    def test_deep_merge_multiple_nested_levels(self, _temp_config: Path) -> None:
        """Deep merge must work across multiple nesting levels."""
        from monocle.config import save_config_patch, _load_yaml

        # Write initial config
        _temp_config.write_text(
            """
agents:
  weekly_summary:
    enabled: true
    cron: "0 17 * * 5"
    domains:
      - work
      - personal
"""
        )

        # Patch a nested field
        save_config_patch(
            {"agents": {"weekly_summary": {"enabled": False}}}
        )

        # Verify the patch and sibling preservation
        config = _load_yaml(_temp_config)
        assert config["agents"]["weekly_summary"]["enabled"] is False
        assert config["agents"]["weekly_summary"]["cron"] == "0 17 * * 5"
        assert config["agents"]["weekly_summary"]["domains"] == ["work", "personal"]

    def test_deep_merge_none_values_skipped(self, _temp_config: Path) -> None:
        """None values in the patch must be skipped (not merged)."""
        from monocle.config import save_config_patch, _load_yaml

        _temp_config.write_text(
            """
review:
  queue_threshold: 1.0
  confidence_weights:
    template_match: 0.35
    metadata_coverage: 0.30
"""
        )

        # Patch with None values (should be ignored)
        save_config_patch(
            {"review": {"confidence_weights": {"template_match": 0.5, "metadata_coverage": None}}}
        )

        config = _load_yaml(_temp_config)
        assert config["review"]["confidence_weights"]["template_match"] == 0.5
        assert config["review"]["confidence_weights"]["metadata_coverage"] == 0.30

    def test_secret_keys_filtered_at_top_level(self, _temp_config: Path) -> None:
        """Secret keys (azure_*, foundry_local_*) at top-level section names must be filtered out."""
        from monocle.config import save_config_patch, _load_yaml

        _temp_config.write_text("review:\n  queue_threshold: 1.0\n")

        # Try to sneak in a secret at the top level (should be filtered)
        save_config_patch(
            {
                "review": {"queue_threshold": 0.5},
                "azure_openai_api_key": "secret_value",
                "foundry_local_api_key": "another_secret",
            }
        )

        config = _load_yaml(_temp_config)
        assert "azure_openai_api_key" not in config
        assert "foundry_local_api_key" not in config
        assert config["review"]["queue_threshold"] == 0.5

    def test_secret_keys_filtered_in_nested_dicts(self, _temp_config: Path) -> None:
        """Secret keys within nested dicts must be filtered out during merge."""
        from monocle.config import save_config_patch, _load_yaml

        _temp_config.write_text("ai:\n  provider: ollama\n")

        # Try to inject secrets within a section (should be filtered)
        save_config_patch(
            {
                "ai": {
                    "chat_model": "mistral",
                    "azure_openai_api_key": "secret",
                    "foundry_local_base_url": "http://secret",
                }
            }
        )

        config = _load_yaml(_temp_config)
        assert config["ai"]["chat_model"] == "mistral"
        assert "azure_openai_api_key" not in config["ai"]
        assert "foundry_local_base_url" not in config["ai"]
