"""
monocle/tests/test_ai.py — Unit tests for the AI Provider Abstraction (M6).

All tests are mock-based — no live Ollama, Foundry, or Azure required.
Integration tests that DO require a live endpoint are gated behind the
``@pytest.mark.integration`` marker and are skipped by default.

Run::

    uv run python -m pytest monocle/tests/test_ai.py -x --tb=short -q
"""
from __future__ import annotations

import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monocle.ai.base import AIProvider, _load_extract_prompt, _parse_json_response
from monocle.config import Settings
from monocle.models import NoteMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> Settings:
    """Return a minimal Settings object (no config.yaml required)."""
    defaults: dict = {
        "ai": {"provider": "ollama"},
        "vault": {"path": "/tmp/vault", "watch": False},
    }
    defaults.update(overrides)
    with patch("monocle.config._find_config_file", return_value=__import__("pathlib").Path("/nonexistent")):
        with patch("monocle.config._load_yaml", return_value=defaults):
            return Settings()


# ---------------------------------------------------------------------------
# _parse_json_response tests
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_plain_json(self):
        raw = '{"title": "Test", "type": "idea"}'
        result = _parse_json_response(raw)
        assert result["title"] == "Test"
        assert result["type"] == "idea"

    def test_json_in_code_fence(self):
        raw = '```json\n{"title": "Test"}\n```'
        result = _parse_json_response(raw)
        assert result["title"] == "Test"

    def test_json_in_plain_code_fence(self):
        raw = "```\n{\"title\": \"Test\"}\n```"
        result = _parse_json_response(raw)
        assert result["title"] == "Test"

    def test_json_with_surrounding_text(self):
        raw = 'Sure! Here is the JSON:\n{"title": "Test"}\nLet me know if you need more.'
        result = _parse_json_response(raw)
        assert result["title"] == "Test"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json at all")


# ---------------------------------------------------------------------------
# _load_extract_prompt tests
# ---------------------------------------------------------------------------


class TestLoadExtractPrompt:
    def test_returns_string(self):
        # With no files present it should still return the built-in default
        with patch("pathlib.Path.exists", return_value=False):
            prompt = _load_extract_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 10


# ---------------------------------------------------------------------------
# OllamaProvider tests
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    def _make_provider(self, mock_client: MagicMock):
        from monocle.ai.ollama_provider import OllamaProvider

        with patch("monocle.ai.ollama_provider.ollama.AsyncClient", return_value=mock_client):
            provider = OllamaProvider(
                embed_model="nomic-embed-text",
                chat_model="llama3.2",
                base_url="http://localhost:11434",
            )
        # Replace the already-created client with the mock
        provider._client = mock_client
        provider._ready_models.add("nomic-embed-text")  # skip auto-pull
        provider._ready_models.add("llama3.2")
        return provider

    @pytest.mark.asyncio
    async def test_embed_returns_list_of_floats(self):
        mock_client = AsyncMock()
        mock_client.embed.return_value = MagicMock(embeddings=[[0.1, 0.2, 0.3]])
        provider = self._make_provider(mock_client)

        result = await provider.embed("hello world")

        assert isinstance(result, list)
        assert result == [0.1, 0.2, 0.3]
        mock_client.embed.assert_awaited_once_with(
            model="nomic-embed-text", input="hello world"
        )

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list_of_vectors(self):
        mock_client = AsyncMock()
        vecs = [[0.1, 0.2], [0.3, 0.4]]
        mock_client.embed.return_value = MagicMock(embeddings=vecs)
        provider = self._make_provider(mock_client)

        result = await provider.embed_batch(["foo", "bar"])

        assert result == vecs
        mock_client.embed.assert_awaited_once_with(
            model="nomic-embed-text", input=["foo", "bar"]
        )

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list_returns_empty(self):
        mock_client = AsyncMock()
        provider = self._make_provider(mock_client)

        result = await provider.embed_batch([])

        assert result == []
        mock_client.embed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_non_stream_returns_string(self):
        mock_client = AsyncMock()
        mock_client.chat.return_value = MagicMock(
            message=MagicMock(content="Hello there!", tool_calls=None)
        )
        provider = self._make_provider(mock_client)

        result = await provider.chat(
            [{"role": "user", "content": "Hi"}], stream=False
        )

        assert result == "Hello there!"
        mock_client.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_stream_returns_async_iterator(self):
        mock_client = AsyncMock()

        # Create the async generator directly
        async def _stream_gen():
            for token in ["Hello", " world", "!"]:
                yield MagicMock(message=MagicMock(content=token))

        # Wrap in a coroutine that returns the generator
        # This models Ollama AsyncClient.chat(stream=True) behavior
        async def _mock_chat_coro(*args, **kwargs):
            return _stream_gen()

        # Set the mock's return value to the coroutine function result
        mock_client.chat = AsyncMock(side_effect=_mock_chat_coro)
        provider = self._make_provider(mock_client)

        result = await provider.chat(
            [{"role": "user", "content": "Hi"}], stream=True
        )
        tokens = [t async for t in result]
        assert tokens == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_auto_pull_on_model_not_found(self):
        """When the model is not found locally, the provider should pull it."""
        import ollama as _ollama

        mock_client = AsyncMock()
        # simulate "model not found" on show(), then success
        mock_client.show.side_effect = _ollama.ResponseError("model not found")
        mock_client.pull.return_value = None
        mock_client.embed.return_value = MagicMock(embeddings=[[0.5]])

        from monocle.ai.ollama_provider import OllamaProvider

        with patch("monocle.ai.ollama_provider.ollama.AsyncClient", return_value=mock_client):
            provider = OllamaProvider(
                embed_model="new-model",
                chat_model="llama3.2",
            )
        provider._client = mock_client

        await provider.embed("test")

        mock_client.pull.assert_awaited_once_with("new-model")

    @pytest.mark.asyncio
    async def test_extract_note_metadata_returns_notemetadata(self):
        mock_client = AsyncMock()
        payload = json.dumps({
            "title": "Meeting with Alice",
            "type": "meeting_note",
            "people": ["Alice"],
            "tags": ["meeting"],
        })
        mock_client.chat.return_value = MagicMock(message=MagicMock(content=payload, tool_calls=None))
        provider = self._make_provider(mock_client)

        result = await provider.extract_note_metadata(
            "Had a meeting with Alice about Q4 plans.", "meeting"
        )

        assert isinstance(result, NoteMetadata)
        assert result.type == "meeting_note"
        assert "Alice" in result.people

    @pytest.mark.asyncio
    async def test_extract_note_metadata_bad_json_returns_defaults(self):
        """If the LLM returns garbage, extract_note_metadata falls back to defaults."""
        mock_client = AsyncMock()
        mock_client.chat.return_value = MagicMock(
            message=MagicMock(content="Sorry, I cannot help with that.")
        )
        provider = self._make_provider(mock_client)

        result = await provider.extract_note_metadata("Some text", "blank")

        assert isinstance(result, NoteMetadata)
        # should return defaults, not raise
        assert result.type == "other"


# ---------------------------------------------------------------------------
# FoundryLocalProvider tests
# ---------------------------------------------------------------------------


class TestFoundryLocalProvider:
    def _make_provider(self, mock_openai_cls=None):
        from monocle.ai.foundry_local_provider import FoundryLocalProvider

        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            provider = FoundryLocalProvider(
                base_url="http://localhost:5272",
                api_key="local",
                embed_model="nomic-embed-text",
                chat_model="llama3.2",
            )
            provider._client = mock_instance
        return provider

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self):
        provider = self._make_provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])
        )

        result = await provider.embed("hello")

        assert result == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self):
        provider = self._make_provider()
        result = await provider.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_returns_ordered_vectors(self):
        provider = self._make_provider()
        vecs = [[0.1, 0.2], [0.3, 0.4]]
        provider._client.embeddings.create = AsyncMock(
            return_value=MagicMock(
                data=[MagicMock(embedding=v) for v in vecs]
            )
        )

        result = await provider.embed_batch(["a", "b"])

        assert result == vecs

    @pytest.mark.asyncio
    async def test_chat_returns_string(self):
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Hi there!", tool_calls=None))]
            )
        )

        result = await provider.chat([{"role": "user", "content": "Hey"}])

        assert result == "Hi there!"


# ---------------------------------------------------------------------------
# AzureOpenAIProvider tests
# ---------------------------------------------------------------------------


class TestAzureOpenAIProvider:
    def _make_provider(self):
        from monocle.ai.azure_provider import AzureOpenAIProvider

        with patch("openai.AsyncAzureOpenAI") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            provider = AzureOpenAIProvider(
                api_key="test-key",
                endpoint="https://example.openai.azure.com",
                api_version="2024-02-01",
                embed_deployment="text-embedding-3-large",
                chat_deployment="gpt-4o",
            )
            provider._client = mock_instance
        return provider

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self):
        provider = self._make_provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=MagicMock(data=[MagicMock(embedding=[0.5, 0.6, 0.7])])
        )

        result = await provider.embed("test")

        assert result == [0.5, 0.6, 0.7]

    @pytest.mark.asyncio
    async def test_embed_with_dimensions(self):
        from monocle.ai.azure_provider import AzureOpenAIProvider

        with patch("openai.AsyncAzureOpenAI") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            provider = AzureOpenAIProvider(
                api_key="key",
                endpoint="https://example.openai.azure.com",
                api_version="2024-02-01",
                embed_deployment="text-embedding-3-large",
                chat_deployment="gpt-4o",
                embed_dimensions=1536,
            )
            provider._client = mock_instance

        provider._client.embeddings.create = AsyncMock(
            return_value=MagicMock(data=[MagicMock(embedding=[0.1] * 1536)])
        )
        result = await provider.embed("hello")
        call_kwargs = provider._client.embeddings.create.call_args.kwargs
        assert call_kwargs.get("dimensions") == 1536
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_chat_returns_string(self):
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Azure says hi!", tool_calls=None))]
            )
        )

        result = await provider.chat([{"role": "user", "content": "Hi"}])

        assert result == "Azure says hi!"

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self):
        provider = self._make_provider()
        result = await provider.embed_batch([])
        assert result == []


# ---------------------------------------------------------------------------
# get_provider factory tests
# ---------------------------------------------------------------------------


class TestGetProviderFactory:
    @staticmethod
    def _settings(provider: str, extra: dict | None = None) -> Settings:
        ai_cfg: dict = {"provider": provider}
        if extra:
            ai_cfg.update(extra)
        cfg = {"ai": ai_cfg, "vault": {"path": "/tmp/vault", "watch": False}}
        if provider == "azure":
            cfg["azure_openai_api_key"] = "key"
            cfg["azure_openai_endpoint"] = "https://example.openai.azure.com"
            cfg["azure_openai_api_version"] = "2024-02-01"
        with patch("monocle.config._find_config_file", return_value=__import__("pathlib").Path("/nonexistent")):
            with patch("monocle.config._load_yaml", return_value=cfg):
                return Settings()

    def test_factory_returns_ollama_for_ollama(self):
        from monocle.ai import get_provider
        from monocle.ai.ollama_provider import OllamaProvider

        settings = self._settings("ollama")
        with patch("ollama.AsyncClient"):
            provider = get_provider(settings)
        assert isinstance(provider, OllamaProvider)

    def test_factory_returns_foundry_local(self):
        from monocle.ai import get_provider
        from monocle.ai.foundry_local_provider import FoundryLocalProvider

        settings = self._settings("foundry_local")
        with patch("openai.AsyncOpenAI"):
            provider = get_provider(settings)
        assert isinstance(provider, FoundryLocalProvider)

    def test_factory_returns_azure(self):
        from monocle.ai import get_provider
        from monocle.ai.azure_provider import AzureOpenAIProvider

        settings = self._settings("azure")
        with patch("openai.AsyncAzureOpenAI"):
            provider = get_provider(settings)
        assert isinstance(provider, AzureOpenAIProvider)

    def test_factory_raises_for_unknown_provider(self):
        from monocle.ai import get_provider

        settings = self._settings("ollama")
        settings.ai.provider = "nonexistent"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown ai.provider"):
            get_provider(settings)


# ---------------------------------------------------------------------------
# AIProvider ABC contract test
# ---------------------------------------------------------------------------


class TestAIProviderIsAbstract:
    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            AIProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# AIProvider.chat() with tools — regression tests for Bug #1/#2
# ---------------------------------------------------------------------------


class TestOllamaChatWithTools:
    """OllamaProvider forwards tools to client and serialises tool_calls response."""

    def _make_provider(self):
        from monocle.ai.ollama_provider import OllamaProvider

        mock_client = AsyncMock()
        with patch("monocle.ai.ollama_provider.ollama.AsyncClient", return_value=mock_client):
            provider = OllamaProvider(
                embed_model="nomic-embed-text",
                chat_model="llama3.2",
            )
        provider._client = mock_client
        provider._ready_models.add("llama3.2")
        return provider, mock_client

    @pytest.mark.asyncio
    async def test_chat_with_tools_accepted_no_typeerror(self):
        """Passing tools= kwarg must not raise TypeError."""
        provider, mock_client = self._make_provider()
        mock_client.chat.return_value = MagicMock(
            message=MagicMock(content="plain text", tool_calls=None)
        )

        result = await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "search_vault", "description": "", "parameters": {}}}],
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_chat_tool_call_response_is_json_string(self):
        """When the model returns tool_calls, chat() returns a JSON string."""
        import json as _json
        provider, mock_client = self._make_provider()

        fake_tc = MagicMock()
        fake_tc.function.name = "search_vault"
        fake_tc.function.arguments = {"query": "Alice"}
        mock_client.chat.return_value = MagicMock(
            message=MagicMock(content="", tool_calls=[fake_tc])
        )

        result = await provider.chat(
            [{"role": "user", "content": "find Alice"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "search_vault", "description": "", "parameters": {}}}],
        )
        parsed = _json.loads(result)
        assert "tool_calls" in parsed
        assert parsed["tool_calls"][0]["function"]["name"] == "search_vault"

    @pytest.mark.asyncio
    async def test_chat_without_tools_still_works(self):
        """chat() with tools=None must still return plain text (no regression)."""
        provider, mock_client = self._make_provider()
        mock_client.chat.return_value = MagicMock(
            message=MagicMock(content="Hello there!", tool_calls=None)
        )

        result = await provider.chat([{"role": "user", "content": "hi"}], stream=False)
        assert result == "Hello there!"


class TestFoundryLocalChatWithTools:
    """FoundryLocalProvider forwards tools and serialises tool_calls."""

    def _make_provider(self):
        from monocle.ai.foundry_local_provider import FoundryLocalProvider

        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            provider = FoundryLocalProvider(
                base_url="http://localhost:5272",
                api_key="local",
                embed_model="nomic-embed-text",
                chat_model="llama3.2",
            )
            provider._client = mock_instance
        return provider

    @pytest.mark.asyncio
    async def test_chat_with_tools_no_typeerror(self):
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))]
            )
        )
        result = await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "read_note", "description": "", "parameters": {}}}],
        )
        assert isinstance(result, str)
        # confirm tools was forwarded
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_tool_call_serialised_to_json(self):
        import json as _json
        provider = self._make_provider()

        fake_tc = MagicMock()
        fake_tc.id = "call-1"
        fake_tc.function.name = "read_note"
        fake_tc.function.arguments = '{"file_path": "people/alice.md"}'
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="", tool_calls=[fake_tc]))]
            )
        )

        result = await provider.chat(
            [{"role": "user", "content": "read alice"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "read_note", "description": "", "parameters": {}}}],
        )
        parsed = _json.loads(result)
        assert parsed["tool_calls"][0]["function"]["name"] == "read_note"


class TestAzureChatWithTools:
    """AzureOpenAIProvider forwards tools and serialises tool_calls."""

    def _make_provider(self):
        from monocle.ai.azure_provider import AzureOpenAIProvider

        with patch("openai.AsyncAzureOpenAI") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            provider = AzureOpenAIProvider(
                api_key="test-key",
                endpoint="https://example.openai.azure.com",
                api_version="2024-02-01",
                embed_deployment="text-embedding-3-large",
                chat_deployment="gpt-4o",
            )
            provider._client = mock_instance
        return provider

    @pytest.mark.asyncio
    async def test_chat_with_tools_no_typeerror(self):
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))]
            )
        )
        result = await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "get_stats", "description": "", "parameters": {}}}],
        )
        assert isinstance(result, str)
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_tool_call_serialised_to_json(self):
        import json as _json
        provider = self._make_provider()

        fake_tc = MagicMock()
        fake_tc.id = "call-2"
        fake_tc.function.name = "get_stats"
        fake_tc.function.arguments = "{}"
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="", tool_calls=[fake_tc]))]
            )
        )

        result = await provider.chat(
            [{"role": "user", "content": "stats"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "get_stats", "description": "", "parameters": {}}}],
        )
        parsed = _json.loads(result)
        assert parsed["tool_calls"][0]["function"]["name"] == "get_stats"


# ---------------------------------------------------------------------------
# Integration tests (skipped by default)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestOllamaIntegration:
    """Live Ollama tests — skipped unless run with `-m integration`."""

    @pytest.mark.asyncio
    async def test_live_embed(self):
        from monocle.ai.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        result = await provider.embed("Hello, Monocle integration test.")
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_live_chat(self):
        from monocle.ai.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        result = await provider.chat(
            [{"role": "user", "content": "Reply with the single word: OK"}],
            stream=False,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_live_embed_batch(self):
        from monocle.ai.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        results = await provider.embed_batch(texts)
        assert len(results) == 3
        assert all(isinstance(v, list) for v in results)


# ---------------------------------------------------------------------------
# TranscriptionProvider tests
# ---------------------------------------------------------------------------


class TestWhisperCppTranscriptionProvider:
    """Tests for the whisper.cpp HTTP-backend transcription provider."""

    @pytest.mark.asyncio
    async def test_transcribe_success(self):
        from monocle.ai.transcription import WhisperCppTranscriptionProvider

        audio = b"fake-audio"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Hello world"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = WhisperCppTranscriptionProvider(base_url="http://localhost:9000")
            result = await provider.transcribe(audio, "audio/wav")

        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_transcribe_connect_error_raises_runtime_error(self):
        import httpx
        from monocle.ai.transcription import WhisperCppTranscriptionProvider

        audio = b"fake-audio"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = WhisperCppTranscriptionProvider(base_url="http://localhost:9000")
            with pytest.raises(RuntimeError, match="whisper.cpp"):
                await provider.transcribe(audio, "audio/wav")

    def test_default_url(self):
        from monocle.ai.transcription import WhisperCppTranscriptionProvider

        p = WhisperCppTranscriptionProvider()
        assert p._base_url == "http://localhost:9000"


class TestSubprocessTranscriptionProvider:
    """Tests for the subprocess (openai-whisper Python API) provider."""

    @pytest.mark.asyncio
    async def test_transcribe_success(self):
        from monocle.ai.transcription import SubprocessTranscriptionProvider

        # Mock the whisper module to return a transcribed result
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "transcribed text"}

        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        # Patch at the import point inside the function, and also mock ffmpeg availability
        import sys
        import shutil
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            # Mock shutil.which (at the standard library level) to pretend ffmpeg is available
            with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
                provider = SubprocessTranscriptionProvider()
                result = await provider.transcribe(b"audio-bytes", "audio/wav")

        assert result == "transcribed text"
        mock_whisper.load_model.assert_called_once()
        mock_model.transcribe.assert_called_once()


class TestNativeOpenAITranscriptionProvider:
    """Tests for the OpenAI-client-based native transcription provider."""

    @pytest.mark.asyncio
    async def test_transcribe_calls_client(self):
        from monocle.ai.transcription import NativeOpenAITranscriptionProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "native transcription"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        provider = NativeOpenAITranscriptionProvider(mock_client, model="whisper-1")
        result = await provider.transcribe(b"audio-bytes", "audio/webm")

        assert result == "native transcription"
        mock_client.audio.transcriptions.create.assert_awaited_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-1"


class TestAIConfigValidation:
    """Tests for AIConfig model-validator logic."""

    def test_ollama_native_explicit_raises(self):
        """Explicitly setting native+ollama must fail at config construction time."""
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="native.*ollama|ollama.*native"):
            _make_settings(ai={"provider": "ollama", "transcribe_backend": "native"})

    def test_ollama_default_gets_subprocess(self):
        """When provider=ollama and transcribe_backend is omitted, default is 'subprocess'."""
        settings = _make_settings(ai={"provider": "ollama"})
        assert settings.ai.transcribe_backend == "subprocess"

    def test_foundry_local_native_valid(self):
        """provider=foundry_local with transcribe_backend=native is allowed."""
        settings = _make_settings(ai={"provider": "foundry_local", "transcribe_backend": "native"})
        assert settings.ai.transcribe_backend == "native"

    def test_ollama_whisper_cpp_valid(self):
        settings = _make_settings(ai={"provider": "ollama", "transcribe_backend": "whisper_cpp"})
        assert settings.ai.transcribe_backend == "whisper_cpp"

    def test_ollama_subprocess_valid(self):
        settings = _make_settings(ai={"provider": "ollama", "transcribe_backend": "subprocess"})
        assert settings.ai.transcribe_backend == "subprocess"


class TestGetTranscriptionProvider:
    """Tests for the get_transcription_provider factory."""

    def test_native_returns_none(self):
        from monocle.ai.transcription import get_transcription_provider

        # "native" is valid with foundry_local / azure (they have a built-in endpoint).
        settings = _make_settings(ai={"provider": "foundry_local", "transcribe_backend": "native"})
        result = get_transcription_provider(settings)
        assert result is None

    def test_whisper_cpp_returns_correct_type(self):
        from monocle.ai.transcription import (
            WhisperCppTranscriptionProvider,
            get_transcription_provider,
        )

        settings = _make_settings(
            ai={
                "provider": "ollama",
                "transcribe_backend": "whisper_cpp",
                "transcribe_url": "http://localhost:9999",
            }
        )
        result = get_transcription_provider(settings)
        assert isinstance(result, WhisperCppTranscriptionProvider)
        assert result._base_url == "http://localhost:9999"

    def test_subprocess_returns_correct_type(self):
        from monocle.ai.transcription import (
            SubprocessTranscriptionProvider,
            get_transcription_provider,
        )

        settings = _make_settings(
            ai={"provider": "ollama", "transcribe_backend": "subprocess"}
        )
        result = get_transcription_provider(settings)
        assert isinstance(result, SubprocessTranscriptionProvider)

    def test_unknown_backend_raises(self):
        from monocle.ai.transcription import get_transcription_provider

        settings = _make_settings(
            ai={"provider": "foundry_local", "transcribe_backend": "native"}
        )
        # Monkeypatch the backend value to an unknown string
        settings.ai.transcribe_backend = "invalid_backend"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="invalid_backend"):
            get_transcription_provider(settings)


class TestOllamaTranscription:
    """Tests for Ollama provider transcription delegation."""

    @pytest.mark.asyncio
    async def test_transcribe_delegates_to_provider(self):
        from monocle.ai.ollama_provider import OllamaProvider

        mock_tp = AsyncMock()
        mock_tp.transcribe = AsyncMock(return_value="ollama transcription")

        provider = OllamaProvider(
            embed_model="nomic-embed-text",
            chat_model="llama3.2",
            transcription_provider=mock_tp,
        )
        result = await provider.transcribe(b"audio", "audio/wav")

        assert result == "ollama transcription"
        mock_tp.transcribe.assert_awaited_once_with(b"audio", "audio/wav")

    @pytest.mark.asyncio
    async def test_transcribe_raises_when_no_provider(self):
        from monocle.ai.ollama_provider import OllamaProvider

        provider = OllamaProvider(transcription_provider=None)
        with pytest.raises(RuntimeError, match="transcription provider"):
            await provider.transcribe(b"audio", "audio/wav")


# ---------------------------------------------------------------------------
# Transcription integration tests (require live servers — skipped by default)
# ---------------------------------------------------------------------------


def _minimal_wav() -> bytes:
    """Return a minimal valid 16-bit mono 16 kHz WAV file (0.1 s silence).

    Used by integration tests so they don't depend on an audio file on disk.
    """
    import struct

    sample_rate = 16000
    n_samples = sample_rate // 10  # 0.1 s
    pcm = bytes(n_samples * 2)  # 16-bit zero samples
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,  # file size - 8
        b"WAVE",
        b"fmt ",
        16,             # PCM chunk size
        1,              # PCM format
        1,              # mono
        sample_rate,
        sample_rate * 2,  # byte rate
        2,              # block align
        16,             # bits per sample
        b"data",
        data_size,
    )
    return header + pcm


@pytest.mark.integration
class TestWhisperCppIntegration:
    """Live whisper.cpp server tests.

    Requires a running whisper.cpp HTTP server on ``http://localhost:9000``.
    Start one with the VS Code task **whisper.cpp: start server**, then run::

        uv run python -m pytest monocle/tests/test_ai.py -m integration -x --tb=short -v

    The test sends a short silent WAV clip — the transcription will be empty or
    near-empty, so we just assert it completes without error and returns a
    ``str``.
    """

    @pytest.mark.asyncio
    async def test_live_transcribe_wav(self):
        from monocle.ai.transcription import WhisperCppTranscriptionProvider

        provider = WhisperCppTranscriptionProvider(base_url="http://localhost:9000")
        result = await provider.transcribe(_minimal_wav(), "audio/wav")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_live_transcribe_via_ollama_provider(self):
        """End-to-end: OllamaProvider.transcribe() → WhisperCppTranscriptionProvider."""
        from monocle.ai.ollama_provider import OllamaProvider
        from monocle.ai.transcription import WhisperCppTranscriptionProvider

        t_provider = WhisperCppTranscriptionProvider(base_url="http://localhost:9000")
        provider = OllamaProvider(transcription_provider=t_provider)
        result = await provider.transcribe(_minimal_wav(), "audio/wav")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_live_transcribe_returns_stripped_text(self):
        """Transcription result should be stripped of leading/trailing whitespace."""
        from monocle.ai.transcription import WhisperCppTranscriptionProvider

        provider = WhisperCppTranscriptionProvider(base_url="http://localhost:9000")
        result = await provider.transcribe(_minimal_wav(), "audio/wav")
        assert result == result.strip()

