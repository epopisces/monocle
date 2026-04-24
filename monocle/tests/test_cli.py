"""
monocle/tests/test_cli.py — CLI command tests using typer.testing.CliRunner.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monocle.cli import app

runner = CliRunner()


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path, notes: list[dict[str, Any]] | None = None) -> Path:
    """Write minimal vault with fixture notes. Returns vault root."""
    import yaml
    import datetime

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "inbox").mkdir()

    if notes is None:
        notes = [
            {
                "path": "people/alice.md",
                "fm": {
                    "type": "person_note",
                    "domain": "work",
                    "source": "web",
                    "confidence": 0.9,
                    "review_status": "approved",
                },
                "body": "Alice is an engineer.",
            }
        ]

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for note in notes:
        file = vault / note["path"]
        file.parent.mkdir(parents=True, exist_ok=True)
        fm = {"created": now, "updated": now, **note["fm"]}
        file.write_text(
            f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{note['body']}\n",
            encoding="utf-8",
        )

    return vault


#endregion

# ---------------------------------------------------------------------------
#region #*   Settings mock helper
# ---------------------------------------------------------------------------


def _mock_settings(vault_path: str):
    from monocle.config import (
        AIConfig,
            HistoryConfig,
        IndexConfig,
        ReviewConfig,
        ServerConfig,
        TelemetryConfig,
        VaultConfig,
        Settings,
    )

    s = MagicMock(spec=Settings)
    s.vault = VaultConfig(path=vault_path, inbox_path=str(Path(vault_path) / "inbox"))
    s.index = IndexConfig(backend="chroma", chroma_persist_path="./data/chroma_test")
    s.ai = AIConfig()  # defaults: llama3.2 chat on ollama, nomic-embed on ollama
    s.history = HistoryConfig()
    s.review = ReviewConfig()
    s.server = ServerConfig()
    s.telemetry = TelemetryConfig(enabled=True, otlp_endpoint="http://localhost:4317", log_level="DEBUG", log_format="text")
    return s


#endregion

# ---------------------------------------------------------------------------
#region #*   TestHelp
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_shows_all_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("serve", "dev", "reindex", "pull-models", "stats", "search", "export", "versions"):
            assert cmd in result.output

    def test_help_shows_stubs(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "watch" in result.output
        assert "capture" in result.output

    def test_versions_help(self):
        result = runner.invoke(app, ["versions", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "restore" in result.output

    def test_reindex_help_shows_force(self):
        result = runner.invoke(app, ["reindex", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output

    def test_export_help_shows_output(self):
        result = runner.invoke(app, ["export", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output


#endregion

# ---------------------------------------------------------------------------
#region #*   TestReindex
# ---------------------------------------------------------------------------


class TestReindex:
    def test_reindex_no_force(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index") as mock_index_factory,
            patch("monocle.cli.get_provider", side_effect=Exception("no AI"), create=True),
        ):
            mock_index = MagicMock()
            mock_index.get_stats.return_value = MagicMock(backend="memory")
            mock_index.get_file_timestamps.return_value = {}
            mock_index_factory.return_value = mock_index

            result = runner.invoke(app, ["reindex"])

        assert result.exit_code == 0
        assert "Re-indexed" in result.output

    def test_reindex_force_flag(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index") as mock_index_factory,
            patch("monocle.cli.get_provider", side_effect=Exception("no AI"), create=True),
        ):
            mock_index = MagicMock()
            mock_index.get_stats.return_value = MagicMock(backend="memory")
            mock_index.get_file_timestamps.return_value = {}
            mock_index_factory.return_value = mock_index

            result = runner.invoke(app, ["reindex", "--force"])

        assert result.exit_code == 0
        assert "Re-indexed" in result.output

    def test_reindex_with_ai_provider(self, tmp_path: Path):
        """embed_fn code path: verifies asyncio.run() works from a thread-pool thread."""
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        mock_ai = MagicMock()
        mock_ai.embed = AsyncMock(return_value=[0.1] * 1536)

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index") as mock_index_factory,
            # Patch on monocle.ai so that `from monocle.ai import get_provider`
            # inside reindex() picks up the mock at import time.
            patch("monocle.ai.get_provider", return_value=mock_ai),
        ):
            mock_index = MagicMock()
            mock_index.get_stats.return_value = MagicMock(backend="memory")
            mock_index.get_file_timestamps.return_value = {}
            mock_index.upsert_chunks = MagicMock()
            mock_index.delete_file = MagicMock()
            mock_index_factory.return_value = mock_index

            result = runner.invoke(app, ["reindex"])

        assert result.exit_code == 0
        assert "Re-indexed" in result.output
        # embed was called at least once per chunk of the fixture note body
        mock_ai.embed.assert_called()


#endregion

# ---------------------------------------------------------------------------
#region #*   TestExport
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_creates_valid_zip(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        output_zip = str(tmp_path / "out.zip")
        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["export", "--output", output_zip])

        assert result.exit_code == 0
        assert "Exported" in result.output
        assert zipfile.is_zipfile(output_zip)

        with zipfile.ZipFile(output_zip) as zf:
            names = zf.namelist()
        # The fixture note should be present
        assert any("alice" in n for n in names)

    def test_export_excludes_versions_and_trash(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        # Create files in excluded dirs
        (vault / ".versions").mkdir()
        (vault / ".versions" / "test.md").write_text("v1", encoding="utf-8")
        (vault / ".trash").mkdir()
        (vault / ".trash" / "deleted.md").write_text("gone", encoding="utf-8")

        output_zip = str(tmp_path / "out.zip")
        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["export", "--output", output_zip])

        assert result.exit_code == 0
        with zipfile.ZipFile(output_zip) as zf:
            names = zf.namelist()
        assert not any(".versions" in n for n in names)
        assert not any(".trash" in n for n in names)

    def test_export_default_filename(self, tmp_path: Path, monkeypatch):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))
        monkeypatch.chdir(tmp_path)

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["export"])

        assert result.exit_code == 0
        assert "export.zip" in result.output


#endregion

# ---------------------------------------------------------------------------
#region #*   TestVersionsList
# ---------------------------------------------------------------------------


class TestVersionsList:
    def test_list_no_versions(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["versions", "list", "people/alice.md"])

        assert result.exit_code == 0
        assert "No versions" in result.output

    def test_list_with_versions(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        # Create a fake version file
        version_dir = vault / ".versions" / "people" / "alice.md"
        version_dir.mkdir(parents=True)
        (version_dir / "2026-03-18T10-00-00.000Z.md").write_text("old", encoding="utf-8")

        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["versions", "list", "people/alice.md"])

        assert result.exit_code == 0
        assert "2026-03-18T10-00-00.000Z" in result.output

    def test_list_invalid_path_exits_nonzero(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["versions", "list", "../../escape.md"])

        # VaultLayer raises HTTPException(403) for traversal — CLI must exit nonzero.
        # Do NOT accept the "No versions" branch: that would allow a traversal
        # attempt to silently succeed and return an empty list.
        assert result.exit_code != 0


#endregion

# ---------------------------------------------------------------------------
#region #*   TestVersionsRestore
# ---------------------------------------------------------------------------


class TestVersionsRestore:
    def test_restore_success(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        # Create version
        version_dir = vault / ".versions" / "people" / "alice.md"
        version_dir.mkdir(parents=True)
        ts = "2026-03-18T10-00-00.000Z"
        (version_dir / f"{ts}.md").write_text("---\ntype: person_note\n---\n\nOld body.\n", encoding="utf-8")

        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["versions", "restore", "people/alice.md", ts])

        assert result.exit_code == 0
        assert "Restored" in result.output

    def test_restore_missing_version_exits_nonzero(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(
                app, ["versions", "restore", "people/alice.md", "2026-03-18T10-00-00.000Z"]
            )

        assert result.exit_code != 0
        assert "ERROR" in result.output.upper() or "error" in result.output.lower()

    def test_restore_path_traversal_blocked(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(
                app,
                ["versions", "restore", "../../escape.md", "2026-03-18T10-00-00.000Z"],
            )

        # VaultLayer raises HTTPException(403) for traversal — CLI must exit nonzero.
        assert result.exit_code != 0


#endregion

# ---------------------------------------------------------------------------
#region #*   TestStats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_runs(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index") as mock_index_factory,
        ):
            mock_index = MagicMock()
            mock_index.get_stats.return_value = MagicMock(total_chunks=5, backend="memory")
            mock_index_factory.return_value = mock_index

            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "Notes" in result.output
        assert "Index chunks" in result.output


#endregion

# ---------------------------------------------------------------------------
#region #*   TestPullModels
# ---------------------------------------------------------------------------


class TestPullModels:
    def test_pull_models_non_ollama_exits_cleanly(self, tmp_path: Path):
        from monocle.config import AIConfig, ModelEntry

        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))
        # Switch chat model to foundry_local
        settings.ai = AIConfig(
            chat_model_key="fl-chat",
            embed_model_key="nomic-embed",
            models=[
                ModelEntry(key="fl-chat", name="llama3.2", role="chat", provider="foundry_local"),
                ModelEntry(key="nomic-embed", name="nomic-embed-text", role="embed", provider="ollama"),
            ],
        )

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["pull-models"])

        assert result.exit_code == 0
        assert "foundry_local" in result.output or "Nothing to pull" in result.output

    def test_pull_models_ollama_missing_package(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))
        # Default settings already have ollama provider

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch.dict("sys.modules", {"ollama": None}),
        ):
            result = runner.invoke(app, ["pull-models"])

        # Should exit with code 1 when ollama not installed
        assert result.exit_code == 1


#endregion

# ---------------------------------------------------------------------------
#region #*   TestStubs
# ---------------------------------------------------------------------------


class TestStubs:
    def test_watch_exits_when_vault_watch_disabled(self, tmp_path: Path):
        """watch command exits immediately when vault.watch=false."""
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))
        settings.vault.watch = False

        with patch("monocle.cli._load_settings", return_value=settings):
            result = runner.invoke(app, ["watch"])

        assert result.exit_code == 0
        assert "vault.watch=false" in result.output.lower()

    def test_capture_calls_uvicorn(self, tmp_path: Path, monkeypatch):
        """capture command sets MONOCLE_COMPONENT and launches uvicorn."""
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))
        monkeypatch.delenv("MONOCLE_COMPONENT", raising=False)

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("uvicorn.run") as mock_uvicorn,
        ):
            result = runner.invoke(app, ["capture"])

        assert result.exit_code == 0
        mock_uvicorn.assert_called_once()


#endregion

# ---------------------------------------------------------------------------
#region #*   TestDevTelemetryBlock
# ---------------------------------------------------------------------------


class TestDevTelemetryBlock:
    def test_dev_prints_telemetry_block(self, tmp_path: Path, monkeypatch):
        """Verify the telemetry status block is printed before uvicorn starts."""
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        # Ensure MONOCLE_DEV writes are isolated — the dev() command calls
        # os.environ["MONOCLE_DEV"] = "true" which would leak into later tests.
        monkeypatch.delenv("MONOCLE_DEV", raising=False)

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("uvicorn.run"),  # uvicorn imported inside the function
            patch.dict(os.environ, {}, clear=False),  # snapshot env; changes rolled back by monkeypatch
        ):
            result = runner.invoke(app, ["dev"])

        assert "[TELEMETRY]" in result.output
        assert "OTLP endpoint" in result.output
        assert "log_level" in result.output
        assert "format" in result.output


#endregion

# ---------------------------------------------------------------------------
#region #*   TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_results(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        mock_ai = MagicMock()
        mock_ai.embed = AsyncMock(return_value=[0.1] * 1536)

        mock_index = MagicMock()
        mock_index.search.return_value = [
            {"file_path": "people/alice.md", "score": 0.95, "text": "Alice is an engineer."},
        ]

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index", return_value=mock_index),
            patch("monocle.ai.get_provider", return_value=mock_ai),
        ):
            result = runner.invoke(app, ["search", "alice"])

        assert result.exit_code == 0
        assert "people/alice.md" in result.output
        assert "0.950" in result.output
        assert "Alice is an engineer" in result.output

    def test_search_empty_results(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        mock_ai = MagicMock()
        mock_ai.embed = AsyncMock(return_value=[0.1] * 1536)

        mock_index = MagicMock()
        mock_index.search.return_value = []

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index", return_value=mock_index),
            patch("monocle.ai.get_provider", return_value=mock_ai),
        ):
            result = runner.invoke(app, ["search", "zzznomatch"])

        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_search_ai_failure_exits_nonzero(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        mock_index = MagicMock()

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index", return_value=mock_index),
            patch("monocle.ai.get_provider", side_effect=Exception("provider unavailable")),
        ):
            result = runner.invoke(app, ["search", "alice"])

        assert result.exit_code == 1

    def test_search_limit_passed_to_index(self, tmp_path: Path):
        vault = _make_vault(tmp_path)
        settings = _mock_settings(str(vault))

        mock_ai = MagicMock()
        mock_ai.embed = AsyncMock(return_value=[0.1] * 1536)

        mock_index = MagicMock()
        mock_index.search.return_value = []

        with (
            patch("monocle.cli._load_settings", return_value=settings),
            patch("monocle.cli._make_index", return_value=mock_index),
            patch("monocle.ai.get_provider", return_value=mock_ai),
        ):
            result = runner.invoke(app, ["search", "query", "--limit", "3"])

        assert result.exit_code == 0
        # index.search must be called with the specified limit
        mock_index.search.assert_called_once()
        call_args = mock_index.search.call_args[0]  # positional args: (embedding, limit)
        assert call_args[1] == 3
