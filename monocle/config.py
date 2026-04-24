"""
monocle/config.py — Settings model (Pydantic v2).

Loads config.yaml (or path from MONOCLE_CONFIG env var) then overlays
values from a .env / environment variables.  On first run, if config.yaml
is absent, it is automatically copied from config.yaml.example.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   Nested config sections
# ---------------------------------------------------------------------------


class ModelEntry(BaseModel):
    """A single model entry in the ai.models registry.

    Each entry describes one model available to the application.  The *key*
    is the short unique identifier used in ``chat_model_key`` / ``embed_model_key``
    / ``stt_key``; *name* is the actual model name forwarded to the provider
    API; *role* describes the model's intended use; *provider* says which
    backend hosts it; *base_url* optionally overrides the provider-level URL.
    """

    key: str
    name: str
    role: Literal["chat", "embed", "stt"]
    provider: Literal["ollama", "foundry_local", "azure"]
    base_url: str | None = None


def _default_models() -> list[ModelEntry]:
    return [
        ModelEntry(key="llama3.2", name="llama3.2", role="chat", provider="ollama"),
        ModelEntry(key="nomic-embed", name="nomic-embed-text", role="embed", provider="ollama"),
    ]


class AIConfig(BaseModel):
    # Active model selection keys — reference entries in the models list.
    chat_model_key: str = "llama3.2"
    embed_model_key: str = "nomic-embed"
    stt_key: str | None = None  # optional; None = fall back to transcribe_backend

    embed_dimensions: int | None = None  # None = auto-detect from first embedding
    url_reference_timeout_s: float = Field(120.0, gt=0.0, le=300.0)

    # Transcription back-end — pluggable at config time:
    #   "native"      providers with built-in transcription (Foundry, Azure) use their own API.
    #   "whisper_cpp" delegates to a local whisper.cpp HTTP server.
    #   "subprocess"  calls the openai-whisper CLI as a subprocess.
    transcribe_backend: Literal["native", "whisper_cpp", "subprocess"] = "subprocess"
    transcribe_url: str = "http://localhost:9000"  # whisper_cpp server URL

    # Provider-level connection settings (used as defaults when a model entry has no base_url).
    ollama_base_url: str = "http://localhost:11434"
    foundry_local_base_url: str = "http://localhost:5272"

    # Model registry — all models known to this installation.
    models: list[ModelEntry] = Field(default_factory=_default_models)

    # ------------------------------------------------------------------
    # Model-registry helpers
    # ------------------------------------------------------------------

    def get_model(self, key: str) -> ModelEntry:
        """Return the ``ModelEntry`` with the given *key*, or raise ``ValueError``."""
        for m in self.models:
            if m.key == key:
                return m
        raise ValueError(f"Model key {key!r} not found in ai.models")

    def get_chat_model(self) -> ModelEntry:
        """Return the active chat ``ModelEntry``."""
        return self.get_model(self.chat_model_key)

    def get_embed_model(self) -> ModelEntry:
        """Return the active embed ``ModelEntry``."""
        return self.get_model(self.embed_model_key)

    def get_stt_model(self) -> ModelEntry | None:
        """Return the active STT ``ModelEntry``, or ``None`` if not configured."""
        if self.stt_key:
            return self.get_model(self.stt_key)
        return None

    # ------------------------------------------------------------------
    # Backward-compatible computed properties
    # These let existing code (cli.py, health.py, index/chroma.py, etc.)
    # continue reading settings.ai.provider / .chat_model / .embed_model
    # without changes, while model_dump() returns the new schema.
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        """Provider of the active chat model (backward compat)."""
        return self.get_chat_model().provider

    @property
    def chat_model(self) -> str:
        """Name of the active chat model (backward compat)."""
        return self.get_chat_model().name

    @property
    def embed_model(self) -> str:
        """Name of the active embed model (backward compat)."""
        return self.get_embed_model().name

    @property
    def transcribe_model(self) -> str:
        """Name of the active STT model, falling back to 'whisper' (backward compat)."""
        stt = self.get_stt_model()
        return stt.name if stt else "whisper"

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_model_keys_exist(self) -> "AIConfig":
        """Ensure all key references resolve to entries in models, with correct roles.

        Validates:
        1. All model keys are unique (no duplicates in models list)
        2. chat_model_key references entry with role='chat'
        3. embed_model_key references entry with role='embed'
        4. stt_key (if set) references entry with role='stt'
        """
        # Check for duplicate keys
        keys = [m.key for m in self.models]
        unique_keys = set(keys)
        if len(keys) != len(unique_keys):
            duplicates = [k for k in unique_keys if keys.count(k) > 1]
            raise ValueError(
                f"ai.models contains duplicate keys: {duplicates}. "
                f"All keys must be unique."
            )

        # Build a dict for role lookup
        key_to_model = {m.key: m for m in self.models}

        # Validate chat_model_key
        if self.chat_model_key not in key_to_model:
            raise ValueError(
                f"ai.chat_model_key {self.chat_model_key!r} references a key not in ai.models. "
                f"Available keys: {sorted(unique_keys)}"
            )
        chat_model = key_to_model[self.chat_model_key]
        if chat_model.role != "chat":
            raise ValueError(
                f"ai.chat_model_key {self.chat_model_key!r} points to model with role={chat_model.role!r}, "
                f"but role='chat' is required. "
                f"Model: {chat_model.model_dump()}"
            )

        # Validate embed_model_key
        if self.embed_model_key not in key_to_model:
            raise ValueError(
                f"ai.embed_model_key {self.embed_model_key!r} references a key not in ai.models. "
                f"Available keys: {sorted(unique_keys)}"
            )
        embed_model = key_to_model[self.embed_model_key]
        if embed_model.role != "embed":
            raise ValueError(
                f"ai.embed_model_key {self.embed_model_key!r} points to model with role={embed_model.role!r}, "
                f"but role='embed' is required. "
                f"Model: {embed_model.model_dump()}"
            )

        # Validate stt_key (if set)
        if self.stt_key:
            if self.stt_key not in key_to_model:
                raise ValueError(
                    f"ai.stt_key {self.stt_key!r} references a key not in ai.models. "
                    f"Available keys: {sorted(unique_keys)}"
                )
            stt_model = key_to_model[self.stt_key]
            if stt_model.role != "stt":
                raise ValueError(
                    f"ai.stt_key {self.stt_key!r} points to model with role={stt_model.role!r}, "
                    f"but role='stt' is required. "
                    f"Model: {stt_model.model_dump()}"
                )

        return self

    @model_validator(mode="after")
    def validate_transcribe_backend(self) -> "AIConfig":
        """Validate transcribe_backend is compatible with the effective STT provider.

        Ensures that:
        1. When transcribe_backend='native', the STT provider supports native transcription
           (i.e., not Ollama)
        2. When stt_key is set to a different provider than chat_model_key, the config
           is compatible with provider construction (either transcribe_backend is not 'native',
           or stt provider has native support like Azure/Foundry)

        Rationale:
        - get_provider() only builds chat and embed providers; it ignores stt_key
        - When transcribe_backend='native', providers try to use their own transcription API
        - Ollama has no transcription API, so native transcription will fail at runtime
        - If stt_key points to a different provider (e.g., Azure), it won't be used in
          provider construction, making the config inconsistent
        """
        stt_entry = self.get_stt_model()
        chat_entry = self.get_chat_model()

        # Determine which provider will actually be used for transcription
        # (get_provider() only looks at chat/embed, not stt_key for native transcription)
        effective_transcribe_provider = (
            stt_entry.provider if stt_entry else chat_entry.provider
        )

        # Check 1: native transcription requires a provider that supports it
        if self.transcribe_backend == "native":
            if effective_transcribe_provider == "ollama":
                raise ValueError(
                    "ai.transcribe_backend='native' is not supported with Ollama. "
                    "Ollama has no built-in transcription API. "
                    "Set ai.transcribe_backend to 'whisper_cpp' or 'subprocess', "
                    "or use a provider with native transcription support (Azure/Foundry)."
                )

        # Check 2: stt_key on different provider than chat requires non-native backend
        # Rationale: get_provider() builds chat provider, not stt provider.
        # So if stt_key is on a different backend, it won't be used in native mode.
        if stt_entry and stt_entry.provider != chat_entry.provider:
            if self.transcribe_backend == "native":
                raise ValueError(
                    f"ai.transcribe_backend='native' with sst_key on a different provider "
                    f"is not supported. "
                    f"sst_key points to {stt_entry.provider!r}, "
                    f"but chat_model_key points to {chat_entry.provider!r}. "
                    f"get_provider() will construct the chat provider, not the sst provider. "
                    f"Either: "
                    f"1. Set sst_key to a model on the same provider as chat_model_key, or "
                    f"2. Set ai.transcribe_backend to 'whisper_cpp' or 'subprocess'."
                )

        return self


class VaultConfig(BaseModel):
    path: str = "./vault"
    inbox_path: str = "./vault/inbox"
    templates_path: str = "./vault/.templates"
    watch: bool = True
    debounce_ms: int = 2000


class IndexConfig(BaseModel):
    backend: Literal["chroma", "azure_search"] = "chroma"
    chroma_persist_path: str = "./data/chroma"
    collection_name: str = "notes"
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64


class WeeklySummaryAgentConfig(BaseModel):
    enabled: bool = True
    cron: str = "0 17 * * 5"
    domains: list[str] = Field(default_factory=lambda: ["work", "personal"])


class ReindexAgentConfig(BaseModel):
    enabled: bool = True
    cron: str = "0 3 * * 0"


class AgentsConfig(BaseModel):
    weekly_summary: WeeklySummaryAgentConfig = Field(default_factory=WeeklySummaryAgentConfig)
    reindex: ReindexAgentConfig = Field(default_factory=ReindexAgentConfig)


class ConfidenceWeightsConfig(BaseModel):
    template_match: float = 0.35
    metadata_coverage: float = 0.30
    tag_plausibility: float = 0.20
    entity_match: float = 0.15


class ReviewConfig(BaseModel):
    queue_threshold: float = 1.0
    auto_approve_threshold_pct: int = 0
    confidence_weights: ConfidenceWeightsConfig = Field(default_factory=ConfidenceWeightsConfig)


class IngestConfig(BaseModel):
    background_prepare_enabled: bool = True
    prepare_poll_interval_s: float = Field(5.0, ge=1.0, le=60.0)
    max_idle_prepare_jobs: int = Field(1, ge=1, le=8)
    related_notes_limit: int = Field(5, ge=1, le=20)
    source_excerpt_chars: int = Field(4000, ge=500, le=20000)


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    mcp_access_key_env: str = "MCP_ACCESS_KEY"
    frontend_dist: str = "./frontend/dist"
    separate_processes: bool = False
    dev_cors: bool = False  # set True by `monocle dev` command

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        allowed = {"127.0.0.1", "0.0.0.0", "localhost"}
        if v not in allowed:
            raise ValueError(f"server.host must be one of {allowed}, got {v!r}")
        return v


class TelemetryConfig(BaseModel):
    enabled: bool = True
    otlp_endpoint: str = "http://localhost:4317"
    otlp_transport: Literal["grpc", "http"] = "grpc"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "text"
    enable_sensitive_data: bool = True
    # Route prefixes whose spans are dropped before export.
    # Useful for suppressing noisy polling routes (e.g. /api/review/count).
    trace_filters: list[str] = Field(default_factory=lambda: ["/api/health"])


class UIConfig(BaseModel):
    chat_session_history_limit: int = 10
    # Controls which voice-input path the frontend uses.
    # "whisper"   — always use MediaRecorder + backend Whisper transcription.
    # "web_speech" — use Web Speech API (requires browser + network access to
    #                Google's speech service); falls back to MediaRecorder+Whisper
    #                automatically if SpeechRecognition is absent from window.
    voice_input_backend: Literal["whisper", "web_speech"] = "whisper"


#endregion

# ---------------------------------------------------------------------------
#region #*   Root Settings
# ---------------------------------------------------------------------------


def _find_config_file() -> Path:
    """Locate config.yaml, auto-copying from example if missing."""
    env_path = os.environ.get("MONOCLE_CONFIG")
    if env_path:
        return Path(env_path)

    candidate = Path("config.yaml")
    example = Path("config.yaml.example")

    if not candidate.exists():
        if example.exists():
            shutil.copy(example, candidate)
            logger.info(
                "config.yaml not found — copied from config.yaml.example. "
                "Edit config.yaml to customise settings."
            )
        else:
            logger.warning(
                "Neither config.yaml nor config.yaml.example found. "
                "Using built-in defaults."
            )
    return candidate


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml  # lazy import so the module is importable before yaml is installed in tests

    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _deep_merge(target: dict, source: dict) -> None:
    """Recursively merge *source* into *target*, modifying *target* in-place.

    Nested dicts are merged recursively; non-dict values are overwritten.
    None values in *source* are skipped (not merged).
    Secret keys (matching azure_* or foundry_local_*) are filtered out.
    """
    for key, value in source.items():
        if value is None:
            continue
        # Filter out secret keys
        if key.startswith("azure_") or key.startswith("foundry_local_"):
            continue
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def save_config_patch(patch: dict) -> None:
    """Deep-merge *patch* into ``config.yaml`` atomically.

    Only recognised top-level settings sections are updated.  Secret fields
    (azure_*, foundry_local_*) are never written.  ``None`` values in the
    patch are skipped.
    """
    import tempfile
    import yaml  # noqa: PLC0415

    _ALLOWED = {"ai", "vault", "index", "agents", "review", "ingest", "server", "telemetry", "ui"}

    config_path = _find_config_file()
    current = _load_yaml(config_path)

    for section, values in patch.items():
        # Filter out secret sections at the top level
        if section.startswith("azure_") or section.startswith("foundry_local_"):
            continue
        if section not in _ALLOWED:
            continue
        if not isinstance(values, dict):
            continue
        if section not in current:
            current[section] = {}
        _deep_merge(current[section], values)

    content = yaml.dump(current, default_flow_style=False, allow_unicode=True)

    dir_path = config_path.parent if isinstance(config_path, Path) else Path(config_path).parent
    fd, tmp = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, str(config_path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Settings(BaseModel):
    """Root settings object. Constructed once at startup."""

    ai: AIConfig = Field(default_factory=AIConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    index: IndexConfig = Field(default_factory=IndexConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    # Azure credentials (env-only, never in config.yaml)
    azure_openai_api_key: str | None = Field(default=None, exclude=True)
    azure_openai_endpoint: str | None = Field(default=None, exclude=True)
    azure_openai_api_version: str | None = Field(default=None, exclude=True)
    azure_openai_embed_deployment: str | None = Field(default=None, exclude=True)
    azure_openai_chat_deployment: str | None = Field(default=None, exclude=True)

    # Foundry Local credentials (env-only)
    foundry_local_base_url: str | None = Field(default=None, exclude=True)
    foundry_local_api_key: str | None = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **data):  # type: ignore[override]
        # Load YAML then overlay env vars before Pydantic validation
        from dotenv import load_dotenv

        load_dotenv(override=False)  # .env → os.environ (env vars take precedence)

        config_path = _find_config_file()
        yaml_data = _load_yaml(config_path)

        # Deep-merge yaml_data with any explicit kwargs (kwargs win)
        merged = {**yaml_data, **data}

        # Inject Azure / Foundry env vars
        merged.setdefault("azure_openai_api_key", os.environ.get("AZURE_OPENAI_API_KEY"))
        merged.setdefault("azure_openai_endpoint", os.environ.get("AZURE_OPENAI_ENDPOINT"))
        merged.setdefault("azure_openai_api_version", os.environ.get("AZURE_OPENAI_API_VERSION"))
        merged.setdefault(
            "azure_openai_embed_deployment", os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT")
        )
        merged.setdefault(
            "azure_openai_chat_deployment", os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
        )
        merged.setdefault(
            "foundry_local_base_url",
            os.environ.get("FOUNDRY_LOCAL_BASE_URL"),
        )
        merged.setdefault("foundry_local_api_key", os.environ.get("FOUNDRY_LOCAL_API_KEY"))

        super().__init__(**merged)

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "Settings":
        if self.ai.provider == "azure":
            missing = [
                k
                for k in (
                    "azure_openai_api_key",
                    "azure_openai_endpoint",
                    "azure_openai_api_version",
                )
                if not getattr(self, k)
            ]
            if missing:
                raise ValueError(
                    f"ai.provider=azure requires env vars: {', '.join(m.upper() for m in missing)}"
                )
        return self
