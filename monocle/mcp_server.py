"""
monocle/mcp_server.py — FastMCP server with 8 vault tools.

The server is mounted at /mcp in main.py as a Starlette sub-application.
All requests are authenticated via an x-monocle-key header or ?key= query
parameter before reaching the MCP handler.

Tools exposed:
  search_vault    — Semantic search returning scored note chunks
  read_note       — Read a full note by vault-relative path
  browse_recent   — List recently-updated notes
  capture_thought — Ingest a raw text via the full IngestPipeline
  create_note     — Create a note via VaultLayer.create_from_template
  update_note     — Overwrite an existing note body
  get_graph       — Return ego-graph data for a focus entity
  get_stats       — Return vault statistics summary

Auth:
  x-monocle-key request header  (preferred)
  ?key=<value> query parameter   (accepted; less secure — avoid in production)

A missing or invalid key returns HTTP 401 before the request reaches FastMCP.
If the MCP_ACCESS_KEY environment variable is not set, ALL requests are
rejected (every request returns 401) so the server is safe out-of-the-box.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import parse_qs

from mcp.server.fastmcp import FastMCP
from pydantic import BeforeValidator

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
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
    reindex_queue: "ReindexQueue | None" = None,
) -> None:
    """Inject shared application state so MCP tool functions can access it.

    Called once from the FastAPI lifespan after all layers are initialised.
    """
    _state.vault = vault
    _state.index = index
    _state.ai = ai
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

_MAX_SEARCH_RESULTS = 10
_MAX_LIST_RESULTS = 50
_MAX_BODY_LENGTH = 50_000  # matches IngestRequest.content character limit


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: normalise tags from various LLM-produced formats
# ---------------------------------------------------------------------------


def _normalize_tags(value: Any) -> list[str] | None:
    """Normalise tags from any LLM-produced format to a flat list[str].

    LLMs frequently send tags as:
    - A proper JSON array: ["work", "python"]
    - A JSON array string: '["work", "python"]'
    - A Python literal dict: "{'category': ['work', 'python']}"
    - A plain comma-separated string: "work, python"
    - A dict object: {"category": ["work", "python"]}
    """
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, dict):
        result: list[str] = []
        for v in value.values():
            if isinstance(v, list):
                result.extend(str(x) for x in v if x is not None)
            elif v is not None:
                result.append(str(v))
        return result or None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Try JSON first (handles double-quoted strings)
        try:
            parsed = json.loads(s)
            return _normalize_tags(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        # Try Python literal eval (handles single-quoted strings / Python dicts)
        try:
            import ast
            parsed = ast.literal_eval(s)
            return _normalize_tags(parsed)
        except (ValueError, SyntaxError):
            pass
        # Final fallback: comma-separated plain text
        return [t.strip() for t in s.split(",") if t.strip()] or None
    return [str(value)]


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: run sync vault / index calls in a thread
# ---------------------------------------------------------------------------


async def _to_thread(fn, *args):
    import asyncio

    return await asyncio.to_thread(fn, *args)


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

    Args:
        query: The search query text.
        n_results: Maximum number of results to return (1–10).
        note_type: Optional note type filter, e.g. 'person_note'.
        domain: Optional domain filter, e.g. 'work'.

    Returns:
        JSON array of objects with file_path, similarity, and chunk fields.
    """
    _state.assert_ready()
    if _state.ai is None:
        raise RuntimeError(
            "search_vault requires an AI provider for embeddings, "
            "but the server was started without one (ai=None). "
            "Configure an AI provider in config.yaml to enable semantic search."
        )
    n = max(1, min(n_results, _MAX_SEARCH_RESULTS))
    filters: dict = {}
    if note_type:
        filters["type"] = note_type
    if domain:
        filters["domain"] = domain

    embedding = await _state.ai.embed(query)
    scored = await _to_thread(
        _state.index.search,
        embedding,
        n,
        filters or None,
        query,
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

    Args:
        file_path: Vault-relative path to the note, e.g. 'people/alice.md'.

    Returns:
        JSON object with file_path, title, type, domain, tags, people, and body.
    """
    _state.assert_ready()
    note = await _to_thread(_state.vault.read_note, file_path)
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
#region #*   Tool: browse_recent
# ---------------------------------------------------------------------------


@mcp.tool()
async def browse_recent(
    limit: int = 10,
    note_type: str | None = None,
    domain: str | None = None,
) -> str:
    """List the most recently updated notes in the vault.

    Args:
        limit: Maximum number of notes to return (1–50).
        note_type: Optional note type filter, e.g. 'decision'.
        domain: Optional domain filter, e.g. 'work'.

    Returns:
        JSON array of objects with file_path, title, type, domain, and updated fields.
    """
    _state.assert_ready()
    n = max(1, min(limit, _MAX_LIST_RESULTS))
    result = await _to_thread(
        _state.vault.list_notes,
        None,       # folder
        note_type,  # type filter
        domain,     # domain filter
        "updated",  # sort key
        n,          # limit
        0,          # offset
    )
    return json.dumps(
        [
            {
                "file_path": ref.file_path,
                "title": ref.title,
                "type": ref.type,
                "domain": ref.domain,
                "updated": ref.updated.isoformat() if ref.updated else None,
            }
            for ref in result.items
        ]
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: capture_thought
# ---------------------------------------------------------------------------


@mcp.tool()
async def capture_thought(content: str, source: str = "mcp") -> str:
    """Capture a raw text thought and run it through the full ingest pipeline.

    The pipeline routes the content, extracts metadata, scores confidence, and
    writes a new note to the vault.  The note may land in the review queue if
    confidence is below the configured threshold.

    Args:
        content: The raw text content to ingest.
        source: Source identifier (default 'mcp').

    Returns:
        JSON object with file_path, type, confidence, and review_status.
    """
    _state.assert_ready()
    if len(content) > _MAX_BODY_LENGTH:
        raise ValueError(f"content exceeds {_MAX_BODY_LENGTH:,} character limit")

    from monocle.models import IngestRequest

    req = IngestRequest(content=content, source=source)  # type: ignore[arg-type]
    note, confidence = await _state.ingest_pipeline.run(req)
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
    note_type: str = "other",
    domain: str = "personal",
    tags: Annotated[list[str] | None, BeforeValidator(_normalize_tags)] = None,
) -> str:
    """Create a new note in the vault from a template.

    Notes created via MCP are placed in the review queue (review_status: pending).

    Args:
        title: The title of the new note.
        body: The Markdown body content.
        note_type: Note type, e.g. 'idea', 'decision', 'person_note'.
        domain: Knowledge domain, e.g. 'work' or 'personal'.
        tags: Optional list of topic tags.

    Returns:
        JSON object with file_path, title, and status.
    """
    _state.assert_ready()
    if len(body) > _MAX_BODY_LENGTH:
        raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")

    from monocle.models import NoteMetadata

    metadata = NoteMetadata(
        type=note_type,  # type: ignore[arg-type]
        domain=domain,
        tags=tags or [],
        review_status="pending",
    )
    note = await _to_thread(
        _state.vault.create_from_template,
        note_type,
        {"title": title, **metadata.model_dump(exclude={"template"}, exclude_none=True)},
        body,
    )
    await _to_thread(_state.vault.write_note, note.file_path, note)
    if _state.reindex_queue is not None:
        _state.reindex_queue.push(note.file_path)
    return json.dumps({"file_path": note.file_path, "title": note.title, "status": "created"})


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: fetch and strip HTML from a URL
# ---------------------------------------------------------------------------

_MAX_FETCH_BYTES = 500_000  # 500 KB — cap before HTML stripping
_MAX_TEXT_CHARS = 20_000    # chars fed to the LLM summariser

_URL_SUMMARISE_PROMPT = """\
You are a knowledge assistant. Summarise the following web page content into a concise Markdown reference note.

Instructions:
- Write 3–6 paragraphs covering the key ideas, arguments, and takeaways.
- Use a short `## Summary` section at the top, then `## Key Points` as a bullet list.
- Preserve any code examples, commands, or structured data verbatim in fenced code blocks.
- Do NOT reproduce boilerplate navigation text, cookie banners, or unrelated sidebar content.
- After the body, output a JSON block fenced with ```json containing:
  {{"title": "<short descriptive title>", "tags": ["tag1", "tag2"], "domain": "<work|personal|technology|...>"}}

Web page URL: {url}

Content:
{content}
"""


def _strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities, returning plain text."""
    import html
    import re

    # Remove script/style blocks
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode HTML entities
    raw = html.unescape(raw)
    # Collapse whitespace
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


async def _fetch_url_text(url: str) -> str:
    """Fetch *url* via httpx and return stripped plain text.

    Raises ``ValueError`` for disallowed schemes and ``RuntimeError`` for
    network / HTTP errors so callers can return a user-friendly message.
    """
    import asyncio
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are supported, got: {parsed.scheme!r}")

    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Monocle-Reference-Bot/1.0"},
            )
            resp.raise_for_status()
            raw = resp.content[:_MAX_FETCH_BYTES].decode("utf-8", errors="replace")
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"HTTP {exc.response.status_code} fetching {url}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc}") from exc

    return _strip_html(raw)[:_MAX_TEXT_CHARS]


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

    The tool fetches the URL, strips HTML, asks the configured AI provider to
    produce a structured Markdown summary, then creates a ``reference`` note
    tagged with ``source: web`` and placed in the review queue.

    Args:
        url: The https:// URL to fetch and summarise.
        extra_context: Optional additional context or instructions for the
                       summariser (e.g. "focus on the security implications").

    Returns:
        JSON object with file_path, title, url, and status.
    """
    _state.assert_ready()

    if _state.ai is None:
        raise RuntimeError(
            "create_reference_from_url requires an AI provider, "
            "but the server was started without one. "
            "Configure an AI provider in config.yaml."
        )

    # 1. Fetch and strip the page
    page_text = await _fetch_url_text(url)

    # 2. Build summarisation prompt
    prompt_content = _URL_SUMMARISE_PROMPT.format(url=url, content=page_text)
    if extra_context:
        prompt_content += f"\n\nAdditional instructions: {extra_context}"

    # 3. Ask AI to summarise
    raw_response = await _state.ai.chat(
        [{"role": "user", "content": prompt_content}],
        stream=False,
    )
    assert isinstance(raw_response, str)

    # 4. Extract the embedded JSON metadata block (last ```json ... ``` fence)
    import re as _re

    json_match = _re.search(r"```json\s*(\{.*?\})\s*```", raw_response, _re.DOTALL)
    if json_match:
        try:
            meta = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            meta = {}
        # Strip the JSON fence from the body text
        body = raw_response[: json_match.start()].strip()
    else:
        meta = {}
        body = raw_response.strip()

    title = meta.get("title") or url
    tags = _normalize_tags(meta.get("tags")) or []
    domain = meta.get("domain") or "personal"

    # Prepend source URL to body
    body = f"> Source: {url}\n\n{body}"

    if len(body) > _MAX_BODY_LENGTH:
        body = body[:_MAX_BODY_LENGTH]

    # 5. Create the note
    from monocle.models import NoteMetadata

    metadata = NoteMetadata(
        type="reference",
        domain=domain,
        tags=["web-reference"] + tags,
        review_status="pending",
        source="web",
    )
    note = await _to_thread(
        _state.vault.create_from_template,
        "reference",
        {"title": title, **metadata.model_dump(exclude={"template"}, exclude_none=True)},
        body,
    )
    await _to_thread(_state.vault.write_note, note.file_path, note)
    if _state.reindex_queue is not None:
        _state.reindex_queue.push(note.file_path)

    return json.dumps(
        {"file_path": note.file_path, "title": note.title, "url": url, "status": "created"}
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: update_note
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_note(file_path: str, body: str) -> str:
    """Overwrite the body of an existing note in the vault.

    Args:
        file_path: Vault-relative path to the note to update.
        body: New Markdown body content. The existing frontmatter is preserved.

    Returns:
        JSON object with file_path and status.
    """
    _state.assert_ready()
    if len(body) > _MAX_BODY_LENGTH:
        raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")

    note = await _to_thread(_state.vault.read_note, file_path)
    note.body = body
    note.metadata.updated = datetime.now(timezone.utc)
    await _to_thread(_state.vault.write_note, file_path, note)
    if _state.reindex_queue is not None:
        _state.reindex_queue.push(note.file_path)
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

    Args:
        focus: Vault-relative path of the focus note (e.g. 'people/alice.md').
               If omitted, returns the full-vault graph.
        max_degree: BFS depth from the focus node (default 2).

    Returns:
        JSON object with focus, nodes, and edges arrays.
    """
    _state.assert_ready()
    import asyncio

    graph_data = await asyncio.to_thread(
        _state.graph_builder.build,
        focus,
        max_degree,
        None,  # types filter
        500,   # max nodes
    )
    return graph_data.model_dump_json()


#endregion

# ---------------------------------------------------------------------------
#region #*   Tool: get_stats
# ---------------------------------------------------------------------------


async def _fetch_all_refs() -> tuple[list, int]:
    """Fetch every NoteRef in the vault via paginated calls.

    Returns a tuple of (all_items, vault_total).  ``vault_total`` comes from
    the most-recent page's ``.total`` field so it reflects any notes added
    during the iteration.  This prevents the pre-M12 bug where stats were
    silently wrong for vaults with more than 1 000 notes.
    """
    _PAGE = 500
    all_items: list = []
    offset = 0
    vault_total = 0
    while True:
        page = await _to_thread(
            _state.vault.list_notes,
            None,       # folder
            None,       # type filter
            None,       # domain filter
            "updated",  # sort key
            _PAGE,      # limit
            offset,     # offset
        )
        vault_total = page.total
        all_items.extend(page.items)
        if offset + len(page.items) >= page.total or len(page.items) < _PAGE:
            break
        offset += _PAGE
    return all_items, vault_total


@mcp.tool()
async def get_stats() -> str:
    """Return a summary of vault statistics: counts, types, domains, and pending reviews.

    Returns:
        JSON object with total_notes, by_type, by_domain, pending_review,
        index_chunks, and failed_ingests fields.
    """
    _state.assert_ready()
    all_refs, vault_total = await _fetch_all_refs()
    index_stats = await _to_thread(_state.index.get_stats)

    by_type: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    pending = 0
    for ref in all_refs:
        by_type[ref.type] = by_type.get(ref.type, 0) + 1
        by_domain[ref.domain] = by_domain.get(ref.domain, 0) + 1
        if ref.review_status == "pending":
            pending += 1

    return json.dumps(
        {
            "total_notes": vault_total,
            "by_type": by_type,
            "by_domain": by_domain,
            "pending_review": pending,
            "index_chunks": index_stats.total_chunks,
            "index_backend": index_stats.backend,
        }
    )


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
