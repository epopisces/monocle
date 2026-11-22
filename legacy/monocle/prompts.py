"""
monocle/prompts.py — Prompt loading helper.

Provides a single function ``load_prompt(name)`` that:
1. Tries ``prompts/local/<name>.md`` first (user overrides, gitignored).
2. Falls back to ``prompts/<name>.md`` (committed defaults).
3. Strips YAML frontmatter (``---...---`` block at the top) from the file.
4. Returns the prompt body as a plain string.

Usage::

    from monocle.prompts import load_prompt

    routing_prompt = load_prompt("routing")   # → body of prompts/routing.md
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   Package-relative prompts directory (resolved once at import time)
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter block from the beginning of *content*.

    If the file begins with ``---``, find the matching closing ``---`` and
    return everything after it (stripped).  Leaves content unchanged if no
    frontmatter is found.
    """
    if not content.startswith("---"):
        return content.strip()
    end = content.find("---", 3)
    if end == -1:
        return content.strip()
    return content[end + 3 :].strip()


def load_prompt(name: str) -> str:
    """Load a prompt file by name, stripping YAML frontmatter.

    Search order:
    1. ``prompts/local/<name>.md``  — gitignored user overrides
    2. ``prompts/<name>.md``        — committed defaults

    Args:
        name: Prompt file stem, e.g. ``"routing"`` for ``prompts/routing.md``.

    Returns:
        Prompt body (frontmatter stripped).  Returns an empty string when
        neither file exists (with a WARNING log).
    """
    candidates = [
        _PROMPTS_DIR / "local" / f"{name}.md",
        _PROMPTS_DIR / f"{name}.md",
    ]
    for path in candidates:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            body = _strip_frontmatter(content)
            logger.debug("load_prompt: loaded %s from %s", name, path)
            return body

    logger.warning("load_prompt: prompt file '%s.md' not found in prompts/ or prompts/local/", name)
    return ""
