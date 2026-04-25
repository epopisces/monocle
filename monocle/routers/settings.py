"""monocle/routers/settings.py — Settings management endpoints."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, ValidationError

from monocle.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


#endregion

# ---------------------------------------------------------------------------
#region #*   Request models
# ---------------------------------------------------------------------------


class ReviewPatch(BaseModel):
    queue_threshold: float | None = Field(None, ge=0.0, le=1.0)
    auto_approve_threshold_pct: int | None = Field(None, ge=0, le=100)


class HistoryPatch(BaseModel):
    retention_versions: int | None = Field(None, ge=1, le=500)


class ModelEntryPatch(BaseModel):
    """A model entry supplied in a PATCH request (full replacement semantics).

    Since models list is treated as full-list replacement (not merge-by-key),
    all fields except base_url must be provided; they are required to match
    the ModelEntry schema and pass AIConfig validation.
    """

    key: str
    name: str
    role: Literal["chat", "embed", "stt"]
    provider: Literal["ollama", "foundry_local", "azure"]
    base_url: str | None = None


class AIPatch(BaseModel):
    # Active model selection
    chat_model_key: str | None = None
    embed_model_key: str | None = None
    stt_key: str | None = None
    url_reference_timeout_s: float | None = Field(None, gt=0.0, le=300.0)
    # Transcription settings
    transcribe_backend: Literal["native", "whisper_cpp", "subprocess"] | None = None
    transcribe_url: str | None = None
    # Provider connection settings
    ollama_base_url: str | None = None
    # Full models-list replacement (optional; replaces entire list when provided)
    models: list[ModelEntryPatch] | None = None


class UIPatch(BaseModel):
    voice_input_backend: Literal["whisper", "web_speech"] | None = None


class TelemetryPatch(BaseModel):
    trace_filters: list[str] | None = None


class SettingsPatch(BaseModel):
    review: ReviewPatch | None = None
    history: HistoryPatch | None = None
    ai: AIPatch | None = None
    ui: UIPatch | None = None
    telemetry: TelemetryPatch | None = None


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _mask_key(key: str | None) -> str | None:
    """Return '****' + last 4 chars, or None if key is absent/empty."""
    if not key:
        return None
    return f"****{key[-4:]}"


def _settings_to_dict(settings: Any) -> dict[str, Any]:
    """Return a settings dict safe for public consumption.

    Secret / excluded fields (azure_*, foundry_local_*) are omitted by
    the model's ``exclude=True`` ``Field`` declarations and are therefore
    absent from ``model_dump()`` output automatically.
    """
    return settings.model_dump()


def _find_env_path() -> str:
    return os.environ.get("MONOCLE_ENV_FILE", ".env")


def _write_env_key(env_path: str, key: str, value: str) -> None:
    """Atomically write or update *key=value* in the .env file."""
    import tempfile

    # Strip embedded newlines to prevent line-injection into the .env file.
    value = value.replace("\n", "").replace("\r", "")

    path = Path(env_path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    lines = existing.splitlines(keepends=True)
    prefix = f"{key}="
    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}\n")

    content = "".join(new_lines)
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


#endregion

# ---------------------------------------------------------------------------
#region #*   Endpoints
# ---------------------------------------------------------------------------


@router.get("/settings")
async def get_settings(request: Request) -> dict:
    """Return current server settings.  MCP key is masked to last 4 chars."""
    settings = request.app.state.settings
    data = _settings_to_dict(settings)
    mcp_key = os.environ.get(settings.server.mcp_access_key_env, "")
    data["mcp_key_last4"] = _mask_key(mcp_key)
    return data


@router.patch("/settings")
@limiter.limit("30/minute")
async def patch_settings(request: Request, patch: SettingsPatch) -> dict:
    """Hot-patch runtime settings.  Changes are persisted to config.yaml.
    
    If AI provider changes, hot-reload is attempted BEFORE persisting.
    If hot-reload fails, the entire patch is rejected (no partial state).
    Trace filter updates are deferred until after all validations complete
    to ensure atomicity (no partial runtime state on rejection).
    """
    from monocle.config import AIConfig, HistoryConfig, ReviewConfig
    from monocle.ai import get_provider

    settings = request.app.state.settings

    config_patch: dict[str, dict] = {}
    ai_provider_changed = False
    history_retention_changed = False
    new_ai_provider = None
    pending_trace_filters: list[str] | None = None  # Deferred until after validation

    if patch.review is not None:
        review_updates = {k: v for k, v in patch.review.model_dump().items() if v is not None}
        if review_updates:
            try:
                # Reconstruct via constructor to run validators
                review_data = settings.review.model_dump()
                review_data.update(review_updates)
                new_review = ReviewConfig(**review_data)
                settings = settings.model_copy(update={"review": new_review})
                config_patch["review"] = review_updates
            except ValidationError as exc:
                from fastapi import HTTPException

                raise HTTPException(status_code=422, detail=str(exc))

    if patch.history is not None:
        history_updates = {k: v for k, v in patch.history.model_dump().items() if v is not None}
        if history_updates:
            try:
                history_data = settings.history.model_dump()
                history_data.update(history_updates)
                new_history = HistoryConfig(**history_data)
                history_retention_changed = new_history.retention_versions != settings.history.retention_versions
                settings = settings.model_copy(update={"history": new_history})
                config_patch["history"] = history_updates
            except ValidationError as exc:
                from fastapi import HTTPException

                raise HTTPException(status_code=422, detail=str(exc))

    if patch.ai is not None:
        # Use exclude_unset=True to only include fields the user explicitly provided.
        # This allows clients to set sst_key: null and actually clear it (not treat as no-op).
        # Fields not provided by the user won't be in ai_updates, so we won't overwrite them.
        ai_updates = patch.ai.model_dump(exclude_unset=True)
        if ai_updates:
            try:
                # Reconstruct via constructor to run validators (including cross-field checks)
                ai_data = settings.ai.model_dump()
                ai_data.update(ai_updates)
                new_ai = AIConfig(**ai_data)
                settings = settings.model_copy(update={"ai": new_ai})
                config_patch["ai"] = ai_updates
                # Hot-reload required when the active model selection or models list changes
                _RELOAD_KEYS = {"chat_model_key", "embed_model_key", "stt_key", "models"}
                if any(k in ai_updates for k in _RELOAD_KEYS):
                    ai_provider_changed = True
            except ValidationError as exc:
                from fastapi import HTTPException

                raise HTTPException(status_code=422, detail=str(exc))

    if patch.ui is not None:
        ui_updates = {k: v for k, v in patch.ui.model_dump().items() if v is not None}
        if ui_updates:
            from monocle.config import UIConfig

            try:
                ui_data = settings.ui.model_dump()
                ui_data.update(ui_updates)
                new_ui = UIConfig(**ui_data)
                settings = settings.model_copy(update={"ui": new_ui})
                config_patch["ui"] = ui_updates
            except ValidationError as exc:
                from fastapi import HTTPException

                raise HTTPException(status_code=422, detail=str(exc))

    if patch.telemetry is not None and patch.telemetry.trace_filters is not None:
        from monocle.config import TelemetryConfig

        try:
            telem_data = settings.telemetry.model_dump()
            telem_data["trace_filters"] = patch.telemetry.trace_filters
            new_telem = TelemetryConfig(**telem_data)
            settings = settings.model_copy(update={"telemetry": new_telem})
            config_patch["telemetry"] = {"trace_filters": patch.telemetry.trace_filters}
            # Defer the live update until after AI hot-reload validates (for atomicity)
            pending_trace_filters = patch.telemetry.trace_filters
        except ValidationError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=str(exc))

    # If AI provider is changing, attempt hot-reload BEFORE persisting.
    # This ensures all changes (disk + app state) are atomic.
    if ai_provider_changed:
        try:
            new_ai_provider = await asyncio.to_thread(get_provider, settings)
            logger.info(
                "[API] AI provider hot-reload succeeded: chat=%s embed=%s",
                settings.ai.chat_model_key,
                settings.ai.embed_model_key,
            )
        except Exception as exc:
            from fastapi import HTTPException

            logger.error("[API] AI provider hot-reload failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize new AI provider: {exc}",
            )

    # Persist to config.yaml (atomic merge-write) — only if hot-reload succeeded above
    if config_patch:
        from monocle.config import save_config_patch

        await asyncio.to_thread(save_config_patch, config_patch)

    # Update app state (now that all validations have passed)
    request.app.state.settings = settings
    if new_ai_provider is not None:
        request.app.state.ai = new_ai_provider
    vault = getattr(request.app.state, "vault", None)
    if vault is not None and history_retention_changed:
        await asyncio.to_thread(vault.set_history_retention, settings.history.retention_versions)

    # Apply trace filters AFTER all validations/hot-reload succeed (atomic guarantee)
    if pending_trace_filters is not None:
        route_filter_processor = getattr(request.app.state, "route_filter_processor", None)
        if route_filter_processor is not None:
            route_filter_processor.set_filters(pending_trace_filters)

    data = _settings_to_dict(settings)
    mcp_key = os.environ.get(settings.server.mcp_access_key_env, "")
    data["mcp_key_last4"] = _mask_key(mcp_key)
    return data


@router.post("/settings/rotate-mcp-key", status_code=200)
@limiter.limit("10/minute")
async def rotate_mcp_key(request: Request) -> dict:
    """Generate a new MCP access key and persist it to .env."""
    settings = request.app.state.settings
    env_var = settings.server.mcp_access_key_env

    new_key = secrets.token_hex(32)

    env_path = _find_env_path()
    await asyncio.to_thread(_write_env_key, env_path, env_var, new_key)

    # Expose the new key to the running process immediately
    os.environ[env_var] = new_key

    logger.info("[API] MCP access key rotated (env_var=%s)", env_var)
    return {"mcp_key_last4": _mask_key(new_key)}
