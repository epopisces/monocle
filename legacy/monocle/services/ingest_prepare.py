"""Idle-gated background preparation for persisted ingest sessions."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from monocle.ai.base import _parse_json_response
from monocle.models import IngestSessionDetailResponse
from monocle.models import ProposedAction
from monocle.prompts import load_prompt
from monocle.services.search import search_vault

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.config import Settings
    from monocle.ingest import IngestPipeline
    from monocle.models import NoteMetadata, RoutingDecision
    from monocle.services.activity import ActivityMonitor
    from monocle.services.ingest_sessions import (
        BackgroundPrepareJob,
        IngestSessionPrepareContext,
        IngestSessionStore,
    )
    from monocle.vault import VaultLayer
    from monocle.index.base import IndexLayer

logger = logging.getLogger(__name__)

_DEFAULT_PREPARE_PROMPT = (
    "You prepare dormant ingest sessions for later human review. "
    "Return only JSON with keys title, digest, open_questions, contradictions, proposed_actions."
)


def _trim_text(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[:limit].strip()


class IngestPreparationWorker:
    def __init__(
        self,
        *,
        store: "IngestSessionStore",
        pipeline: "IngestPipeline",
        vault: "VaultLayer",
        index: "IndexLayer",
        ai: "AIProvider | None",
        settings: "Settings",
        activity: "ActivityMonitor",
    ) -> None:
        self._store = store
        self._pipeline = pipeline
        self._vault = vault
        self._index = index
        self._ai = ai
        self._settings = settings
        self._activity = activity
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def run_once(self) -> int:
        if not self._settings.ingest.background_prepare_enabled:
            return 0
        if not self._activity.is_idle():
            logger.debug("[INGEST] Background prepare skipped: app is busy")
            return 0

        jobs = await asyncio.to_thread(
            self._store.claim_prepare_jobs,
            limit=self._settings.ingest.max_idle_prepare_jobs,
        )
        if not jobs:
            return 0

        await asyncio.gather(*(self._prepare_job(job) for job in jobs))
        return len(jobs)

    async def prepare_session_now(self, session_id: str) -> IngestSessionDetailResponse | None:
        from monocle.services.ingest_workflow import load_session_detail

        job = await asyncio.to_thread(self._store.claim_prepare_job_for_session, session_id)
        if job is None:
            detail = await load_session_detail(self._store, self._vault, session_id)
            if detail is None or detail.session.state != "preparing":
                return detail
            return await self._wait_for_preparing_session(session_id)

        await self._prepare_job(job)
        return await load_session_detail(self._store, self._vault, session_id)

    async def _wait_for_preparing_session(self, session_id: str) -> IngestSessionDetailResponse | None:
        from monocle.services.ingest_workflow import load_session_detail

        timeout_s = max(0.25, float(self._settings.ingest.prepare_poll_interval_s))
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            detail = await load_session_detail(self._store, self._vault, session_id)
            if detail is None or detail.session.state != "preparing":
                return detail
            if asyncio.get_running_loop().time() >= deadline:
                return detail
            await asyncio.sleep(0.05)

    async def _run_loop(self) -> None:
        interval = self._settings.ingest.prepare_poll_interval_s
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("[INGEST] Background prepare loop failed: %s", exc, exc_info=True)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _prepare_job(self, job: "BackgroundPrepareJob") -> None:
        context = await asyncio.to_thread(self._store.get_prepare_context, job.session_id)
        if context is None:
            await asyncio.to_thread(
                self._store.fail_prepare_job,
                job.job_id,
                job.session_id,
                "Session no longer exists.",
            )
            return

        try:
            prepared = await self._build_prepared_session(context)
            await asyncio.to_thread(
                self._store.complete_prepare_job,
                job.job_id,
                job.session_id,
                title=prepared["title"],
                digest=prepared["digest"],
                open_questions=prepared["open_questions"],
                related_notes=prepared["related_notes"],
                contradictions=prepared["contradictions"],
                proposed_actions=prepared["proposed_actions"],
                artifact_payload=prepared["artifact_payload"],
            )
            logger.info("[INGEST] Prepared dormant session %s", job.session_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("[INGEST] Failed to prepare session %s: %s", job.session_id, exc, exc_info=True)
            await asyncio.to_thread(
                self._store.fail_prepare_job,
                job.job_id,
                job.session_id,
                str(exc),
            )

    async def _build_prepared_session(self, context: "IngestSessionPrepareContext") -> dict[str, Any]:
        source_text = await self._extract_source_text(context)
        routing_decision, note_metadata = await self._pipeline.analyze_content(
            source_text,
            context.template_hint,
        )
        related_notes = await self._related_notes(source_text)
        ai_payload = await self._generate_prep_payload(
            source_text=source_text,
            routing_decision=routing_decision,
            note_metadata=note_metadata,
            related_notes=related_notes,
            context=context,
        )

        title = ai_payload.get("title") or self._default_title(note_metadata, context)
        digest = ai_payload.get("digest") or _trim_text(source_text, 280)
        open_questions = self._normalise_open_questions(ai_payload.get("open_questions"))
        contradictions = self._normalise_contradictions(ai_payload.get("contradictions"))
        proposed_actions = self._normalise_proposed_actions(
            ai_payload.get("proposed_actions"),
            routing_decision=routing_decision,
            note_metadata=note_metadata,
            context=context,
        )

        artifact_payload = {
            "title": title,
            "digest": digest,
            "open_questions": open_questions,
            "related_notes": related_notes,
            "contradictions": contradictions,
            "proposed_actions": [action.model_dump(mode="json") for action in proposed_actions],
            "routing": routing_decision.model_dump(mode="json"),
            "metadata": note_metadata.model_dump(mode="json"),
            "source_excerpt": _trim_text(source_text, self._settings.ingest.source_excerpt_chars),
        }

        return {
            "title": title,
            "digest": digest,
            "open_questions": open_questions,
            "related_notes": related_notes,
            "contradictions": contradictions,
            "proposed_actions": proposed_actions,
            "artifact_payload": artifact_payload,
        }

    async def _extract_source_text(self, context: "IngestSessionPrepareContext") -> str:
        parts: list[str] = []
        for source in context.sources:
            payload_path = self._store_path(context, source.archive_path)
            data = await asyncio.to_thread(payload_path.read_bytes)
            mime_type = source.mime_type or "application/octet-stream"
            if mime_type.startswith("audio/") or source.kind == "audio":
                if self._ai is None:
                    parts.append(f"[Audio source unavailable: {source.source_name}]")
                else:
                    transcript = await self._ai.transcribe(data, mime_type)
                    parts.append(transcript)
            else:
                parts.append(data.decode("utf-8", errors="replace"))
        return "\n\n".join(part for part in parts if part).strip()

    def _store_path(self, context: "IngestSessionPrepareContext", archive_path: str) -> Path:
        sources_root = self._store.sources_root.resolve()
        resolved = (sources_root / archive_path).resolve()
        if not resolved.is_relative_to(sources_root):
            raise ValueError(
                f"Archived source path escapes sources_root for session {context.session.session_id}: {archive_path}"
            )
        return resolved

    async def _related_notes(self, source_text: str) -> list[dict[str, Any]]:
        query = _trim_text(source_text, min(self._settings.ingest.source_excerpt_chars, 1200))
        if not query:
            return []
        try:
            matches = await search_vault(
                self._index,
                self._ai,
                query,
                n_results=self._settings.ingest.related_notes_limit,
            )
        except Exception:
            logger.warning("[INGEST] Related-note search unavailable during background prep", exc_info=True)
            return []
        related: list[dict[str, Any]] = []
        seen: set[str] = set()
        for match in matches:
            if match.file_path in seen:
                continue
            seen.add(match.file_path)
            try:
                note = await asyncio.to_thread(self._vault.read_note, match.file_path)
            except Exception:
                continue
            related.append(
                {
                    "file_path": note.file_path,
                    "title": note.title,
                    "score": round(match.score, 4),
                    "excerpt": _trim_text(note.body, 240),
                }
            )
        return related

    async def _generate_prep_payload(
        self,
        *,
        source_text: str,
        routing_decision: "RoutingDecision",
        note_metadata: "NoteMetadata",
        related_notes: list[dict[str, Any]],
        context: "IngestSessionPrepareContext",
    ) -> dict[str, Any]:
        if self._ai is None:
            return self._deterministic_payload(source_text, routing_decision, note_metadata, related_notes, context)

        system_prompt = load_prompt("ingest_prepare") or _DEFAULT_PREPARE_PROMPT
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "session_id": context.session.session_id,
                        "source_excerpt": _trim_text(source_text, self._settings.ingest.source_excerpt_chars),
                        "routing_decision": routing_decision.model_dump(mode="json"),
                        "metadata": note_metadata.model_dump(mode="json"),
                        "related_notes": related_notes,
                    },
                    ensure_ascii=True,
                ),
            },
        ]
        try:
            raw = await self._ai.chat(messages, stream=False)
            if not isinstance(raw, str):
                raw = "".join([chunk async for chunk in raw])
            return _parse_json_response(raw)
        except Exception:
            logger.warning("[INGEST] Falling back to deterministic background prep", exc_info=True)
            return self._deterministic_payload(source_text, routing_decision, note_metadata, related_notes, context)

    def _deterministic_payload(
        self,
        source_text: str,
        routing_decision: "RoutingDecision",
        note_metadata: "NoteMetadata",
        related_notes: list[dict[str, Any]],
        context: "IngestSessionPrepareContext",
    ) -> dict[str, Any]:
        default_target = related_notes[0]["file_path"] if related_notes else None
        action_type = "update_note" if default_target else "create_note"
        return {
            "title": self._default_title(note_metadata, context),
            "digest": _trim_text(source_text, 280),
            "open_questions": [],
            "contradictions": [],
            "proposed_actions": [
                {
                    "action_type": action_type,
                    "target_file_path": default_target,
                    "target_note_type": routing_decision.note_type,
                    "rationale": "Drafted automatically from the captured source for later review.",
                    "proposed_content": {
                        "title": self._default_title(note_metadata, context),
                        "body": _trim_text(source_text, 600),
                    },
                }
            ],
        }

    def _default_title(self, note_metadata: "NoteMetadata", context: "IngestSessionPrepareContext") -> str:
        title = getattr(note_metadata, "title", None) or context.session.title
        if title:
            return str(title)
        source_name = context.sources[0].source_name if context.sources else "Captured source"
        return Path(source_name).stem.replace("-", " ").strip().title() or "Captured Source"

    def _normalise_open_questions(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        questions: list[dict[str, Any]] = []
        for idx, item in enumerate(value, start=1):
            if isinstance(item, str):
                questions.append({"id": f"oq_{idx}", "question": item})
            elif isinstance(item, dict) and item.get("question"):
                questions.append({"id": item.get("id", f"oq_{idx}"), "question": str(item["question"]), "reason": item.get("reason")})
        return questions

    def _normalise_contradictions(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        contradictions: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict) and item.get("summary"):
                contradictions.append(
                    {
                        "file_path": item.get("file_path"),
                        "summary": str(item["summary"]),
                        "severity": item.get("severity", "warning"),
                    }
                )
        return contradictions

    def _normalise_proposed_actions(
        self,
        value: Any,
        *,
        routing_decision: "RoutingDecision",
        note_metadata: "NoteMetadata",
        context: "IngestSessionPrepareContext",
    ) -> list[ProposedAction]:
        actions: list[ProposedAction] = []
        if isinstance(value, list):
            for idx, item in enumerate(value, start=1):
                if not isinstance(item, dict):
                    continue
                action_type = item.get("action_type") or "create_note"
                if action_type not in {"create_note", "update_note"}:
                    continue
                proposed_content = item.get("proposed_content") if isinstance(item.get("proposed_content"), dict) else {}
                actions.append(
                    ProposedAction(
                        action_id=f"act_{context.session.session_id}_{idx}",
                        action_type=action_type,
                        approval_state="draft",
                        target_file_path=item.get("target_file_path"),
                        target_note_type=item.get("target_note_type") or routing_decision.note_type,
                        rationale=str(item.get("rationale") or "Prepared for review."),
                        proposed_content=proposed_content,
                    )
                )
        if actions:
            return actions
        fallback = self._deterministic_payload("", routing_decision, note_metadata, [], context)
        return self._normalise_proposed_actions(
            fallback.get("proposed_actions"),
            routing_decision=routing_decision,
            note_metadata=note_metadata,
            context=context,
        )