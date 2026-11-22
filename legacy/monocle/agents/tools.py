"""
monocle/agents/tools.py — Chat-agent tool adapters for canonical Monocle operations.

Each tool is a thin adapter decorated with @ai_function that delegates to the
shared service layer in ``monocle.services.*``.  Tool names are aligned with the
canonical MCP tool names defined in ``docs/tool-contracts.md``.

Adapter responsibilities (not in services):
  - Query-based note discovery (wikilink → title scan → semantic search)
  - AI content merge for update_note
  - Wikilink name resolution for get_graph
  - MemoryIndex fallback for no-AI search
  - Tag normalization from LLM-produced formats
  - @ai_function binding and JSON serialization

Canonical tools (6 — excludes MCP-only capture_thought):
    search_vault              — Semantic search returning scored note chunks
    read_note                 — Read a full note by vault-relative path
    update_note               — Find a note by path or query and merge new content
    create_note               — Create a new note via VaultLayer.create_from_template
    get_graph                 — Return ego-graph for an entity (name or path)
    create_reference_from_url — Fetch a web page, summarize it with AI, and create a reference note
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Annotated, Any

from agent_framework import ai_function
from pydantic import Field

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.config import Settings
    from monocle.graph import GraphBuilder
    from monocle.index.base import IndexLayer
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   Maximum results caps to keep context windows manageable
# ---------------------------------------------------------------------------

_MAX_SEARCH_RESULTS = 10
_MAX_LIST_RESULTS = 20
_MAX_BODY_LENGTH = 50_000  # matches IngestRequest.content character limit


# Canonical tag normaliser — shared across MCP, agent tools, and services.
from monocle.services.tags import normalize_tags as _normalize_tags


def _try_unwrap_json_body(content: str) -> str:
    """Extract plain text if the LLM accidentally serialized content as a JSON object.

    Handles patterns like ``{"body": "text"}``, ``{"content": "text"}``, etc.
    Returns *content* unchanged when it is already plain text.
    """
    stripped = content.strip()
    if not stripped.startswith("{"):
        return content
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            for key in ("body", "content", "text", "note"):
                if key in parsed and isinstance(parsed[key], str):
                    return parsed[key]
    except (json.JSONDecodeError, ValueError):
        pass
    return content


class VaultTools:
    """Container that holds bound references to vault/index/AI and exposes
    @ai_function decorated methods for the agent framework.

    Instantiate once per request (or per agent); the tool methods capture
    the runtime state via closure.
    """

    def __init__(
        self,
        vault: "VaultLayer",
        index: "IndexLayer",
        ai: "AIProvider | None",
        settings: "Settings | None" = None,
        graph_builder: "GraphBuilder | None" = None,
        reindex_queue: "ReindexQueue | None" = None,
    ) -> None:
        self._vault = vault
        self._index = index
        self._ai = ai
        self._settings = settings
        self._graph_builder = graph_builder
        self._reindex_queue = reindex_queue

        # Bind the @ai_function decorated methods to this instance so the tool
        # implementations can reference self.  The agent framework accepts any
        # callable decorated with @ai_function, including bound methods.
        self.tools = [
            self.search_vault,
            self.read_note,
            self.update_note,
            self.create_note,
            self.create_reference_from_url,
            self.get_graph,
        ]
        
        # Rebuild input models for tools that use Annotated validators.
        # This resolves any forward references and ensures JSON schema generation works.
        self._rebuild_tool_input_models()

    def _rebuild_tool_input_models(self) -> None:
        """Initialize tool input models for proper schema generation.
        
        The agent framework's observability code calls tool.parameters() which
        triggers model_json_schema() generation. We trigger this eagerly to catch
        any Pydantic validation errors before the agent runs.
        """
        for tool in self.tools:
            try:
                # Eagerly call parameters() to trigger schema generation and catch
                # any Pydantic model errors before agent.run_stream().
                # parameters() is sync for the agent-framework decorators used here.
                if hasattr(tool, 'parameters'):
                    tool.parameters()
            except Exception as exc:
                # Log at warning level to ensure visibility of model issues
                tool_name = getattr(tool, 'name', str(tool))
                logger.warning("Tool %s schema generation failed: %s", 
                             tool_name, exc)

    # ------------------------------------------------------------------
    # Tool: search_vault
    # ------------------------------------------------------------------

    @ai_function
    async def search_vault(
        self,
        query: Annotated[str, "The search query text"],
        n_results: Annotated[int, "Maximum number of results to return (1–10)"] = 5,
        note_type: Annotated[str | None, "Optional note type filter, e.g. 'person_note'"] = None,
        domain: Annotated[str | None, "Optional domain filter, e.g. 'work'"] = None,
    ) -> str:
        """Search the vault using semantic similarity and return matching note excerpts."""
        try:
            from monocle.services.search import search_vault as _search_vault

            scored = await _search_vault(
                self._index, self._ai, query, n_results, note_type, domain,
            )

            results = [
                {
                    "file_path": c.file_path,
                    "similarity": round(c.score, 3),
                    "chunk": c.text[:500],
                }
                for c in scored
            ]
            return json.dumps(results)
        except Exception as exc:
            logger.warning("search_vault tool error: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Tool: read_note
    # ------------------------------------------------------------------

    @ai_function
    async def read_note(
        self,
        file_path: Annotated[str, "Vault-relative path to the note, e.g. 'people/alice.md'"],
    ) -> str:
        """Read a full note from the vault and return its title, metadata, and body."""
        try:
            from monocle.services.notes import read_note as _read_note

            note = await _read_note(self._vault, file_path)
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
        except Exception as exc:
            logger.warning("read_note tool error for %r: %s", file_path, exc)
            raise

    # ------------------------------------------------------------------
    # Tool: update_note
    # ------------------------------------------------------------------

    @ai_function
    async def update_note(
        self,
        body: Annotated[str, "New content to merge into the existing note (required, must not be empty)"],
        file_path: Annotated[str | None, "Vault-relative path to the note (preferred when known from search_vault/read_note, e.g. 'people/alice.md')"] = None,
        query: Annotated[str | None, "Person name or topic to find the note (used when file_path is not known, e.g. 'Alice Example')"] = None,
        title: Annotated[str | None, "Optional replacement title for the note"] = None,
        metadata_updates: Annotated[dict[str, object] | None, "Optional frontmatter updates merged into the note"] = None,
    ) -> str:
        """Update an EXISTING note with new content using content-aware merging.

        **Use this to ADD or MODIFY content in a note that already exists.**
        Provide `file_path` when you have it (from search_vault or read_note results);
        otherwise provide `query` and the tool locates the note by name or topic.

        New content is intelligently merged with the existing body using AI when
        available, so facts are synthesised rather than blindly appended.

        **DO NOT use this to CREATE a new note** — use create_note instead.
        Returns an error JSON if the note cannot be found via query.
        Raises if the note does not exist when accessed by file_path.
        """
        if not body.strip():
            raise ValueError("body must not be empty")
        if len(body) > _MAX_BODY_LENGTH:
            raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")

        # Unwrap JSON-encoded body that LLMs occasionally produce
        body = _try_unwrap_json_body(body)
        if not body.strip():
            raise ValueError("body must not be empty")

        if file_path is None and query is None:
            raise ValueError("Either file_path or query must be provided")

        resolved_path = file_path

        if resolved_path is None:
            # Step 1: Wikilink resolution
            resolved_path = await _to_thread(self._vault.resolve_wikilink, query)

            # Step 2: Title-prefix scan (scan all notes, not just first 500)
            if not resolved_path:
                query_lower = query.lower()
                # Use a large limit and rely on vault.list_notes pagination
                offset = 0
                found = None
                while not found:
                    page = await _to_thread(
                        self._vault.list_notes,
                        None, None, None, "updated", 1000, offset,
                    )
                    if not page.items:
                        break
                    exact = next(
                        (r for r in page.items if r.title.lower() == query_lower), None
                    )
                    starts = next(
                        (r for r in page.items if r.title.lower().startswith(query_lower)), None
                    )
                    found = exact or starts
                    if found:
                        resolved_path = found.file_path
                        break
                    # If we got fewer items than the limit, we've hit the end
                    if len(page.items) < 1000:
                        break
                    offset += 1000

            # Step 3: Semantic search (min similarity 0.6 to avoid false matches)
            if not resolved_path and self._ai is not None:
                embedding = await self._ai.embed(query)
                scored = await _to_thread(
                    self._index.search, embedding, 1, None, query
                )
                if scored and scored[0].score >= 0.6:
                    resolved_path = scored[0].file_path

            if not resolved_path:
                return json.dumps(
                    {"error": f"No note found matching {query!r}. Use create_note to start one."}
                )

        try:
            from monocle.services.notes import read_note as _read_note

            note = await _read_note(self._vault, resolved_path)
            merged_body = await self._merge_body(note.body or "", body)

            from monocle.services.notes import update_note as _update_note

            note = await _update_note(
                self._vault,
                self._reindex_queue,
                resolved_path,
                merged_body,
                title=title,
                metadata_updates=metadata_updates,
            )
            return json.dumps({"file_path": resolved_path, "title": note.title, "status": "updated"})
        except Exception as exc:
            logger.warning("update_note tool error for %r: %s", resolved_path, exc)
            raise

    # ------------------------------------------------------------------
    # Tool: create_note (previously preceded by a separate append_to_note;
    # append behaviour is now part of update_note)
    # ------------------------------------------------------------------

    @ai_function
    async def create_note(
        self,
        title: Annotated[str, "Title of the new note"],
        body: Annotated[str, "Markdown body content"],
        note_type: Annotated[str, "Note type or template key, e.g. 'person'/'person_note', 'meeting'/'meeting_note', 'idea', 'reference', 'blank'/'other'"] = "observation",
        domain: Annotated[str, "Domain, e.g. 'work' or 'personal'"] = "personal",
        tags: Annotated[
            str | list[str] | None,
            Field(description="List of string tags or a string representation, e.g. ['python', 'automation']."),
        ] = None,
        metadata_updates: Annotated[dict[str, object] | None, "Optional frontmatter updates merged into the new note"] = None,
    ) -> str:
        """Create a NEW note in the vault from scratch using the appropriate template.

        **Use this whenever the user wants to CREATE or START a new note** — e.g., 'add a note for Grayson', 'create a decision note'.
        **DO NOT use this to APPEND to an existing note** — use update_note instead.

        Returns the file_path of the newly created note.
        Notes created by the agent are placed in the review queue (review_status: pending).
        """
        if len(body) > _MAX_BODY_LENGTH:
            raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")
        
        # Normalize tags from various LLM-produced formats
        normalized_tags = _normalize_tags(tags)
        
        try:
            from monocle.services.notes import create_note as _create_note

            note = await _create_note(
                self._vault, self._reindex_queue, title, body,
                note_type, domain, normalized_tags, metadata_updates,
            )
            return json.dumps(
                {"file_path": note.file_path, "title": note.title, "status": "created"}
            )
        except Exception as exc:
            logger.warning("create_note tool error: %s", exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Tool: get_graph (canonical name — replaces former get_person_graph)
    # ------------------------------------------------------------------

    @ai_function
    async def get_graph(
        self,
        name_or_path: Annotated[
            str,
            "Person name (e.g. 'Alice') or vault-relative path (e.g. 'people/alice.md')",
        ],
    ) -> str:
        """Return the first-degree relationship graph for an entity in the vault.

        Canonical operation — see ``docs/tool-contracts.md § get_graph``.

        Shows which notes mention the entity and what the relationships are.
        """
        try:
            if self._graph_builder is None:
                return json.dumps({"error": "Graph builder not available"})

            # Resolve name to path if not already a path
            if not name_or_path.endswith(".md"):
                resolved = await _to_thread(self._vault.resolve_wikilink, name_or_path)
                focus = resolved or name_or_path
            else:
                focus = name_or_path

            from monocle.services.graph import get_graph as _get_graph

            graph = await _get_graph(self._graph_builder, focus, 1, None, 50)
            return json.dumps(
                {
                    "focus": graph.focus,
                    "node_count": len(graph.nodes),
                    "edge_count": len(graph.edges),
                    "nodes": [
                        {"id": n.id, "label": n.label, "type": n.type, "degree": n.degree}
                        for n in graph.nodes
                    ],
                    "edges": [
                        {
                            "source": e.source,
                            "target": e.target,
                            "relation": e.relation,
                            "edge_type": e.edge_type,
                        }
                        for e in graph.edges
                    ],
                }
            )
        except Exception as exc:
            logger.warning("get_graph tool error: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Tool: create_reference_from_url (canonical name — replaces former fetch_and_summarize_url)
    # ------------------------------------------------------------------

    @ai_function
    async def create_reference_from_url(
        self,
        url: Annotated[str, "The https:// URL to fetch and summarize into a reference note"],
        extra_context: Annotated[
            str | None,
            "Optional focus or extra instructions for the summary (e.g. 'focus on the setup steps')"
        ] = None,
    ) -> str:
        """Fetch a web page, summarise its content with AI, and create a reference note.

        Canonical operation — see ``docs/tool-contracts.md § create_reference_from_url``.

        Use this when the user asks to create a reference note from a URL.
        The tool fetches the page, strips HTML boilerplate, uses AI to write a
        structured Markdown summary with ## Summary and ## Key Points sections,
        and creates a note of type 'reference' with review_status 'pending'.

        Returns JSON with file_path, title, url, and status.
        """
        if self._ai is None:
            raise RuntimeError(
                "create_reference_from_url requires an AI provider. "
                "Configure ai.provider in config.yaml."
            )

        try:
            from monocle.services.references import create_reference_from_url as _create_ref

            note = await _create_ref(
                self._vault,
                self._ai,
                self._reindex_queue,
                url,
                extra_context,
                summarize_timeout_s=(
                    self._settings.ai.url_reference_timeout_s if self._settings is not None else None
                ),
            )
            return json.dumps(
                {
                    "file_path": note.file_path,
                    "title": note.title,
                    "url": url,
                    "status": "created",
                }
            )
        except Exception as exc:
            logger.warning("create_reference_from_url tool error: %s", exc, exc_info=True)
            raise

    async def _merge_body(self, existing: str, new_content: str) -> str:
        """Merge new_content into existing note body.

        When an AI provider is available and the existing body is non-empty,
        asks the LLM to produce a single coherent Markdown body that integrates
        both texts (avoiding duplication). Falls back to a simple append on any
        failure or when no AI is configured.
        """
        if not existing.strip():
            return new_content.strip()

        if self._ai is None:
            sep = "\n\n"
            return existing.rstrip() + sep + new_content.strip()

        try:
            messages = [
                {
                    "role": "user",
                    "content": (
                        "Merge the new information into the existing note body. "
                        "Produce a single coherent Markdown body that integrates "
                        "all facts, avoids duplication, and reads naturally. "
                            "Preserve existing section headings, tables, and checklist "
                            "structure when they already provide a useful note scaffold. "
                        "Return ONLY the merged body — no YAML frontmatter, no JSON, "
                        "no commentary.\n\n"
                        f"EXISTING:\n{existing}\n\n"
                        f"NEW INFORMATION:\n{new_content}"
                    ),
                }
            ]
            result = await self._ai.chat(messages, stream=False)
            merged: str = ""
            if isinstance(result, str):
                merged = result.strip()
            elif hasattr(result, "__aiter__"):
                parts: list[str] = []
                async for chunk in result:
                    parts.append(chunk)
                merged = "".join(parts).strip()

            # Sanity-check: the merged result must contain at least part of
            # the new content; if not, fall back to append (prevents a metadata
            # JSON leak from the AI contaminating the note body).
            if merged and new_content.split()[0].lower() in merged.lower():
                return merged
        except Exception as exc:
            logger.debug("AI merge failed, falling back to append: %s", exc)

        # Fallback: simple paragraph append
        return existing.rstrip() + "\n\n" + new_content.strip()


#endregion

# ---------------------------------------------------------------------------
#region #*   Helper: asyncio.to_thread wrapper (avoids import boilerplate in tools)
# ---------------------------------------------------------------------------


async def _to_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)

