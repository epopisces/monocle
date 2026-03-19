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

# ---------------------------------------------------------------------------
# Nested config sections
# ---------------------------------------------------------------------------


class AIConfig(BaseModel):
    provider: Literal["ollama", "foundry_local", "azure"] = "ollama"
    embed_model: str = "nomic-embed-text"
    embed_dimensions: int = 1536
    chat_model: str = "llama3.2"
    transcribe_model: str = "whisper"
    # Transcription back-end — pluggable at config time:
    #   "native"      providers with built-in transcription (e.g. Foundry, Azure) use their
    #                 own API. Ollama does not support "native" and requires an explicit
    #                 backend like "whisper_cpp" or "subprocess".
    #   "whisper_cpp" all providers delegate to a local whisper.cpp HTTP server.
    #   "subprocess"  all providers call the openai-whisper CLI as a subprocess.
    transcribe_backend: Literal["native", "whisper_cpp", "subprocess"] = "native"
    transcribe_url: str = "http://localhost:9000"  # whisper_cpp server URL
    ollama_base_url: str = "http://localhost:11434"
    foundry_local_base_url: str = "http://localhost:5272"

    @model_validator(mode="before")
    @classmethod
    def default_transcribe_backend_for_ollama(cls, data: object) -> object:
        """Set transcribe_backend to 'subprocess' when provider is 'ollama' and
        transcribe_backend was not explicitly supplied.

        This prevents the default config (ollama + native) from being silently
        invalid.  Users who explicitly set transcribe_backend='native' with
        provider='ollama' will get a clear error from the after-validator below.
        """
        if isinstance(data, dict):
            if data.get("provider", "ollama") == "ollama" and "transcribe_backend" not in data:
                data = {**data, "transcribe_backend": "subprocess"}
        return data

    @model_validator(mode="after")
    def validate_transcribe_backend(self) -> "AIConfig":
        """Reject native transcription when provider is Ollama.

        Ollama has no built-in audio-transcription API.  Catching this at
        config-load time gives a clear error rather than a cryptic RuntimeError
        at the first transcription call.
        """
        if self.provider == "ollama" and self.transcribe_backend == "native":
            raise ValueError(
                "ai.transcribe_backend='native' is not supported with ai.provider='ollama'. "
                "Ollama has no built-in transcription API. "
                "Set ai.transcribe_backend to 'whisper_cpp' or 'subprocess' in config.yaml."
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


class UIConfig(BaseModel):
    chat_session_history_limit: int = 10


# ---------------------------------------------------------------------------
# Root Settings
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

    _ALLOWED = {"ai", "vault", "index", "agents", "review", "server", "telemetry", "ui"}

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
