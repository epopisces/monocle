"""monocle/routers/chat.py — Chat / agent streaming SSE endpoint."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from monocle.rate_limit import limiter
from monocle.telemetry import get_meter
from monocle.agents import create_chat_agent

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OTel metrics — created lazily to avoid top-level SDK calls at import time
# ---------------------------------------------------------------------------

_meter = None
_ttft_hist = None
_duration_hist = None


def _get_metrics():
    global _meter, _ttft_hist, _duration_hist
    if _meter is None:
        _meter = get_meter("monocle.chat")
        _ttft_hist = _meter.create_histogram(
            "chat.ttft",
            unit="ms",
            description="Time from POST /api/chat to first token SSE event",
        )
        _duration_hist = _meter.create_histogram(
            "chat.total_duration",
            unit="ms",
            description="Time from POST /api/chat to done SSE event",
        )
    return _ttft_hist, _duration_hist


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatMessageRequest(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageRequest]
    session_id: str | None = None


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_agent_response(
    request: Request,
    chat_request: ChatRequest,
) -> AsyncIterator[str]:
    """Run the agent and yield SSE events.

    Event types (see Architecture Quick Reference):
      token       — text delta from the model
      tool_call   — tool was invoked
      note_created — agent created a new note
      error       — fatal or recoverable error (emitted before done)
      done        — stream terminator (always emitted); includes status field:
                    - "success" on normal completion
                    - "error" if an exception occurred (see error event for details)
    """
    from agent_framework import (
        AgentRunResponseUpdate,
        FunctionCallContent,
        FunctionResultContent,
        TextContent,
    )
    from agent_framework._tools import AIFunction  # type: ignore[attr-defined]

    ttft_hist, duration_hist = _get_metrics()
    start_ms = time.monotonic() * 1000
    first_token_sent = False
    total_tokens = 0
    done_status = "success"
    done_error_message = None

    app = request.app
    ai = getattr(app.state, "ai", None)
    vault = getattr(app.state, "vault", None)
    index = getattr(app.state, "index", None)
    settings = getattr(app.state, "settings", None)
    graph_builder = getattr(app.state, "graph_builder", None)

    if ai is None or vault is None or index is None or settings is None:
        yield _sse("error", {"message": "AI provider not available"})
        return

    try:
        agent = create_chat_agent(
            ai=ai,
            vault=vault,
            index=index,
            settings=settings,
            graph_builder=graph_builder,
        )

        # Convert request messages to agent framework format
        from agent_framework import ChatMessage

        af_messages = [
            ChatMessage(role=m.role, text=m.content)
            for m in chat_request.messages
        ]

        async for update in agent.run_stream(af_messages):
            update: AgentRunResponseUpdate
            for content in update.contents:
                if isinstance(content, TextContent) and content.text:
                    delta = content.text
                    total_tokens += len(delta.split())

                    if not first_token_sent:
                        elapsed = time.monotonic() * 1000 - start_ms
                        try:
                            ttft_hist.record(elapsed)
                        except Exception:
                            pass
                        first_token_sent = True

                    yield _sse("token", {"delta": delta})

                elif isinstance(content, FunctionCallContent):
                    tool_name = content.name or "unknown"
                    yield _sse("tool_call", {"name": tool_name, "result_count": 0})

                elif isinstance(content, FunctionResultContent):
                    # Check if a note was created by inspecting the result
                    result = content.result
                    if isinstance(result, str):
                        try:
                            parsed = json.loads(result)
                            if isinstance(parsed, dict) and parsed.get("status") == "created":
                                yield _sse(
                                    "note_created",
                                    {
                                        "file_path": parsed.get("file_path", ""),
                                        "type": parsed.get("type", "other"),
                                    },
                                )
                        except (json.JSONDecodeError, TypeError):
                            pass

        # Record total duration
        elapsed_total = time.monotonic() * 1000 - start_ms
        try:
            duration_hist.record(elapsed_total)
        except Exception:
            pass

    except Exception as exc:
        logger.exception("[AGENT] Chat stream error: %s", exc)
        done_status = "error"
        done_error_message = "An error occurred processing your request"
        yield _sse("error", {"message": done_error_message})

    finally:
        # Always emit done as the terminal event
        done_data: dict[str, Any] = {
            "status": done_status,
            "total_tokens": total_tokens,
            "session_id": chat_request.session_id,
        }
        if done_error_message is not None:
            done_data["error"] = done_error_message
        yield _sse("done", done_data)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    """Stream agent responses as Server-Sent Events.

    The stream always terminates with a 'done' event carrying a status field
    indicating success or error. If status=error, an 'error' event was also
    emitted prior to done with failure details.

    Event types: token | tool_call | note_created | error | done
    """
    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    return StreamingResponse(
        _stream_agent_response(request, body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
