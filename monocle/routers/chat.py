"""monocle/routers/chat.py — Chat / agent streaming SSE endpoint."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from monocle.rate_limit import limiter
from monocle.telemetry import get_meter, span, add_user_message_event, add_assistant_message_event
from monocle.agents import create_chat_agent

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#region #*   OTel metrics — created lazily to avoid top-level SDK calls at import time
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


#endregion

# ---------------------------------------------------------------------------
#region #*   Request / response models
# ---------------------------------------------------------------------------


class ChatMessageRequest(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageRequest]
    session_id: str | None = None
    tool_hint: str | None = None
    fetch_urls: list[str] | None = None

    def model_post_init(self, __context):
        """Validate that messages is not empty."""
        if not self.messages:
            raise ValueError("messages must not be empty")


#endregion

# ---------------------------------------------------------------------------
#region #*   SSE helpers
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _iter_stream_with_disconnect(
    request: Request,
    stream_iter: AsyncIterator[Any],
    poll_interval_s: float = 0.1,
) -> AsyncIterator[Any]:
    """Yield agent updates while polling for client disconnects."""
    pending_next: asyncio.Task[Any] | None = None
    try:
        while True:
            if pending_next is None:
                pending_next = asyncio.create_task(anext(stream_iter))

            done, _ = await asyncio.wait({pending_next}, timeout=poll_interval_s)
            if done:
                try:
                    yield pending_next.result()
                except StopAsyncIteration:
                    return
                finally:
                    pending_next = None
                continue

            if await request.is_disconnected():
                pending_next.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await pending_next
                raise asyncio.CancelledError("Client disconnected")
    finally:
        aclose = getattr(stream_iter, "aclose", None)
        if callable(aclose):
            with suppress(Exception):
                await aclose()


async def _stream_agent_response(
    request: Request,
    chat_request: ChatRequest,
) -> AsyncIterator[str]:
    """Run the agent and yield SSE events.

    Event types (see Architecture Quick Reference):
      token       — text delta from the model
      tool_call   — tool was invoked, with name and call_id
      tool_error  — tool returned an error result (stream continues)
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
    update_count = 0
    done_status = "success"
    done_error_message = None
    client_disconnected = False
    _active_tool_calls: dict[str, str] = {}  # call_id → tool_name, for enriching result events

    app = request.app
    ai = getattr(app.state, "ai", None)
    vault = getattr(app.state, "vault", None)
    index = getattr(app.state, "index", None)
    settings = getattr(app.state, "settings", None)
    graph_builder = getattr(app.state, "graph_builder", None)
    reindex_queue = getattr(app.state, "reindex_queue", None)

    if ai is None or vault is None or index is None or settings is None:
        logger.error("[CHAT] Missing provider or state: ai=%s, vault=%s, index=%s, settings=%s", ai, vault, index, settings)
        yield _sse("error", {"message": "AI provider not available"})
        return

    # -----------------------------------------------------------------------
    # Optional parallel URL pre-fetch (fetch_urls in ChatRequest)
    # Each opted-in URL is fetched and summarised in parallel before the
    # agent starts. Results are emitted as note_created events and injected
    # as context into the last user message so the agent can reference them.
    # -----------------------------------------------------------------------
    pre_fetch_context = ""
    if chat_request.fetch_urls:
        from monocle.agents.tools import VaultTools
        _MAX_PREFETCH = 5  # safety cap
        urls_to_fetch = [
            u for u in chat_request.fetch_urls[:_MAX_PREFETCH]
            if isinstance(u, str) and u.startswith(("http://", "https://"))
        ]
        if urls_to_fetch:
            vault_tools = VaultTools(
                vault=vault,
                index=index,
                ai=ai,
                reindex_queue=reindex_queue,
            )
            logger.info("[CHAT] Pre-fetching %d URL(s) in parallel", len(urls_to_fetch))
            results = await asyncio.gather(
                *[vault_tools.create_reference_from_url(url) for url in urls_to_fetch],
                return_exceptions=True,
            )
            context_lines: list[str] = []
            for url, result in zip(urls_to_fetch, results):
                if isinstance(result, Exception):
                    logger.warning("[CHAT] Pre-fetch failed for %s: %s", url, result)
                    context_lines.append(f"- {url}: failed to fetch")
                else:
                    try:
                        data = json.loads(result)  # type: ignore[arg-type]
                        yield _sse("note_created", {
                            "file_path": data.get("file_path", ""),
                            "type": "reference",
                        })
                        context_lines.append(
                            f"- {url} → saved as '{data.get('title', '')}' at {data.get('file_path', '')}"
                        )
                    except Exception:
                        context_lines.append(f"- {url}: fetched")
            if context_lines:
                pre_fetch_context = (
                    "[The following URLs have been pre-fetched and saved as reference notes:]\n"
                    + "\n".join(context_lines)
                    + "\n\n"
                )

    try:
        logger.debug("[CHAT] Creating chat agent...")
        agent = create_chat_agent(
            ai=ai,
            vault=vault,
            index=index,
            settings=settings,
            graph_builder=graph_builder,
            reindex_queue=reindex_queue,
            tool_hint=chat_request.tool_hint,
        )
        logger.debug("[CHAT] Chat agent created")

        # Convert request messages to agent framework format
        from agent_framework import ChatMessage

        af_messages = [
            ChatMessage(role=m.role, text=m.content)
            for m in chat_request.messages
        ]
        # Inject pre-fetch context into the last user message so the agent
        # knows which URLs were already summarised and where their notes live.
        if pre_fetch_context and af_messages:
            last = af_messages[-1]
            af_messages[-1] = ChatMessage(role=last.role, text=pre_fetch_context + last.text)
        logger.info("[CHAT] Starting agent stream: %d messages, session=%s", len(af_messages), chat_request.session_id)

        stream_iter = agent.run_stream(af_messages)
        logger.debug("[CHAT] run_stream() returned: %s", stream_iter)
        logger.debug("[CHAT] Entering async for loop to consume stream...")

        try:
            # asyncio.timeout(300) wraps the streaming loop with a 5-minute timeout.
            # This protects against indefinite hangs while allowing time for slow model
            # responses (some LLMs may take 2-3 minutes on complex queries).
            # Protects at the app level, independent of httpx transport timeouts.
            async with asyncio.timeout(300):
                async for update in _iter_stream_with_disconnect(request, stream_iter):
                    update_count += 1
                    update: AgentRunResponseUpdate
                    logger.debug("[CHAT] Update #%d: %s (%d contents)", update_count, type(update).__name__, len(update.contents))
                    for i, content in enumerate(update.contents):
                        logger.debug("[CHAT]   Content[%d]: %s", i, type(content).__name__)
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
                            call_id = content.call_id or ""
                            tool_name = content.name or "unknown"
                            if call_id:
                                _active_tool_calls[call_id] = tool_name
                            logger.debug("[CHAT]   → FunctionCallContent: name=%s, call_id=%s", tool_name, call_id)
                            yield _sse("tool_call", {"name": tool_name, "call_id": call_id})

                        elif isinstance(content, FunctionResultContent):
                            call_id = content.call_id or ""
                            tool_name = _active_tool_calls.get(call_id, "unknown")
                            logger.debug("[CHAT]   → FunctionResultContent: call_id=%s, tool=%s", call_id, tool_name)
                            result = content.result
                            if isinstance(result, str):
                                try:
                                    parsed = json.loads(result)
                                    if isinstance(parsed, dict):
                                        if "error" in parsed:
                                            yield _sse("tool_error", {
                                                "name": tool_name,
                                                "call_id": call_id,
                                                "error": str(parsed["error"]),
                                            })
                                        if parsed.get("status") == "created":
                                            yield _sse(
                                                "note_created",
                                                {
                                                    "file_path": parsed.get("file_path", ""),
                                                    "type": parsed.get("type", "other"),
                                                },
                                            )
                                except (json.JSONDecodeError, TypeError):
                                    pass

            logger.info("[CHAT] Stream complete: %d updates, %d tokens", update_count, total_tokens)

        except asyncio.CancelledError:
            client_disconnected = True
            logger.info("[CHAT] Client disconnected; stopping stream after %d updates", update_count)

        except asyncio.TimeoutError:
            logger.warning("[CHAT] Stream timed out after 300s (received %d updates). Closing stream.", update_count)
            done_status = "error"
            done_error_message = "Agent did not respond within 5 minutes — check system logs or try a simpler query"
            yield _sse("error", {"message": done_error_message})

        except Exception as stream_exc:
            logger.exception("[CHAT] Error during stream processing: %s", stream_exc)
            done_status = "error"
            done_error_message = "An error occurred processing your request"
            yield _sse("error", {"message": done_error_message})

    except Exception as exc:
        logger.exception("[AGENT] Chat stream error during agent creation: %s", exc)
        done_status = "error"
        done_error_message = "An error occurred processing your request"
        yield _sse("error", {"message": done_error_message})

    finally:
        elapsed_total = time.monotonic() * 1000 - start_ms
        logger.info("[CHAT] Session ending: status=%s, updates=%d, total_tokens=%d, elapsed=%.1fms", done_status, update_count, total_tokens, elapsed_total)
        try:
            duration_hist.record(elapsed_total)
        except Exception:
            pass
        if not client_disconnected:
            done_data = {"status": done_status}
            if chat_request.session_id:
                done_data["session_id"] = chat_request.session_id
            if done_error_message:
                done_data["error"] = done_error_message
            yield _sse("done", done_data)


#endregion

# ---------------------------------------------------------------------------
#region #*   Route
# ---------------------------------------------------------------------------


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    """Stream agent responses as Server-Sent Events.

    The stream always terminates with a 'done' event carrying a status field
    indicating success or error. If status=error, an 'error' event was also
    emitted prior to done with failure details.

    Event types: token | tool_call | note_created | error | done
    
    Tracing: Records user and assistant messages as span events for AI Toolkit
    Input/Output column visualization.
    """
    
    async def stream_with_tracing():
        """Wrap streaming response with OTel span for message event recording."""
        async with span("chat.stream", session_id=body.session_id or "unknown") as trace_span:
            # Record the last user message (the one that triggered this request)
            # Request includes full conversation history; new user turn is appended at the end
            user_message = None
            if body.messages and trace_span:
                # Find the last user-role message
                for msg in reversed(body.messages):
                    if msg.role == "user" and msg.content:
                        user_message = msg.content
                        break
                if user_message:
                    add_user_message_event(trace_span, user_message)
            
            # Accumulate assistant tokens for final message event
            assistant_tokens = []
            
            # Stream all events from agent
            async for event_str in _stream_agent_response(request, body):
                yield event_str
                
                # Parse token events to accumulate assistant response
                if trace_span:
                    try:
                        # SSE frames are formatted as:
                        # event: token
                        # data: {"delta": "..."}
                        # 
                        # Check if this frame is a token event
                        lines = event_str.split('\n')
                        event_type = None
                        for line in lines:
                            if line.startswith('event: '):
                                event_type = line[7:].strip()
                                break
                        
                        if event_type == 'token':
                            # Parse the data payload
                            for line in lines:
                                if line.startswith('data: '):
                                    data = json.loads(line[6:])
                                    if isinstance(data, dict) and 'delta' in data:
                                        assistant_tokens.append(data['delta'])
                                    break
                    except (json.JSONDecodeError, ValueError, IndexError):
                        pass  # Silently skip parse errors
            
            # Record accumulated assistant response as a span event
            if trace_span and assistant_tokens:
                assistant_text = "".join(assistant_tokens)
                add_assistant_message_event(trace_span, assistant_text)
    
    return StreamingResponse(
        stream_with_tracing(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


#endregion
