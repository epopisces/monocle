"""monocle/routers/ingest.py — Ingest endpoints with rate limiting."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from monocle.ingest import DuplicateSuspected
from monocle.models import IngestRequest, IngestResponse
from monocle.rate_limit import limiter

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

# Maximum audio payload (25 MB)
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _check_audio_size(request: IngestRequest) -> None:
    if request.audio_bytes and len(request.audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Audio payload exceeds 25 MB limit ({len(request.audio_bytes)} bytes)",
        )


@router.post("/ingest", response_model=IngestResponse, status_code=201)
@limiter.limit("30/minute")
async def ingest(req: IngestRequest, request: Request) -> IngestResponse:
    """Run the 8-step ingest pipeline and return the created note + confidence."""
    _check_audio_size(req)

    pipeline = request.app.state.ingest_pipeline

    try:
        note, confidence = await pipeline.run(req)
    except DuplicateSuspected as dup:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Duplicate note detected. Re-submit with allow_duplicate=true to force creation.",
                "similar_note_detected": True,
                "similar_note_path": dup.similar_note_path,
                "similarity_score": round(dup.score, 4),
            },
        )
    except Exception as exc:
        logger.error("[INGEST] Pipeline error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Ingest pipeline failed. See server logs for details.")

    return IngestResponse(note=note, confidence=confidence)


@router.post("/ingest/stream")
@limiter.limit("30/minute")
async def ingest_stream(req: IngestRequest, request: Request) -> StreamingResponse:
    """Streaming ingest — emits SSE progress events for each pipeline step."""
    _check_audio_size(req)

    pipeline = request.app.state.ingest_pipeline

    async def _event_stream() -> AsyncIterator[str]:
        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        t0 = time.perf_counter()
        step_names = [
            "plugin_resolution",
            "content_extraction",
            "routing",
            "metadata_extraction",
            "note_construction",
            "file_write",
            "confidence_scoring",
            "frontmatter_patch",
        ]

        # Wire per-step progress events into the pipeline via a callback.
        # The pipeline calls this after each step completes so clients
        # receive events as work progresses, not all upfront.
        completed_steps: list[int] = []

        async def _on_step_complete(step_index: int) -> None:
            """Called by the pipeline after each step finishes."""
            name = step_names[step_index - 1] if 1 <= step_index <= len(step_names) else f"step_{step_index}"
            completed_steps.append(step_index)
            # Can't yield from a callback, so we use a queue
            await _step_queue.put((step_index, name))

        _step_queue: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue()

        async def _run_pipeline() -> tuple:
            try:
                result = await pipeline.run(req, on_step=_on_step_complete)
                return result
            finally:
                await _step_queue.put(None)  # always unblock the consumer

        pipeline_task = asyncio.create_task(_run_pipeline())

        # Stream step events as they arrive from the queue
        while True:
            item = await _step_queue.get()
            if item is None:
                break
            step_i, name = item
            yield _sse("step_complete", {"step": step_i, "name": name})

        try:
            note, confidence = await pipeline_task
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            yield _sse(
                "done",
                {
                    "note_path": note.file_path,
                    "confidence": confidence.score,
                    "elapsed_ms": elapsed,
                    "similar_note_detected": confidence.similar_note_detected,
                    "similar_note_path": confidence.similar_note_path,
                },
            )
        except DuplicateSuspected as dup:
            yield _sse(
                "duplicate",
                {
                    "similar_note_path": dup.similar_note_path,
                    "similarity_score": round(dup.score, 4),
                    "message": "Duplicate detected. Re-submit with allow_duplicate=true.",
                },
            )
        except Exception as exc:
            logger.error("[INGEST] Stream pipeline error: %s", exc, exc_info=True)
            yield _sse("error", {"message": "Ingest pipeline failed. See server logs for details."})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
