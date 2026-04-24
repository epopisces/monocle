"""monocle/tests/test_settings.py — Tests for Settings endpoints (M13)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


#endregion

# ---------------------------------------------------------------------------
#region #*   Module-scoped autouse fixture: redirect config writes to a temp file
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

    def test_patch_history_retention_versions(self, api_client: TestClient) -> None:
        r = api_client.patch("/api/settings", json={"history": {"retention_versions": 12}})
        assert r.status_code == 200
        assert r.json()["history"]["retention_versions"] == 12
        assert api_client.app.state.settings.history.retention_versions == 12
        assert api_client.app.state.vault.retention_versions == 12

    def test_patch_history_retention_prunes_existing_versions(self, api_client: TestClient) -> None:
        payload = {"title": "History", "body": "v1", "metadata": {"type": "observation", "domain": "work"}}
        api_client.put("/api/notes/work/history-prune.md", json=payload)
        api_client.put("/api/notes/work/history-prune.md", json={**payload, "body": "v2"})
        api_client.put("/api/notes/work/history-prune.md", json={**payload, "body": "v3"})

        versions_before = api_client.app.state.vault.list_versions("work/history-prune.md")
        assert len(versions_before) == 2

        r = api_client.patch("/api/settings", json={"history": {"retention_versions": 1}})
        assert r.status_code == 200

        versions_after = api_client.app.state.vault.list_versions("work/history-prune.md")
        assert len(versions_after) == 1

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

    def test_patch_ai_transcribe_backend_no_crash(self, api_client: TestClient) -> None:
        """Patching ai.transcribe_backend should succeed without hot-reloading the provider."""
        r = api_client.patch("/api/settings", json={"ai": {"transcribe_backend": "whisper_cpp"}})
        assert r.status_code == 200
        assert r.json()["ai"]["transcribe_backend"] == "whisper_cpp"

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
        """Patching transcribe_backend='native' must fail when chat model is on ollama.

        Default config has chat model on ollama.  Validators should reject
        native transcription since Ollama has no built-in audio API.
        """
        r = api_client.patch(
            "/api/settings",
            json={"ai": {"transcribe_backend": "native"}},
        )
        assert r.status_code == 422, "native transcribe_backend must be rejected for ollama models"

    def test_default_transcribe_backend_is_safe_for_ollama(
        self, api_client: TestClient
    ) -> None:
        """Default transcribe_backend must be subprocess or whisper_cpp (safe for ollama)."""
        body = api_client.get("/api/settings").json()
        assert body["ai"]["transcribe_backend"] in ["subprocess", "whisper_cpp"]


# ===========================================================================
# AI provider hot-reload (B3)
# ===========================================================================


class TestAIProviderHotReload:
    # Default models list for tests that need multiple chat models
    _EXTRA_MODELS = [
        {"key": "llama3.2", "name": "llama3.2", "role": "chat", "provider": "ollama"},
        {"key": "qwen3", "name": "qwen3:8b", "role": "chat", "provider": "ollama"},
        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
    ]

    def test_patch_ai_chat_model_key_triggers_hot_reload(self, api_client: TestClient) -> None:
        """Changing chat_model_key must call get_provider and update app.state.ai (B3)."""
        from unittest.mock import MagicMock, patch

        mock_new_ai = MagicMock()
        with patch("monocle.ai.get_provider", return_value=mock_new_ai) as mock_get:
            r = api_client.patch(
                "/api/settings",
                json={"ai": {"chat_model_key": "qwen3", "models": self._EXTRA_MODELS}},
            )
        assert r.status_code == 200
        assert r.json()["ai"]["chat_model_key"] == "qwen3"
        assert mock_get.call_count == 1, "get_provider must be called on model-key change"

    def test_patch_transcribe_backend_does_not_trigger_hot_reload(
        self, api_client: TestClient
    ) -> None:
        """Patching transcribe_backend alone must NOT re-initialise the provider."""
        from unittest.mock import patch

        with patch("monocle.ai.get_provider") as mock_get:
            r = api_client.patch("/api/settings", json={"ai": {"transcribe_backend": "whisper_cpp"}})
        assert r.status_code == 200
        mock_get.assert_not_called()

    def test_patch_ai_hot_reload_failure_rejects_entire_patch(
        self, api_client: TestClient, _temp_config: Path
    ) -> None:
        """If hot-reload fails, the entire patch must be rejected (no partial state).

        Config file must not be updated, and app.state must not be changed.
        """
        from unittest.mock import patch
        from monocle.config import _load_yaml

        # Record initial config state
        initial_config = _load_yaml(_temp_config)
        initial_key = api_client.get("/api/settings").json()["ai"]["chat_model_key"]

        # Attempt patch with model key change, but mock get_provider to fail
        with patch("monocle.ai.get_provider", side_effect=RuntimeError("Provider init failed")):
            r = api_client.patch(
                "/api/settings",
                json={"ai": {"chat_model_key": "qwen3", "models": self._EXTRA_MODELS}},
            )

        # Must return 500 due to hot-reload failure
        assert r.status_code == 500

        # Config file must NOT have been updated
        current_config = _load_yaml(_temp_config)
        assert current_config == initial_config, "Config should not be written on hot-reload failure"

        # app.state.settings must NOT have been updated
        current_key = api_client.get("/api/settings").json()["ai"]["chat_model_key"]
        assert current_key == initial_key, "Settings should not be persisted on hot-reload failure"

    def test_patch_ai_model_key_success_updates_app_state_consistently(
        self, api_client: TestClient
    ) -> None:
        """On successful model-key change, app state and response must be consistent."""
        from unittest.mock import MagicMock, patch

        mock_new_ai = MagicMock()
        with patch("monocle.ai.get_provider", return_value=mock_new_ai):
            r = api_client.patch(
                "/api/settings",
                json={"ai": {"chat_model_key": "qwen3", "models": self._EXTRA_MODELS}},
            )

        assert r.status_code == 200
        response_key = r.json()["ai"]["chat_model_key"]
        state_key = api_client.get("/api/settings").json()["ai"]["chat_model_key"]
        assert response_key == state_key == "qwen3"


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


# ===========================================================================
# PATCH /api/settings — Schema & Atomicity Fixes
# ===========================================================================


class TestModelEntryPatchSchema:
    """Tests for ModelEntryPatch schema enforcement (fix: all fields required for full replacement)."""

    def test_model_entry_patch_rejects_incomplete_name(self, api_client: TestClient) -> None:
        """ModelEntryPatch must require name (not optional) — full replacement semantics."""
        # Attempt to patch models with incomplete entry (missing name)
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "models": [
                        {"key": "llama3.2", "role": "chat", "provider": "ollama"},
                        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
                    ]
                }
            },
        )
        # Must fail validation (422) because name is required
        assert r.status_code == 422

    def test_model_entry_patch_rejects_incomplete_role(self, api_client: TestClient) -> None:
        """ModelEntryPatch must require role (not optional) — full replacement semantics."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "models": [
                        {"key": "llama3.2", "name": "llama3.2", "provider": "ollama"},
                        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
                    ]
                }
            },
        )
        assert r.status_code == 422

    def test_model_entry_patch_rejects_incomplete_provider(self, api_client: TestClient) -> None:
        """ModelEntryPatch must require provider (not optional) — full replacement semantics."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "models": [
                        {"key": "llama3.2", "name": "llama3.2", "role": "chat"},
                        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
                    ]
                }
            },
        )
        assert r.status_code == 422

    def test_model_entry_patch_accepts_complete_entry(self, api_client: TestClient) -> None:
        """ModelEntryPatch must accept complete entries with all required fields."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "models": [
                        {"key": "llama3.2", "name": "llama3.2", "role": "chat", "provider": "ollama"},
                        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
                    ]
                }
            },
        )
        assert r.status_code == 200


class TestAIPatchNullFieldClearing:
    """Tests for setting optional AI fields to null (e.g., stt_key clearing)."""

    def test_patch_stt_key_set_to_null_clears_it(self, api_client: TestClient) -> None:
        """Sending stt_key: null must actually clear it (not treated as no-op)."""
        # First, set up models with an STT key, then set stt_key to it
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "chat1",
                    "embed_model_key": "embed1",
                    "stt_key": "stt1",
                    "models": [
                        {"key": "chat1", "name": "Chat", "role": "chat", "provider": "ollama"},
                        {"key": "embed1", "name": "Embed", "role": "embed", "provider": "ollama"},
                        {"key": "stt1", "name": "STT", "role": "stt", "provider": "ollama"},
                    ],
                }
            },
        )
        assert r.status_code == 200, f"Setup PATCH failed: {r.text}"
        assert r.json()["ai"]["stt_key"] == "stt1"

        # Now explicitly set it to null
        r = api_client.patch("/api/settings", json={"ai": {"stt_key": None}})
        assert r.status_code == 200

        # Must now be null in response and app state
        assert r.json()["ai"]["stt_key"] is None
        assert api_client.get("/api/settings").json()["ai"]["stt_key"] is None

    def test_patch_omitted_stt_key_does_not_change_it(self, api_client: TestClient) -> None:
        """When stt_key is not provided in patch, it must remain unchanged."""
        # First, set up models with an STT key
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "chat1",
                    "embed_model_key": "embed1",
                    "stt_key": "stt1",
                    "models": [
                        {"key": "chat1", "name": "Chat", "role": "chat", "provider": "ollama"},
                        {"key": "embed1", "name": "Embed", "role": "embed", "provider": "ollama"},
                        {"key": "stt1", "name": "STT", "role": "stt", "provider": "ollama"},
                    ],
                }
            },
        )
        assert r.status_code == 200, f"Setup PATCH failed: {r.text}"
        assert r.json()["ai"]["stt_key"] == "stt1"

        # Patch something else WITHOUT mentioning stt_key
        r = api_client.patch("/api/settings", json={"ai": {"transcribe_backend": "whisper_cpp"}})
        assert r.status_code == 200

        # stt_key must still be set to the previous value
        assert r.json()["ai"]["stt_key"] == "stt1"




class TestTraceFiltersAtomicity:
    """Tests for atomicity of trace_filters updates (defer set_filters until validation succeeds)."""

    def test_patch_trace_filters_not_applied_on_ai_hot_reload_failure(
        self, api_client: TestClient, _temp_config: Path
    ) -> None:
        """If AI hot-reload fails, trace_filters must NOT be updated (atomic guarantee).

        This tests the fix: trace_filters.set_filters() is now deferred until
        after all validations (including AI provider hot-reload) succeed.
        """
        from unittest.mock import MagicMock, patch

        # Set up mock to track set_filters calls
        mock_processor = MagicMock()
        api_client.app.state.route_filter_processor = mock_processor

        # Attempt patch with both trace_filters change AND AI model change that will fail
        with patch("monocle.ai.get_provider", side_effect=RuntimeError("Provider init failed")):
            r = api_client.patch(
                "/api/settings",
                json={
                    "ai": {"chat_model_key": "qwen3", "models": [
                        {"key": "llama3.2", "name": "llama3.2", "role": "chat", "provider": "ollama"},
                        {"key": "qwen3", "name": "qwen3:8b", "role": "chat", "provider": "ollama"},
                        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
                    ]},
                    "telemetry": {"trace_filters": ["/api/health", "/api/ingest"]},
                },
            )

        # Patch must fail due to AI hot-reload
        assert r.status_code == 500

        # set_filters() must NOT have been called (atomicity preserved)
        mock_processor.set_filters.assert_not_called()

    def test_patch_trace_filters_applied_on_ai_hot_reload_success(
        self, api_client: TestClient
    ) -> None:
        """When AI hot-reload succeeds, trace_filters must be applied afterward."""
        from unittest.mock import MagicMock, patch

        mock_processor = MagicMock()
        api_client.app.state.route_filter_processor = mock_processor
        mock_new_ai = MagicMock()

        # Patch with both trace_filters change AND AI model change (that succeeds)
        with patch("monocle.ai.get_provider", return_value=mock_new_ai):
            r = api_client.patch(
                "/api/settings",
                json={
                    "ai": {"chat_model_key": "qwen3", "models": [
                        {"key": "llama3.2", "name": "llama3.2", "role": "chat", "provider": "ollama"},
                        {"key": "qwen3", "name": "qwen3:8b", "role": "chat", "provider": "ollama"},
                        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
                    ]},
                    "telemetry": {"trace_filters": ["/api/health"]},
                },
            )

        # Patch must succeed
        assert r.status_code == 200

        # set_filters() must have been called with the new filters (after validation)
        mock_processor.set_filters.assert_called_once_with(["/api/health"])

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


# ===========================================================================
# Model Key & Role Validation (unique keys, role correctness)
# ===========================================================================


class TestModelKeyAndRoleValidation:
    """Tests for enhanced model key and role validation (uniqueness, role correctness)."""

    def test_duplicate_model_keys_rejected_via_config(self) -> None:
        """AIConfig must reject duplicate model keys."""
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="contains duplicate keys"):
            AIConfig(
                chat_model_key="chat1",
                embed_model_key="embed1",
                models=[
                    ModelEntry(key="chat1", name="Chat Model", role="chat", provider="ollama"),
                    ModelEntry(key="embed1", name="Embed Model", role="embed", provider="ollama"),
                    ModelEntry(key="chat1", name="Duplicate", role="chat", provider="ollama"),  # duplicate
                ],
            )

    def test_chat_model_key_must_have_chat_role(self) -> None:
        """chat_model_key must point to entry with role='chat'."""
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="chat_model_key.*points to model with role='embed'"):
            AIConfig(
                chat_model_key="embed1",  # points to embed role
                embed_model_key="embed1",
                models=[
                    ModelEntry(key="embed1", name="Embed Model", role="embed", provider="ollama"),
                ],
            )

    def test_embed_model_key_must_have_embed_role(self) -> None:
        """embed_model_key must point to entry with role='embed'."""
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="embed_model_key.*points to model with role='stt'"):
            AIConfig(
                chat_model_key="chat1",
                embed_model_key="stt1",  # points to stt role
                models=[
                    ModelEntry(key="chat1", name="Chat Model", role="chat", provider="ollama"),
                    ModelEntry(key="stt1", name="STT Model", role="stt", provider="ollama"),
                ],
            )

    def test_stt_key_must_have_stt_role_if_provided(self) -> None:
        """stt_key (if set) must point to entry with role='stt'."""
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="stt_key.*points to model with role='chat'"):
            AIConfig(
                chat_model_key="chat1",
                embed_model_key="embed1",
                stt_key="chat1",  # points to chat role, not stt
                models=[
                    ModelEntry(key="chat1", name="Chat Model", role="chat", provider="ollama"),
                    ModelEntry(key="embed1", name="Embed Model", role="embed", provider="ollama"),
                ],
            )

    def test_stt_key_null_is_allowed(self) -> None:
        """stt_key can be null (optional)."""
        from monocle.config import AIConfig, ModelEntry

        # This must not raise
        config = AIConfig(
            chat_model_key="chat1",
            embed_model_key="embed1",
            stt_key=None,  # explicitly null is OK
            models=[
                ModelEntry(key="chat1", name="Chat Model", role="chat", provider="ollama"),
                ModelEntry(key="embed1", name="Embed Model", role="embed", provider="ollama"),
            ],
        )
        assert config.stt_key is None

    def test_valid_config_with_all_roles_accepted(self) -> None:
        """Valid configuration with unique keys and correct roles is accepted."""
        from monocle.config import AIConfig, ModelEntry

        config = AIConfig(
            chat_model_key="chat1",
            embed_model_key="embed1",
            stt_key="stt1",
            models=[
                ModelEntry(key="chat1", name="Chat Model", role="chat", provider="ollama"),
                ModelEntry(key="embed1", name="Embed Model", role="embed", provider="ollama"),
                ModelEntry(key="stt1", name="STT Model", role="stt", provider="ollama"),
            ],
        )
        assert config.chat_model_key == "chat1"
        assert config.embed_model_key == "embed1"
        assert config.stt_key == "stt1"

    def test_patch_with_duplicate_keys_rejected(self, api_client: TestClient) -> None:
        """PATCH with duplicate model keys in models list is rejected (422)."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "models": [
                        {"key": "chat1", "name": "Chat 1", "role": "chat", "provider": "ollama"},
                        {"key": "embed1", "name": "Embed", "role": "embed", "provider": "ollama"},
                        {"key": "chat1", "name": "Chat Duplicate", "role": "chat", "provider": "ollama"},
                    ]
                }
            },
        )
        assert r.status_code == 422
        assert "contains duplicate keys" in r.text or "Duplicate" in r.text

    def test_patch_chat_model_key_wrong_role_rejected(self, api_client: TestClient) -> None:
        """PATCH with chat_model_key pointing to non-chat role is rejected (422)."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "embed1",
                    "embed_model_key": "embed1",
                    "models": [
                        {"key": "embed1", "name": "Embed Model", "role": "embed", "provider": "ollama"},
                    ],
                }
            },
        )
        assert r.status_code == 422
        assert "chat_model_key" in r.text and "role='embed'" in r.text

    def test_patch_embed_model_key_wrong_role_rejected(self, api_client: TestClient) -> None:
        """PATCH with embed_model_key pointing to non-embed role is rejected (422)."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "chat1",
                    "embed_model_key": "stt1",
                    "models": [
                        {"key": "chat1", "name": "Chat", "role": "chat", "provider": "ollama"},
                        {"key": "stt1", "name": "STT", "role": "stt", "provider": "ollama"},
                    ],
                }
            },
        )
        assert r.status_code == 422
        assert "embed_model_key" in r.text and "role='stt'" in r.text

    def test_patch_stt_key_wrong_role_rejected(self, api_client: TestClient) -> None:
        """PATCH with stt_key pointing to non-stt role is rejected (422)."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "chat1",
                    "embed_model_key": "embed1",
                    "stt_key": "chat1",
                    "models": [
                        {"key": "chat1", "name": "Chat", "role": "chat", "provider": "ollama"},
                        {"key": "embed1", "name": "Embed", "role": "embed", "provider": "ollama"},
                    ],
                }
            },
        )
        assert r.status_code == 422
        assert "stt_key" in r.text and "role='chat'" in r.text

    def test_patch_valid_all_roles_accepted(self, api_client: TestClient) -> None:
        """PATCH with valid unique keys and correct roles is accepted (200)."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "chat1",
                    "embed_model_key": "embed1",
                    "stt_key": "stt1",
                    "models": [
                        {"key": "chat1", "name": "Chat", "role": "chat", "provider": "ollama"},
                        {"key": "embed1", "name": "Embed", "role": "embed", "provider": "ollama"},
                        {"key": "stt1", "name": "STT", "role": "stt", "provider": "ollama"},
                    ],
                }
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ai"]["chat_model_key"] == "chat1"
        assert body["ai"]["embed_model_key"] == "embed1"
        assert body["ai"]["stt_key"] == "stt1"


# ===========================================================================
# Transcribe Backend + STT Key Validation
# ===========================================================================


class TestTranscribeBackendAndSTTKeyValidation:
    """Tests for validation of transcribe_backend and stt_key compatibility.

    Issue: sst_key is validated and influences transcribe_model, but get_provider()
    only builds chat+embed providers and never uses sst_key. This allows configs
    like chat=Ollama + stt_key=Azure + transcribe_backend='native' to pass
    validation but fail at runtime because get_provider() returns OllamaProvider
    (which has no native transcription API).

    Solution: Validate that transcribe_backend='native' is only allowed when the
    provider that will actually be used for transcription supports native transcription.
    """

    def test_native_transcribe_with_ollama_chat_rejected(self) -> None:
        """native transcribe_backend requires provider with native transcription support."""
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="transcribe_backend='native'.*not supported.*Ollama"):
            AIConfig(
                chat_model_key="chat1",
                embed_model_key="embed1",
                transcribe_backend="native",
                models=[
                    ModelEntry(key="chat1", name="Chat", role="chat", provider="ollama"),
                    ModelEntry(key="embed1", name="Embed", role="embed", provider="ollama"),
                ],
            )

    def test_native_transcribe_with_ollama_stt_rejected(self) -> None:
        """native transcribe_backend rejected even if ssat_key points to Ollama."""
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="transcribe_backend='native'.*not supported.*Ollama"):
            AIConfig(
                chat_model_key="chat1",
                embed_model_key="embed1",
                stt_key="stt1",
                transcribe_backend="native",
                models=[
                    ModelEntry(key="chat1", name="Chat", role="chat", provider="azure"),
                    ModelEntry(key="embed1", name="Embed", role="embed", provider="azure"),
                    ModelEntry(key="stt1", name="STT", role="stt", provider="ollama"),
                ],
            )

    def test_native_transcribe_with_azure_accepted(self) -> None:
        """native transcribe_backend works when provider is Azure."""
        from monocle.config import AIConfig, ModelEntry

        config = AIConfig(
            chat_model_key="chat1",
            embed_model_key="embed1",
            transcribe_backend="native",
            models=[
                ModelEntry(key="chat1", name="Chat", role="chat", provider="azure"),
                ModelEntry(key="embed1", name="Embed", role="embed", provider="azure"),
            ],
        )
        assert config.transcribe_backend == "native"

    def test_native_transcribe_with_foundry_accepted(self) -> None:
        """native transcribe_backend works when provider is foundry_local."""
        from monocle.config import AIConfig, ModelEntry

        config = AIConfig(
            chat_model_key="chat1",
            embed_model_key="embed1",
            transcribe_backend="native",
            models=[
                ModelEntry(key="chat1", name="Chat", role="chat", provider="foundry_local"),
                ModelEntry(key="embed1", name="Embed", role="embed", provider="foundry_local"),
            ],
        )
        assert config.transcribe_backend == "native"

    def test_stt_key_on_different_provider_with_native_rejected(self) -> None:
        """sst_key on different provider than chat + native transcribe_backend is rejected.

        Rationale: get_provider() only builds chat provider, not sst provider.
        If sst_key points to a different backend (e.g., Azure), it won't be used.
        """
        from monocle.config import AIConfig, ModelEntry

        with pytest.raises(ValueError, match="different provider.*not supported"):
            AIConfig(
                chat_model_key="chat1",
                embed_model_key="embed1",
                stt_key="azure_stt",
                transcribe_backend="native",
                models=[
                    ModelEntry(key="chat1", name="Chat", role="chat", provider="ollama"),
                    ModelEntry(key="embed1", name="Embed", role="embed", provider="ollama"),
                    ModelEntry(key="azure_stt", name="Azure STT", role="stt", provider="azure"),
                ],
            )

    def test_stt_key_on_different_provider_with_whisper_cpp_accepted(self) -> None:
        """sst_key on different provider is OK when transcribe_backend is whisper_cpp."""
        from monocle.config import AIConfig, ModelEntry

        # This config is valid because whisper_cpp doesn't use any provider's native transcription
        config = AIConfig(
            chat_model_key="chat1",
            embed_model_key="embed1",
            stt_key="azure_stt",
            transcribe_backend="whisper_cpp",
            models=[
                ModelEntry(key="chat1", name="Chat", role="chat", provider="ollama"),
                ModelEntry(key="embed1", name="Embed", role="embed", provider="ollama"),
                ModelEntry(key="azure_stt", name="Azure STT", role="stt", provider="azure"),
            ],
        )
        assert config.stt_key == "azure_stt"
        assert config.transcribe_backend == "whisper_cpp"

    def test_stt_key_on_same_provider_with_native_accepted(self) -> None:
        """sst_key on same provider as chat + native transcribe_backend is OK."""
        from monocle.config import AIConfig, ModelEntry

        config = AIConfig(
            chat_model_key="chat1",
            embed_model_key="embed1",
            stt_key="azure_stt",
            transcribe_backend="native",
            models=[
                ModelEntry(key="chat1", name="Chat", role="chat", provider="azure"),
                ModelEntry(key="embed1", name="Embed", role="embed", provider="azure"),
                ModelEntry(key="azure_stt", name="Azure STT", role="stt", provider="azure"),
            ],
        )
        assert config.stt_key == "azure_stt"
        assert config.transcribe_backend == "native"

    def test_patch_native_transcribe_with_ollama_chat_rejected(self, api_client: TestClient) -> None:
        """PATCH transcribe_backend='native' rejected for Ollama chat model (422)."""
        r = api_client.patch(
            "/api/settings",
            json={"ai": {"transcribe_backend": "native"}},
        )
        assert r.status_code == 422
        assert "native" in r.text or "Ollama" in r.text

    def test_patch_native_transcribe_with_stt_key_on_different_provider_rejected(
        self, api_client: TestClient
    ) -> None:
        """PATCH transcribe_backend='native' + sst_key on different provider rejected (422)."""
        r = api_client.patch(
            "/api/settings",
            json={
                "ai": {
                    "chat_model_key": "chat1",
                    "embed_model_key": "embed1",
                    "stt_key": "azure_stt",
                    "transcribe_backend": "native",
                    "models": [
                        {"key": "chat1", "name": "Chat", "role": "chat", "provider": "ollama"},
                        {"key": "embed1", "name": "Embed", "role": "embed", "provider": "ollama"},
                        {"key": "azure_stt", "name": "Azure STT", "role": "stt", "provider": "azure"},
                    ],
                }
            },
        )
        assert r.status_code == 422
        assert "different provider" in r.text or "native" in r.text


# ===========================================================================
# PATCH /api/settings — telemetry.trace_filters (runtime filter update)
# ===========================================================================


class TestPatchTelemetryTraceFilters:
    """Tests for patching telemetry.trace_filters via the settings API."""

    def test_patch_trace_filters_returns_200(self, api_client: TestClient) -> None:
        """PATCH telemetry.trace_filters must return 200."""
        r = api_client.patch(
            "/api/settings",
            json={"telemetry": {"trace_filters": ["/api/health", "/api/review/count"]}},
        )
        assert r.status_code == 200

    def test_patch_trace_filters_reflected_in_response(self, api_client: TestClient) -> None:
        """Updated trace_filters must appear in response body."""
        new_filters = ["/api/health", "/api/ingest/failures"]
        r = api_client.patch(
            "/api/settings",
            json={"telemetry": {"trace_filters": new_filters}},
        )
        body = r.json()
        assert body["telemetry"]["trace_filters"] == new_filters

    def test_patch_trace_filters_updates_app_state(self, api_client: TestClient) -> None:
        """Updated trace_filters must be visible on subsequent GET."""
        new_filters = ["/api/review/count"]
        api_client.patch(
            "/api/settings",
            json={"telemetry": {"trace_filters": new_filters}},
        )
        got = api_client.get("/api/settings").json()
        assert got["telemetry"]["trace_filters"] == new_filters

    def test_patch_trace_filters_updates_live_processor(self, api_client: TestClient) -> None:
        """Patching trace_filters must call set_filters() on the live route_filter_processor."""
        from unittest.mock import MagicMock

        mock_processor = MagicMock()
        api_client.app.state.route_filter_processor = mock_processor
        api_client.patch(
            "/api/settings",
            json={"telemetry": {"trace_filters": ["/api/health", "/api/review/count"]}},
        )
        mock_processor.set_filters.assert_called_once_with(
            ["/api/health", "/api/review/count"]
        )

    def test_patch_empty_trace_filters_list_accepted(self, api_client: TestClient) -> None:
        """An empty list disables all filtering — must be accepted."""
        r = api_client.patch(
            "/api/settings",
            json={"telemetry": {"trace_filters": []}},
        )
        assert r.status_code == 200
        assert r.json()["telemetry"]["trace_filters"] == []
