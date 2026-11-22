"""
monocle/tests/test_ingest.py — Unit tests for M7: Ingest Pipeline & Plugin Registry.

All tests are mock-based — no live AI provider, vault, or index required.

Run::

    uv run python -m pytest monocle/tests/test_ingest.py -x --tb=short -q
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monocle.ingest import DuplicateSuspected, IngestPipeline
from monocle.ingest.confidence import compute_approval_metadata, score_confidence
from monocle.ingest.failed_registry import FailedIngestRegistry
from monocle.ingest.plugin import IngestPlugin, IngestPluginRegistry
from monocle.ingest.plugins import AudioPlugin, TeamsPlugin, TextPlugin, register_default_plugins
from monocle.models import (
    IngestConfidence,
    IngestRequest,
    Note,
    NoteMetadata,
    RoutingDecision,
)


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _make_settings(auto_approve_pct: int = 0, **overrides):
    """Return a minimal Settings object without touching the filesystem."""
    from monocle.config import Settings

    defaults = {
        "ai": {"provider": "ollama"},
        "vault": {"path": "/tmp/vault", "watch": False},
        "review": {"auto_approve_threshold_pct": auto_approve_pct},
    }
    for k, v in overrides.items():
        defaults[k] = v

    with patch(
        "monocle.config._find_config_file",
        return_value=Path("/nonexistent"),
    ), patch("monocle.config._load_yaml", return_value=defaults):
        return Settings()


def _make_note(
    file_path: str = "work/test.md",
    title: str = "Test",
    body: str = "Sample body text.",
    template: str = "blank",
    note_type: str = "other",
    tags: list[str] | None = None,
    people: list[str] | None = None,
) -> Note:
    metadata = NoteMetadata(
        type=note_type,  # type: ignore[arg-type]
        template=template,
        tags=tags or [],
        people=people or [],
    )
    return Note(file_path=file_path, title=title, body=body, metadata=metadata)


def _make_ai(
    embed_return: list[float] | None = None,
    chat_return: str = '{"template": "blank", "confidence": 0.5, "rationale": "test"}',
    extract_return: NoteMetadata | None = None,
) -> MagicMock:
    ai = AsyncMock()
    ai._provider_name = "mock"
    emb = embed_return or ([0.1] * 1536)
    ai.embed.return_value = emb
    ai.embed_batch.return_value = [emb]
    ai.chat.return_value = chat_return
    ai.extract_note_metadata.return_value = extract_return or NoteMetadata(
        title="Extracted Title",
        tags=["test"],
    )
    return ai


#endregion

# ---------------------------------------------------------------------------
#region #*   IngestPlugin ABC tests
# ---------------------------------------------------------------------------


class TestIngestPlugin:
    def test_text_plugin_can_handle_web(self):
        req = IngestRequest(content="hello", source="web")
        assert TextPlugin.can_handle(req) is True

    def test_text_plugin_can_handle_mcp(self):
        req = IngestRequest(content="hello", source="mcp")
        assert TextPlugin.can_handle(req) is True

    def test_text_plugin_cannot_handle_voice(self):
        req = IngestRequest(content="hello", source="voice")
        assert TextPlugin.can_handle(req) is False

    def test_text_plugin_cannot_handle_teams(self):
        req = IngestRequest(content="hello", source="teams")
        assert TextPlugin.can_handle(req) is False

    def test_audio_plugin_can_handle_audio_bytes(self):
        req = IngestRequest(audio_bytes=b"audio", source="voice")
        assert AudioPlugin.can_handle(req) is True

    def test_audio_plugin_cannot_handle_no_bytes(self):
        req = IngestRequest(content="text", source="voice")
        assert AudioPlugin.can_handle(req) is False

    def test_teams_plugin_can_handle_teams_source(self):
        req = IngestRequest(content="hello teams", source="teams")
        assert TeamsPlugin.can_handle(req) is True

    def test_teams_plugin_cannot_handle_web(self):
        req = IngestRequest(content="hello", source="web")
        assert TeamsPlugin.can_handle(req) is False


#endregion

# ---------------------------------------------------------------------------
#region #*   Plugin extraction tests
# ---------------------------------------------------------------------------


class TestPluginExtract:
    @pytest.mark.asyncio
    async def test_text_plugin_returns_content(self):
        plugin = TextPlugin()
        req = IngestRequest(content="Some text", source="web")
        result = await plugin.extract(req)
        assert result == "Some text"

    @pytest.mark.asyncio
    async def test_text_plugin_empty_content(self):
        plugin = TextPlugin()
        req = IngestRequest(content=None, source="web")
        result = await plugin.extract(req)
        assert result == ""

    @pytest.mark.asyncio
    async def test_teams_plugin_returns_content(self):
        plugin = TeamsPlugin()
        req = IngestRequest(content="Teams message body", source="teams")
        result = await plugin.extract(req)
        assert result == "Teams message body"

    @pytest.mark.asyncio
    async def test_audio_plugin_calls_transcribe(self):
        plugin = AudioPlugin()
        ai = AsyncMock()
        ai.transcribe.return_value = "transcribed text"
        req = IngestRequest(audio_bytes=b"raw_audio", audio_mime_type="audio/webm", source="voice")
        result = await plugin.extract(req, ai=ai)
        assert result == "transcribed text"
        ai.transcribe.assert_called_once_with(b"raw_audio", "audio/webm")

    @pytest.mark.asyncio
    async def test_audio_plugin_raises_without_ai(self):
        plugin = AudioPlugin()
        req = IngestRequest(audio_bytes=b"raw_audio", source="voice")
        with pytest.raises(RuntimeError, match="AIProvider"):
            await plugin.extract(req, ai=None)


#endregion

# ---------------------------------------------------------------------------
#region #*   IngestPluginRegistry tests
# ---------------------------------------------------------------------------


class TestIngestPluginRegistry:
    def setup_method(self):
        IngestPluginRegistry.reset()

    def teardown_method(self):
        IngestPluginRegistry.reset()

    def test_singleton_returns_same_instance(self):
        r1 = IngestPluginRegistry.get()
        r2 = IngestPluginRegistry.get()
        assert r1 is r2

    def test_reset_clears_singleton(self):
        r1 = IngestPluginRegistry.get()
        IngestPluginRegistry.reset()
        r2 = IngestPluginRegistry.get()
        assert r1 is not r2

    def test_register_and_resolve_audio_first(self):
        registry = IngestPluginRegistry.get()
        register_default_plugins(registry)

        audio_req = IngestRequest(audio_bytes=b"data", source="voice")
        plugin = registry.resolve(audio_req)
        assert isinstance(plugin, AudioPlugin)

    def test_resolve_teams_plugin(self):
        registry = IngestPluginRegistry.get()
        register_default_plugins(registry)

        req = IngestRequest(content="hello", source="teams")
        plugin = registry.resolve(req)
        assert isinstance(plugin, TeamsPlugin)

    def test_resolve_text_plugin_fallback(self):
        registry = IngestPluginRegistry.get()
        register_default_plugins(registry)

        req = IngestRequest(content="hello", source="web")
        plugin = registry.resolve(req)
        assert isinstance(plugin, TextPlugin)

    def test_first_match_wins(self):
        """Register order matters — first can_handle wins."""
        IngestPluginRegistry.reset()
        registry = IngestPluginRegistry.get()

        class AnyPlugin(IngestPlugin):
            source_id = "test"
            source_label = "Test"

            @classmethod
            def can_handle(cls, request):
                return True

            async def extract(self, request, ai=None):
                return "any"

        registry.register(AnyPlugin())
        register_default_plugins(registry)

        req = IngestRequest(content="test", source="web")
        plugin = registry.resolve(req)
        assert isinstance(plugin, AnyPlugin)

    def test_custom_plugin_registration_no_code_change(self):
        """A new plugin registered without touching pipeline code."""
        IngestPluginRegistry.reset()
        registry = IngestPluginRegistry.get()

        class CustomPlugin(IngestPlugin):
            source_id = "custom"
            source_label = "Custom"

            @classmethod
            def can_handle(cls, request):
                return request.source == "import"

            async def extract(self, request, ai=None):
                return f"imported: {request.content}"

        registry.register(CustomPlugin())
        register_default_plugins(registry)

        req = IngestRequest(content="data", source="import")
        plugin = registry.resolve(req)
        assert isinstance(plugin, CustomPlugin)

    def test_no_match_falls_back_to_text_plugin(self):
        """When no plugin is registered, resolve() falls back to TextPlugin."""
        registry = IngestPluginRegistry.get()
        # No plugins registered — bare singleton
        req = IngestRequest(content="hello", source="web")
        plugin = registry.resolve(req)
        assert isinstance(plugin, TextPlugin)


#endregion

# ---------------------------------------------------------------------------
#region #*   RoutingAgent tests
# ---------------------------------------------------------------------------


class TestRoutingAgent:
    @pytest.mark.asyncio
    async def test_sentence_starter_decision(self):
        """'I decided to…' → decision template, fast_path=True, no LLM call."""
        from monocle.agents.routing import RoutingAgent

        agent = RoutingAgent(ai=None)
        result = await agent.route("I decided to use Python for the backend.")
        assert result.template == "decision"
        assert result.fast_path is True
        assert result.confidence >= 0.8
        assert result.note_type == "decision"

    @pytest.mark.asyncio
    async def test_sentence_starter_meeting(self):
        from monocle.agents.routing import RoutingAgent

        agent = RoutingAgent(ai=None)
        result = await agent.route("Meeting with Alice and Bob to discuss roadmap.")
        assert result.template == "meeting"
        assert result.fast_path is True

    @pytest.mark.asyncio
    async def test_sentence_starter_person(self):
        from monocle.agents.routing import RoutingAgent

        agent = RoutingAgent(ai=None)
        result = await agent.route("Met with Sarah today about the quarterly review.")
        assert result.template == "person"
        assert result.fast_path is True

    @pytest.mark.asyncio
    async def test_sentence_starter_idea(self):
        from monocle.agents.routing import RoutingAgent

        agent = RoutingAgent(ai=None)
        result = await agent.route("What if we added a mobile offline mode?")
        assert result.template == "idea"
        assert result.fast_path is True

    @pytest.mark.asyncio
    async def test_fast_path_bypasses_llm(self):
        """Sentence starter should not call AIProvider.chat at all."""
        from monocle.agents.routing import RoutingAgent

        ai = AsyncMock()
        agent = RoutingAgent(ai=ai)
        await agent.route("I decided to switch to PostgreSQL.")
        ai.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_ai_returns_blank(self):
        """Without AI and no sentence match → blank template, confidence=0."""
        from monocle.agents.routing import RoutingAgent

        agent = RoutingAgent(ai=None)
        result = await agent.route("Some completely unknown content xyz123.")
        assert result.template == "blank"
        assert result.confidence == 0.0
        assert result.fast_path is False

    @pytest.mark.asyncio
    async def test_llm_fallback_parses_json(self):
        """LLM returns JSON → RoutingDecision with parsed fields."""
        from monocle.agents.routing import RoutingAgent

        ai = _make_ai(
            chat_return='{"template": "observation", "confidence": 0.8, "rationale": "factual"}'
        )
        agent = RoutingAgent(ai=ai)
        result = await agent.route("Interesting pattern noticed in production logs.")
        assert result.template == "observation"
        assert result.confidence == 0.8
        assert result.fast_path is False
        ai.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_low_confidence_falls_back_to_blank(self):
        """LLM confidence < 0.6 → blank template regardless of LLM response."""
        from monocle.agents.routing import RoutingAgent

        ai = _make_ai(
            chat_return='{"template": "project", "confidence": 0.4, "rationale": "weak"}'
        )
        agent = RoutingAgent(ai=ai)
        result = await agent.route("Some ambiguous text with no clear category.")
        assert result.template == "blank"
        assert result.note_type == "other"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_blank(self):
        """LLM error → blank template (no exception propagated)."""
        from monocle.agents.routing import RoutingAgent

        ai = AsyncMock()
        ai.chat.side_effect = RuntimeError("Provider unavailable")
        agent = RoutingAgent(ai=ai)
        result = await agent.route("Random text without sentence starter.")
        assert result.template == "blank"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_template_hint_accepted(self):
        """Explicit template_hint is accepted without LLM call."""
        from monocle.agents.routing import RoutingAgent

        ai = AsyncMock()
        agent = RoutingAgent(ai=ai)
        result = await agent.route("Some text", template_hint="decision")
        assert result.template == "decision"
        assert result.confidence == 1.0
        assert result.fast_path is True
        ai.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_case_insensitive_starter(self):
        """Sentence starters should match regardless of input case."""
        from monocle.agents.routing import RoutingAgent

        agent = RoutingAgent(ai=None)
        result = await agent.route("TODO: follow up with marketing team.")
        assert result.template == "action_item"
        assert result.fast_path is True


#endregion

# ---------------------------------------------------------------------------
#region #*   IngestConfidence scoring tests
# ---------------------------------------------------------------------------


class TestScoreConfidence:
    def test_full_coverage_returns_high_score(self, tmp_path):
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        settings = _make_settings()
        note = _make_note(
            template="blank",
            body="This has some tags content and people mentioned",
            tags=["tags"],
            people=[],
        )
        result = score_confidence(
            note=note,
            routing_confidence=1.0,
            body_embedding=[0.1] * 1536,
            vault=vault,
            settings=settings,
        )
        assert isinstance(result, IngestConfidence)
        assert 0.0 <= result.score <= 1.0
        assert result.template_match == 1.0
        assert result.rationale is not None

    def test_zero_routing_confidence_lowers_score(self, tmp_path):
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        settings = _make_settings()
        note = _make_note(template="blank", body="Body with tag text")
        result = score_confidence(
            note=note,
            routing_confidence=0.0,
            body_embedding=[],
            vault=vault,
            settings=settings,
        )
        assert result.template_match == 0.0
        # Score should be < 1 since template_match contributes 35%
        assert result.score < 1.0

    def test_tag_plausibility_one_when_no_tags(self, tmp_path):
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        settings = _make_settings()
        note = _make_note(template="blank", body="Body text", tags=[])
        result = score_confidence(
            note=note,
            routing_confidence=1.0,
            body_embedding=[],
            vault=vault,
            settings=settings,
        )
        assert result.tag_plausibility == 1.0

    def test_tag_plausibility_partial_match(self, tmp_path):
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        settings = _make_settings()
        # body contains "python" but not "java"
        note = _make_note(
            template="blank",
            body="We use python extensively in this project.",
            tags=["python", "java"],
        )
        result = score_confidence(
            note=note,
            routing_confidence=1.0,
            body_embedding=[],
            vault=vault,
            settings=settings,
        )
        # Only 1 of 2 tags in body → 0.5
        assert result.tag_plausibility == pytest.approx(0.5)

    def test_entity_match_one_when_no_people(self, tmp_path):
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        settings = _make_settings()
        note = _make_note(template="blank", body="Body text", people=[])
        result = score_confidence(
            note=note,
            routing_confidence=0.9,
            body_embedding=[],
            vault=vault,
            settings=settings,
        )
        assert result.entity_match == 1.0

    def test_entity_match_person_resolved(self, tmp_path):
        """Person who has a note in vault → entity_match > 0."""
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        # Create a person note for Alice
        alice_path = tmp_path / "people" / "alice.md"
        alice_path.parent.mkdir()
        alice_path.write_text("---\ntype: person_note\n---\nAlice bio.", encoding="utf-8")

        settings = _make_settings()
        note = _make_note(template="person", body="Met Alice today.", people=["Alice"])
        result = score_confidence(
            note=note,
            routing_confidence=0.9,
            body_embedding=[],
            vault=vault,
            settings=settings,
        )
        # Alice resolves to people/alice.md → entity_match = 1.0
        assert result.entity_match == 1.0

    def test_score_formula_correct(self, tmp_path):
        """Verify the weighted formula: 0.35*tm + 0.30*mc + 0.20*tp + 0.15*em."""
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        settings = _make_settings()
        note = _make_note(template="blank", body="Body text", tags=[], people=[])
        result = score_confidence(
            note=note,
            routing_confidence=0.8,
            body_embedding=[],
            vault=vault,
            settings=settings,
        )
        # blank template has no required fields → metadata_coverage = 1.0
        # tags=[] → tag_plausibility = 1.0
        # people=[] → entity_match = 1.0
        expected = 0.35 * 0.8 + 0.30 * 1.0 + 0.20 * 1.0 + 0.15 * 1.0
        assert result.score == pytest.approx(expected, abs=0.01)


#endregion

# ---------------------------------------------------------------------------
#region #*   compute_approval_metadata tests
# ---------------------------------------------------------------------------


class TestComputeApprovalMetadata:
    def test_threshold_zero_always_pending(self):
        settings = _make_settings(auto_approve_pct=0)
        result = compute_approval_metadata(0.99, settings)
        assert result["review_status"] == "pending"
        assert "approval_mode" not in result or result.get("approval_mode") != "auto"

    def test_above_threshold_auto_approved(self):
        settings = _make_settings(auto_approve_pct=80)
        result = compute_approval_metadata(0.85, settings)
        assert result["review_status"] == "approved"
        assert result["approval_mode"] == "auto"
        assert result["approved_by"] == "system:auto"
        assert "approved_at" in result

    def test_below_threshold_pending(self):
        settings = _make_settings(auto_approve_pct=90)
        result = compute_approval_metadata(0.85, settings)
        assert result["review_status"] == "pending"

    def test_exact_threshold_approved(self):
        settings = _make_settings(auto_approve_pct=80)
        result = compute_approval_metadata(0.80, settings)
        assert result["review_status"] == "approved"


#endregion

# ---------------------------------------------------------------------------
#region #*   FailedIngestRegistry tests
# ---------------------------------------------------------------------------


class TestFailedIngestRegistry:
    def test_add_creates_record(self, tmp_path):
        reg = FailedIngestRegistry(tmp_path / "failed.json")
        record_id = reg.add(
            source="web",
            content_preview="Some content",
            error_message="Routing failed",
            sidecar_path="inbox/error.md",
            step=3,
        )
        assert record_id
        assert reg.count() == 1

    def test_get_all_newest_first(self, tmp_path):
        reg = FailedIngestRegistry(tmp_path / "failed.json")
        reg.add(source="web", content_preview="first", error_message="e1", sidecar_path=None, step=3)
        reg.add(source="web", content_preview="second", error_message="e2", sidecar_path=None, step=4)
        records = reg.get_all()
        assert len(records) == 2
        # newest first — second record's timestamp >= first's
        timestamps = [r["timestamp"] for r in records]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_delete_removes_record(self, tmp_path):
        reg = FailedIngestRegistry(tmp_path / "failed.json")
        rid = reg.add(source="web", content_preview="x", error_message="e", sidecar_path=None, step=3)
        assert reg.delete(rid) is True
        assert reg.count() == 0

    def test_delete_nonexistent_returns_false(self, tmp_path):
        reg = FailedIngestRegistry(tmp_path / "failed.json")
        assert reg.delete("nonexistent") is False

    def test_mark_retried(self, tmp_path):
        reg = FailedIngestRegistry(tmp_path / "failed.json")
        rid = reg.add(source="web", content_preview="x", error_message="e", sidecar_path=None, step=3)
        assert reg.mark_retried(rid) is True
        record = reg.get(rid)
        assert record["status"] == "retried"

    def test_persists_to_disk(self, tmp_path):
        path = tmp_path / "failed.json"
        reg = FailedIngestRegistry(path)
        reg.add(source="web", content_preview="x", error_message="e", sidecar_path=None, step=3)

        # Re-load from disk
        reg2 = FailedIngestRegistry(path)
        assert reg2.count() == 1

    def test_content_preview_truncated(self, tmp_path):
        reg = FailedIngestRegistry(tmp_path / "failed.json")
        long_content = "x" * 500
        reg.add(source="web", content_preview=long_content, error_message="e", sidecar_path=None, step=3)
        record = reg.get_all()[0]
        assert len(record["content_preview"]) <= 200


#endregion

# ---------------------------------------------------------------------------
#region #*   IngestPipeline tests
# ---------------------------------------------------------------------------


def _make_pipeline(tmp_path, ai=None, auto_approve_pct: int = 0, **settings_overrides):
    """Helper: create an IngestPipeline wired to a tmp vault and MemoryIndex."""
    from monocle.index.memory import MemoryIndex
    from monocle.vault import VaultLayer

    vault = VaultLayer(tmp_path)
    index = MemoryIndex()
    settings = _make_settings(auto_approve_pct=auto_approve_pct, **settings_overrides)

    registry = IngestPluginRegistry()
    register_default_plugins(registry)

    failed = FailedIngestRegistry(tmp_path / "failed_ingests.json")

    pipeline = IngestPipeline(
        vault=vault,
        index=index,
        ai=ai,
        settings=settings,
        registry=registry,
        failed_registry=failed,
    )
    return pipeline, vault, index, failed


class TestIngestPipelineTextIngest:
    @pytest.mark.asyncio
    async def test_text_ingest_creates_note(self, tmp_path):
        ai = _make_ai()
        pipeline, vault, index, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="I decided to adopt async Python everywhere.", source="web")
        note, confidence = await pipeline.run(request)

        assert note.file_path
        assert note.file_path.endswith(".md")
        # Should route to decision via sentence starter
        assert confidence.score >= 0.0

    @pytest.mark.asyncio
    async def test_text_ingest_without_ai(self, tmp_path):
        """Pipeline can run with ai=None (blank template, no LLM calls)."""
        pipeline, vault, index, _ = _make_pipeline(tmp_path, ai=None)

        request = IngestRequest(content="Some note content here.", source="web")
        note, confidence = await pipeline.run(request)

        assert note.file_path.endswith(".md")
        # No AI → blank template, empty body_embedding
        assert note.metadata.template == "blank"
        assert confidence.score >= 0.0

    @pytest.mark.asyncio
    async def test_note_frontmatter_has_confidence(self, tmp_path):
        ai = _make_ai()
        pipeline, vault, _, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="I decided to use PostgreSQL.", source="web")
        note, confidence = await pipeline.run(request)

        # note returned is re-read from vault, frontmatter has confidence
        assert note.metadata.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_source_web_in_metadata(self, tmp_path):
        ai = _make_ai()
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="Observation about the team dynamics.", source="web")
        note, _ = await pipeline.run(request)

        assert note.metadata.source == "web"


class TestIngestPipelineAudioIngest:
    @pytest.mark.asyncio
    async def test_audio_ingest_calls_transcribe(self, tmp_path):
        ai = _make_ai(
            extract_return=NoteMetadata(title="Voice Note", tags=["voice"]),
        )
        ai.transcribe = AsyncMock(return_value="I decided to adopt a new strategy.")
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(
            audio_bytes=b"fake_audio_data",
            audio_mime_type="audio/webm",
            source="voice",
        )
        note, _ = await pipeline.run(request)

        ai.transcribe.assert_called_once_with(b"fake_audio_data", "audio/webm")
        assert note.metadata.source == "voice"

    @pytest.mark.asyncio
    async def test_audio_note_has_source_voice(self, tmp_path):
        ai = _make_ai()
        ai.transcribe = AsyncMock(return_value="Transcribed voice content.")
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(
            audio_bytes=b"audio",
            audio_mime_type="audio/wav",
            source="voice",
        )
        note, _ = await pipeline.run(request)
        assert note.metadata.source == "voice"


class TestIngestPipelineAutoApproval:
    @pytest.mark.asyncio
    async def test_auto_approved_above_threshold(self, tmp_path):
        """High confidence note is auto-approved when threshold is set."""
        ai = _make_ai(
            chat_return='{"template": "decision", "confidence": 0.95, "rationale": "clear decision"}',
            extract_return=NoteMetadata(
                title="Decision Note",
                tags=[],  # no tags → tag_plausibility=1.0
                type="decision",
                template="decision",
            ),
        )
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai, auto_approve_pct=80)

        # Sentence starter "I decided" → fast_path confidence=0.9
        # Score ≈ 0.35*0.9 + 0.30*1.0 + 0.20*1.0 + 0.15*1.0 = 0.965 → approved at 80%
        request = IngestRequest(content="I decided to migrate to cloud infrastructure.", source="web")
        note, confidence = await pipeline.run(request)

        assert note.metadata.review_status == "approved"
        assert note.metadata.approval_mode == "auto"
        assert note.metadata.approved_by == "system:auto"
        assert note.metadata.approved_at is not None

    @pytest.mark.asyncio
    async def test_pending_when_threshold_zero(self, tmp_path):
        ai = _make_ai()
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai, auto_approve_pct=0)

        request = IngestRequest(content="I decided to test auto-approval.", source="web")
        note, _ = await pipeline.run(request)

        assert note.metadata.review_status == "pending"

    @pytest.mark.asyncio
    async def test_pending_below_threshold(self, tmp_path):
        ai = _make_ai(
            chat_return='{"template": "idea", "confidence": 0.5, "rationale": "weak"}',
        )
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai, auto_approve_pct=90)

        request = IngestRequest(content="Random note content without clear category.", source="web")
        note, _ = await pipeline.run(request)

        assert note.metadata.review_status == "pending"


class TestIngestPipelineSentenceStarterFastPath:
    @pytest.mark.asyncio
    async def test_sentence_starter_no_llm_routing_call(self, tmp_path):
        """Sentence starter fast path must NOT call ai.chat for routing."""
        ai = _make_ai()
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="I decided to rewrite everything in Rust.", source="web")
        note, _ = await pipeline.run(request)

        # Routing used the fast path — template must be "decision", not blank/other.
        assert note.metadata.template == "decision"
        # chat should NOT have been called for routing (only extract_note_metadata can run)
        ai.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_blank_template_when_confidence_low(self, tmp_path):
        """LLM returns confidence < 0.6 → blank template."""
        ai = _make_ai(
            chat_return='{"template": "project", "confidence": 0.4, "rationale": "weak match"}',
        )
        pipeline, _, _, _ = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="Vague content with no clear category.", source="web")
        note, _ = await pipeline.run(request)

        assert note.metadata.type in ("other",) or note.metadata.template == "blank"


class TestIngestPipelineFailure:
    @pytest.mark.asyncio
    async def test_routing_failure_writes_sidecar(self, tmp_path):
        """Step 3 failure → .error.md sidecar written in inbox."""
        ai = AsyncMock()
        # routing will fail because ai.chat raises
        ai.chat.side_effect = RuntimeError("LLM unavailable")
        ai.embed_batch.return_value = [[0.1] * 1536]
        ai.extract_note_metadata.side_effect = RuntimeError("LLM unavailable")
        ai._provider_name = "mock"

        pipeline, _, _, failed_reg = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="Some input that forces LLM routing.", source="web")

        with pytest.raises(Exception):
            await pipeline.run(request)

        # A .error.md sidecar should be in inbox/
        inbox = tmp_path / "inbox"
        sidecars = list(inbox.glob("*.error.md"))
        assert len(sidecars) >= 1

    @pytest.mark.asyncio
    async def test_failure_registers_in_failed_registry(self, tmp_path):
        """Failure during steps 3-5 creates a FailedIngestRegistry entry."""
        ai = AsyncMock()
        ai.chat.side_effect = RuntimeError("LLM offline")
        ai.embed_batch.return_value = [[0.1] * 1536]
        ai.extract_note_metadata.side_effect = RuntimeError("LLM offline")
        ai._provider_name = "mock"

        pipeline, _, _, failed_reg = _make_pipeline(tmp_path, ai=ai)

        request = IngestRequest(content="Content that triggers failure.", source="web")

        with pytest.raises(Exception):
            await pipeline.run(request)

        assert failed_reg.count() >= 1
        records = failed_reg.get_all()
        assert records[0]["source"] == "web"


class TestIngestPipelineDuplicateDetection:
    @pytest.mark.asyncio
    async def test_duplicate_raises_without_allow_flag(self, tmp_path):
        """Similarity > 0.95 to existing note → DuplicateSuspected when allow_duplicate=False."""
        from monocle.index.memory import MemoryIndex
        from monocle.models import NoteChunk
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        # Pre-populate index with a chunk that will be "similar"
        # MemoryIndex returns score=1.0 for all results
        from datetime import datetime, timezone

        existing_chunk = NoteChunk(
            chunk_id="existing_note.md::0",
            file_path="existing_note.md",
            chunk_index=0,
            text="Similar content",
            embedding=[0.1] * 1536,
            metadata={
                "created": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        index.upsert_chunks([existing_chunk])

        ai = _make_ai()
        # Make embed_batch return same embedding as above chunk → high similarity in real index
        ai.embed_batch.return_value = [[0.1] * 1536]

        # For MemoryIndex, score is always 1.0 (regardless of embedding),
        # so similarity check would flag any existing note.
        # However, MemoryIndex doesn't use embeddings for scoring, so the
        # similarity check in _detect_duplicate will only trigger when
        # embedding-based cosine similarity logic is used.
        # For MemoryIndex, search always returns score=1.0 → duplicate detected.

        pipeline = IngestPipeline(
            vault=vault,
            index=index,
            ai=ai,
            settings=settings,
            registry=registry,
            failed_registry=failed,
        )

        request = IngestRequest(
            content="I decided to use Python for the project.",
            source="web",
            allow_duplicate=False,
        )

        with pytest.raises(DuplicateSuspected) as exc_info:
            await pipeline.run(request)

        assert exc_info.value.similar_note_path == "existing_note.md"

    @pytest.mark.asyncio
    async def test_duplicate_allowed_with_flag(self, tmp_path):
        """allow_duplicate=True proceeds and sets similar_note_detected flag."""
        from monocle.index.memory import MemoryIndex
        from monocle.models import NoteChunk
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        from datetime import datetime, timezone

        existing_chunk = NoteChunk(
            chunk_id="existing_note.md::0",
            file_path="existing_note.md",
            chunk_index=0,
            text="Similar content",
            embedding=[0.1] * 1536,
            metadata={
                "created": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        index.upsert_chunks([existing_chunk])

        ai = _make_ai()
        ai.embed_batch.return_value = [[0.1] * 1536]

        pipeline = IngestPipeline(
            vault=vault,
            index=index,
            ai=ai,
            settings=settings,
            registry=registry,
            failed_registry=failed,
        )

        request = IngestRequest(
            content="I decided to use Python for the project.",
            source="web",
            allow_duplicate=True,
        )

        note, confidence = await pipeline.run(request)

        assert note.file_path.endswith(".md")
        assert confidence.similar_note_detected is True
        assert confidence.similar_note_path == "existing_note.md"


class TestIngestPipelineIndexing:
    @pytest.mark.asyncio
    async def test_note_is_indexed_after_ingest(self, tmp_path):
        """After ingest, note chunks appear in the index."""
        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        ai = _make_ai()
        pipeline = IngestPipeline(
            vault=vault, index=index, ai=ai, settings=settings,
            registry=registry, failed_registry=failed,
        )

        request = IngestRequest(content="I decided to adopt event-driven architecture.", source="web")
        note, _ = await pipeline.run(request)

        stats = index.get_stats()
        assert stats.total_chunks >= 1
        assert stats.total_files >= 1


#endregion

# ---------------------------------------------------------------------------
#region #*   Duplicate detection edge-case tests
# ---------------------------------------------------------------------------


class TestDuplicateDetectionEdgeCases:
    @pytest.mark.asyncio
    async def test_old_note_not_flagged_as_duplicate(self, tmp_path):
        """Notes older than 7 days must NOT trigger duplicate detection."""
        from datetime import timedelta

        from monocle.index.memory import MemoryIndex
        from monocle.models import NoteChunk
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        # Chunk created 8 days ago — outside the 7-day window
        old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        old_chunk = NoteChunk(
            chunk_id="old_note.md::0",
            file_path="old_note.md",
            chunk_index=0,
            text="Old content",
            embedding=[0.1] * 1536,
            metadata={"created": old_ts, "updated_at": old_ts},
        )
        index.upsert_chunks([old_chunk])

        ai = _make_ai()
        ai.embed_batch.return_value = [[0.1] * 1536]

        pipeline = IngestPipeline(
            vault=vault, index=index, ai=ai, settings=settings,
            registry=registry, failed_registry=failed,
        )

        request = IngestRequest(
            content="I decided to use Python for the project.",
            source="web",
            allow_duplicate=False,
        )

        # Must NOT raise DuplicateSuspected (old note is filtered by 7-day cutoff)
        note, confidence = await pipeline.run(request)
        assert note.file_path.endswith(".md")
        assert confidence.similar_note_detected is False

    @pytest.mark.asyncio
    async def test_unparseable_created_date_still_triggers_duplicate(self, tmp_path):
        """A chunk with an unparseable 'created' date is kept in scope (conservative).

        The except clause silently ignores date-parse failures, which means the
        chunk is NOT filtered out and the duplicate check fires.
        """
        from monocle.index.memory import MemoryIndex
        from monocle.models import NoteChunk
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        # Corrupt date string
        corrupt_chunk = NoteChunk(
            chunk_id="corrupt_note.md::0",
            file_path="corrupt_note.md",
            chunk_index=0,
            text="Corrupt metadata",
            embedding=[0.1] * 1536,
            metadata={"created": "not-a-date", "updated_at": "also-bad"},
        )
        index.upsert_chunks([corrupt_chunk])

        ai = _make_ai()
        ai.embed_batch.return_value = [[0.1] * 1536]

        pipeline = IngestPipeline(
            vault=vault, index=index, ai=ai, settings=settings,
            registry=registry, failed_registry=failed,
        )

        request = IngestRequest(
            content="I decided to use Python for the project.",
            source="web",
            allow_duplicate=False,
        )

        # Conservative: unparseable date means note is NOT filtered → dup fires
        with pytest.raises(DuplicateSuspected) as exc_info:
            await pipeline.run(request)

        assert exc_info.value.similar_note_path == "corrupt_note.md"

    @pytest.mark.asyncio
    async def test_duplicate_suspected_does_not_register_failure(self, tmp_path):
        """DuplicateSuspected is a normal advisory signal, NOT a pipeline error.

        It must NOT create a FailedIngestRegistry entry or .error.md sidecar.
        """
        from monocle.index.memory import MemoryIndex
        from monocle.models import NoteChunk
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        existing_chunk = NoteChunk(
            chunk_id="existing.md::0",
            file_path="existing.md",
            chunk_index=0,
            text="Similar content",
            embedding=[0.1] * 1536,
            metadata={"created": datetime.now(timezone.utc).isoformat()},
        )
        index.upsert_chunks([existing_chunk])

        ai = _make_ai()
        ai.embed_batch.return_value = [[0.1] * 1536]

        pipeline = IngestPipeline(
            vault=vault, index=index, ai=ai, settings=settings,
            registry=registry, failed_registry=failed,
        )

        request = IngestRequest(
            content="I decided to use a new approach.", source="web", allow_duplicate=False
        )

        with pytest.raises(DuplicateSuspected):
            await pipeline.run(request)

        # No failure should have been recorded
        assert failed.count() == 0
        # No .error.md sidecar should exist
        inbox = tmp_path / "inbox"
        sidecars = list(inbox.glob("*.error.md")) if inbox.exists() else []
        assert len(sidecars) == 0


#endregion

# ---------------------------------------------------------------------------
#region #*   Step-8 failure test
# ---------------------------------------------------------------------------


class TestIngestPipelineStep8Failure:
    @pytest.mark.asyncio
    async def test_step8_failure_propagates_without_sidecar(self, tmp_path):
        """patch_frontmatter failure (step 8) propagates to the caller.

        Step 8 is outside the steps-3-5 sidecar guard, so no .error.md is
        written and no FailedIngestRegistry entry is created.  The note has
        already been written and indexed at step 6.
        """
        from unittest.mock import patch as mock_patch

        from monocle.index.memory import MemoryIndex
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        index = MemoryIndex()
        settings = _make_settings()
        registry = IngestPluginRegistry()
        register_default_plugins(registry)
        failed = FailedIngestRegistry(tmp_path / "failed.json")

        ai = _make_ai()
        pipeline = IngestPipeline(
            vault=vault, index=index, ai=ai, settings=settings,
            registry=registry, failed_registry=failed,
        )

        with mock_patch.object(vault, "patch_frontmatter", side_effect=OSError("disk full")):
            request = IngestRequest(
                content="I decided to test step-8 failures.", source="web"
            )
            with pytest.raises(OSError, match="disk full"):
                await pipeline.run(request)

        # No FailedIngestRegistry entry (step-8 failures are not tracked there)
        assert failed.count() == 0
        # No sidecar
        inbox = tmp_path / "inbox"
        sidecars = list(inbox.glob("*.error.md")) if inbox.exists() else []
        assert len(sidecars) == 0


#endregion

# ---------------------------------------------------------------------------
#region #*   Plugin registry idempotency
# ---------------------------------------------------------------------------


class TestRegisterDefaultPluginsIdempotency:
    def setup_method(self):
        IngestPluginRegistry.reset()

    def teardown_method(self):
        IngestPluginRegistry.reset()

    def test_calling_twice_does_not_duplicate_plugins(self):
        """register_default_plugins is idempotent — second call is a no-op."""
        registry = IngestPluginRegistry.get()
        register_default_plugins(registry)
        count_after_first = len(registry.plugins)
        register_default_plugins(registry)
        assert len(registry.plugins) == count_after_first

    def test_all_three_plugins_present_after_one_call(self):
        registry = IngestPluginRegistry.get()
        register_default_plugins(registry)
        ids = {p.source_id for p in registry.plugins}
        assert "voice" in ids
        assert "teams" in ids
        assert "web" in ids


#endregion

# ---------------------------------------------------------------------------
#region #*   RoutingAgent — unknown template and greedy-regex tests
# ---------------------------------------------------------------------------


class TestRoutingAgentValidation:
    @pytest.mark.asyncio
    async def test_llm_unknown_template_falls_back_to_blank(self):
        """LLM returns an unrecognised template name → blank, not a pipeline crash."""
        from monocle.agents.routing import RoutingAgent

        ai = _make_ai(
            chat_return='{"template": "hallucinated_type", "confidence": 0.9, "rationale": "bad"}'
        )
        agent = RoutingAgent(ai=ai)
        result = await agent.route("Some ambiguous content.")
        assert result.template == "blank"
        assert result.note_type == "other"
        assert result.confidence == 0.0

    def test_parse_routing_response_nested_json(self):
        """Greedy regex must handle nested JSON objects without truncating."""
        from monocle.agents.routing import _parse_routing_response

        raw = '{"template": "idea", "meta": {"k": "v"}, "confidence": 0.8, "rationale": "ok"}'
        data = _parse_routing_response(raw)
        assert data["template"] == "idea"
        assert data["confidence"] == 0.8

    def test_parse_routing_response_fenced_nested_json(self):
        """Greedy regex extracts full JSON even inside a markdown fence."""
        from monocle.agents.routing import _parse_routing_response

        raw = '```json\n{"template": "meeting", "extra": {"a": 1}, "confidence": 0.75, "rationale": "x"}\n```'
        data = _parse_routing_response(raw)
        assert data["template"] == "meeting"
        assert data["confidence"] == 0.75
