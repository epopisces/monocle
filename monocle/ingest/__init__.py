"""
monocle/ingest/__init__.py — IngestPipeline and DuplicateSuspected exception.

The ``IngestPipeline`` executes the 8-step ingest flow described in the
build-plan:

1. Plugin resolution
2. Content extraction  (transcription for audio)
3. Routing             (sentence-starter fast path; LLM fallback)
4. Metadata extraction (LLM; runs concurrently with step 3 when LLM is used)
5. Note construction
6. File write + immediate re-index  (body embedding retained for step 7)
7. Confidence scoring  (deterministic; reuses body embedding)
8. Frontmatter patch   (write confidence + review_status)

Failure in steps 3–5 writes a ``<name>.error.md`` sidecar to the vault inbox
and records an entry in the ``FailedIngestRegistry``.

Usage::

    pipeline = IngestPipeline(vault=vault_layer, index=index_layer, ai=provider, settings=settings)
    note, confidence = await pipeline.run(request)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable
from collections.abc import Awaitable

from monocle.ingest.confidence import compute_approval_metadata, score_confidence
from monocle.ingest.failed_registry import FailedIngestRegistry
from monocle.ingest.plugin import IngestPluginRegistry
from monocle.ingest.plugins import register_default_plugins
from monocle.models import IngestConfidence, NoteChunk

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.config import Settings
    from monocle.index.base import IndexLayer
    from monocle.models import IngestRequest, Note
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   Module-level OTel instruments (created once per process, not per instance)
# ---------------------------------------------------------------------------
_otel_instruments: dict[str, Any] | None = None


def _get_otel_instruments() -> dict[str, Any]:
    """Lazily create and cache OTel instruments for the ingest pipeline.

    Creating them per-instance triggers OTel duplicate-instrument warnings;
    caching here ensures a single set of instruments for the entire process.
    """
    global _otel_instruments  # noqa: PLW0603
    if _otel_instruments is None:
        from monocle.telemetry import get_meter

        _meter = get_meter("monocle.ingest")
        _otel_instruments = {
            "pipeline_hist": _meter.create_histogram(
                "ingest.pipeline_duration",
                unit="ms",
                description="End-to-end ingest pipeline per note",
            ),
            "step_hist": _meter.create_histogram(
                "ingest.step_duration",
                unit="ms",
                description="Per-step ingest latency",
            ),
            "notes_counter": _meter.create_counter(
                "ingest.notes_total",
                unit="notes",
                description="Notes ingested, by source and template",
            ),
            "failures_counter": _meter.create_counter(
                "ingest.failures_total",
                unit="errors",
                description="Failed ingests, by pipeline step",
            ),
        }
    return _otel_instruments


# Characters illegal in filenames on Windows (and generally unsafe)
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]')

#endregion

# ---------------------------------------------------------------------------
#region #*   Exceptions
# ---------------------------------------------------------------------------


class DuplicateSuspected(Exception):
    """Raised when a high-similarity note is found and allow_duplicate=False.

    Attributes:
        similar_note_path: Vault-relative path of the similar existing note.
        score:             Cosine similarity (0.0–1.0).
    """

    def __init__(self, similar_note_path: str, score: float) -> None:
        self.similar_note_path = similar_note_path
        self.score = score
        super().__init__(
            f"Similar note detected (similarity={score:.3f}): {similar_note_path}. "
            "Pass allow_duplicate=True to force creation."
        )


#endregion

# ---------------------------------------------------------------------------
#region #*   IngestPipeline
# ---------------------------------------------------------------------------


class IngestPipeline:
    """Execute the 8-step ingest pipeline for a single IngestRequest.

    Args:
        vault:    VaultLayer instance for note construction and file writes.
        index:    IndexLayer instance for immediate re-indexing after write.
        ai:       AIProvider for embedding, transcription, and LLM calls.
                  May be ``None`` for offline/test usage; steps 3 and 4
                  degrade gracefully (blank template + empty metadata).
        settings: Settings object for config values (review thresholds, etc.).
        registry: Plugin registry.  Defaults to the singleton populated with
                  the three built-in plugins if not supplied.
        failed_registry: Failed-ingest registry.  Created fresh if None.
    """

    def __init__(
        self,
        *,
        vault: "VaultLayer",
        index: "IndexLayer",
        ai: "AIProvider | None" = None,
        settings: "Settings",
        registry: IngestPluginRegistry | None = None,
        failed_registry: FailedIngestRegistry | None = None,
    ) -> None:
        self._vault = vault
        self._index = index
        self._ai = ai
        self._settings = settings

        # Plugin registry — ensure built-in plugins are registered
        if registry is None:
            self._registry = IngestPluginRegistry.get()
            if not self._registry.plugins:
                register_default_plugins(self._registry)
        else:
            self._registry = registry

        self._failed = failed_registry or FailedIngestRegistry()

        # RoutingAgent cached here — its __init__ loads all template YAMLs
        # from disk; instantiating on every run() call wastes repeated I/O.
        from monocle.agents.routing import RoutingAgent

        self._routing_agent = RoutingAgent(ai=self._ai)

        # OTel metrics — shared module-level instruments (no per-instance duplicates)
        _instruments = _get_otel_instruments()
        self._pipeline_hist = _instruments["pipeline_hist"]
        self._step_hist = _instruments["step_hist"]
        self._notes_counter = _instruments["notes_counter"]
        self._failures_counter = _instruments["failures_counter"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        request: "IngestRequest",
        on_step: "Callable[[int], Awaitable[None]] | None" = None,
    ) -> tuple["Note", IngestConfidence]:
        """Execute the full 8-step pipeline for *request*.

        Args:
            request:  The ``IngestRequest`` to process.
            on_step:  Optional async callback invoked with the step number
                      (1-8) immediately after each step completes.  Used by
                      the SSE streaming endpoint to emit real-time progress
                      events as work happens, not all at once upfront.

        Returns:
            ``(note, confidence)`` on success.

        Raises:
            DuplicateSuspected: When body similarity > 0.95 to an existing
                note and ``request.allow_duplicate`` is False.
            Exception:          Any unrecovered pipeline failure (steps 3–5
                                also write a ``.error.md`` sidecar and record
                                a FailedIngestRegistry entry before re-raising).
        """
        import time

        from monocle.telemetry import span, timed

        t_pipeline_start = time.perf_counter()

        async with span("ingest.pipeline", source=request.source):
            # --------------------------------------------------------
            # Step 1: Plugin resolution
            # --------------------------------------------------------
            async with span("ingest.step.1", step=1):
                t0 = time.perf_counter()
                plugin = self._registry.resolve(request)
                self._step_hist.record(
                    (time.perf_counter() - t0) * 1_000, {"step": "1"}
                )
                logger.debug("[INGEST] Step 1: resolved plugin %s", type(plugin).__name__)
                if on_step:
                    await on_step(1)

            # --------------------------------------------------------
            # Step 2: Content extraction
            # --------------------------------------------------------
            async with span("ingest.step.2", step=2):
                t0 = time.perf_counter()
                text = await plugin.extract(request, self._ai)
                self._step_hist.record(
                    (time.perf_counter() - t0) * 1_000, {"step": "2"}
                )
                logger.info(
                    "[INGEST] Step 2: extracted %d chars from %s",
                    len(text),
                    type(plugin).__name__,
                )
                if on_step:
                    await on_step(2)

            # --------------------------------------------------------
            # Steps 3 & 4: Routing + Metadata extraction (concurrent)
            # --------------------------------------------------------
            _current_step = 3
            try:
                async with span("ingest.step.3_4"):
                    t0 = time.perf_counter()
                    routing_decision, note_metadata = await self._route_and_extract(
                        text, request.template_hint
                    )
                    elapsed = (time.perf_counter() - t0) * 1_000
                    self._step_hist.record(elapsed, {"step": "3"})
                    self._step_hist.record(elapsed, {"step": "4"})
                    logger.info(
                        "[INGEST] Steps 3&4: template=%s confidence=%.2f fast_path=%s",
                        routing_decision.template,
                        routing_decision.confidence,
                        routing_decision.fast_path,
                    )
                    if on_step:
                        await on_step(3)
                        await on_step(4)

                # --------------------------------------------------------
                # Step 5: Note construction
                # --------------------------------------------------------
                _current_step = 5
                async with span("ingest.step.5", step=5):
                    t0 = time.perf_counter()
                    note = await self._construct_note(
                        request, routing_decision, note_metadata, text
                    )
                    self._step_hist.record(
                        (time.perf_counter() - t0) * 1_000, {"step": "5"}
                    )
                    logger.info(
                        "[INGEST] Step 5: constructed note %s (type=%s)",
                        note.file_path,
                        note.metadata.type,
                    )
                    if on_step:
                        await on_step(5)

            except DuplicateSuspected:
                raise
            except Exception as exc:
                await self._handle_failure(request, exc, step=_current_step, text=text)
                raise

            # --------------------------------------------------------
            # Step 6: File write + immediate re-index + duplicate check
            # --------------------------------------------------------
            async with span("ingest.step.6", step=6):
                t0 = time.perf_counter()
                body_embedding, similar_path, similar_score = await self._write_and_index(
                    note, request
                )
                self._step_hist.record(
                    (time.perf_counter() - t0) * 1_000, {"step": "6"}
                )
                logger.info("[INGEST] Step 6: note written and indexed → %s", note.file_path)
                if on_step:
                    await on_step(6)

            # --------------------------------------------------------
            # Step 7: Confidence scoring
            # --------------------------------------------------------
            async with span("ingest.step.7", step=7):
                t0 = time.perf_counter()
                confidence = score_confidence(
                    note=note,
                    routing_confidence=routing_decision.confidence,
                    body_embedding=body_embedding,
                    vault=self._vault,
                    settings=self._settings,
                )
                # Attach advisory duplicate flag
                if similar_path:
                    confidence = IngestConfidence(
                        **confidence.model_dump(exclude={"similar_note_detected", "similar_note_path"}),
                        similar_note_detected=True,
                        similar_note_path=similar_path,
                    )
                self._step_hist.record(
                    (time.perf_counter() - t0) * 1_000, {"step": "7"}
                )
                logger.info(
                    "[INGEST] Step 7: confidence=%.3f %s",
                    confidence.score,
                    confidence.rationale,
                )
                if on_step:
                    await on_step(7)

            # --------------------------------------------------------
            # Step 8: Frontmatter patch
            # --------------------------------------------------------
            async with span("ingest.step.8", step=8):
                t0 = time.perf_counter()
                approval = compute_approval_metadata(confidence.score, self._settings)
                await asyncio.to_thread(
                    self._vault.patch_frontmatter, note.file_path, approval
                )
                self._step_hist.record(
                    (time.perf_counter() - t0) * 1_000, {"step": "8"}
                )
                logger.info(
                    "[INGEST] Step 8: patched frontmatter (review_status=%s)",
                    approval.get("review_status"),
                )
                if on_step:
                    await on_step(8)

            # Re-read the note so callers get consistent frontmatter
            note = await asyncio.to_thread(self._vault.read_note, note.file_path)

            # Emit pipeline metrics
            self._pipeline_hist.record(
                (time.perf_counter() - t_pipeline_start) * 1_000,
                {"source": request.source},
            )
            self._notes_counter.add(
                1, {"source": request.source, "template": routing_decision.template}
            )

            return note, confidence

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _route_and_extract(
        self,
        text: str,
        template_hint: str | None,
    ) -> tuple[Any, Any]:  # (RoutingDecision, NoteMetadata)
        """Run routing (step 3) and metadata extraction (step 4) concurrently.

        When the routing fast-path fires (sentence starters), the routing
        coroutine returns almost immediately, so the gather still provides
        the correct concurrent semantics for the LLM-routing slow path.
        """
        if self._ai is None:
            # No AI — route only, return empty metadata
            from monocle.models import NoteMetadata

            routing = await self._routing_agent.route(text, template_hint)
            return routing, NoteMetadata()

        # Concurrent gather — both coroutines start simultaneously
        routing_decision, note_metadata = await asyncio.gather(
            self._routing_agent.route(text, template_hint),
            self._ai.extract_note_metadata(text, template_hint or ""),
        )
        return routing_decision, note_metadata

    async def _construct_note(
        self,
        request: "IngestRequest",
        routing_decision: Any,  # RoutingDecision
        note_metadata: Any,  # NoteMetadata
        text: str,
    ) -> "Note":
        """Step 5: construct Note in memory from template + extracted metadata."""
        # Build metadata dict from the NoteMetadata model, filtering None values
        # for cleaner template merging.
        # Exclude "template": the routing decision (step 3) is authoritative for
        # which template schema is used; allowing the LLM-extracted NoteMetadata
        # to carry a default "blank" here would silently overwrite the routing
        # decision inside create_from_template's fm.update() call.
        metadata_dict = note_metadata.model_dump(
            exclude={"confidence", "confidence_rationale", "review_status",
                     "approved_by", "approved_at", "approval_mode",
                     "created", "updated", "template"},
            exclude_none=True,
        )
        # Override source from the request explicitly
        metadata_dict["source"] = request.source

        note = await asyncio.to_thread(
            self._vault.create_from_template,
            routing_decision.template,
            metadata_dict,
            text,
        )
        return note

    async def _write_and_index(
        self,
        note: "Note",
        request: "IngestRequest",
    ) -> tuple[list[float], str | None, float]:
        """Step 6: write note to vault and upsert chunks to index.

        Returns:
            (body_embedding, similar_note_path, similar_score)
            where similar_note_path is non-None only if a near-duplicate is
            found (score > 0.95) within the last 7 days.
        """
        from monocle.ingest.chunker import chunk_text

        body = note.body or ""
        chunks_text = chunk_text(
            body,
            chunk_size=self._settings.index.chunk_size_tokens,
            overlap=self._settings.index.chunk_overlap_tokens,
        )

        body_embedding: list[float] = []
        similar_path: str | None = None
        similar_score: float = 0.0

        if not chunks_text or not self._ai:
            # Empty body or no AI → write without indexing
            await asyncio.to_thread(self._vault.write_note, note.file_path, note)
            return body_embedding, None, 0.0

        # Embed all chunks in one batch (efficient)
        chunk_embeddings: list[list[float]] = await self._ai.embed_batch(chunks_text)
        body_embedding = chunk_embeddings[0] if chunk_embeddings else []

        # Duplicate detection BEFORE writing (uses pre-computed body embedding)
        similar_path, similar_score = await asyncio.to_thread(
            self._detect_duplicate,
            body_embedding,
            note.file_path,
        )

        if similar_path and not request.allow_duplicate:
            raise DuplicateSuspected(similar_path, similar_score)

        # Write note to vault
        await asyncio.to_thread(self._vault.write_note, note.file_path, note)

        # Build NoteChunks with metadata and upsert
        now_iso = datetime.now(timezone.utc).isoformat()
        note_chunks: list[NoteChunk] = []
        for i, (chunk_text_str, emb) in enumerate(zip(chunks_text, chunk_embeddings)):
            note_chunks.append(
                NoteChunk(
                    chunk_id=f"{note.file_path}::{i}",
                    file_path=note.file_path,
                    chunk_index=i,
                    text=chunk_text_str,
                    embedding=emb,
                    metadata={
                        "type": note.metadata.type,
                        "domain": note.metadata.domain,
                        "source": note.metadata.source,
                        "updated_at": now_iso,
                        "created": note.metadata.created.isoformat()
                        if note.metadata.created
                        else now_iso,
                    },
                )
            )

        await asyncio.to_thread(self._index.upsert_chunks, note_chunks)
        logger.debug(
            "[INGEST] Upserted %d chunk(s) for %s", len(note_chunks), note.file_path
        )

        return body_embedding, similar_path if request.allow_duplicate else None, similar_score

    def _detect_duplicate(
        self,
        body_embedding: list[float],
        current_file_path: str,
    ) -> tuple[str | None, float]:
        """Search for a near-duplicate note in the index.

        Returns:
            (file_path, score) of the most similar note from the last 7 days,
            or (None, 0.0) if no near-duplicate is found.
        """
        if not body_embedding:
            return None, 0.0

        try:
            results = self._index.search(
                query_embedding=body_embedding,
                n_results=20,
                query_text="",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[INGEST] Duplicate search failed: %s", exc)
            return None, 0.0

        cutoff = datetime.now(timezone.utc).timestamp() - (7 * 24 * 3600)

        for chunk in results:
            if chunk.file_path == current_file_path:
                continue  # skip self
            if chunk.score < 0.95:
                continue

            # Check if the note was created within the last 7 days
            created_str = chunk.metadata.get("created") or chunk.metadata.get("updated_at", "")
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    if created_dt.timestamp() < cutoff:
                        continue  # note is older than 7 days
                except (ValueError, TypeError):
                    pass  # can't parse date → don't filter out (conservative)

            logger.info(
                "[INGEST] Near-duplicate detected: %s (similarity=%.3f)",
                chunk.file_path,
                chunk.score,
            )
            return chunk.file_path, chunk.score

        return None, 0.0

    async def _handle_failure(
        self,
        request: "IngestRequest",
        exc: Exception,
        step: int,
        text: str = "",
    ) -> None:
        """Write a .error.md sidecar and register the failure.

        The sidecar is placed in the vault inbox directory.

        Args:
            request: The ingest request that failed.
            exc:     The exception that was raised.
            step:    The pipeline step number (1–8) where the failure occurred.
            text:    The extracted text from step 2 (if failure occurred in steps 3–5).
                     Used as fallback for content_preview when request.content is None
                     (e.g., audio ingests where content_bytes are the input).
        """
        self._failures_counter.add(1, {"step": str(step)})
        try:
            from monocle.vault import VaultLayer

            # Use extracted text as fallback when request.content is None
            content_preview = (request.content or text or "")[:200]
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            # Strip characters illegal in Windows filenames and general unsafe chars
            raw_preview = content_preview[:40].replace("/", "-").replace("\\", "-")
            safe_preview = _UNSAFE_FILENAME_RE.sub("_", raw_preview).strip("._") or "ingest"
            sidecar_name = f"{ts}-{safe_preview}.error.md"
            sidecar_rel = f"inbox/{sidecar_name}"

            # Source is a validated Literal; escape the error message to prevent
            # accidental YAML frontmatter injection if the string contains '---'.
            safe_error = str(exc).replace("---", "- - -")
            sidecar_body = (
                f"# Ingest Error\n\n"
                f"**Occurred:** {datetime.now(timezone.utc).isoformat()}\n"
                f"**Step:** {step}\n"
                f"**Source:** {request.source}\n"
                f"**Error:**\n\n```\n{safe_error}\n```\n\n"
                f"## Content Preview\n\n```\n{content_preview}\n```\n"
            )

            try:
                sidecar_path = self._vault.root / sidecar_rel
                sidecar_path.parent.mkdir(parents=True, exist_ok=True)
                sidecar_path.write_text(sidecar_body, encoding="utf-8")
                logger.info("[INGEST] Error sidecar written: %s", sidecar_rel)
            except Exception as write_exc:  # noqa: BLE001
                logger.error("[INGEST] Could not write error sidecar: %s", write_exc)
                sidecar_rel = None  # type: ignore[assignment]

            self._failed.add(
                source=request.source,
                content_preview=content_preview,
                error_message=str(exc),
                sidecar_path=sidecar_rel,
                step=step,
            )

        except Exception as handle_exc:  # noqa: BLE001
            logger.error("[INGEST] _handle_failure itself failed: %s", handle_exc)
