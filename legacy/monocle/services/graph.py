"""monocle/services/graph.py — Canonical get_graph service."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monocle.graph import GraphBuilder
    from monocle.models import GraphData

logger = logging.getLogger(__name__)


async def get_graph(
    graph_builder: "GraphBuilder",
    focus: str | None = None,
    max_degree: int = 2,
    types: tuple[str, ...] | None = None,
    n: int = 500,
) -> "GraphData":
    """Return a relationship graph centred on *focus* (or the full vault).

    Args:
        graph_builder: The ``GraphBuilder`` instance.
        focus: Vault-relative file path for ego-graph, or ``None`` for full vault.
        max_degree: BFS depth from the focus node (ignored in full-vault mode).
        types: Optional tuple of node types to include (post-BFS filter).
        n: Maximum number of nodes to return.

    Returns:
        A ``GraphData`` model with nodes and edges.
    """
    return await asyncio.to_thread(
        graph_builder.build,
        focus,
        max_degree,
        types,
        n,
    )
