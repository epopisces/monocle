"""monocle/routers/graph.py — Knowledge graph endpoint."""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request

from monocle.models import GraphData

router = APIRouter(tags=["graph"])
logger = logging.getLogger(__name__)


@router.get("/graph", response_model=GraphData)
async def get_graph(
    request: Request,
    focus: str | None = Query(None, description="Vault-relative path of the focal note"),
    max_degree: int = Query(3, ge=1, le=6, description="Max BFS hops from focus"),
    types: Annotated[list[str] | None, Query()] = None,
    n: int = Query(500, ge=1, le=2000, description="Max notes to include"),
) -> GraphData:
    """Return the knowledge graph, optionally centred on a focal note.

    - **focus** — vault-relative path (e.g. ``people/sarah.md``).  When
      omitted, the full-vault graph is returned.
    - **max_degree** — maximum BFS distance from the focus node (default 3).
    - **types** — comma-separated list of note types to include (e.g.
      ``person_note,meeting_note``).  Pass multiple ``types=`` parameters or
      use repeated values.  When omitted all types are included.
    - **n** — maximum number of vault notes considered (default 500).
    """
    graph_builder = request.app.state.graph_builder
    return await asyncio.to_thread(
        graph_builder.build,
        focus=focus,
        max_degree=max_degree,
        types=types,
        n=n,
    )
