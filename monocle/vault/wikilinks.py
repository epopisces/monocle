"""
monocle/vault/wikilinks.py — Wikilink parsing and resolution helpers.

Three public functions:

- ``parse_wikilinks(body)``   → list of raw link targets extracted from [[…]]
- ``parse_links_field(links)`` → normalise a YAML ``links:`` list to LinkRef objects
- ``resolve_wikilink(name, vault_root)`` → case-insensitive file match → vault-relative path
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from monocle.models import LinkRef

# Matches [[Note Name]] and [[Note Name|Alias]] — captures the target part only.
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]")


def parse_wikilinks(body: str) -> list[str]:
    """Return a list of wikilink targets found in *body*.

    Given::

        "See [[Sarah Chen]] and [[Q4 Project|alias]]"

    Returns::

        ["Sarah Chen", "Q4 Project"]

    Duplicate targets are preserved (ordering matters for weight counts in M9).
    """
    return _WIKILINK_RE.findall(body)


def parse_links_field(links: list[Any] | None) -> list[LinkRef]:
    """Normalise the YAML ``links:`` frontmatter list into ``LinkRef`` objects.

    Each item may be:
    - A plain string: treated as the ``target`` with no relation metadata.
    - A dict: must contain ``target``; relation and arbitrary extra keys are
      forwarded to ``LinkRef.metadata``.

    Examples::

        parse_links_field(["Sarah Chen"])
        # → [LinkRef(target="Sarah Chen")]

        parse_links_field([{"target": "Q4 Project", "relation": "manages"}])
        # → [LinkRef(target="Q4 Project", relation="manages")]

        parse_links_field(None)
        # → []
    """
    if not links:
        return []

    result: list[LinkRef] = []
    for item in links:
        if isinstance(item, str):
            result.append(LinkRef(target=item))
        elif isinstance(item, dict):
            item = dict(item)  # defensive copy
            target = item.pop("target", None)
            if not target:
                continue  # skip malformed entries without a target
            relation = item.pop("relation", None)
            # Any remaining keys become LinkRef.metadata
            result.append(LinkRef(target=str(target), relation=relation, metadata=item))
        # Skip any other types silently
    return result


def resolve_wikilink(name: str, vault_root: str | Path) -> str | None:
    """Search *vault_root* for a note whose stem matches *name* (case-insensitive).

    The search is case-insensitive on both the raw filename and a slugified
    variant. Returns the vault-relative path (forward-slash separated) of the
    first match, or ``None`` if not found.

    Hidden directories (``.versions``, ``.trash``, ``.obsidian``) are skipped.

    Args:
        name: The wikilink target — e.g. ``"Sarah Chen"`` or ``"sarah-chen"``.
        vault_root: Absolute path to the vault root directory.

    Returns:
        Vault-relative path such as ``"people/sarah-chen.md"`` or ``None``.
    """
    root = Path(vault_root)
    if not root.is_dir():
        return None

    name_lower = name.lower()
    # Build a slug variant for comparison: "Sarah Chen" → "sarah-chen"
    name_slug = re.sub(r"[\s_]+", "-", re.sub(r"[^\w\s-]", "", name_lower)).strip("-")

    def _slugify(text: str) -> str:
        """Helper to convert any stem to slugified form."""
        return re.sub(r"[\s_]+", "-", re.sub(r"[^\w\s-]", "", text.lower())).strip("-")

    for md_file in root.rglob("*.md"):
        # Skip hidden/system directories
        relative = md_file.relative_to(root)
        parts = relative.parts
        if any(part.startswith(".") for part in parts):
            continue

        stem_lower = md_file.stem.lower()
        stem_slug = _slugify(md_file.stem)
        # Bidirectional matching: compare all combinations
        if stem_lower == name_lower or stem_lower == name_slug or stem_slug == name_lower or stem_slug == name_slug:
            # Return with forward slashes for cross-platform consistency
            return str(relative).replace(os.sep, "/")

    return None
