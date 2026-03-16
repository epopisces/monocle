"""
monocle/vault/__init__.py — VaultLayer: all filesystem operations for vault notes.

Responsibilities:
- CRUD for Markdown notes (read, write, patch, delete, move)
- Atomic writes via system tempdir + os.replace
- Shadow versions in <vault>/.versions/<path>/<timestamp>.md
- Soft-delete to <vault>/.trash/<path>
- Frontmatter schema normalisation on read
- Template-based note construction (in-memory, no file write)
- Wikilink resolution
- Path traversal protection (every path resolved + validated against vault root)
"""
from __future__ import annotations

import functools
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

from monocle.models import LinkRef, Note, NoteMetadata, NoteRef, Page
from monocle.vault.normalise import normalise_frontmatter
from monocle.vault.wikilinks import (
    parse_links_field,
    parse_wikilinks,
    resolve_wikilink as _resolve_wikilink,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template type → filename mapping
# ---------------------------------------------------------------------------

TEMPLATE_FILE_MAP: dict[str, str] = {
    "person_note": "person",
    "person": "person",
    "decision": "decision",
    "project": "project",
    "meeting_note": "meeting",
    "meeting": "meeting",
    "idea": "idea",
    "observation": "observation",
    "reference": "reference",
    "action_item": "action_item",
    "weekly_summary": "weekly_summary",
    "other": "blank",
    "blank": "blank",
}


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class NoteNotFound(HTTPException):
    """Raised when a requested note file does not exist."""

    def __init__(self, file_path: str) -> None:
        super().__init__(status_code=404, detail=f"Note not found: {file_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_timestamp() -> str:
    """Return current UTC time as a Windows-safe millisecond ISO 8601 string.

    Colons are replaced with hyphens so the string can be used as a filename
    on Windows (which prohibits colons in filenames). The result is still
    lexicographically sortable.

    Example: ``"2026-03-16T10-30-45.123Z"``
    """
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H-%M-%S.") + f"{dt.microsecond // 1000:03d}Z"


def _slugify(text: str) -> str:
    """Convert a title string to a kebab-case filename slug.

    Returns ``"untitled"`` if the result would be empty.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "untitled"


@functools.lru_cache(maxsize=None)
def _load_template_schema(template_name: str) -> dict[str, Any]:
    """Load and LRU-cache a YAML template schema by name.

    Falls back to ``blank.yaml`` for unknown template names.
    """
    template_dir = Path(__file__).parent / "templates"
    yaml_file = template_dir / f"{template_name}.yaml"
    if not yaml_file.exists():
        yaml_file = template_dir / "blank.yaml"
    with open(yaml_file, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _parse_note_file(path: Path, relative_path: str) -> Note:
    """Parse a Markdown file at *path* into a :class:`Note` model.

    Uses ``python-frontmatter`` for YAML frontmatter extraction.
    ``normalise_frontmatter`` is applied so all schema defaults are present.
    """
    import frontmatter as _frontmatter  # lazy import

    text = path.read_text(encoding="utf-8")
    try:
        post = _frontmatter.loads(text)
    except Exception:
        post = _frontmatter.Post(content=text)

    fm: dict[str, Any] = dict(post.metadata)
    normalise_frontmatter(fm)

    # Normalise structured links before constructing NoteMetadata
    raw_links = fm.pop("links", None) or []
    parsed_links = parse_links_field(raw_links)

    # title is not a NoteMetadata field — extract separately
    title: str = fm.pop("title", None) or Path(path.stem).name

    try:
        metadata = NoteMetadata(**fm, links=parsed_links)
    except Exception as exc:
        logger.warning("Failed to parse note metadata for %s: %s", relative_path, exc)
        metadata = NoteMetadata(links=parsed_links)

    mtime = path.stat().st_mtime

    return Note(
        file_path=relative_path,
        title=title,
        body=post.content,
        metadata=metadata,
        mtime=mtime,
    )


def _note_to_markdown(note: Note) -> str:
    """Serialise a :class:`Note` to Obsidian-compatible Markdown."""
    fm: dict[str, Any] = {"title": note.title}

    if note.metadata:
        raw = note.metadata.model_dump()
        # Serialize LinkRef objects → plain dicts (omit None values)
        fm["links"] = [
            {k: v for k, v in lnk.model_dump().items() if v is not None}
            for lnk in (raw.pop("links", None) or [])
        ]
        # Convert datetime objects → ISO strings
        for dt_field in ("created", "updated", "approved_at"):
            val = raw.get(dt_field)
            if isinstance(val, datetime):
                raw[dt_field] = val.isoformat()
        fm.update(raw)

    body = note.body or ""
    return f"---\n{yaml.dump(fm, default_flow_style=False, allow_unicode=True)}---\n\n{body}\n"


# ---------------------------------------------------------------------------
# VaultLayer
# ---------------------------------------------------------------------------


class VaultLayer:
    """All filesystem operations for vault notes.

    Args:
        vault_path: Path to the vault root directory. Resolved to an absolute
            realpath at construction time for robust path-security checks.
    """

    def __init__(self, vault_path: str | Path) -> None:
        self.root = Path(os.path.realpath(str(vault_path)))
        self.root.mkdir(parents=True, exist_ok=True)
        logger.debug("VaultLayer initialised at %s", self.root)

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    def _safe_resolve(self, file_path: str) -> Path:
        """Resolve *file_path* to an absolute path and reject traversal.

        Raises ``HTTPException(403)`` if the resolved path escapes the
        vault root or is a symlink that resolves outside the vault.
        """
        if os.path.isabs(file_path):
            resolved = Path(os.path.realpath(file_path))
        else:
            resolved = Path(os.path.realpath(os.path.join(str(self.root), file_path)))

        try:
            resolved.relative_to(self.root)
        except ValueError:
            logger.warning("Path traversal attempt blocked: %r", file_path)
            raise HTTPException(status_code=403, detail="Path traversal denied")

        return resolved

    def _to_relative(self, absolute: Path) -> str:
        """Return vault-relative forward-slash path for *absolute*."""
        return str(absolute.relative_to(self.root)).replace(os.sep, "/")

    # ------------------------------------------------------------------
    # Versioning & trash helpers
    # ------------------------------------------------------------------

    def _version_dir(self, relative_path: str) -> Path:
        """Return the ``.versions/<relative_path>/`` directory path."""
        return self.root / ".versions" / relative_path

    def _shadow_version(self, relative_path: str, resolved: Path) -> None:
        """Copy *resolved* to the shadow ``.versions/`` directory."""
        version_dir = self._version_dir(relative_path)
        version_dir.mkdir(parents=True, exist_ok=True)
        ts = _ms_timestamp()
        version_file = version_dir / f"{ts}.md"
        shutil.copy2(str(resolved), str(version_file))
        logger.debug("Versioned %s → %s", relative_path, version_file.name)

    def _trash_path(self, relative_path: str) -> Path:
        """Return the ``.trash/<relative_path>`` destination path."""
        return self.root / ".trash" / relative_path

    # ------------------------------------------------------------------
    # Atomic write helper
    # ------------------------------------------------------------------

    def _atomic_write(self, target: Path, content: str) -> None:
        """Write *content* to *target* atomically via system tempdir.

        Creates a temp file in the system tempdir, writes content,
        then uses ``os.replace`` for an atomic rename.  Falls back to
        ``shutil.move`` on cross-device scenarios (e.g. Windows cross-drive).
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="monocle_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            try:
                os.replace(tmp_path, str(target))
                tmp_path = None  # replace succeeded; no cleanup needed
            except OSError:
                shutil.move(tmp_path, str(target))
                tmp_path = None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Public API — CRUD
    # ------------------------------------------------------------------

    def list_notes(
        self,
        folder: str | None = None,
        type: str | None = None,
        domain: str | None = None,
        sort: str = "updated",
        limit: int = 50,
        offset: int = 0,
    ) -> "Page[NoteRef]":
        """Return a paginated list of :class:`NoteRef` objects.

        Args:
            folder: Vault-relative subdirectory to restrict the scan to.
            type:   Frontmatter ``type`` filter.
            domain: Frontmatter ``domain`` filter.
            sort:   Sort column — ``"updated"`` (desc), ``"created"`` (desc),
                    or ``"title"`` (asc).
            limit:  Page size.
            offset: Zero-based record offset.
        """
        if folder:
            scan_root = self._safe_resolve(folder)
        else:
            scan_root = self.root

        refs: list[NoteRef] = []
        for md_file in sorted(scan_root.rglob("*.md")):
            # Skip hidden/system directories (.versions, .trash, .obsidian…)
            rel_parts = md_file.relative_to(self.root).parts
            if any(p.startswith(".") for p in rel_parts):
                continue

            relative = self._to_relative(md_file)
            try:
                note = _parse_note_file(md_file, relative)
            except Exception as exc:
                logger.warning("Skipping unreadable note %s: %s", relative, exc)
                continue

            if type and note.metadata.type != type:
                continue
            if domain and note.metadata.domain != domain:
                continue

            refs.append(
                NoteRef(
                    file_path=relative,
                    title=note.title,
                    type=note.metadata.type,
                    domain=note.metadata.domain,
                    tags=list(note.metadata.tags),
                    created=note.metadata.created,
                    updated=note.metadata.updated,
                    confidence=note.metadata.confidence,
                    review_status=note.metadata.review_status,
                )
            )

        # Sort
        sort_key = sort.lstrip("-")
        descending = sort_key in ("updated", "created") or sort.startswith("-")

        def _sort_value(ref: NoteRef) -> Any:
            if sort_key == "updated":
                return ref.updated or datetime.min.replace(tzinfo=timezone.utc)
            if sort_key == "created":
                return ref.created or datetime.min.replace(tzinfo=timezone.utc)
            return ref.title.lower()

        refs.sort(key=_sort_value, reverse=descending)

        total = len(refs)
        return Page(items=refs[offset : offset + limit], total=total, offset=offset, limit=limit)

    def read_note(self, file_path: str) -> Note:
        """Read and parse a note file.

        Raises:
            HTTPException(403): Path traversal detected.
            NoteNotFound(404):  File does not exist.
        """
        resolved = self._safe_resolve(file_path)
        if not resolved.exists():
            raise NoteNotFound(file_path)
        relative = self._to_relative(resolved)
        return _parse_note_file(resolved, relative)

    def write_note(
        self,
        file_path: str,
        note: Note,
        if_mtime: float | None = None,
    ) -> None:
        """Write (create or overwrite) a note atomically.

        If the file already exists:
        - Raises 409 if *if_mtime* is provided and does not match.
        - Creates a shadow version in ``.versions/`` before overwriting.

        Raises:
            HTTPException(403): Path traversal.
            HTTPException(409): Mtime conflict.
        """
        target = self._safe_resolve(file_path)

        if target.exists():
            current_mtime = target.stat().st_mtime
            if if_mtime is not None and abs(current_mtime - if_mtime) > 0.01:
                raise HTTPException(
                    status_code=409,
                    detail=f"Conflict: note modified (expected mtime={if_mtime:.3f}, "
                    f"actual={current_mtime:.3f})",
                )
            self._shadow_version(self._to_relative(target), target)

        content = _note_to_markdown(note)
        self._atomic_write(target, content)
        logger.info("Written note: %s", file_path)

    def patch_frontmatter(self, file_path: str, updates: dict[str, Any]) -> Note:
        """Merge-update the frontmatter of a note, leaving the body intact.

        Shadow-versions the file before patching.

        Returns:
            The updated :class:`Note`.

        Raises:
            NoteNotFound(404): File does not exist.
            HTTPException(403): Path traversal.
        """
        import frontmatter as _frontmatter

        resolved = self._safe_resolve(file_path)
        if not resolved.exists():
            raise NoteNotFound(file_path)

        text = resolved.read_text(encoding="utf-8")
        try:
            post = _frontmatter.loads(text)
        except Exception:
            post = _frontmatter.Post(content=text)

        fm = dict(post.metadata)
        fm.update(updates)

        # Shadow before patching
        self._shadow_version(self._to_relative(resolved), resolved)

        frontmatter_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter_str}---\n\n{post.content}\n"
        self._atomic_write(resolved, content)
        logger.info("Patched frontmatter: %s (%s)", file_path, list(updates.keys()))

        return self.read_note(file_path)

    def delete_note(self, file_path: str) -> None:
        """Soft-delete a note by moving it to ``.trash/``.

        The original file is never removed from the filesystem.

        Raises:
            NoteNotFound(404): File does not exist.
            HTTPException(403): Path traversal.
        """
        resolved = self._safe_resolve(file_path)
        if not resolved.exists():
            raise NoteNotFound(file_path)

        trash_target = self._trash_path(self._to_relative(resolved))
        trash_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved), str(trash_target))
        logger.info("Soft-deleted note: %s → %s", file_path, trash_target)

    def move_note(self, from_path: str, to_path: str) -> None:
        """Move (rename) a note within the vault.

        Raises:
            NoteNotFound(404): Source does not exist.
            HTTPException(403): Path traversal on either path.
            HTTPException(409): Destination already exists.
        """
        src = self._safe_resolve(from_path)
        dst = self._safe_resolve(to_path)

        if not src.exists():
            raise NoteNotFound(from_path)
        if dst.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Destination already exists: {to_path}",
            )

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        logger.info("Moved note: %s → %s", from_path, to_path)

    # ------------------------------------------------------------------
    # Template-based construction
    # ------------------------------------------------------------------

    def create_from_template(
        self,
        template_type: str,
        metadata: dict[str, Any],
        body: str = "",
    ) -> Note:
        """Construct a :class:`Note` in memory from a template schema.

        **Does not write to disk.** Call :meth:`write_note` to persist.

        Args:
            template_type: Template key — e.g. ``"person"``, ``"decision"``,
                           ``"meeting_note"``.
            metadata:      Frontmatter values from metadata extraction.
            body:          Markdown body text.

        Returns:
            A :class:`Note` with ``file_path`` set to
            ``<default_folder>/<slug>.md``.
        """
        schema_name = TEMPLATE_FILE_MAP.get(template_type, "blank")
        schema = _load_template_schema(schema_name)

        default_folder: str = schema.get("default_folder", "inbox")
        note_type: str = schema.get("note_type", "other")

        # Determine domain, preferring caller metadata, then schema default, then "personal"
        schema_default_domain: str | None = None
        fields = schema.get("fields")
        if isinstance(fields, dict):
            domain_field = fields.get("domain")
            if isinstance(domain_field, dict):
                schema_default_domain = domain_field.get("default")
        domain_value: str = metadata.get("domain") or schema_default_domain or "personal"

        # Derive title and filename
        people_list = metadata.get("people") or []
        title: str = (
            metadata.get("title")
            or (people_list[0] if people_list else None)
            or template_type.replace("_", " ").title()
        )
        slug = _slugify(str(title))
        file_path = f"{default_folder}/{slug}.md"

        # Build merged frontmatter dict
        now = datetime.now(timezone.utc)
        fm: dict[str, Any] = {
            "type": note_type,
            "template": schema_name,
            "domain": domain_value,
            "tags": [],
            "people": [],
            "action_items": [],
            "source": "web",
            "created": now,
            "updated": now,
            "confidence": 1.0,
            "review_status": "pending",
            "approved_by": None,
            "approved_at": None,
            "approval_mode": None,
        }
        fm.update(metadata)
        fm.pop("title", None)  # title lives on Note, not NoteMetadata

        raw_links = fm.pop("links", None) or []
        parsed_links = parse_links_field(raw_links)

        try:
            note_metadata = NoteMetadata(**fm, links=parsed_links)
        except Exception as exc:
            logger.warning("create_from_template validation error: %s", exc)
            note_metadata = NoteMetadata(links=parsed_links)

        return Note(
            file_path=file_path,
            title=str(title),
            body=body,
            metadata=note_metadata,
        )

    # ------------------------------------------------------------------
    # Wikilink resolution
    # ------------------------------------------------------------------

    def resolve_wikilink(self, name: str) -> str | None:
        """Case-insensitive wikilink resolution within this vault.

        Returns vault-relative path (forward-slash) or ``None``.
        """
        return _resolve_wikilink(name, self.root)

    # ------------------------------------------------------------------
    # Version management
    # ------------------------------------------------------------------

    def list_versions(self, file_path: str) -> list[str]:
        """List all version timestamps for *file_path*, oldest-first.

        Returns timestamp strings (filename stems, without ``.md``).

        Raises:
            HTTPException(403): Path traversal.
        """
        resolved = self._safe_resolve(file_path)  # validate and resolve
        relative = self._to_relative(resolved)  # ensure relative path
        version_dir = self._version_dir(relative)
        if not version_dir.exists():
            return []
        return sorted(f.stem for f in version_dir.glob("*.md"))

    def restore_version(self, file_path: str, timestamp: str) -> None:
        """Restore a note from a historical version.

        Shadow-versions the current file before replacing it.

        Raises:
            NoteNotFound(404): Note or version not found.
            HTTPException(403): Path traversal or invalid timestamp.
        """
        # Validate timestamp format: must match _ms_timestamp() pattern
        # Pattern: YYYY-MM-DDTHH-MM-SS.mmmZ (e.g. 2026-03-16T10-30-45.123Z)
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}Z$", timestamp):
            raise HTTPException(
                status_code=403,
                detail="Invalid timestamp format",
            )

        resolved = self._safe_resolve(file_path)
        relative = self._to_relative(resolved)
        version_dir = self._version_dir(relative)
        version_file = version_dir / f"{timestamp}.md"

        # Ensure version_file is within the intended version directory tree
        try:
            version_file.relative_to(version_dir)
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail="Invalid version path",
            )

        if not version_file.exists():
            raise NoteNotFound(f"{file_path}@{timestamp}")

        if resolved.exists():
            self._shadow_version(relative, resolved)

        resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(version_file), str(resolved))
        logger.info("Restored %s from version %s", file_path, timestamp)

    # ------------------------------------------------------------------
    # Template listing
    # ------------------------------------------------------------------

    def list_templates(self) -> list[dict[str, Any]]:
        """Return metadata for all built-in note templates.

        Returns a list of template schema dicts sorted by template name.
        """
        template_dir = Path(__file__).parent / "templates"
        schemas: list[dict[str, Any]] = []
        for yaml_file in sorted(template_dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as fh:
                    schema = yaml.safe_load(fh) or {}
                schemas.append(schema)
            except Exception as exc:
                logger.warning("Could not load template %s: %s", yaml_file.name, exc)
        return schemas
