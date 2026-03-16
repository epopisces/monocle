"""
monocle/agents/reindex.py — ReindexAgent stub.

Scans vault .md files and re-embeds those that have changed since last index.

Wired in M5.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ReindexAgent:
    """Full-vault re-index agent.

    Wired in M5.
    """

    async def run(self, force: bool = False) -> None:
        """Re-index the vault (stub in M1)."""
        logger.debug("ReindexAgent.run(force=%s) — stub (wired in M5)", force)

    async def startup_check(self) -> None:
        """Run a full re-index on startup if the index is empty."""
        logger.debug("ReindexAgent.startup_check() — stub (wired in M5)")
