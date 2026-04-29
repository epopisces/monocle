"""AI-free cached catalog for topbar omnisearch."""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Literal

if False:  # pragma: no cover
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)

_FULL_SCAN_LIMIT = 1_000_000
_EXCERPT_WIDTH = 200
_EXCERPT_LEAD = 60


@dataclass(slots=True)
class OmniCatalogEntry:
    file_path: str
    title: str
    filename_excerpt: str
    filename_search: str
    frontmatter_excerpt: str
    frontmatter_search: str
    body_text: str
    body_search: str


class OmniSearchCatalog:
    """Caches a text-only vault catalog so omnisearch avoids per-request disk scans."""

    def __init__(self, vault: "VaultLayer") -> None:
        self._vault = vault
        self._lock = threading.RLock()
        self._entries: dict[str, OmniCatalogEntry] = {}
        self._dirty_paths: set[str] = set()
        self._built = False

    def invalidate(self, file_path: str | None = None) -> None:
        with self._lock:
            if file_path is None:
                self._entries.clear()
                self._dirty_paths.clear()
                self._built = False
                return
            self._dirty_paths.add(file_path)

    def search(self, query: str, limit: int) -> list[dict[str, str]]:
        query = query.strip()
        if len(query) < 3:
            return []

        self._ensure_catalog_current()
        needle = query.casefold()

        with self._lock:
            entries = tuple(self._entries.values())

        filename_hits: list[dict[str, str]] = []
        frontmatter_hits: list[dict[str, str]] = []
        body_hits: list[dict[str, str]] = []

        for entry in entries:
            if needle in entry.filename_search:
                filename_hits.append(
                    {
                        "file_path": entry.file_path,
                        "title": entry.title,
                        "excerpt": entry.filename_excerpt,
                        "match_location": "filename",
                    }
                )
                continue

            if needle in entry.frontmatter_search:
                frontmatter_hits.append(
                    {
                        "file_path": entry.file_path,
                        "title": entry.title,
                        "excerpt": entry.frontmatter_excerpt,
                        "match_location": "frontmatter",
                    }
                )
                continue

            idx = entry.body_search.find(needle)
            if idx >= 0:
                body_hits.append(
                    {
                        "file_path": entry.file_path,
                        "title": entry.title,
                        "excerpt": _compact_whitespace(
                            entry.body_text[max(0, idx - _EXCERPT_LEAD) : max(0, idx - _EXCERPT_LEAD) + _EXCERPT_WIDTH]
                        ),
                        "match_location": "body",
                    }
                )

            if len(filename_hits) + len(frontmatter_hits) + len(body_hits) >= limit:
                # Keep scanning only until the current bucket boundary is satisfied.
                # This preserves strict bucket priority while avoiding a full walk once enough hits exist.
                if not body_hits:
                    continue

        return (filename_hits + frontmatter_hits + body_hits)[:limit]

    def _ensure_catalog_current(self) -> None:
        with self._lock:
            needs_full_build = not self._built
            dirty_paths = tuple(self._dirty_paths)
            self._dirty_paths.clear()

        if needs_full_build:
            entries = self._build_full_catalog()
            with self._lock:
                self._entries = {entry.file_path: entry for entry in entries}
                self._built = True
            return

        if not dirty_paths:
            return

        updates = {file_path: self._load_entry(file_path) for file_path in dirty_paths}
        with self._lock:
            for file_path, entry in updates.items():
                if entry is None:
                    self._entries.pop(file_path, None)
                else:
                    self._entries[file_path] = entry

    def _build_full_catalog(self) -> list[OmniCatalogEntry]:
        refs_page = self._vault.list_notes(limit=_FULL_SCAN_LIMIT)
        if refs_page.total > len(refs_page.items):
            refs_page = self._vault.list_notes(limit=refs_page.total)

        entries: list[OmniCatalogEntry] = []
        for ref in refs_page.items:
            entry = self._load_entry(ref.file_path)
            if entry is not None:
                entries.append(entry)

        logger.debug("[OMNI] Built cached catalog with %d entries", len(entries))
        return entries

    def _load_entry(self, file_path: str) -> OmniCatalogEntry | None:
        try:
            note = self._vault.read_note(file_path)
        except Exception:
            return None

        filename_excerpt = os.path.basename(file_path)
        if filename_excerpt.endswith(".md"):
            filename_excerpt = filename_excerpt[:-3]

        title = note.title or filename_excerpt
        frontmatter_parts = [
            title,
            note.metadata.type,
            note.metadata.domain,
            note.metadata.org or "",
            *note.metadata.people,
            *note.metadata.tags,
        ]
        frontmatter_text = _compact_whitespace(" | ".join(part for part in frontmatter_parts if part))[:_EXCERPT_WIDTH]
        body_text = note.body or ""

        return OmniCatalogEntry(
            file_path=file_path,
            title=title,
            filename_excerpt=filename_excerpt,
            filename_search=filename_excerpt.casefold(),
            frontmatter_excerpt=frontmatter_text,
            frontmatter_search=" ".join(part for part in frontmatter_parts if part).casefold(),
            body_text=body_text,
            body_search=body_text.casefold(),
        )


def _compact_whitespace(text: str) -> str:
    return " ".join(text.split())


OmniMatchLocation = Literal["filename", "frontmatter", "body"]


__all__ = ["OmniSearchCatalog", "OmniMatchLocation"]