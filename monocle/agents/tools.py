"""
monocle/agents/tools.py — Agent tool library for the chat agent.

All tools are decorated with @ai_function and accept the vault, index, and AI
provider as constructor arguments on the ToolRegistry container class, then
expose bound methods that the agent framework can invoke.

Tools:
  search_vault      — Semantic search returning scored note chunks
  read_note         — Read a full note by vault-relative path
  write_note        — Overwrite an existing note body/metadata
  create_note       — Create a new note via VaultLayer.create_from_template
  get_stats         — Return BrainStats summary
  list_notes        — List notes with optional type/domain filter
  get_person_graph  — Return first-degree ego-graph for a person
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Annotated, Any

from agent_framework import ai_function

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.graph import GraphBuilder
    from monocle.index.base import IndexLayer
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Maximum results caps to keep context windows manageable
# ---------------------------------------------------------------------------

_MAX_SEARCH_RESULTS = 10
_MAX_LIST_RESULTS = 20
_MAX_BODY_LENGTH = 50_000  # matches IngestRequest.content character limit


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
        graph_builder: "GraphBuilder | None" = None,
    ) -> None:
        self._vault = vault
        self._index = index
        self._ai = ai
        self._graph_builder = graph_builder

        # Bind the @ai_function decorated methods to this instance so the tool
        # implementations can reference self.  The agent framework accepts any
        # callable decorated with @ai_function, including bound methods.
        self.tools = [
            self.search_vault,
            self.read_note,
            self.write_note,
            self.create_note,
            self.get_stats,
            self.list_notes,
            self.get_person_graph,
        ]

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
            n = max(1, min(n_results, _MAX_SEARCH_RESULTS))
            filters: dict[str, Any] = {}
            if note_type:
                filters["type"] = note_type
            if domain:
                filters["domain"] = domain

            if self._ai is not None:
                embedding = await self._ai.embed(query)
                scored = await _to_thread(
                    self._index.search,
                    embedding,
                    n,
                    filters or None,
                    query,
                )
            else:
                # No AI — fall back to substring search in MemoryIndex
                scored = await _to_thread(
                    self._index.search,
                    [],
                    n,
                    filters or None,
                    query,
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
            note = await _to_thread(self._vault.read_note, file_path)
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
    # Tool: write_note
    # ------------------------------------------------------------------

    @ai_function
    async def write_note(
        self,
        file_path: Annotated[str, "Vault-relative path to the note to update"],
        body: Annotated[str, "New Markdown body for the note"],
    ) -> str:
        """Overwrite the body of an existing note. Returns the updated note path."""
        if len(body) > _MAX_BODY_LENGTH:
            raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")
        try:
            note = await _to_thread(self._vault.read_note, file_path)
            note.body = body
            await _to_thread(self._vault.write_note, file_path, note)
            return json.dumps({"file_path": file_path, "status": "updated"})
        except Exception as exc:
            logger.warning("write_note tool error for %r: %s", file_path, exc)
            raise

    # ------------------------------------------------------------------
    # Tool: create_note
    # ------------------------------------------------------------------

    @ai_function
    async def create_note(
        self,
        title: Annotated[str, "Title of the new note"],
        body: Annotated[str, "Markdown body content"],
        note_type: Annotated[str, "Note type, e.g. 'idea', 'person_note', 'decision'"] = "other",
        domain: Annotated[str, "Domain, e.g. 'work' or 'personal'"] = "personal",
        tags: Annotated[
            list[str] | None,
            "List of topic tags",
        ] = None,
    ) -> str:
        """Create a new note in the vault using the appropriate template.

        Returns the file_path of the newly created note.
        Notes created by the agent are placed in the review queue (review_status: pending).
        """
        if len(body) > _MAX_BODY_LENGTH:
            raise ValueError(f"body exceeds {_MAX_BODY_LENGTH:,} character limit")
        try:
            from monocle.models import NoteMetadata

            metadata = NoteMetadata(
                type=note_type,  # type: ignore[arg-type]
                domain=domain,
                tags=tags or [],
                review_status="pending",
            )
            note = await _to_thread(
                self._vault.create_from_template,
                note_type,
                {"title": title, **metadata.model_dump(exclude={"template"}, exclude_none=True)},
                body,
            )
            await _to_thread(self._vault.write_note, note.file_path, note)
            return json.dumps(
                {"file_path": note.file_path, "title": note.title, "status": "created"}
            )
        except Exception as exc:
            logger.warning("create_note tool error: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Tool: get_stats
    # ------------------------------------------------------------------

    @ai_function
    async def get_stats(self) -> str:
        """Return a summary of vault statistics: note counts, type breakdown, and pending reviews."""
        try:
            from monocle.models import NoteMetadata

            all_notes = await _to_thread(
                self._vault.list_notes,
                None,  # folder
                None,  # type
                None,  # domain
                "updated",
                1000,
                0,
            )
            index_stats = await _to_thread(self._index.get_stats)

            by_type: dict[str, int] = {}
            by_domain: dict[str, int] = {}
            pending = 0
            for ref in all_notes.items:
                by_type[ref.type] = by_type.get(ref.type, 0) + 1
                by_domain[ref.domain] = by_domain.get(ref.domain, 0) + 1
                if ref.review_status == "pending":
                    pending += 1

            return json.dumps(
                {
                    "total_notes": all_notes.total,
                    "total_chunks": index_stats.total_chunks,
                    "notes_by_type": by_type,
                    "notes_by_domain": by_domain,
                    "pending_review": pending,
                }
            )
        except Exception as exc:
            logger.warning("get_stats tool error: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Tool: list_notes
    # ------------------------------------------------------------------

    @ai_function
    async def list_notes(
        self,
        note_type: Annotated[str | None, "Filter by note type, e.g. 'person_note'"] = None,
        domain: Annotated[str | None, "Filter by domain, e.g. 'work'"] = None,
        limit: Annotated[int, "Maximum number of notes to return (1–20)"] = 10,
    ) -> str:
        """List notes from the vault with optional type and domain filters."""
        try:
            n = max(1, min(limit, _MAX_LIST_RESULTS))
            page = await _to_thread(
                self._vault.list_notes,
                None,  # folder
                note_type,
                domain,
                "updated",
                n,
                0,
            )
            items = [
                {
                    "file_path": ref.file_path,
                    "title": ref.title,
                    "type": ref.type,
                    "domain": ref.domain,
                    "updated": ref.updated.isoformat() if ref.updated else None,
                }
                for ref in page.items
            ]
            return json.dumps({"total": page.total, "items": items})
        except Exception as exc:
            logger.warning("list_notes tool error: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Tool: get_person_graph
    # ------------------------------------------------------------------

    @ai_function
    async def get_person_graph(
        self,
        name_or_path: Annotated[
            str,
            "Person name (e.g. 'Alice') or vault-relative path (e.g. 'people/alice.md')",
        ],
    ) -> str:
        """Return the first-degree relationship graph for a person in the vault.

        Shows which notes mention the person and what the relationships are.
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

            graph = await _to_thread(
                self._graph_builder.build,
                focus,  # focus
                1,       # max_degree=1 (immediate connections only)
                None,    # types
                50,      # n
            )
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
            logger.warning("get_person_graph tool error: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Helper: asyncio.to_thread wrapper (avoids import boilerplate in tools)
# ---------------------------------------------------------------------------


async def _to_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)
