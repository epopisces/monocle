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


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


_DEFAULT_AI_CFG: dict = {
    "chat_model_key": "llama3.2",
    "embed_model_key": "nomic-embed",
    "models": [
        {"key": "llama3.2", "name": "llama3.2", "role": "chat", "provider": "ollama"},
        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
    ],
}

# AI config where the chat model uses foundry_local (supports native transcription)
_FL_AI_NATIVE: dict = {
    "chat_model_key": "fl-chat",
    "embed_model_key": "nomic-embed",
    "models": [
        {"key": "fl-chat", "name": "phi4", "role": "chat", "provider": "foundry_local"},
        {"key": "nomic-embed", "name": "nomic-embed-text", "role": "embed", "provider": "ollama"},
    ],
    "transcribe_backend": "native",
}


def _make_settings(**overrides) -> Settings:
    """Return a minimal Settings object (no config.yaml required)."""
    defaults: dict = {
        "ai": dict(_DEFAULT_AI_CFG),
        "vault": {"path": "/tmp/vault", "watch": False},
    }
    # Deep-merge overrides so callers can pass ai sub-keys
    if "ai" in overrides:
        merged_ai = {**dict(_DEFAULT_AI_CFG), **overrides.pop("ai")}
        defaults["ai"] = merged_ai
    defaults.update(overrides)
    with patch("monocle.config._find_config_file", return_value=__import__("pathlib").Path("/nonexistent")):
        with patch("monocle.config._load_yaml", return_value=defaults):
            return Settings()


#endregion

# ---------------------------------------------------------------------------
#region #*   _parse_json_response tests
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


#endregion

# ---------------------------------------------------------------------------
#region #*   _load_extract_prompt tests
# ---------------------------------------------------------------------------


class TestLoadExtractPrompt:
    def test_returns_string(self):
        # With no files present it should still return the built-in default
        with patch("pathlib.Path.exists", return_value=False):
            prompt = _load_extract_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 10


#endregion

# ---------------------------------------------------------------------------
#region #*   OllamaProvider tests
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

    # ------------------------------------------------------------------
    # get_model_status tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_model_status_provider_reachable(self):
        """When ollama list/ps succeed, it reports provider reachable."""
        mock_client = AsyncMock()
        mock_client.list.return_value = MagicMock(
            models=[MagicMock(model="llama3.2"), MagicMock(model="nomic-embed-text")]
        )
        mock_client.ps.return_value = MagicMock(
            models=[MagicMock(model="llama3.2")]
        )
        provider = self._make_provider(mock_client)

        result = await provider.get_model_status()

        assert result.provider_reachable is True
        assert result.provider == "ollama"
        chat = next(m for m in result.models if m.role == "chat")
        embed = next(m for m in result.models if m.role == "embed")
        assert chat.available is True
        assert chat.loaded is True
        assert embed.available is True
        assert embed.loaded is False  # not in ps output

    @pytest.mark.asyncio
    async def test_get_model_status_provider_unreachable(self):
        """When ollama list() raises, it reports provider unreachable."""
        mock_client = AsyncMock()
        mock_client.list.side_effect = Exception("connection refused")
        provider = self._make_provider(mock_client)

        result = await provider.get_model_status()

        assert result.provider_reachable is False
        assert result.models == []

    @pytest.mark.asyncio
    async def test_get_model_status_model_not_available(self):
        """Model not in the local list is reported as unavailable and not loaded."""
        mock_client = AsyncMock()
        mock_client.list.return_value = MagicMock(models=[])  # nothing pulled
        mock_client.ps.return_value = MagicMock(models=[])
        provider = self._make_provider(mock_client)

        result = await provider.get_model_status()

        assert result.provider_reachable is True
        for m in result.models:
            assert m.available is False
            assert m.loaded is False

    @pytest.mark.asyncio
    async def test_get_model_status_ps_failure_is_non_fatal(self):
        """If ps() fails, available is still reported (just loaded=False for all)."""
        mock_client = AsyncMock()
        mock_client.list.return_value = MagicMock(
            models=[MagicMock(model="llama3.2"), MagicMock(model="nomic-embed-text")]
        )
        mock_client.ps.side_effect = Exception("ps not supported")
        provider = self._make_provider(mock_client)

        result = await provider.get_model_status()

        assert result.provider_reachable is True
        for m in result.models:
            assert m.available is True
            assert m.loaded is False  # ps failed → none known loaded


#endregion

# ---------------------------------------------------------------------------
#region #*   FoundryLocalProvider tests
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


#endregion

# ---------------------------------------------------------------------------
#region #*   AzureOpenAIProvider tests
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


#endregion

# ---------------------------------------------------------------------------
#region #*   get_provider factory tests
# ---------------------------------------------------------------------------


class TestGetProviderFactory:
    @staticmethod
    def _settings(provider: str, extra: dict | None = None) -> Settings:
        models = [
            {"key": "chat-model", "name": "llama3.2", "role": "chat", "provider": provider},
            {"key": "embed-model", "name": "nomic-embed-text", "role": "embed", "provider": provider},
        ]
        ai_cfg: dict = {
            "chat_model_key": "chat-model",
            "embed_model_key": "embed-model",
            "models": models,
        }
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
        # Directly mutate the ModelEntry provider to an invalid value (bypasses Pydantic)
        settings.ai.get_chat_model().provider = "nonexistent"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider(settings)


#endregion

# ---------------------------------------------------------------------------
#region #*   CompositeAIProvider tests
# ---------------------------------------------------------------------------


class TestCompositeAIProvider:
    """Tests for CompositeAIProvider deduplication of model status by role."""

    def _make_composite(
        self,
        chat_status_models: list,
        embed_status_models: list,
        chat_reachable: bool = True,
        embed_reachable: bool = True,
    ):
        """Helper to construct a CompositeAIProvider with mocked underlying providers."""
        from monocle.ai.composite import CompositeAIProvider
        from monocle.models import ProviderModelsResponse

        # Create mock providers
        chat_provider = AsyncMock()
        embed_provider = AsyncMock()

        # Set up the mock return values
        chat_provider.get_model_status = AsyncMock(
            return_value=ProviderModelsResponse(
                provider="ollama",
                provider_reachable=chat_reachable,
                models=chat_status_models,
            )
        )
        embed_provider.get_model_status = AsyncMock(
            return_value=ProviderModelsResponse(
                provider="foundry_local",
                provider_reachable=embed_reachable,
                models=embed_status_models,
            )
        )
        chat_provider._provider_name = "ollama"
        embed_provider._provider_name = "foundry_local"

        return CompositeAIProvider(chat_provider=chat_provider, embed_provider=embed_provider)

    @pytest.mark.asyncio
    async def test_deduplicates_chat_role_from_chat_provider(self):
        """The composite should return exactly one chat model (from chat_provider)."""
        from monocle.models import ModelStatus

        chat_models = [
            ModelStatus(name="llama3.2", role="chat", available=True, loaded=True),
        ]
        embed_models = [
            ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        # Should have exactly one model with role='chat'
        chat_entries = [m for m in result.models if m.role == "chat"]
        assert len(chat_entries) == 1
        assert chat_entries[0].name == "llama3.2"

    @pytest.mark.asyncio
    async def test_deduplicates_embed_role_from_embed_provider(self):
        """The composite should return exactly one embed model (from embed_provider)."""
        from monocle.models import ModelStatus

        chat_models = [
            ModelStatus(name="llama3.2", role="chat", available=True, loaded=True),
        ]
        embed_models = [
            ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        # Should have exactly one model with role='embed'
        embed_entries = [m for m in result.models if m.role == "embed"]
        assert len(embed_entries) == 1
        assert embed_entries[0].name == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_prefers_chat_provider_for_transcribe(self):
        """When both providers report transcribe, prefer chat_provider."""
        from monocle.models import ModelStatus

        # Both providers have transcribe models; chat should win
        chat_models = [
            ModelStatus(name="llama3.2", role="chat", available=True, loaded=True),
            ModelStatus(name="whisper-chat", role="transcribe", available=True, loaded=False),
        ]
        embed_models = [
            ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False),
            ModelStatus(name="whisper-embed", role="transcribe", available=True, loaded=False),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        # Should have exactly one transcribe model from chat_provider
        transcribe_entries = [m for m in result.models if m.role == "transcribe"]
        assert len(transcribe_entries) == 1
        assert transcribe_entries[0].name == "whisper-chat"

    @pytest.mark.asyncio
    async def test_falls_back_to_embed_provider_for_transcribe(self):
        """When only embed_provider has transcribe, use it."""
        from monocle.models import ModelStatus

        chat_models = [
            ModelStatus(name="llama3.2", role="chat", available=True, loaded=True),
        ]
        embed_models = [
            ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False),
            ModelStatus(name="whisper-embed", role="transcribe", available=True, loaded=False),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        # Should have exactly one transcribe model from embed_provider
        transcribe_entries = [m for m in result.models if m.role == "transcribe"]
        assert len(transcribe_entries) == 1
        assert transcribe_entries[0].name == "whisper-embed"

    @pytest.mark.asyncio
    async def test_no_transcribe_when_neither_provider_has_it(self):
        """When neither provider supports transcribe, omit it from the result."""
        from monocle.models import ModelStatus

        chat_models = [
            ModelStatus(name="llama3.2", role="chat", available=True, loaded=True),
        ]
        embed_models = [
            ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        # Should have no transcribe model
        transcribe_entries = [m for m in result.models if m.role == "transcribe"]
        assert len(transcribe_entries) == 0

    @pytest.mark.asyncio
    async def test_provider_name_concatenated(self):
        """The provider name should be concatenated as 'chat+embed'."""
        from monocle.models import ModelStatus

        chat_models = [
            ModelStatus(name="llama3.2", role="chat", available=True, loaded=True),
        ]
        embed_models = [
            ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        assert result.provider == "ollama+foundry_local"

    @pytest.mark.asyncio
    async def test_provider_reachable_or_logic(self):
        """provider_reachable should be True if either provider is reachable."""
        from monocle.models import ModelStatus

        chat_models = [ModelStatus(name="llama3.2", role="chat", available=True, loaded=True)]
        embed_models = [ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False)]

        # Case 1: both reachable
        composite = self._make_composite(chat_models, embed_models, chat_reachable=True, embed_reachable=True)
        result = await composite.get_model_status()
        assert result.provider_reachable is True

        # Case 2: only chat reachable
        composite = self._make_composite(chat_models, embed_models, chat_reachable=True, embed_reachable=False)
        result = await composite.get_model_status()
        assert result.provider_reachable is True

        # Case 3: only embed reachable
        composite = self._make_composite(chat_models, embed_models, chat_reachable=False, embed_reachable=True)
        result = await composite.get_model_status()
        assert result.provider_reachable is True

        # Case 4: neither reachable
        composite = self._make_composite(chat_models, embed_models, chat_reachable=False, embed_reachable=False)
        result = await composite.get_model_status()
        assert result.provider_reachable is False

    @pytest.mark.asyncio
    async def test_model_order_preserved_chat_embed_transcribe(self):
        """Models should be returned in a consistent order: chat, embed, transcribe."""
        from monocle.models import ModelStatus

        chat_models = [
            ModelStatus(name="phi4", role="chat", available=True, loaded=True),
            ModelStatus(name="whisper", role="transcribe", available=True, loaded=False),
        ]
        embed_models = [
            ModelStatus(name="text-embedding", role="embed", available=True, loaded=True),
        ]

        composite = self._make_composite(chat_models, embed_models)
        result = await composite.get_model_status()

        # Check order
        roles = [m.role for m in result.models]
        assert roles == ["chat", "embed", "transcribe"]

    @pytest.mark.asyncio
    async def test_multiple_calls_consistent_results(self):
        """Multiple calls to get_model_status should return consistent results."""
        from monocle.models import ModelStatus

        chat_models = [ModelStatus(name="llama3.2", role="chat", available=True, loaded=True)]
        embed_models = [ModelStatus(name="nomic-embed-text", role="embed", available=True, loaded=False)]

        composite = self._make_composite(chat_models, embed_models)

        result1 = await composite.get_model_status()
        result2 = await composite.get_model_status()

        assert len(result1.models) == len(result2.models)
        for m1, m2 in zip(result1.models, result2.models):
            assert m1.role == m2.role
            assert m1.name == m2.name


#endregion

# ---------------------------------------------------------------------------
#region #*   AIProvider ABC contract test
# ---------------------------------------------------------------------------


class TestAIProviderIsAbstract:
    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            AIProvider()  # type: ignore[abstract]


#endregion

# ---------------------------------------------------------------------------
#region #*   AIProvider.chat() with tools — regression tests for Bug #1/#2
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


class TestToolChoiceOllama:
    """OllamaProvider enforces tool_choice via schema filtering."""

    def _make_provider(self):
        from monocle.ai.ollama_provider import OllamaProvider

        mock_client = AsyncMock()
        with patch("monocle.ai.ollama_provider.ollama.AsyncClient", return_value=mock_client):
            provider = OllamaProvider(embed_model="nomic-embed-text", chat_model="llama3.2")
        provider._client = mock_client
        provider._ready_models.add("llama3.2")
        return provider, mock_client

    @pytest.mark.asyncio
    async def test_tool_choice_filters_to_single_tool(self):
        """tool_choice filters the tools list to only the named function."""
        provider, mock_client = self._make_provider()
        mock_client.chat.return_value = MagicMock(message=MagicMock(content="ok", tool_calls=None))

        all_tools = [
            {"type": "function", "function": {"name": "search_vault", "parameters": {}}},
            {"type": "function", "function": {"name": "read_note", "parameters": {}}},
        ]
        await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=all_tools,
            tool_choice={"type": "function", "function": {"name": "search_vault"}},
        )
        call_kwargs = mock_client.chat.call_args.kwargs
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["function"]["name"] == "search_vault"

    @pytest.mark.asyncio
    async def test_tool_choice_unknown_name_passes_all_tools(self):
        """When the hinted name doesn't match any tool, all tools are forwarded unfiltered."""
        provider, mock_client = self._make_provider()
        mock_client.chat.return_value = MagicMock(message=MagicMock(content="ok", tool_calls=None))

        all_tools = [
            {"type": "function", "function": {"name": "search_vault", "parameters": {}}},
        ]
        await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=all_tools,
            tool_choice={"type": "function", "function": {"name": "nonexistent_tool"}},
        )
        call_kwargs = mock_client.chat.call_args.kwargs
        # Falls back to all tools when hint doesn't match any name
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["function"]["name"] == "search_vault"

    @pytest.mark.asyncio
    async def test_no_tool_choice_passes_all_tools(self):
        """Without tool_choice, all tools are forwarded unchanged."""
        provider, mock_client = self._make_provider()
        mock_client.chat.return_value = MagicMock(message=MagicMock(content="ok", tool_calls=None))

        all_tools = [
            {"type": "function", "function": {"name": "search_vault", "parameters": {}}},
            {"type": "function", "function": {"name": "read_note", "parameters": {}}},
        ]
        await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=all_tools,
        )
        call_kwargs = mock_client.chat.call_args.kwargs
        assert len(call_kwargs["tools"]) == 2


class TestToolChoiceFoundryLocal:
    """FoundryLocalProvider forwards tool_choice to the OpenAI SDK."""

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
    async def test_tool_choice_forwarded_non_stream(self):
        """tool_choice is forwarded to chat.completions.create in non-streaming mode."""
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))]
            )
        )
        tc = {"type": "function", "function": {"name": "read_note"}}
        await provider.chat(
            [{"role": "user", "content": "read"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "read_note", "parameters": {}}}],
            tool_choice=tc,
        )
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == tc

    @pytest.mark.asyncio
    async def test_no_tool_choice_not_forwarded(self):
        """Without tool_choice, the SDK is not passed a tool_choice key."""
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))]
            )
        )
        await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "search_vault", "parameters": {}}}],
        )
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert "tool_choice" not in call_kwargs


class TestToolChoiceAzure:
    """AzureOpenAIProvider forwards tool_choice to the OpenAI SDK."""

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
    async def test_tool_choice_forwarded_non_stream(self):
        """tool_choice is forwarded to Azure chat.completions.create."""
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))]
            )
        )
        tc = {"type": "function", "function": {"name": "search_vault"}}
        await provider.chat(
            [{"role": "user", "content": "search"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "search_vault", "parameters": {}}}],
            tool_choice=tc,
        )
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == tc

    @pytest.mark.asyncio
    async def test_no_tool_choice_not_forwarded(self):
        """Without tool_choice, no tool_choice key in Azure SDK call."""
        provider = self._make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))]
            )
        )
        await provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
        )
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert "tool_choice" not in call_kwargs


#endregion

# ---------------------------------------------------------------------------
#region #*   Integration tests (skipped by default)
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


#endregion

# ---------------------------------------------------------------------------
#region #*   TranscriptionProvider tests
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

        with pytest.raises(ValidationError, match="(?i:native.*ollama|ollama.*native)"):
            _make_settings(ai={"provider": "ollama", "transcribe_backend": "native"})

    def test_ollama_default_gets_subprocess(self):
        """When provider=ollama and transcribe_backend is omitted, default is 'subprocess'."""
        settings = _make_settings(ai={"provider": "ollama"})
        assert settings.ai.transcribe_backend == "subprocess"

    def test_foundry_local_native_valid(self):
        """provider=foundry_local with transcribe_backend=native is allowed."""
        settings = _make_settings(ai=_FL_AI_NATIVE)
        assert settings.ai.transcribe_backend == "native"

    def test_ollama_whisper_cpp_valid(self):
        settings = _make_settings(ai={"provider": "ollama", "transcribe_backend": "whisper_cpp"})
        assert settings.ai.transcribe_backend == "whisper_cpp"

    def test_ollama_subprocess_valid(self):
        settings = _make_settings(ai={"provider": "ollama", "transcribe_backend": "subprocess"})
        assert settings.ai.transcribe_backend == "subprocess"

    def test_url_reference_timeout_default_and_override(self):
        default_settings = _make_settings(ai={"provider": "ollama"})
        assert default_settings.ai.url_reference_timeout_s == 120.0

        custom_settings = _make_settings(
            ai={"provider": "ollama", "url_reference_timeout_s": 90.0}
        )
        assert custom_settings.ai.url_reference_timeout_s == 90.0


class TestGetTranscriptionProvider:
    """Tests for the get_transcription_provider factory."""

    def test_native_returns_none(self):
        from monocle.ai.transcription import get_transcription_provider

        # "native" is valid with foundry_local / azure (they have a built-in endpoint).
        settings = _make_settings(ai=_FL_AI_NATIVE)
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

        settings = _make_settings(ai=_FL_AI_NATIVE)
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


#endregion

# ---------------------------------------------------------------------------
#region #*   Transcription integration tests (require live servers — skipped by default)
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

