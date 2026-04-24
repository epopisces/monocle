"""monocle/mcp_server.py — Canonical MCP tool surface for Monocle vault operations.

This module is the **authoritative schema definition** for all Monocle-owned
data operations.  Every tool listed here maps 1:1 to a shared service function
in ``monocle.services.*`` with no inline business logic.  Return contracts are
frozen in ``docs/tool-contracts.md``; breaking changes require versioned
acceptance.

The server is mounted at ``/mcp`` in ``main.py`` as a Starlette sub-application.
All requests are authenticated via an ``x-monocle-key`` header or ``?key=``
query parameter before reaching the MCP handler.

Canonical tools (7):
  search_vault              — Semantic search returning scored note chunks
  read_note                 — Read a full note by vault-relative path
  capture_thought           — Ingest raw text via the full IngestPipeline
  create_note               — Create a note via VaultLayer.create_from_template
  update_note               — Overwrite an existing note body
  get_graph                 — Return ego-graph data for a focus entity
  create_reference_from_url — Fetch a web page, summarise it, and create a reference note

Auth:
  x-monocle-key request header  (preferred)
  ?key=<value> query parameter   (accepted; less secure — avoid in production)

A missing or invalid key returns HTTP 401 before the request reaches FastMCP.
If the MCP_ACCESS_KEY environment variable is not set, ALL requests are
rejected (every request returns 401) so the server is safe out-of-the-box.

See also:
  docs/tool-contracts.md — Frozen contract definitions (input/output schemas)
  monocle/services/      — Shared service implementations
  monocle/agents/tools.py — Chat-agent thin wrappers (mirrors this surface)
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from typing import TYPE_CHECKING, Annotated
from urllib.parse import parse_qs

from mcp.server.fastmcp import FastMCP
from pydantic import BeforeValidator

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.config import Settings
    from monocle.graph import GraphBuilder
    from monocle.index.base import IndexLayer
    from monocle.ingest import IngestPipeline
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   Module-level state — set once during lifespan startup via init_mcp_state()
# ---------------------------------------------------------------------------


class _MCPState:
    """Container for shared application state injected via ``init_mcp_state()``.

    Uses instance attributes so the singleton is unambiguously mutable and
    each attribute access reflects the most recently injected value.  Call
    ``assert_ready()`` in any context that requires initialisation to have
    completed — this gives a clear ``RuntimeError`` instead of a cryptic
    ``AttributeError: 'NoneType' object has no attribute ...``.
    """

    def __init__(self) -> None:
        self.vault: "VaultLayer | None" = None
        self.index: "IndexLayer | None" = None
        self.ai: "AIProvider | None" = None
        self.settings: "Settings | None" = None
        self.ingest_pipeline: "IngestPipeline | None" = None
        self.graph_builder: "GraphBuilder | None" = None
        self.reindex_queue: "ReindexQueue | None" = None
        self._initialised: bool = False

    def assert_ready(self) -> None:
        """Raise ``RuntimeError`` if ``init_mcp_state()`` has not been called."""
        if not self._initialised:
            raise RuntimeError(
                "MCP state has not been initialised — "
                "call init_mcp_state() from the FastAPI lifespan before using any MCP tools."
            )


_state = _MCPState()


def init_mcp_state(
    vault: "VaultLayer",
    index: "IndexLayer",
    ai: "AIProvider | None",
    ingest_pipeline: "IngestPipeline",
    graph_builder: "GraphBuilder",
    *,
    settings: "Settings | None" = None,
    reindex_queue: "ReindexQueue | None" = None,
) -> None:
    """Inject shared application state so MCP tool functions can access it.

    Called once from the FastAPI lifespan after all layers are initialised.
    """
    _state.vault = vault
    _state.index = index
    _state.ai = ai
    _state.settings = settings
    _state.ingest_pipeline = ingest_pipeline
    _state.graph_builder = graph_builder
    _state.reindex_queue = reindex_queue
    _state._initialised = True
    logger.info("[MCP] State initialised")


#endregion

# ---------------------------------------------------------------------------
#region #*   FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("monocle", stateless_http=True)

#endregion

# ---------------------------------------------------------------------------
#region #*   Constants
# ---------------------------------------------------------------------------

#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: normalise tags from various LLM-produced formats
# ---------------------------------------------------------------------------


# Canonical tag normaliser — shared across MCP, agent tools, and services.
from monocle.services.tags import normalize_tags as _normalize_tags  # noqa: E402


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: search_vault
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_vault(
    query: str,
    n_results: int = 5,
    note_type: str | None = None,
    domain: str | None = None,
) -> str:
    """Search the vault using semantic similarity and return matching note excerpts.

    Canonical operation — see ``docs/tool-contracts.md § search_vault``.

    Args:
        query: The search query text.
        n_results: Maximum number of results to return (1–10).
        note_type: Optional note type filter, e.g. 'person_note'.
        domain: Optional domain filter, e.g. 'work'.

    Returns:
        JSON array of objects with ``file_path``, ``similarity``, and ``chunk``.
    """
    _state.assert_ready()

    from monocle.services.search import search_vault as _search_vault

    scored = await _search_vault(
        _state.index, _state.ai, query, n_results, note_type, domain,
    )
    return json.dumps(
        [
            {
                "file_path": c.file_path,
                "similarity": round(c.score, 3),
                "chunk": c.text[:500],
            }
            for c in scored
        ]
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: read_note
# ---------------------------------------------------------------------------


@mcp.tool()
async def read_note(file_path: str) -> str:
    """Read a full note from the vault and return its metadata and body.

    Canonical operation — see ``docs/tool-contracts.md § read_note``.

    Args:
        file_path: Vault-relative path to the note, e.g. 'people/alice.md'.

    Returns:
        JSON object with ``file_path``, ``title``, ``type``, ``domain``,
        ``tags``, ``people``, and ``body``.
    """
    _state.assert_ready()

    from monocle.services.notes import read_note as _read_note

    note = await _read_note(_state.vault, file_path)
    return json.dumps(
        {
            "file_path": note.file_path,
            "title": note.title,
            "type": note.metadata.type,
            "domain": note.metadata.domain,
            "tags": note.metadata.tags,
            "people": note.metadata.people,
            "body": note.body,
        }
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: capture_thought
# ---------------------------------------------------------------------------


@mcp.tool()
async def capture_thought(content: str, source: str = "mcp") -> str:
    """Capture a raw text thought and run it through the full ingest pipeline.

    Canonical operation — see ``docs/tool-contracts.md § capture_thought``.

    The pipeline routes the content, extracts metadata, scores confidence, and
    writes a new note to the vault.  The note may land in the review queue if
    confidence is below the configured threshold.

    Args:
        content: The raw text content to ingest.
        source: Source identifier (default 'mcp').

    Returns:
        JSON object with ``file_path``, ``type``, ``confidence``, and
        ``review_status``.
    """
    _state.assert_ready()

    from monocle.services.ingest import capture_thought as _capture_thought

    note, confidence = await _capture_thought(_state.ingest_pipeline, content, source)
    return json.dumps(
        {
            "file_path": note.file_path,
            "type": note.metadata.type,
            "confidence": round(confidence.score, 3) if confidence else None,
            "review_status": note.metadata.review_status,
        }
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: create_note
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_note(
    title: str,
    body: str,
    note_type: str = "observation",
    domain: str = "personal",
    tags: Annotated[list[str] | None, BeforeValidator(_normalize_tags)] = None,
) -> str:
    """Create a new note in the vault from a template.

    Canonical operation — see ``docs/tool-contracts.md § create_note``.

    Notes created via MCP are placed in the review queue (review_status: pending).

    Args:
        title: The title of the new note.
        body: The Markdown body content.
        note_type: Note type, e.g. 'idea', 'decision', 'person_note'.
        domain: Knowledge domain, e.g. 'work' or 'personal'.
        tags: Optional list of topic tags.

    Returns:
        JSON object with ``file_path``, ``title``, and ``status``.
    """
    _state.assert_ready()

    from monocle.services.notes import create_note as _create_note

    note = await _create_note(
        _state.vault, _state.reindex_queue, title, body, note_type, domain, tags,
    )
    return json.dumps({"file_path": note.file_path, "title": note.title, "status": "created"})


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: create_reference_from_url
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_reference_from_url(
    url: str,
    extra_context: str | None = None,
) -> str:
    """Fetch a web page, summarise it with AI, and create a reference note in the vault.

    Canonical operation — see ``docs/tool-contracts.md § create_reference_from_url``.

    The tool fetches the URL, strips HTML, asks the configured AI provider to
    produce a structured Markdown summary, then creates a ``reference`` note
    tagged with ``source: web`` and placed in the review queue.

    Args:
        url: The https:// URL to fetch and summarise.
        extra_context: Optional additional context or instructions for the
                       summariser (e.g. "focus on the security implications").

    Returns:
        JSON object with ``file_path``, ``title``, ``url``, and ``status``.
    """
    _state.assert_ready()

    if _state.ai is None:
        raise RuntimeError(
            "create_reference_from_url requires an AI provider, "
            "but the server was started without one. "
            "Configure an AI provider in config.yaml."
        )

    from monocle.services.references import create_reference_from_url as _create_ref

    note = await _create_ref(
        _state.vault,
        _state.ai,
        _state.reindex_queue,
        url,
        extra_context,
        summarize_timeout_s=(
            _state.settings.ai.url_reference_timeout_s if _state.settings is not None else None
        ),
    )
    return json.dumps(
        {"file_path": note.file_path, "title": note.title, "url": url, "status": "created"}
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: update_note
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_note(file_path: str, body: str) -> str:
    """Update the body of an EXISTING note in the vault.

    Canonical operation — see ``docs/tool-contracts.md § update_note``.

    Raises an error if the note does not exist. Use create_note to make new notes.

    Args:
        file_path: Vault-relative path to the EXISTING note to update.
        body: New Markdown body content. The existing frontmatter is preserved.

    Returns:
        JSON object with ``file_path`` and ``status``.
    """
    _state.assert_ready()

    from monocle.services.notes import update_note as _update_note

    await _update_note(_state.vault, _state.reindex_queue, file_path, body)
    return json.dumps({"file_path": file_path, "status": "updated"})


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: get_graph
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_graph(
    focus: str | None = None,
    max_degree: int = 2,
) -> str:
    """Return the knowledge graph centred on a focus entity.

    Canonical operation — see ``docs/tool-contracts.md § get_graph``.

    Args:
        focus: Vault-relative path of the focus note (e.g. 'people/alice.md').
               If omitted, returns the full-vault graph.
        max_degree: BFS depth from the focus node (default 2).

    Returns:
        JSON object with ``focus``, ``nodes``, and ``edges`` arrays.
    """
    _state.assert_ready()

    from monocle.services.graph import get_graph as _get_graph

    graph_data = await _get_graph(_state.graph_builder, focus, max_degree)
    return graph_data.model_dump_json()


#endregion

# ---------------------------------------------------------------------------
#region #*   Auth middleware — wraps the MCP Starlette app
# ---------------------------------------------------------------------------


class _MCPAuthMiddleware:
    """ASGI middleware that validates the MCP access key before forwarding
    requests to the FastMCP handler.

    Accepts the key from:
      - ``x-monocle-key`` request header (preferred)
      - ``?key=<value>`` query parameter (logged by servers; less secure)

    Returns HTTP 401 if the key is missing or does not match.
    """

    _UNAUTHORIZED_BODY = b'{"detail":"Unauthorized"}'

    def __init__(self, app: "ASGIApp", key: str) -> None:
        self._app = app
        self._key = key

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] == "http":
            # Extract key from headers
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            provided = headers.get(b"x-monocle-key", b"").decode()

            # Fall back to query parameter — less secure; query strings appear
            # in server access logs and OTel span attributes.
            if not provided:
                qs = scope.get("query_string", b"").decode()
                params = parse_qs(qs)
                provided = params.get("key", [""])[0]
                if provided:
                    logger.warning(
                        "[MCP] API key passed via ?key= query parameter; "
                        "use the x-monocle-key header instead "
                        "(query parameters are visible in server logs and OTel spans)"
                    )

            # Constant-time comparison prevents timing-based key enumeration.
            if not provided or not hmac.compare_digest(provided, self._key):
                await self._reject(scope, receive, send)
                return

        await self._app(scope, receive, send)

    async def _reject(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(self._UNAUTHORIZED_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": self._UNAUTHORIZED_BODY})


#endregion

# ---------------------------------------------------------------------------
#region #*   Factory — returns the auth-wrapped ASGI app for mounting at /mcp
# ---------------------------------------------------------------------------


def create_mcp_app(mcp_key: str) -> "_MCPAuthMiddleware | object":
    """Return the auth-wrapped FastMCP ASGI app.

    Args:
        mcp_key: The expected value of the x-monocle-key header / ?key= param.
                 Pass an empty string to reject every request (key not configured).

    Returns:
        An ASGI app that enforces key auth before delegating to FastMCP.
    """
    starlette_app = mcp.streamable_http_app()
    return _MCPAuthMiddleware(starlette_app, mcp_key)
