"""
monocle/ai/transcription.py — Pluggable transcription provider abstraction.

The ``TranscriptionProvider`` ABC decouples audio-to-text conversion from the
main ``AIProvider`` chat/embed interface.  This lets you mix providers freely:
e.g. use Ollama for chat/embeddings and a local whisper.cpp server for audio.

Implementations
---------------
WhisperCppTranscriptionProvider
    Calls a locally running whisper.cpp HTTP server via ``POST /inference``.
    Default target: ``http://localhost:9000``.
    Start the server with::

        ./server --model ggml-base.en.bin --host 0.0.0.0 --port 9000

    Swap to a cloud endpoint or faster-whisper HTTP server by changing
    ``ai.transcribe_url`` in ``config.yaml`` — no code change required.

SubprocessTranscriptionProvider
    Fallback: runs the ``openai-whisper`` CLI as a subprocess.  Useful for
    development when no HTTP server is running.  Slower than the HTTP path.
    Requires ``uv add openai-whisper``.

NativeOpenAITranscriptionProvider
    Internal adapter that wraps an ``openai.AsyncOpenAI`` or
    ``openai.AsyncAzureOpenAI`` client.  Used by ``FoundryLocalProvider`` and
    ``AzureOpenAIProvider`` so they share the same swappable interface.

Factory
-------
``get_transcription_provider(settings)`` selects and constructs the right
implementation based on ``settings.ai.transcribe_backend``.

Custom providers
----------------
Subclass ``TranscriptionProvider`` and register it before calling
``get_provider(settings)``::

    class MyWhisperProvider(TranscriptionProvider):
        async def transcribe(self, audio_bytes, mime_type):
            ...

Then wire it in manually::

    provider = OllamaProvider(..., transcription_provider=MyWhisperProvider())
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extension-to-filename map for audio MIME types
# ---------------------------------------------------------------------------
_EXT_MAP: dict[str, str] = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
}

_FILENAME_MAP: dict[str, str] = {
    "audio/webm": "audio.webm",
    "audio/mp4": "audio.mp4",
    "audio/mpeg": "audio.mp3",
    "audio/wav": "audio.wav",
    "audio/ogg": "audio.ogg",
    "audio/flac": "audio.flac",
}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class TranscriptionProvider(ABC):
    """Abstract interface for audio-to-text transcription.

    A single method: receive raw audio bytes and a MIME type hint; return
    the transcript as a plain string.
    """

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        """Convert *audio_bytes* to a text transcript.

        Parameters
        ----------
        audio_bytes:
            Raw audio content (e.g. from a multipart upload).
        mime_type:
            MIME type hint (e.g. ``"audio/webm"``, ``"audio/wav"``).

        Returns
        -------
        str
            Transcribed text; empty string if no speech detected.
        """


# ---------------------------------------------------------------------------
# whisper.cpp HTTP server (primary default)
# ---------------------------------------------------------------------------


class WhisperCppTranscriptionProvider(TranscriptionProvider):
    """Transcription via a locally running whisper.cpp HTTP server.

    The server exposes a single endpoint::

        POST <base_url>/inference
        Content-Type: multipart/form-data
        Fields: file (required), response_format=json, language (optional)

    Response JSON::

        {"text": "transcribed text", "segments": [...]}

    Start the server::

        ./server --model ggml-base.en.bin --host 0.0.0.0 --port 9000

    Parameters
    ----------
    base_url:
        Base URL of the whisper.cpp server (default ``http://localhost:9000``).
        Change ``ai.transcribe_url`` in ``config.yaml`` to point at any
        OpenAI-Whisper-compatible HTTP endpoint (faster-whisper, a cloud proxy,
        etc.) without modifying code.
    model:
        Optional model name forwarded in the request (server may ignore it).
    language:
        Optional BCP-47 language code (e.g. ``"en"``).  ``None`` = auto-detect.
    timeout:
        HTTP timeout in seconds (default 300 — long audio may take a while).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9000",
        model: str | None = None,
        language: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._language = language
        self._timeout = timeout

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        import httpx

        filename = _FILENAME_MAP.get(mime_type, "audio.webm")

        files: dict = {"file": (filename, audio_bytes, mime_type)}
        data: dict = {"response_format": "json"}
        if self._language:
            data["language"] = self._language
        if self._model:
            data["model"] = self._model

        url = f"{self._base_url}/inference"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, files=files, data=data)
                response.raise_for_status()
                payload = response.json()
                return payload.get("text", "").strip()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Could not connect to whisper.cpp server at {url}.  "
                "Start it with: ./server --model ggml-base.en.bin --port 9000"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"whisper.cpp server returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc


# ---------------------------------------------------------------------------
# openai-whisper subprocess (fallback / dev mode)
# ---------------------------------------------------------------------------


class SubprocessTranscriptionProvider(TranscriptionProvider):
    """Transcription via the ``openai-whisper`` CLI subprocess.

    Use as a fallback when no HTTP server is available.  Slower than the HTTP
    path but requires no separate server process.

    Requires ``uv add openai-whisper`` (downloads ~150 MB–1.5 GB model on
    first use depending on model size).
    """

    def __init__(self, model: str = "base") -> None:
        self._model = model

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        ext = _EXT_MAP.get(mime_type, ".webm")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _run_whisper_subprocess, audio_bytes, ext, self._model
        )


def _run_whisper_subprocess(audio_bytes: bytes, ext: str, model: str) -> str:
    """Blocking helper — runs openai-whisper CLI and returns the transcript."""
    import shutil
    import subprocess

    if shutil.which("whisper") is None:
        raise RuntimeError(
            "openai-whisper CLI not found on PATH.  "
            "Install it with: uv add openai-whisper"
        )

    tmp_dir = tempfile.mkdtemp(prefix="monocle_whisper_")
    tmp_audio = os.path.join(tmp_dir, f"audio{ext}")
    try:
        with open(tmp_audio, "wb") as fh:
            fh.write(audio_bytes)

        result = subprocess.run(
            [
                "whisper",
                tmp_audio,
                "--model",
                model,
                "--output_format",
                "txt",
                "--fp16",
                "False",
                "--output_dir",
                tmp_dir,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"whisper subprocess failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        txt_path = os.path.join(tmp_dir, "audio.txt")
        if os.path.exists(txt_path):
            with open(txt_path, encoding="utf-8") as fh:
                return fh.read().strip()

        return result.stdout.strip()
    finally:
        import shutil as _sh

        _sh.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Native OpenAI-compatible adapter (used by FoundryLocal + Azure providers)
# ---------------------------------------------------------------------------


class NativeOpenAITranscriptionProvider(TranscriptionProvider):
    """Transcription via an OpenAI-compatible ``/audio/transcriptions`` endpoint.

    Used internally by ``FoundryLocalProvider`` and ``AzureOpenAIProvider``
    so that their native transcription capability is also a swappable plugin.
    External callers can replace it with any other ``TranscriptionProvider``.

    Parameters
    ----------
    client:
        An ``openai.AsyncOpenAI`` or ``openai.AsyncAzureOpenAI`` instance.
    model:
        Model/deployment name for transcription (e.g. ``"whisper-1"``).
    """

    def __init__(self, client, model: str = "whisper-1") -> None:
        self._client = client
        self._model = model

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        import io

        filename = _FILENAME_MAP.get(mime_type, "audio.webm")
        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=(filename, io.BytesIO(audio_bytes), mime_type),
        )
        return response.text


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_transcription_provider(settings: "Settings") -> "TranscriptionProvider | None":
    """Construct the configured ``TranscriptionProvider``.

    Selection is governed by ``settings.ai.transcribe_backend``:

    * ``"native"``       → ``None``  (Foundry/Azure use their built-in endpoint;
                           Ollama raises at transcription time unless another
                           backend is configured)
    * ``"whisper_cpp"``  → ``WhisperCppTranscriptionProvider``
    * ``"subprocess"``   → ``SubprocessTranscriptionProvider``
    """
    backend = settings.ai.transcribe_backend
    logger.info("[AI] Transcription backend: %s", backend)

    if backend == "native":
        return None

    if backend == "whisper_cpp":
        return WhisperCppTranscriptionProvider(
            base_url=settings.ai.transcribe_url,
        )

    if backend == "subprocess":
        return SubprocessTranscriptionProvider()

    raise ValueError(
        f"Unknown ai.transcribe_backend: {backend!r}. "
        "Expected one of: native, whisper_cpp, subprocess."
    )
