"""
monocle/agents/routing.py — RoutingAgent stub.

Fast-path: checks template sentence_starters (no LLM call).
Slow-path: falls back to LLM classification via prompts/routing.md.

Wired in M7.
"""
from __future__ import annotations

import logging

from monocle.models import RoutingDecision

logger = logging.getLogger(__name__)


class RoutingAgent:
    """Dispatch raw content to the appropriate note template.

    Wired in M7.
    """

    async def route(
        self,
        text: str,
        template_hint: str | None = None,
    ) -> RoutingDecision:
        """Return a routing decision for *text* (stub in M1)."""
        logger.debug("RoutingAgent.route() — stub (wired in M7)")
        return RoutingDecision(template="blank", note_type="other", confidence=0.0)
