"""monocle/routers/transcribe.py — Audio transcription endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from monocle.rate_limit import limiter

router = APIRouter(tags=["transcribe"])
logger = logging.getLogger(__name__)

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


class TranscribeResponse(BaseModel):
    transcript: str
    mime_type: str


@router.post("/transcribe", response_model=TranscribeResponse)
@limiter.limit("30/minute")
async def transcribe(
    request: Request,
    file: UploadFile = File(..., description="Audio file to transcribe"),
    mime_type: str = Form("audio/webm", description="MIME type of the audio file"),
) -> TranscribeResponse:
    """Transcribe an uploaded audio file using the configured provider."""
    ai = getattr(request.app.state, "ai", None)
    if ai is None:
        raise HTTPException(status_code=503, detail="AI provider not available")

    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Audio exceeds 25 MB limit ({len(audio_bytes)} bytes)",
        )
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=422, detail="Empty audio file")

    effective_mime = file.content_type or mime_type or "audio/webm"
    logger.info(
        "[TRANSCRIBE] Transcribing %d bytes, mime=%s", len(audio_bytes), effective_mime
    )

    try:
        transcript = await ai.transcribe(audio_bytes, effective_mime)
    except Exception as exc:
        logger.error("[TRANSCRIBE] Transcription failed: %s", exc)
        raise HTTPException(status_code=502, detail="Transcription failed. See server logs for details.")

    return TranscribeResponse(transcript=transcript, mime_type=effective_mime)
