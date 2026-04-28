"""
monocle/ai/openai_provider.py — AIProvider backed by OpenAI.

Uses ``openai.AsyncOpenAI`` for embeddings, chat completions, and audio
transcription.

Configuration (from Settings / env vars):
    ``OPENAI_API_KEY`` — required API key for OpenAI-hosted models.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, AsyncIterator

from monocle.ai.base import AIProvider, _open_span
from monocle.telemetry import get_meter, span, timed

if TYPE_CHECKING:
    from monocle.ai.transcription import TranscriptionProvider
    from monocle.models import ProviderModelsResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """AIProvider backed by the public OpenAI API.

    Parameters
    ----------
    api_key:
        OpenAI API key (``OPENAI_API_KEY``).
    embed_model:
        Model name for embeddings.
    chat_model:
        Model name for chat completions.
    transcribe_model:
        Model name for audio transcription (default: ``"whisper-1"``).
    embed_dimensions:
        Requested embedding dimensions — passed where the API supports it.
    """

    _provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        embed_model: str = "text-embedding-3-large",
        chat_model: str = "gpt-4o",
        transcribe_model: str = "whisper-1",
        embed_dimensions: int | None = 1536,
        transcription_provider: "TranscriptionProvider | None" = None,
    ) -> None:
        import openai

        self._embed_model = embed_model
        self._chat_model = chat_model
        self._transcribe_model = transcribe_model
        self._embed_dimensions = embed_dimensions

        self._client = openai.AsyncOpenAI(api_key=api_key)
        if transcription_provider is None:
            from monocle.ai.transcription import NativeOpenAITranscriptionProvider

            transcription_provider = NativeOpenAITranscriptionProvider(
                self._client, model=transcribe_model
            )
        self._transcription_provider = transcription_provider

        meter = get_meter("monocle.ai")
        self._embed_hist = meter.create_histogram("ai.embed_duration", unit="ms")
        self._chat_hist = meter.create_histogram("ai.chat_duration", unit="ms")
        self._transcribe_hist = meter.create_histogram("ai.transcribe_duration", unit="ms")

    async def embed(self, text: str) -> list[float]:
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_model}
        async with span("ai.embed", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                kwargs: dict = {"model": self._embed_model, "input": text}
                if self._embed_dimensions:
                    kwargs["dimensions"] = self._embed_dimensions
                response = await self._client.embeddings.create(**kwargs)
                return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        attrs = {"ai.provider": self._provider_name, "ai.model": self._embed_model}
        async with span("ai.embed_batch", **attrs):
            async with timed(self._embed_hist, **{"provider": self._provider_name}):
                kwargs: dict = {"model": self._embed_model, "input": texts}
                if self._embed_dimensions:
                    kwargs["dimensions"] = self._embed_dimensions
                response = await self._client.embeddings.create(**kwargs)
                return [item.embedding for item in response.data]

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
    ) -> str | AsyncIterator[str]:
        attrs = {"ai.provider": self._provider_name, "ai.model": self._chat_model}
        if not stream:
            async with span("ai.chat", **attrs):
                async with timed(self._chat_hist, **{"provider": self._provider_name}):
                    kwargs: dict = {"model": self._chat_model, "messages": messages, "stream": False}
                    if tools:
                        kwargs["tools"] = tools
                    if tool_choice:
                        kwargs["tool_choice"] = tool_choice
                    response = await self._client.chat.completions.create(**kwargs)
                    message = response.choices[0].message
                    if message.tool_calls:
                        return json.dumps({
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in message.tool_calls
                            ]
                        })
                    return message.content or ""
        return self._stream_chat(messages, tools, tool_choice)

    async def _stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
    ) -> AsyncIterator[str]:  # type: ignore[override]
        with _open_span(
            "ai.chat.stream",
            provider=self._provider_name,
            model=self._chat_model,
        ):
            create_kwargs: dict = {"model": self._chat_model, "messages": messages, "stream": True}
            if tools:
                create_kwargs["tools"] = tools
            if tool_choice:
                create_kwargs["tool_choice"] = tool_choice
            stream = await self._client.chat.completions.create(**create_kwargs)
            accumulated: dict[int, dict] = {}
            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = delta.content
                if content:
                    yield content
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in accumulated:
                            accumulated[idx] = {"id": "", "name": "", "args": ""}
                        if tc_delta.id:
                            accumulated[idx]["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            accumulated[idx]["name"] += tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            accumulated[idx]["args"] += tc_delta.function.arguments
            if accumulated:
                yield json.dumps({
                    "tool_calls": [
                        {
                            "id": value["id"],
                            "type": "function",
                            "function": {"name": value["name"], "arguments": value["args"]},
                        }
                        for value in accumulated.values()
                    ]
                })

    async def get_model_status(self) -> "ProviderModelsResponse":  # type: ignore[override]
        """Query OpenAI's models endpoint for availability."""
        from monocle.models import ModelStatus, ProviderModelsResponse

        try:
            response = await self._client.models.list()
            available_ids = {model.id for model in response.data}
        except Exception as exc:
            logger.debug("[AI] OpenAI models.list() failed: %s", exc)
            return ProviderModelsResponse(
                provider=self._provider_name,
                provider_reachable=False,
                models=[],
            )

        def _status(name: str, role: str) -> ModelStatus:
            available = name in available_ids
            return ModelStatus(name=name, role=role, available=available, loaded=available)  # type: ignore[arg-type]

        models = [
            _status(self._chat_model, "chat"),
            _status(self._embed_model, "embed"),
            _status(self._transcribe_model, "transcribe"),
        ]
        return ProviderModelsResponse(
            provider=self._provider_name,
            provider_reachable=True,
            models=models,
        )