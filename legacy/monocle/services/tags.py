"""monocle/services/tags.py — Shared tag normalisation utility.

Provides a single canonical ``normalize_tags()`` function used by the MCP
layer (``BeforeValidator``), the agent tool layer, and the services layer
to coerce varied LLM-produced tag formats into a flat ``list[str]``.
"""
from __future__ import annotations

import json
from typing import Any


def normalize_tags(value: Any) -> list[str] | None:
    """Normalise tags from various LLM-produced formats to a flat ``list[str]``.

    The LLM may send tags as:
    - A proper JSON array: ``["work", "python"]``
    - A Python dict string: ``"{'hobbies': ['Lego', 'programming']}"``
    - A JSON object string: ``'{"hobbies": ["Lego"]}'``
    - A plain comma-separated string: ``"work, python"``
    - Already a list, dict, or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return [str(t) for t in value if t is not None]
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
            return normalize_tags(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        # Try Python literal eval (handles single-quoted strings / Python dicts)
        try:
            import ast
            parsed = ast.literal_eval(s)
            return normalize_tags(parsed)
        except (ValueError, SyntaxError):
            pass
        # Final fallback: comma-separated plain text
        return [t.strip() for t in s.split(",") if t.strip()] or None
    return [str(value)]
