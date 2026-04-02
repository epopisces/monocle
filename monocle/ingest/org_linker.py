"""
monocle/ingest/org_linker.py — Cross-link person notes to organization notes.

When a person note is ingested with an ``organizations`` frontmatter field,
this module:

1. Iterates each ``organizations`` entry (name, role, join_date, leave_date, current).
2. Attempts to resolve an existing organization note via ``VaultLayer.resolve_wikilink``.
3. If no org note exists, auto-creates a stub organization note
   (``review_status: "pending"``) via ``VaultLayer.create_from_template`` +
   ``VaultLayer.write_note``.
4. Patches the person note's ``links`` field to add a ``{relation: "works-at"}``
   structured link for each org, carrying temporal metadata (join_date,
   leave_date, current, role) as flat link keys for clean ``LinkRef.metadata``
   deserialization.

This function is called from ``IngestPipeline.run()`` after step 8 (frontmatter
patch) for person notes only.  Failures are logged as warnings and do not
propagate — org-linking is best-effort and must not abort the ingest.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from monocle.models import Note
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Kebab-case slug — mirrors ``VaultLayer._slugify``."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "untitled"


def _link_to_patch_dict(lnk: Any) -> dict[str, Any]:
    """Convert a ``LinkRef`` to a flat dict suitable for ``patch_frontmatter``.

    Uses the flat format so that on the next read, ``parse_links_field`` puts
    extra keys directly into ``LinkRef.metadata`` (not nested under a
    ``"metadata"`` sub-key).

    Handles the nested ``{"metadata": {...}}`` structure that results when a
    link was previously written by ``_note_to_markdown`` (which uses
    ``lnk.model_dump()``).
    """
    d: dict[str, Any] = {"target": lnk.target}
    if lnk.relation:
        d["relation"] = lnk.relation
    meta: dict[str, Any] = lnk.metadata or {}
    # _note_to_markdown writes {"metadata": {...}} nesting; flatten it here
    if len(meta) == 1 and "metadata" in meta and isinstance(meta.get("metadata"), dict):
        d.update(meta["metadata"])
    else:
        d.update(meta)
    return d


def wire_org_links(note: "Note", vault: "VaultLayer") -> None:
    """Resolve or create org stubs and patch the person note's ``links`` field.

    Args:
        note:  The person ``Note`` already written to disk (step 8 complete).
        vault: The ``VaultLayer`` instance for resolution, creation, and patching.

    This function is a **no-op** for non-person notes or notes without an
    ``organizations`` field.
    """
    if note.metadata.type != "person_note":
        return

    # `organizations` lives in model_extra because NoteMetadata uses extra="allow"
    org_entries: list[Any] = (note.metadata.model_extra or {}).get("organizations") or []
    if not org_entries:
        return

    # Normalise: accept both dicts (preferred) and plain strings
    normalised: list[dict[str, Any]] = []
    for entry in org_entries:
        if isinstance(entry, str) and entry.strip():
            normalised.append({"name": entry.strip()})
        elif isinstance(entry, dict) and entry.get("name"):
            normalised.append(entry)

    if not normalised:
        return

    # Build set of already-linked org paths (to avoid duplicate links)
    existing_resolved: set[str] = set()
    for lnk in note.metadata.links:
        # Resolve display names to vault paths for accurate dedup
        resolved = vault.resolve_wikilink(lnk.target)
        existing_resolved.add(resolved if resolved else lnk.target)

    # Flat-dict representations of existing links for final patch
    existing_link_dicts: list[dict[str, Any]] = [
        _link_to_patch_dict(lnk) for lnk in note.metadata.links
    ]
    links_to_add: list[dict[str, Any]] = []

    for org in normalised:
        org_name: str = str(org["name"])
        slug = _slugify(org_name)

        # 1. Try to resolve an existing org note by slug path then by name
        candidate_path = vault.resolve_wikilink(f"organizations/{slug}")
        if candidate_path is None:
            candidate_path = vault.resolve_wikilink(org_name)

        # 2. Auto-create a stub if no existing org note found
        if candidate_path is None:
            try:
                stub_metadata: dict[str, Any] = {
                    "name": org_name,
                    "domain": note.metadata.domain,
                    "review_status": "pending",
                    "source": note.metadata.source,
                }
                if org.get("short_name"):
                    stub_metadata["short_name"] = org["short_name"]
                stub = vault.create_from_template("organization", stub_metadata)
                vault.write_note(stub.file_path, stub)
                candidate_path = stub.file_path
                logger.info(
                    "[ORG-LINK] Created stub org note: '%s' → %s",
                    org_name,
                    candidate_path,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ORG-LINK] Failed to create stub org for '%s': %s", org_name, exc
                )
                continue

        # 3. Skip if this org is already linked
        if candidate_path in existing_resolved:
            logger.debug(
                "[ORG-LINK] %s already links to %s — skipping",
                note.file_path,
                candidate_path,
            )
            continue

        # 4. Build flat link dict (extra keys → LinkRef.metadata on next read)
        link_dict: dict[str, Any] = {
            "target": candidate_path,
            "relation": "works-at",
        }
        for key in ("role", "join_date", "leave_date", "current"):
            val = org.get(key)
            if val is not None:
                link_dict[key] = val

        links_to_add.append(link_dict)
        existing_resolved.add(candidate_path)

    if not links_to_add:
        return

    all_links = existing_link_dicts + links_to_add
    try:
        vault.patch_frontmatter(note.file_path, {"links": all_links})
        logger.info(
            "[ORG-LINK] Patched links on %s (+%d org link(s))",
            note.file_path,
            len(links_to_add),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ORG-LINK] Failed to patch links on %s: %s", note.file_path, exc
        )
