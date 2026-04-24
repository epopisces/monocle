"""monocle/tests/test_services.py — Unit tests for the canonical service layer.

Tests cover happy paths, validation, review-status, reindex queue pushes,
and result shape for each service in ``monocle.services.*``.
"""
from __future__ import annotations

import asyncio
import datetime
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monocle.models import (
    GraphData,
    GraphEdge,
    GraphNode,
    IngestConfidence,
    Note,
    NoteMetadata,
    ScoredChunk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_note(
    file_path: str = "work/test-note.md",
    title: str = "Test Note",
    body: str = "Hello world.",
    **meta_overrides,
) -> Note:
    meta = NoteMetadata(**meta_overrides) if meta_overrides else NoteMetadata()
    return Note(file_path=file_path, title=title, body=body, metadata=meta)


def _make_scored_chunk(file_path: str = "work/test.md", score: float = 0.95) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=f"{file_path}::0",
        file_path=file_path,
        score=score,
        text="chunk text",
        metadata={"type": "decision"},
    )


# ===========================================================================
# search_vault
# ===========================================================================


class TestSearchVault:
    """Tests for monocle.services.search.search_vault."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.search import search_vault

        chunks = [_make_scored_chunk()]
        index = MagicMock()
        index.search = MagicMock(return_value=chunks)
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)

        result = await search_vault(index, ai, "test query")

        ai.embed.assert_awaited_once_with("test query")
        index.search.assert_called_once()
        assert result == chunks

    @pytest.mark.asyncio
    async def test_n_results_clamped_low(self):
        from monocle.services.search import search_vault

        index = MagicMock()
        index.search = MagicMock(return_value=[])
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)

        await search_vault(index, ai, "q", n_results=-5)

        # n should be clamped to 1
        call_args = index.search.call_args
        assert call_args[0][1] == 1  # second positional arg = n

    @pytest.mark.asyncio
    async def test_n_results_clamped_high(self):
        from monocle.services.search import search_vault, _MAX_SEARCH_RESULTS

        index = MagicMock()
        index.search = MagicMock(return_value=[])
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)

        await search_vault(index, ai, "q", n_results=999)

        call_args = index.search.call_args
        assert call_args[0][1] == _MAX_SEARCH_RESULTS

    @pytest.mark.asyncio
    async def test_filters_passed(self):
        from monocle.services.search import search_vault

        index = MagicMock()
        index.search = MagicMock(return_value=[])
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)

        await search_vault(index, ai, "q", note_type="decision", domain="work")

        call_args = index.search.call_args
        assert call_args[0][2] == {"type": "decision", "domain": "work"}

    @pytest.mark.asyncio
    async def test_no_filters_passes_none(self):
        from monocle.services.search import search_vault

        index = MagicMock()
        index.search = MagicMock(return_value=[])
        ai = AsyncMock()
        ai.embed = AsyncMock(return_value=[0.1] * 1536)

        await search_vault(index, ai, "q")

        call_args = index.search.call_args
        assert call_args[0][2] is None  # filters=None when no filters

    @pytest.mark.asyncio
    async def test_memory_index_fallback_without_ai(self):
        from monocle.index.memory import MemoryIndex
        from monocle.models import NoteChunk
        from monocle.services.search import search_vault

        index = MemoryIndex()
        index.upsert_chunks([
            NoteChunk(
                chunk_id="work/test.md::0",
                file_path="work/test.md",
                chunk_index=0,
                text="engineer platform notes",
                embedding=[],
                metadata={"type": "observation", "domain": "work"},
            )
        ])

        results = await search_vault(index, None, "engineer")

        assert len(results) == 1
        assert results[0].file_path == "work/test.md"


# ===========================================================================
# read_note
# ===========================================================================


class TestReadNote:
    """Tests for monocle.services.notes.read_note."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.notes import read_note

        note = _make_note()
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=note)

        result = await read_note(vault, "work/test-note.md")

        vault.read_note.assert_called_once_with("work/test-note.md")
        assert result is note

    @pytest.mark.asyncio
    async def test_missing_file_propagates(self):
        from monocle.services.notes import read_note

        vault = MagicMock()
        vault.read_note = MagicMock(side_effect=FileNotFoundError("nope"))

        with pytest.raises(FileNotFoundError):
            await read_note(vault, "no/such/note.md")


# ===========================================================================
# create_note
# ===========================================================================


class TestCreateNote:
    """Tests for monocle.services.notes.create_note."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.notes import create_note

        note = _make_note(review_status="pending")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        rq = MagicMock()

        result = await create_note(vault, rq, "Test", "Some body", "idea", "personal", ["tag1"])

        vault.create_from_template.assert_called_once()
        vault.write_note.assert_called_once_with(note.file_path, note)
        rq.push.assert_called_once_with(note.file_path)
        assert result is note

    @pytest.mark.asyncio
    async def test_review_status_pending(self):
        from monocle.services.notes import create_note

        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=_make_note())
        vault.write_note = MagicMock()

        await create_note(vault, None, "T", "B")

        # Verify the metadata passed to create_from_template has review_status=pending
        call_args = vault.create_from_template.call_args
        template_data = call_args[0][1]
        assert template_data["review_status"] == "pending"

    @pytest.mark.asyncio
    async def test_body_too_long_raises(self):
        from monocle.services.notes import create_note, _MAX_BODY_LENGTH

        with pytest.raises(ValueError, match="character limit"):
            await create_note(MagicMock(), None, "T", "x" * (_MAX_BODY_LENGTH + 1))

    @pytest.mark.asyncio
    async def test_no_reindex_queue(self):
        from monocle.services.notes import create_note

        note = _make_note()
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()

        # Should not raise when reindex_queue is None
        result = await create_note(vault, None, "T", "B")
        assert result is note

    @pytest.mark.asyncio
    async def test_invalid_note_type_raises(self):
        """Validate that invalid note_type raises clear error at service boundary."""
        from monocle.services.notes import create_note

        vault = MagicMock()
        rq = MagicMock()

        with pytest.raises(ValueError, match="not valid"):
            await create_note(vault, rq, "Title", "Body", note_type="invalid_type")

    @pytest.mark.asyncio
    async def test_valid_note_types_accepted(self):
        """Validate that all allowed note types are accepted."""
        from monocle.services.notes import create_note

        allowed_types = [
            "person_note", "person", "decision", "idea", "observation",
            "reference", "meeting_note", "meeting", "project", "action_item",
            "weekly_summary", "organization", "other", "blank"
        ]

        note = _make_note()
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        rq = MagicMock()

        for note_type in allowed_types:
            vault.reset_mock()
            rq.reset_mock()
            result = await create_note(vault, rq, "T", "B", note_type=note_type)
            assert result is note
            vault.create_from_template.assert_called_once()
            call_args = vault.create_from_template.call_args[0]
            assert call_args[0] == note_type

    @pytest.mark.asyncio
    async def test_alias_note_type_normalized_in_metadata(self):
        from monocle.services.notes import create_note

        note = _make_note(type="person_note")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()

        await create_note(vault, None, "Alice", "Body", note_type="person")

        template_data = vault.create_from_template.call_args[0][1]
        assert template_data["type"] == "person_note"


# ===========================================================================
# update_note
# ===========================================================================


class TestUpdateNote:
    """Tests for monocle.services.notes.update_note."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.notes import update_note

        existing = _make_note(body="old body")
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=existing)
        vault.write_note = MagicMock()
        rq = MagicMock()

        result = await update_note(vault, rq, "work/test-note.md", "new body")

        assert result.body == "new body"
        vault.write_note.assert_called_once_with("work/test-note.md", existing)
        rq.push.assert_called_once_with(existing.file_path)

    @pytest.mark.asyncio
    async def test_updated_timestamp_set(self):
        from monocle.services.notes import update_note

        existing = _make_note()
        existing.metadata.updated = None
        vault = MagicMock()
        vault.read_note = MagicMock(return_value=existing)
        vault.write_note = MagicMock()

        before = datetime.datetime.now(datetime.timezone.utc)
        result = await update_note(vault, None, "work/test-note.md", "new body")

        assert result.metadata.updated is not None
        assert result.metadata.updated >= before

    @pytest.mark.asyncio
    async def test_body_too_long_raises(self):
        from monocle.services.notes import update_note, _MAX_BODY_LENGTH

        with pytest.raises(ValueError, match="character limit"):
            await update_note(MagicMock(), None, "x.md", "x" * (_MAX_BODY_LENGTH + 1))

    @pytest.mark.asyncio
    async def test_missing_file_propagates(self):
        from monocle.services.notes import update_note

        vault = MagicMock()
        vault.read_note = MagicMock(side_effect=FileNotFoundError("nope"))

        with pytest.raises(FileNotFoundError):
            await update_note(vault, None, "no/file.md", "body")


# ===========================================================================
# get_graph
# ===========================================================================


class TestGetGraph:
    """Tests for monocle.services.graph.get_graph."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.graph import get_graph

        graph_data = GraphData(
            focus="people/alice.md",
            nodes=[GraphNode(id="people/alice.md", label="Alice", type="person_note")],
            edges=[],
        )
        builder = MagicMock()
        builder.build = MagicMock(return_value=graph_data)

        result = await get_graph(builder, focus="people/alice.md")

        builder.build.assert_called_once_with("people/alice.md", 2, None, 500)
        assert result is graph_data
        assert result.focus == "people/alice.md"

    @pytest.mark.asyncio
    async def test_full_vault_no_focus(self):
        from monocle.services.graph import get_graph

        graph_data = GraphData(nodes=[], edges=[])
        builder = MagicMock()
        builder.build = MagicMock(return_value=graph_data)

        result = await get_graph(builder)

        builder.build.assert_called_once_with(None, 2, None, 500)
        assert result.focus is None

    @pytest.mark.asyncio
    async def test_custom_params(self):
        from monocle.services.graph import get_graph

        builder = MagicMock()
        builder.build = MagicMock(return_value=GraphData())

        await get_graph(builder, focus="x.md", max_degree=3, types=("person_note",), n=100)

        builder.build.assert_called_once_with("x.md", 3, ("person_note",), 100)


# ===========================================================================
# create_reference_from_url
# ===========================================================================


class TestCreateReferenceFromUrl:
    """Tests for monocle.services.references.create_reference_from_url."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.references import create_reference_from_url

        note = _make_note(type="reference", review_status="pending")
        ai_response = (
            "## Summary\nGreat article.\n\n## Key Points\n- Point 1\n\n"
            '```json\n{"title": "Test Article", "tags": ["ai"], "domain": "technology"}\n```'
        )

        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value=ai_response)
        rq = MagicMock()

        with patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Page content")):
            result = await create_reference_from_url(vault, ai, rq, "https://example.com")

        assert result is note
        vault.create_from_template.assert_called_once()
        vault.write_note.assert_called_once()
        rq.push.assert_called_once_with(note.file_path)

        # Verify reference note metadata
        call_args = vault.create_from_template.call_args[0]
        assert call_args[0] == "reference"  # template type
        template_data = call_args[1]
        assert template_data["review_status"] == "pending"
        assert template_data["type"] == "reference"
        assert "web-reference" in template_data["tags"]

    @pytest.mark.asyncio
    async def test_logs_stage_timings(self):
        from monocle.services.references import create_reference_from_url

        note = _make_note(type="reference", review_status="pending")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="Summary\n```json\n{}\n```")

        with (
            patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Page content")),
            patch("monocle.services.references.logger.info") as info_mock,
        ):
            await create_reference_from_url(vault, ai, None, "https://example.com")

        assert info_mock.called
        assert "create_reference_from_url complete" in info_mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_summarize_timeout_uses_fallback_body(self):
        from monocle.services.references import create_reference_from_url

        note = _make_note(type="reference", review_status="pending")
        page_text = (
            "Sentence one explains the article in enough detail to be useful. "
            "Sentence two adds another key idea worth preserving for later. "
            "Sentence three gives more detail on the implementation approach. "
            "Sentence four rounds out the main points for review."
        )

        async def _slow_chat(*args, **kwargs):
            await asyncio.sleep(0.05)
            return "late summary"

        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=_slow_chat)

        with (
            patch("monocle.services.references.fetch_url_text", AsyncMock(return_value=page_text)),
            patch("monocle.services.references._DEFAULT_URL_SUMMARISE_TIMEOUT_S", 0.01),
            patch("monocle.services.references.logger.warning") as warning_mock,
        ):
            result = await create_reference_from_url(
                vault,
                ai,
                None,
                "https://example.com/articles/test-post",
            )

        assert result is note
        warning_mock.assert_called_once()
        template_data = vault.create_from_template.call_args[0][1]
        assert template_data["title"] == "example.com / test post"
        assert "fallback-summary" in template_data["tags"]
        body = vault.create_from_template.call_args[0][2]
        assert body.startswith("> Source: https://example.com/articles/test-post")
        assert "AI summarization timed out after 0.01s" in body
        assert "## Extracted Excerpt" in body

    @pytest.mark.asyncio
    async def test_disallowed_scheme_raises(self):
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="http"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "ftp://example.com"
            )

    @pytest.mark.asyncio
    async def test_no_json_block_uses_url_as_title(self):
        from monocle.services.references import create_reference_from_url

        note = _make_note(type="reference")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="Just a plain summary without JSON.")

        with patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Content")):
            await create_reference_from_url(vault, ai, None, "https://example.com/page")

        template_data = vault.create_from_template.call_args[0][1]
        assert template_data["title"] == "https://example.com/page"  # fallback

    @pytest.mark.asyncio
    async def test_ssrf_blocked_loopback_localhost(self):
        """SSRF protection: reject localhost hostname."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://localhost:8000/admin"
            )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_loopback_127_0_0_1(self):
        """SSRF protection: reject 127.0.0.1 loopback address."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://127.0.0.1:8000/"
            )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_loopback_ipv6(self):
        """SSRF protection: reject IPv6 loopback (::1)."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://[::1]:8000/"
            )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_private_10_0_0_0(self):
        """SSRF protection: reject private range 10.0.0.0/8."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://10.0.0.50/"
            )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_private_172_16_0_0(self):
        """SSRF protection: reject private range 172.16.0.0/12."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://172.16.1.50/"
            )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_private_192_168_0_0(self):
        """SSRF protection: reject private range 192.168.0.0/16."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://192.168.1.1/"
            )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_link_local_169_254(self):
        """SSRF protection: reject link-local range 169.254.0.0/16 (AWS metadata)."""
        from monocle.services.references import create_reference_from_url

        with pytest.raises(ValueError, match="not allowed"):
            await create_reference_from_url(
                MagicMock(), AsyncMock(), None, "http://169.254.169.254/latest/meta-data/"
            )

    @pytest.mark.asyncio
    async def test_ssrf_allowed_public_url(self):
        """SSRF protection: allow public URLs (example.com)."""
        from monocle.services.references import create_reference_from_url

        note = _make_note(type="reference")
        vault = MagicMock()
        vault.create_from_template = MagicMock(return_value=note)
        vault.write_note = MagicMock()
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value='```json\n{"title": "Test"}\n```')

        with patch("monocle.services.references.fetch_url_text", AsyncMock(return_value="Content")):
            result = await create_reference_from_url(
                vault, ai, None, "https://example.com/public"
            )

        # Should succeed without raising
        assert result is note

    @pytest.mark.asyncio
    async def test_ssrf_blocked_hostname_resolving_to_private_ip(self):
        from monocle.services.references import create_reference_from_url

        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.20", 0)),
        ]

        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with pytest.raises(ValueError, match="not allowed"):
                await create_reference_from_url(
                    MagicMock(), AsyncMock(), None, "https://public.example.test/path"
                )

    @pytest.mark.asyncio
    async def test_ssrf_blocked_redirect_to_private_host(self):
        from monocle.services.references import create_reference_from_url
        import httpx

        redirect_response = httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
            request=httpx.Request("GET", "https://example.com/start"),
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=redirect_response)

        class _ClientContext:
            async def __aenter__(self):
                return mock_client

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch("httpx.AsyncClient", return_value=_ClientContext()):
            with pytest.raises(ValueError, match="not allowed"):
                await create_reference_from_url(
                    MagicMock(), AsyncMock(), None, "https://example.com/start"
                )


# ===========================================================================
# capture_thought
# ===========================================================================


class TestCaptureThought:
    """Tests for monocle.services.ingest.capture_thought."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from monocle.services.ingest import capture_thought

        note = _make_note()
        confidence = IngestConfidence(
            score=0.8,
            template_match=0.35,
            metadata_coverage=0.30,
            tag_plausibility=0.20,
            entity_match=0.15,
        )
        pipeline = AsyncMock()
        pipeline.run = AsyncMock(return_value=(note, confidence))

        result_note, result_conf = await capture_thought(pipeline, "A quick thought")

        assert result_note is note
        assert result_conf is confidence
        pipeline.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_content_too_long_raises(self):
        from monocle.services.ingest import capture_thought, _MAX_BODY_LENGTH

        with pytest.raises(ValueError, match="character limit"):
            await capture_thought(AsyncMock(), "x" * (_MAX_BODY_LENGTH + 1))

    @pytest.mark.asyncio
    async def test_source_passed_through(self):
        from monocle.services.ingest import capture_thought

        pipeline = AsyncMock()
        pipeline.run = AsyncMock(return_value=(_make_note(), None))

        await capture_thought(pipeline, "thought", source="voice")

        req = pipeline.run.call_args[0][0]
        assert req.source == "voice"

    @pytest.mark.asyncio
    async def test_confidence_none_accepted(self):
        """Test capture_thought when pipeline returns (note, None) for confidence.
        
        This tests the error recovery path where ingest fails to calculate confidence
        but successfully creates a note. The service must still return both the note
        and the None confidence value to the caller.
        """
        from monocle.services.ingest import capture_thought

        note = _make_note()
        pipeline = AsyncMock()
        pipeline.run = AsyncMock(return_value=(note, None))

        result_note, result_conf = await capture_thought(pipeline, "recovery thought")

        assert result_note is note
        assert result_conf is None
