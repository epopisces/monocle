"""
monocle/ai/base.py — AIProvider abstract base class.

All concrete providers (Ollama, FoundryLocal, AzureOpenAI) inherit from
AIProvider and implement its abstract methods.  The non-abstract helper
``extract_note_metadata`` is implemented once here using ``self.chat()``.

Usage::

    from monocle.ai import get_provider
    provider = get_provider(settings)
    embedding = await provider.embed("some text")
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from monocle.models import NoteMetadata, ProviderModelsResponse

logger = logging.getLogger(__name__)


#endregion

# ---------------------------------------------------------------------------
#region #*   Synchronous span helper (safe inside async generator functions)
# ---------------------------------------------------------------------------


def _open_span(name: str, provider: str = "", model: str = ""):
    """Return a synchronous OTel span context manager.

    This avoids attaching the span as the current context, which is important
    for async generator functions that yield across task/context boundaries.
    Falls back to :class:`contextlib.nullcontext` when OTel is unavailable.
    """
    from contextlib import nullcontext

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("monocle")
        span = tracer.start_span(name)
        return _AttrSpanContext(span, provider=provider, model=model)
    except Exception:  # noqa: BLE001
        return nullcontext()


class _AttrSpanContext:
    """Thin wrapper that sets attributes and ends spans without context attach."""

    def __init__(self, span, provider: str, model: str) -> None:
        self._span = span
        self._provider = provider
        self._model = model

    def __enter__(self):
        try:
            if self._provider:
                self._span.set_attribute("ai.provider", self._provider)
            if self._model:
                self._span.set_attribute("ai.model", self._model)
        except Exception:  # noqa: BLE001
            pass
        return self._span

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            try:
                from opentelemetry import trace

                self._span.record_exception(exc)
                self._span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            except Exception:  # noqa: BLE001
                pass
        try:
            self._span.end()
        except Exception:  # noqa: BLE001
            pass
        return False


#endregion

# ---------------------------------------------------------------------------
#region #*   Default extract prompt fallback (used when prompts/extract.md is missing)
# ---------------------------------------------------------------------------

_DEFAULT_EXTRACT_PROMPT = """\
You are a knowledge assistant. Extract structured metadata from the following note text.
Return a JSON object with these fields (all optional unless stated):
- "title": string (required) - a short descriptive title
- "type": one of: person_note, decision, idea, observation, reference, meeting_note, project, action_item, weekly_summary, other
- "domain": string (e.g. work, personal, technology, theology, entertainment)
- "people": array of person names mentioned
- "tags": array of relevant topic tags (short, lowercase, hyphenated)
- "action_items": array of follow-up tasks as short strings
- "org": string (organisation/company if relevant, else omit)

Return ONLY valid JSON. Do not include explanation or markdown fencing.
"""


def _load_extract_prompt() -> str:
    """Load prompts/extract.md, strip YAML frontmatter, return body text."""
    # Try local override first
    for candidate in (Path("prompts/local/extract.md"), Path("prompts/extract.md")):
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    content = content[end + 3 :].strip()
            return content
    return _DEFAULT_EXTRACT_PROMPT


def _parse_json_response(raw: str) -> dict:
    """Extract a JSON object from an LLM response that may include markdown fencing."""
    # Strip markdown code fences
    stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    stripped = re.sub(r"```\s*$", "", stripped, flags=re.MULTILINE).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Try to find the first {...} block
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


#endregion

# ---------------------------------------------------------------------------
#region #*   AIProvider ABC
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """Abstract interface for all AI back-ends used by Monocle.

    Every concrete provider must implement the four abstract methods.
    ``extract_note_metadata`` is implemented here for free using ``chat()``.
    """

    # Subclasses set these for OTel attribute values
    _provider_name: str = "unknown"

    # Cache for auto-detected embedding dimensions (determined on first embed call)
    _cached_embed_dimensions: int | None = None

    # ------------------------------------------------------------------
    # Abstract methods — must be implemented by each provider
    # ------------------------------------------------------------------

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for *text*."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per item in *texts* (preserves order).

        Must return an empty list when *texts* is empty.
        """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
    ) -> str | AsyncIterator[str]:
        """Send *messages* to the chat model.

        When *stream* is ``False`` (default), returns the full completion
        string.  When *stream* is ``True``, returns an ``AsyncIterator``
        that yields text delta strings as they arrive.  If *tools* is
        provided the provider forwards them to the underlying API; when the
        model makes a tool call in non-streaming mode the response is a
        JSON string ``{"tool_calls": [...]}``; in streaming mode the
        provider accumulates streaming tool-call deltas and emits the same
        JSON string as a single final chunk so the adapter can detect it.
        """

    async def get_model_status(self) -> "ProviderModelsResponse":
        """Return the availability and load state of all configured model roles.

        The default implementation returns provider-unreachable with an empty
        model list.  Subclasses override this to query provider-specific APIs.
        """
        from monocle.models import ProviderModelsResponse

        return ProviderModelsResponse(
            provider=self._provider_name,
            provider_reachable=False,
            models=[],
        )

    async def detect_embed_dimensions(self) -> int:
        """Auto-detect embedding dimensions by performing a test embedding.

        Caches the result so subsequent calls are instantaneous.
        """
        if self._cached_embed_dimensions is None:
            test_embedding = await self.embed("test")
            self._cached_embed_dimensions = len(test_embedding)
            logger.info(
                "[AI] Auto-detected embed_dimensions=%d for provider=%s",
                self._cached_embed_dimensions,
                self._provider_name,
            )
        return self._cached_embed_dimensions

    # Each provider sets this in __init__ to its configured TranscriptionProvider.
    # Providers with a native transcription API (Foundry, Azure) default to that;
    # providers without one (Ollama) require an explicit TranscriptionProvider.
    _transcription_provider: object = None  # TranscriptionProvider | None

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        """Transcribe raw audio bytes to plain text.

        Delegates to ``self._transcription_provider``.  Providers that have a
        native transcription API set a ``NativeOpenAITranscriptionProvider`` as
        the default; providers without one (Ollama) require an explicit
        ``TranscriptionProvider`` configured via ``ai.transcribe_backend``.

        *mime_type* hints the format (e.g. ``"audio/webm"``, ``"audio/wav"``).

        Raises ``RuntimeError`` if no transcription provider is configured.
        """
        if self._transcription_provider is None:
            raise RuntimeError(
                "No transcription provider configured.  "
                "Set ai.transcribe_backend to 'whisper_cpp' or 'subprocess' in config.yaml, "
                "or start a whisper.cpp server and set ai.transcribe_url."
            )
        from monocle.telemetry import span, timed

        attrs = {"ai.provider": self._provider_name}
        async with span("ai.transcribe", **attrs):
            async with timed(self._transcribe_hist, **{"provider": self._provider_name}):
                return await self._transcription_provider.transcribe(audio_bytes, mime_type)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Concrete helper (shared across all providers)
    # ------------------------------------------------------------------

    async def extract_note_metadata(self, text: str, template: str) -> "NoteMetadata":
        """Extract structured note metadata from *text* using the chat model.

        Loads ``prompts/extract.md`` (or a built-in default) as a system
        prompt, calls ``self.chat()``, and parses the JSON response into a
        ``NoteMetadata`` instance.  The caller (ingest pipeline step 4) runs
        this concurrently with routing via ``asyncio.gather``.
        """
        from monocle.models import NoteMetadata

        system_prompt = _load_extract_prompt()
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Template hint: {template}\n\n"
                    f"Note text:\n{text}"
                ),
            },
        ]

        try:
            raw = await self.chat(messages, stream=False)
            if not isinstance(raw, str):
                # Shouldn't happen for stream=False — consume iterator as fallback
                raw = "".join([chunk async for chunk in raw])  # type: ignore[arg-type]

            data = _parse_json_response(raw)
            # Remove fields that are system-managed (not from the LLM)
            for field in ("confidence", "confidence_rationale", "review_status",
                          "approved_by", "approved_at", "approval_mode",
                          "created", "updated"):
                data.pop(field, None)
            return NoteMetadata(**data)

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[AI] extract_note_metadata failed for template=%s: %s — returning defaults",
                template,
                exc,
            )
            return NoteMetadata()
