"""
monocle/graph.py — Knowledge graph builder.

``GraphBuilder`` traverses the vault and extracts four kinds of edges:

1. **Structured links** — ``links:`` frontmatter list (highest-priority source).
2. **Wikilinks** — ``[[Target]]`` syntax in the note body.
3. **People co-mentions** — entries in the ``people:`` frontmatter list,
   resolved to person notes in the vault.
4. **Shared tags** — pairs of notes that share at least one tag.

Results are cached in memory keyed on ``(focus, max_degree, types_tuple, n)``;
the entire cache is invalidated whenever any vault file changes (call
``invalidate()``).
"""
from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path
from typing import Any

from monocle.models import GraphData, GraphEdge, GraphNode
from monocle.vault.wikilinks import parse_wikilinks

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Build ``GraphData`` from a ``VaultLayer`` instance.

    Args:
        vault: A fully initialised ``VaultLayer`` instance.
    """

    def __init__(self, vault: Any) -> None:
        self._vault = vault
        # Cache: (focus, max_degree, types_tuple | None, n) -> GraphData
        self._cache: dict[tuple[Any, ...], GraphData] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        """Discard the entire in-memory cache.

        Called whenever the watcher detects a file change or when any note is
        written through the API.
        """
        self._cache.clear()
        logger.debug("[GRAPH] Cache invalidated")

    def build(
        self,
        focus: str | None = None,
        max_degree: int = 3,
        types: list[str] | None = None,
        n: int = 500,
    ) -> GraphData:
        """Build (or return cached) a ``GraphData`` for the given parameters.

        Args:
            focus: Vault-relative path of the focal note.  When *None* the
                full-vault graph is returned (``degree`` is ``null`` on all
                nodes).
            max_degree: Maximum BFS hops from the focus node.  Ignored when
                *focus* is ``None``.
            types: If given, only nodes whose ``type`` field is in this list
                are included.  Edges touching excluded nodes are also removed.
            n: Maximum number of vault notes to consider.

        Returns:
            A ``GraphData`` instance (may be served from cache).
        """
        types_key: tuple[str, ...] | None = tuple(sorted(types)) if types else None
        cache_key = (focus, max_degree, types_key, n)
        if cache_key in self._cache:
            logger.debug("[GRAPH] Cache hit: %s", cache_key)
            return self._cache[cache_key]

        logger.debug("[GRAPH] Building graph: focus=%s max_degree=%d n=%d", focus, max_degree, n)
        result = self._build_uncached(focus, max_degree, types, n)
        self._cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Internal build logic
    # ------------------------------------------------------------------

    def _build_uncached(
        self,
        focus: str | None,
        max_degree: int,
        types: list[str] | None,
        n: int,
    ) -> GraphData:
        # ----------------------------------------------------------
        # 1. Load all notes (up to `n`)
        # ----------------------------------------------------------
        page = self._vault.list_notes(limit=n)
        notes_by_path: dict[str, Any] = {}  # path -> Note
        for ref in page.items:
            try:
                note = self._vault.read_note(ref.file_path)
                notes_by_path[ref.file_path] = note
            except Exception as exc:  # noqa: BLE001
                logger.debug("[GRAPH] Skipping unreadable note %s: %s", ref.file_path, exc)

        if not notes_by_path:
            return GraphData(focus=focus)

        # Ensure the focus note is present even when `n` truncated it out of
        # the top-n list.  We load it explicitly so the BFS always has a
        # starting node.
        if focus is not None and focus not in notes_by_path:
            try:
                focus_note = self._vault.read_note(focus)
                notes_by_path[focus] = focus_note
                logger.debug("[GRAPH] Loaded focus note outside top-n: %s", focus)
            except Exception:  # noqa: BLE001
                pass  # genuinely missing — BFS step handles it below

        # ----------------------------------------------------------
        # 2. Build GraphNode objects (weight filled in later)
        # ----------------------------------------------------------
        nodes: dict[str, GraphNode] = {}
        for path, note in notes_by_path.items():
            label = note.title or Path(path).stem
            nodes[path] = GraphNode(
                id=path,
                label=label,
                type=note.metadata.type,
                degree=None,
                weight=0,
            )

        # ----------------------------------------------------------
        # 3. Extract edges from all four sources
        #    Use plain dicts internally to allow weight accumulation,
        #    then convert to GraphEdge at the end.
        # ----------------------------------------------------------
        # edge_map: (source, target, edge_type) -> dict with mutable weight
        edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}

        def _add_edge(
            source: str,
            target: str,
            edge_type: str,
            relation: str | None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            if source not in nodes or target not in nodes or source == target:
                return
            key = (source, target, edge_type)
            if key in edge_map:
                edge_map[key]["weight"] += 1
            else:
                edge_map[key] = {
                    "source": source,
                    "target": target,
                    "edge_type": edge_type,
                    "relation": relation,
                    "weight": 1,
                    "metadata": metadata or {},
                }

        # ----------------------------------------------------------
        # Pre-build a name → vault-relative-path lookup dict so that
        # wikilink/people resolution is O(1) instead of calling
        # resolve_wikilink() (which does a full rglob() scan) for every
        # reference.  The matching rules mirror resolve_wikilink():
        #   stem_lower == name_lower  OR  stem_lower == name_slug
        #   stem_slug  == name_lower  OR  stem_slug  == name_slug
        # ----------------------------------------------------------
        def _slugify(text: str) -> str:
            return re.sub(r"[\s_]+", "-", re.sub(r"[^\w\s-]", "", text.lower())).strip("-")

        _name_to_path: dict[str, str] = {}
        for _p in notes_by_path:
            _stem = Path(_p).stem
            _stem_lower = _stem.lower()
            _stem_slug = _slugify(_stem)
            # setdefault keeps the first (shallowest) match, mirroring rglob order
            _name_to_path.setdefault(_stem_lower, _p)
            _name_to_path.setdefault(_stem_slug, _p)

        def _resolve(name: str) -> str | None:
            """Resolve a wikilink target or person name to a vault path."""
            if name in notes_by_path:  # exact vault-relative path
                return name
            name_lower = name.lower()
            name_slug = _slugify(name)
            return _name_to_path.get(name_lower) or _name_to_path.get(name_slug)

        # Tags → list of note paths (for source 4)
        tags_to_paths: dict[str, list[str]] = {}

        for path, note in notes_by_path.items():
            # Source 1: Structured links frontmatter
            for link in note.metadata.links:
                target = _resolve(link.target)
                if target:
                    meta = dict(link.metadata) if link.metadata else {}
                    _add_edge(path, target, "structured", link.relation or "links-to", meta)

            # Source 2: Body wikilinks
            for wl in parse_wikilinks(note.body):
                target = _resolve(wl)
                if target:
                    _add_edge(path, target, "wikilink", "links-to")

            # Source 3: People co-mentions
            for person in note.metadata.people:
                target = _resolve(person)
                if target:
                    _add_edge(path, target, "co-mention", "mentioned-in")

            # Collect tags for source 4
            for tag in note.metadata.tags:
                tags_to_paths.setdefault(tag, []).append(path)

        # Source 4: Shared tags (connect pairs of notes that share a tag)
        # Cap at notes-per-tag ≤ 20 to avoid combinatorial explosion for
        # very common tags (like "work") producing O(n²) edges.
        _TAG_FAN_OUT_LIMIT = 20
        for tag, tag_paths in tags_to_paths.items():
            if len(tag_paths) < 2 or len(tag_paths) > _TAG_FAN_OUT_LIMIT:
                continue
            for i, p1 in enumerate(tag_paths):
                for p2 in tag_paths[i + 1 :]:
                    # Use canonical order so (A,B) and (B,A) get same key
                    s, t = (p1, p2) if p1 < p2 else (p2, p1)
                    key = (s, t, "co-mention")
                    if key in edge_map:
                        edge_map[key]["weight"] += 1
                    else:
                        edge_map[key] = {
                            "source": s,
                            "target": t,
                            "edge_type": "co-mention",
                            "relation": "shares-tag",
                            "weight": 1,
                            "metadata": {"tag": tag},
                        }

        # ----------------------------------------------------------
        # 4. Compute node weights (total edge connections)
        # ----------------------------------------------------------
        for s, t, _ in edge_map:
            nodes[s].weight += 1
            nodes[t].weight += 1

        # ----------------------------------------------------------
        # 5. BFS degree computation (only when focus is given)
        # ----------------------------------------------------------
        if focus is not None:
            if focus not in nodes:
                logger.warning("[GRAPH] Focus node not found: %s", focus)
                return GraphData(focus=focus)

            # Build adjacency list from all edges
            adjacency: dict[str, set[str]] = {p: set() for p in nodes}
            for s, t, _ in edge_map:
                adjacency[s].add(t)
                adjacency[t].add(s)

            # BFS
            degrees: dict[str, int] = {focus: 0}
            queue: deque[str] = deque([focus])
            while queue:
                current = queue.popleft()
                current_degree = degrees[current]
                if current_degree >= max_degree:
                    continue
                for neighbour in adjacency.get(current, set()):
                    if neighbour not in degrees:
                        degrees[neighbour] = current_degree + 1
                        queue.append(neighbour)

            # Assign degrees; nodes not reachable within max_degree are dropped
            reachable: set[str] = set()
            for path, node in nodes.items():
                deg = degrees.get(path)
                if deg is not None and deg <= max_degree:
                    node.degree = deg
                    reachable.add(path)

            nodes = {p: n for p, n in nodes.items() if p in reachable}
            edge_map = {
                k: v
                for k, v in edge_map.items()
                if k[0] in reachable and k[1] in reachable
            }

        # ----------------------------------------------------------
        # 6. Apply types filter
        # ----------------------------------------------------------
        if types:
            type_set = set(types)
            nodes = {p: n for p, n in nodes.items() if n.type in type_set}
            edge_map = {
                k: v
                for k, v in edge_map.items()
                if k[0] in nodes and k[1] in nodes
            }

        # ----------------------------------------------------------
        # 7. Assemble final GraphData
        # ----------------------------------------------------------
        final_edges = [
            GraphEdge(
                source=v["source"],
                target=v["target"],
                edge_type=v["edge_type"],
                relation=v["relation"],
                weight=v["weight"],
                metadata=v["metadata"],
            )
            for v in edge_map.values()
        ]

        return GraphData(
            focus=focus,
            nodes=list(nodes.values()),
            edges=final_edges,
        )
