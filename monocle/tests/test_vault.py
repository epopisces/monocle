"""
monocle/tests/test_vault.py — Comprehensive tests for the M3 Vault Layer.

Covers:
- normalise_frontmatter schema defaults
- parse_wikilinks / parse_links_field / resolve_wikilink
- VaultLayer CRUD (read, write, patch, delete, move)
- Atomic writes (temp file in system tempdir)
- Versioning (.versions/ shadow copies)
- Soft-delete (.trash/)
- Path traversal protection (403)
- Mtime conflict detection (409)
- create_from_template slug + folder derivation
- list_notes pagination and filtering
- list_versions / restore_version round-trip
"""
from __future__ import annotations

import datetime
import os
import time
from pathlib import Path

import pytest
import yaml

from monocle.models import LinkRef, Note, NoteMetadata
from monocle.vault import NoteNotFound, VaultLayer, _ms_timestamp, _slugify
from monocle.vault.normalise import normalise_frontmatter
from monocle.vault.wikilinks import (
    parse_links_field,
    parse_wikilinks,
    resolve_wikilink,
)


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _write_md(root: Path, rel: str, fm: dict, body: str = "") -> Path:
    """Write a minimal YAML-frontmatter note to `root / rel`."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    merged = {"created": now, "updated": now, **fm}
    content = f"---\n{yaml.dump(merged, default_flow_style=False)}---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


# ============================================================================
# normalise_frontmatter
# ============================================================================


class TestNormaliseFrontmatter:
    def test_missing_type_defaults_to_other(self):
        fm = {}
        result = normalise_frontmatter(fm)
        assert result["type"] == "other"

    def test_existing_type_preserved(self):
        fm = {"type": "decision"}
        result = normalise_frontmatter(fm)
        assert result["type"] == "decision"

    def test_missing_lists_default_to_empty(self):
        fm = {}
        result = normalise_frontmatter(fm)
        assert result["people"] == []
        assert result["tags"] == []
        assert result["action_items"] == []
        assert result["links"] == []

    def test_null_list_fields_coerced_to_empty(self):
        fm = {"people": None, "tags": None, "action_items": None, "links": None}
        result = normalise_frontmatter(fm)
        assert result["people"] == []
        assert result["tags"] == []
        assert result["action_items"] == []
        assert result["links"] == []

    def test_missing_review_status_defaults_to_approved(self):
        fm = {}
        result = normalise_frontmatter(fm)
        assert result["review_status"] == "approved"

    def test_missing_confidence_defaults_to_one(self):
        fm = {}
        result = normalise_frontmatter(fm)
        assert result["confidence"] == 1.0

    def test_missing_approved_fields_default_to_none(self):
        fm = {}
        result = normalise_frontmatter(fm)
        assert result["approved_by"] is None
        assert result["approved_at"] is None
        assert result["approval_mode"] is None

    def test_populated_values_preserved(self):
        fm = {
            "type": "person_note",
            "people": ["Alice"],
            "tags": ["colleague"],
            "confidence": 0.9,
            "review_status": "pending",
        }
        result = normalise_frontmatter(fm)
        assert result["type"] == "person_note"
        assert result["people"] == ["Alice"]
        assert result["confidence"] == 0.9
        assert result["review_status"] == "pending"

    def test_returns_same_dict(self):
        """normalise_frontmatter mutates and returns the same dict."""
        fm = {"type": "idea"}
        returned = normalise_frontmatter(fm)
        assert returned is fm

    def test_default_lists_are_independent_instances(self):
        """Each call produces independent default lists (no shared mutable state)."""
        fm1 = normalise_frontmatter({})
        fm2 = normalise_frontmatter({})
        fm1["tags"].append("x")
        assert fm2["tags"] == []


# ============================================================================
# parse_wikilinks
# ============================================================================


class TestParseWikilinks:
    def test_single_link(self):
        assert parse_wikilinks("See [[Sarah Chen]] for details.") == ["Sarah Chen"]

    def test_alias_link(self):
        """Alias syntax [[Target|Display]] should return the target."""
        assert parse_wikilinks("See [[Sarah Chen|Sarah]]") == ["Sarah Chen"]

    def test_multiple_links(self):
        result = parse_wikilinks("[[Alice]] and [[Bob]] attended.")
        assert result == ["Alice", "Bob"]

    def test_no_links(self):
        assert parse_wikilinks("No links here.") == []

    def test_duplicate_links_preserved(self):
        result = parse_wikilinks("[[Alice]] then [[Alice]] again")
        assert result == ["Alice", "Alice"]

    def test_link_with_spaces(self):
        assert parse_wikilinks("See [[Q4 Project Plan]]") == ["Q4 Project Plan"]

    def test_empty_string(self):
        assert parse_wikilinks("") == []


# ============================================================================
# parse_links_field
# ============================================================================


class TestParseLinksField:
    def test_none_returns_empty(self):
        assert parse_links_field(None) == []

    def test_empty_list_returns_empty(self):
        assert parse_links_field([]) == []

    def test_plain_string_normalised(self):
        result = parse_links_field(["Sarah Chen"])
        assert len(result) == 1
        assert isinstance(result[0], LinkRef)
        assert result[0].target == "Sarah Chen"
        assert result[0].relation is None

    def test_dict_with_target_and_relation(self):
        result = parse_links_field([{"target": "Q4 Project", "relation": "manages"}])
        assert len(result) == 1
        assert result[0].target == "Q4 Project"
        assert result[0].relation == "manages"

    def test_dict_minimal(self):
        result = parse_links_field([{"target": "Some Note"}])
        assert result[0].target == "Some Note"
        assert result[0].relation is None

    def test_dict_extra_keys_go_to_metadata(self):
        result = parse_links_field([{"target": "Alice", "relation": "reports-to", "since": "2024-01"}])
        assert result[0].metadata.get("since") == "2024-01"

    def test_mixed_strings_and_dicts(self):
        result = parse_links_field(["Alice", {"target": "Bob", "relation": "peer"}])
        assert len(result) == 2
        assert result[0].target == "Alice"
        assert result[1].target == "Bob"
        assert result[1].relation == "peer"

    def test_dict_missing_target_skipped(self):
        result = parse_links_field([{"relation": "unknown"}])
        assert result == []


# ============================================================================
# resolve_wikilink (standalone function)
# ============================================================================


class TestResolveWikilink:
    def test_exact_stem_match(self, tmp_path: Path):
        (tmp_path / "people").mkdir()
        (tmp_path / "people" / "sarah-chen.md").write_text("---\n---\n")
        result = resolve_wikilink("sarah-chen", tmp_path)
        assert result == "people/sarah-chen.md"

    def test_case_insensitive_match(self, tmp_path: Path):
        (tmp_path / "people").mkdir()
        (tmp_path / "people" / "alice-example.md").write_text("---\n---\n")
        result = resolve_wikilink("Alice Example", tmp_path)
        assert result == "people/alice-example.md"

    def test_slug_match(self, tmp_path: Path):
        """Space-separated name should match hyphenated filename."""
        (tmp_path / "people").mkdir()
        (tmp_path / "people" / "sarah-chen.md").write_text("---\n---\n")
        result = resolve_wikilink("Sarah Chen", tmp_path)
        assert result == "people/sarah-chen.md"

    def test_reverse_slug_match(self, tmp_path: Path):
        """Hyphenated search should match space-separated filename (bidirectional)."""
        (tmp_path / "people").mkdir()
        (tmp_path / "people" / "Sarah Chen.md").write_text("---\n---\n")
        result = resolve_wikilink("sarah-chen", tmp_path)
        assert result == "people/Sarah Chen.md"

    def test_reverse_slug_match_case_insensitive(self, tmp_path: Path):
        """Case-insensitive hyphenated search for space-separated filename."""
        (tmp_path / "people").mkdir()
        (tmp_path / "people" / "Alice Example.md").write_text("---\n---\n")
        result = resolve_wikilink("alice-example", tmp_path)
        assert result == "people/Alice Example.md"

    def test_not_found_returns_none(self, tmp_path: Path):
        assert resolve_wikilink("Nonexistent Person", tmp_path) is None

    def test_skips_versions_directory(self, tmp_path: Path):
        versions = tmp_path / ".versions" / "people" / "alice.md"
        versions.mkdir(parents=True)
        (versions / "2026-01-01T00-00-00.000Z.md").write_text("---\n---\n")
        # Should not find the file inside .versions
        assert resolve_wikilink("2026-01-01T00-00-00.000Z", tmp_path) is None

    def test_skips_trash_directory(self, tmp_path: Path):
        trash = tmp_path / ".trash" / "people"
        trash.mkdir(parents=True)
        (trash / "alice.md").write_text("---\n---\n")
        assert resolve_wikilink("alice", tmp_path) is None

    def test_nonexistent_vault_returns_none(self, tmp_path: Path):
        fake_root = tmp_path / "does_not_exist"
        assert resolve_wikilink("anything", fake_root) is None


# ============================================================================
# VaultLayer: read_note
# ============================================================================


class TestVaultLayerReadNote:
    def test_reads_fixture_note(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        note = vault.read_note("people/alice-example.md")
        assert note.file_path == "people/alice-example.md"
        assert note.title == "alice-example"  # derived from stem (no title in FM)
        assert note.metadata.type == "person_note"
        assert note.metadata.domain == "work"
        assert "Alice Example" in note.metadata.people

    def test_schema_normalisation_applied(self, tmp_path: Path):
        """A note without `type` should read back with type='other'."""
        _write_md(tmp_path, "inbox/bare.md", {}, "Bare note with no type.")
        vault = VaultLayer(tmp_path)
        note = vault.read_note("inbox/bare.md")
        assert note.metadata.type == "other"
        assert note.metadata.review_status == "approved"
        assert note.metadata.confidence == 1.0
        assert note.metadata.tags == []

    def test_missing_file_raises_not_found(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        with pytest.raises(NoteNotFound):
            vault.read_note("nonexistent.md")

    def test_path_traversal_raises_403(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        with pytest.raises(Exception) as exc_info:
            vault.read_note("../../.env")
        assert exc_info.value.status_code == 403

    def test_mtime_populated(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        note = vault.read_note("people/alice-example.md")
        assert note.mtime is not None
        assert note.mtime > 0

    def test_body_parsed_correctly(self, tmp_path: Path):
        _write_md(tmp_path, "work/test.md", {"type": "decision"}, "Body text here.")
        vault = VaultLayer(tmp_path)
        note = vault.read_note("work/test.md")
        assert "Body text here." in note.body


# ============================================================================
# VaultLayer: write_note
# ============================================================================


class TestVaultLayerWriteNote:
    def _make_note(self, file_path: str, title: str = "Test Note", body: str = "Test body.") -> Note:
        return Note(
            file_path=file_path,
            title=title,
            body=body,
            metadata=NoteMetadata(type="idea", domain="personal", tags=["test"]),
        )

    def test_creates_new_file(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = self._make_note("ideas/my-idea.md")
        vault.write_note("ideas/my-idea.md", note)
        assert (tmp_path / "ideas" / "my-idea.md").exists()

    def test_atomic_write_uses_system_tempdir(self, tmp_path: Path, monkeypatch):
        """Verify that mkstemp is called (atomic path goes through tempfile)."""
        calls = []
        original_mkstemp = __import__("tempfile").mkstemp

        def _fake_mkstemp(**kwargs):
            result = original_mkstemp(**kwargs)
            calls.append(result[1])
            return result

        monkeypatch.setattr("monocle.vault.tempfile.mkstemp", _fake_mkstemp)
        vault = VaultLayer(tmp_path)
        vault.write_note("ideas/atomic.md", self._make_note("ideas/atomic.md"))
        assert len(calls) == 1

    def test_write_creates_version_on_overwrite(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = self._make_note("ideas/versioned.md", body="Version 1")
        vault.write_note("ideas/versioned.md", note)

        note2 = self._make_note("ideas/versioned.md", body="Version 2")
        vault.write_note("ideas/versioned.md", note2)

        # Version directory should exist with one entry
        version_dir = tmp_path / ".versions" / "ideas" / "versioned.md"
        assert version_dir.exists()
        versions = list(version_dir.glob("*.md"))
        assert len(versions) == 1
        # Version file should contain "Version 1"
        assert "Version 1" in versions[0].read_text(encoding="utf-8")

    def test_mtime_conflict_raises_409(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = self._make_note("ideas/conflict.md")
        vault.write_note("ideas/conflict.md", note)

        stale_mtime = 0.0  # definitely stale
        with pytest.raises(Exception) as exc_info:
            vault.write_note("ideas/conflict.md", note, if_mtime=stale_mtime)
        assert exc_info.value.status_code == 409

    def test_correct_mtime_does_not_raise(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = self._make_note("ideas/ok.md")
        vault.write_note("ideas/ok.md", note)
        current_mtime = (tmp_path / "ideas" / "ok.md").stat().st_mtime
        # Should not raise
        vault.write_note("ideas/ok.md", note, if_mtime=current_mtime)

    def test_creates_parent_directories(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = self._make_note("deep/nested/dir/note.md")
        vault.write_note("deep/nested/dir/note.md", note)
        assert (tmp_path / "deep" / "nested" / "dir" / "note.md").exists()

    def test_path_traversal_raises_403(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = self._make_note("../../bad.md")
        with pytest.raises(Exception) as exc_info:
            vault.write_note("../../bad.md", note)
        assert exc_info.value.status_code == 403


# ============================================================================
# VaultLayer: patch_frontmatter
# ============================================================================


class TestVaultLayerPatchFrontmatter:
    def test_updates_only_frontmatter(self, tmp_path: Path):
        path = _write_md(
            tmp_path, "work/patch-test.md",
            {"type": "decision", "review_status": "pending"},
            "Original body text.",
        )
        vault = VaultLayer(tmp_path)
        updated = vault.patch_frontmatter("work/patch-test.md", {"review_status": "approved"})
        assert updated.metadata.review_status == "approved"
        assert "Original body text." in updated.body

    def test_creates_version_before_patch(self, tmp_path: Path):
        _write_md(tmp_path, "work/patch-v.md", {"type": "idea"}, "Body.")
        vault = VaultLayer(tmp_path)
        vault.patch_frontmatter("work/patch-v.md", {"confidence": 0.9})
        version_dir = tmp_path / ".versions" / "work" / "patch-v.md"
        assert version_dir.exists()
        assert len(list(version_dir.glob("*.md"))) == 1

    def test_missing_file_raises_not_found(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        with pytest.raises(NoteNotFound):
            vault.patch_frontmatter("nonexistent.md", {"type": "idea"})

    def test_preserves_existing_fields(self, tmp_path: Path):
        _write_md(tmp_path, "work/p.md", {"type": "decision", "domain": "work", "tags": ["arch"]})
        vault = VaultLayer(tmp_path)
        updated = vault.patch_frontmatter("work/p.md", {"confidence": 0.75})
        assert updated.metadata.type == "decision"
        assert updated.metadata.domain == "work"


# ============================================================================
# VaultLayer: delete_note
# ============================================================================


class TestVaultLayerDeleteNote:
    def test_moves_to_trash(self, tmp_path: Path):
        _write_md(tmp_path, "people/to-delete.md", {"type": "person_note"})
        vault = VaultLayer(tmp_path)
        vault.delete_note("people/to-delete.md")

        # Original should be gone
        assert not (tmp_path / "people" / "to-delete.md").exists()
        # Trash entry should exist
        assert (tmp_path / ".trash" / "people" / "to-delete.md").exists()

    def test_missing_file_raises_not_found(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        with pytest.raises(NoteNotFound):
            vault.delete_note("nonexistent.md")

    def test_path_traversal_raises_403(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        with pytest.raises(Exception) as exc_info:
            vault.delete_note("../../.env")
        assert exc_info.value.status_code == 403


# ============================================================================
# VaultLayer: move_note
# ============================================================================


class TestVaultLayerMoveNote:
    def test_renames_file(self, tmp_path: Path):
        _write_md(tmp_path, "inbox/draft.md", {"type": "other"})
        vault = VaultLayer(tmp_path)
        vault.move_note("inbox/draft.md", "ideas/promoted.md")
        assert not (tmp_path / "inbox" / "draft.md").exists()
        assert (tmp_path / "ideas" / "promoted.md").exists()

    def test_missing_source_raises_not_found(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        with pytest.raises(NoteNotFound):
            vault.move_note("nonexistent.md", "ideas/x.md")

    def test_existing_destination_raises_409(self, tmp_path: Path):
        _write_md(tmp_path, "inbox/a.md", {})
        _write_md(tmp_path, "ideas/b.md", {})
        vault = VaultLayer(tmp_path)
        with pytest.raises(Exception) as exc_info:
            vault.move_note("inbox/a.md", "ideas/b.md")
        assert exc_info.value.status_code == 409

    def test_destination_path_traversal_raises_403(self, tmp_path: Path):
        _write_md(tmp_path, "inbox/draft.md", {})
        vault = VaultLayer(tmp_path)
        with pytest.raises(Exception) as exc_info:
            vault.move_note("inbox/draft.md", "../../escaped.md")
        assert exc_info.value.status_code == 403


# ============================================================================
# VaultLayer: create_from_template
# ============================================================================


class TestVaultLayerCreateFromTemplate:
    def test_person_template_default_folder(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template(
            "person_note", {"title": "Sarah Chen", "domain": "work"}
        )
        assert note.file_path == "people/sarah-chen.md"
        assert note.metadata.type == "person_note"
        assert note.metadata.people == ["Sarah Chen"]

    def test_person_template_schema_supports_personal_and_org_contexts(self):
        schema_path = Path(__file__).parent.parent / "vault" / "templates" / "person.yaml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))

        field_names = {field["name"] for field in schema.get("fields", [])}
        expected = {
            "title",
            "people",
            "relationship_type",
            "org",
            "org_role",
            "organizations",
            "family_context",
            "life_stage",
            "prayer_requests",
            "care_topics",
            "conversation_topics",
            "next_action",
        }
        missing = expected - field_names
        assert not missing, f"Missing person template fields: {missing}"

    def test_decision_template(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template(
            "decision", {"title": "Choose Python Stack"}
        )
        assert note.file_path.startswith("work/")
        assert "choose-python-stack" in note.file_path

    def test_idea_template(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("idea", {"title": "My Great Idea"})
        assert "my-great-idea" in note.file_path

    def test_blank_template_for_unknown(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("other", {})
        assert note.file_path.startswith("inbox/")

    def test_title_in_note_not_metadata(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("idea", {"title": "Test"})
        assert note.title == "Test"
        # title should NOT appear in metadata model
        assert not hasattr(note.metadata, "title_field")

    def test_does_not_write_to_disk(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("decision", {"title": "Disk Check"})
        # File should not exist until write_note is called
        assert not (tmp_path / note.file_path).exists()

    def test_body_set_correctly(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("idea", {"title": "Body Test"}, body="Custom body.")
        assert note.body == "Custom body."

    def test_person_template_uses_markdown_scaffold_when_body_empty(self, tmp_path: Path):
        (tmp_path / ".templates").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".templates" / "person.md").write_text(
            "# {title}\n\n## Relationship Snapshot\n- **Relationship type:**\n\n## Notes\n{body}\n",
            encoding="utf-8",
        )

        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("person_note", {"title": "Alice Example"})

        assert note.body.startswith("# Alice Example")
        assert "## Relationship Snapshot" in note.body
        assert "[Add note content here.]" in note.body

    def test_person_template_inserts_body_into_scaffold_when_present(self, tmp_path: Path):
        (tmp_path / ".templates").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".templates" / "person.md").write_text(
            "# {title}\n\n## Summary\n[Summary placeholder]\n\n## Notes\n{body}\n",
            encoding="utf-8",
        )

        vault = VaultLayer(tmp_path)
        note = vault.create_from_template(
            "person_note",
            {"title": "Alice Example"},
            body="Met over coffee and talked about AI.",
        )

        assert note.body.startswith("# Alice Example")
        assert "## Summary" in note.body
        assert "## Notes\nMet over coffee and talked about AI." in note.body

    def test_template_scaffold_reload_picks_up_runtime_edits(self, tmp_path: Path):
        template_dir = tmp_path / ".templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        template_file = template_dir / "person.md"
        template_file.write_text("# First Version\n\n{body}\n", encoding="utf-8")

        vault = VaultLayer(tmp_path)
        first = vault.create_from_template("person_note", {"title": "Alice Example"})

        template_file.write_text("# Second Version\n\n{body}\n", encoding="utf-8")
        second = vault.create_from_template("person_note", {"title": "Alice Example"})

        assert first.body.startswith("# First Version")
        assert second.body.startswith("# Second Version")

    def test_organization_template_renders_name_alias_and_body(self, tmp_path: Path):
        (tmp_path / ".templates").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".templates" / "organization.md").write_text(
            "# {org_name}\n\n## Notes\n{body}\n",
            encoding="utf-8",
        )

        vault = VaultLayer(tmp_path)
        note = vault.create_from_template(
            "organization",
            {"name": "Acme Corp", "org_type": "company"},
            body="Important partner organization.",
        )

        assert note.body.startswith("# Acme Corp")
        assert "Important partner organization." in note.body

    def test_template_preserved_on_roundtrip(self, tmp_path: Path):
        """Template field should be preserved when written and read back."""
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("person_note", {"title": "Alice"})
        assert note.metadata.template == "person"
        
        # Write and read back
        vault.write_note(note.file_path, note)
        read_back = vault.read_note(note.file_path)
        assert read_back.metadata.template == "person"

    def test_decision_template_preserved(self, tmp_path: Path):
        """Decision template should be preserved in round-trip."""
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("decision", {"title": "Choose Stack"})
        assert note.metadata.template == "decision"
        
        vault.write_note(note.file_path, note)
        read_back = vault.read_note(note.file_path)
        assert read_back.metadata.template == "decision"

    def test_slugify_special_chars(self, tmp_path: Path):
        """Special characters are stripped, spaces become hyphens."""
        vault = VaultLayer(tmp_path)
        note = vault.create_from_template("person_note", {"title": "O'Brien & Co!"})
        assert "obrien--co" in note.file_path or "obrien" in note.file_path



# ============================================================================
# VaultLayer: resolve_wikilink
# ============================================================================


class TestVaultLayerResolveWikilink:
    def test_resolves_person_note(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        result = vault.resolve_wikilink("alice-example")
        assert result == "people/alice-example.md"

    def test_case_insensitive(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        result = vault.resolve_wikilink("Alice Example")
        assert result == "people/alice-example.md"

    def test_not_found_returns_none(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        assert vault.resolve_wikilink("nobody-here") is None


# ============================================================================
# VaultLayer: list_versions / restore_version
# ============================================================================


class TestVaultLayerVersions:
    def test_no_versions_returns_empty(self, tmp_path: Path):
        _write_md(tmp_path, "ideas/note.md", {})
        vault = VaultLayer(tmp_path)
        assert vault.list_versions("ideas/note.md") == []

    def test_versions_created_on_overwrite(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        n = Note(file_path="ideas/n.md", title="T", body="v1", metadata=NoteMetadata())
        vault.write_note("ideas/n.md", n)
        time.sleep(0.05)  # ensure distinct timestamps
        vault.write_note("ideas/n.md", n)
        versions = vault.list_versions("ideas/n.md")
        assert len(versions) == 1

    def test_versions_sorted_oldest_first(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        n = Note(file_path="w/n.md", title="T", body="v1", metadata=NoteMetadata())
        vault.write_note("w/n.md", n)
        time.sleep(0.05)
        vault.write_note("w/n.md", n)
        time.sleep(0.05)
        vault.write_note("w/n.md", n)
        versions = vault.list_versions("w/n.md")
        assert len(versions) == 2
        assert versions == sorted(versions)

    def test_restore_version_replaces_current(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        n1 = Note(file_path="w/r.md", title="T", body="Original", metadata=NoteMetadata())
        vault.write_note("w/r.md", n1)
        time.sleep(0.05)
        n2 = Note(file_path="w/r.md", title="T", body="Modified", metadata=NoteMetadata())
        vault.write_note("w/r.md", n2)

        versions = vault.list_versions("w/r.md")
        assert len(versions) == 1

        vault.restore_version("w/r.md", versions[0])
        restored = vault.read_note("w/r.md")
        assert "Original" in restored.body

    def test_restore_nonexistent_version_raises(self, tmp_path: Path):
        _write_md(tmp_path, "w/n.md", {})
        vault = VaultLayer(tmp_path)
        with pytest.raises(NoteNotFound):
            vault.restore_version("w/n.md", "2000-01-01T00-00-00.000Z")

    def test_restore_version_invalid_timestamp_format_raises_403(self, tmp_path: Path):
        """Invalid timestamp format should raise 403 (not allow arbitrary strings)."""
        _write_md(tmp_path, "w/n.md", {})
        vault = VaultLayer(tmp_path)
        # Should reject timestamps that don't match YYYYMMDDTHHmmss.fffZ format
        with pytest.raises(Exception) as exc_info:
            vault.restore_version("w/n.md", "invalid-timestamp")
        assert exc_info.value.status_code == 403

    def test_restore_version_path_traversal_attempt_raises_403(self, tmp_path: Path):
        """Timestamp containing .. or path separators should be rejected."""
        _write_md(tmp_path, "w/n.md", {})
        vault = VaultLayer(tmp_path)
        # Try to escape the version directory
        with pytest.raises(Exception) as exc_info:
            vault.restore_version("w/n.md", "../../../etc/passwd.000Z")
        assert exc_info.value.status_code == 403

    def test_restore_version_absolute_path_safe(self, tmp_path: Path):
        """Absolute file paths in restore_version should be safe (converted to relative)."""
        vault = VaultLayer(tmp_path)
        n = Note(file_path="w/r.md", title="T", body="v1", metadata=NoteMetadata())
        vault.write_note("w/r.md", n)
        time.sleep(0.05)
        vault.write_note("w/r.md", n)
        
        # Get an absolute path
        absolute_path = str(tmp_path / "w" / "r.md")
        versions = vault.list_versions(absolute_path)
        assert len(versions) > 0
        
        # Restore should work with absolute path
        vault.restore_version(absolute_path, versions[0])
        restored = vault.read_note("w/r.md")
        assert restored.title == "T"


# ============================================================================
# VaultLayer: list_notes
# ============================================================================


class TestVaultLayerListNotes:
    def test_returns_all_notes(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes()
        # The tmp_vault fixture has 5 notes
        assert page.total == 5
        assert len(page.items) == 5

    def test_pagination_offset_and_limit(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes(limit=2, offset=0)
        assert len(page.items) == 2
        assert page.total == 5

        page2 = vault.list_notes(limit=2, offset=2)
        assert len(page2.items) == 2
        # Items should be different
        assert page.items[0].file_path != page2.items[0].file_path

    def test_filter_by_type(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes(type="person_note")
        assert all(note.type == "person_note" for note in page.items)
        assert page.total >= 1

    def test_filter_by_domain(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes(domain="work")
        assert all(note.domain == "work" for note in page.items)

    def test_filter_by_folder(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes(folder="people")
        assert all(note.file_path.startswith("people/") for note in page.items)

    def test_hidden_directories_excluded(self, tmp_vault: Path):
        # Write a note inside .versions/ - it should be excluded
        versions_note = tmp_vault / ".versions" / "people" / "alice-example.md"
        versions_note.mkdir(parents=True, exist_ok=True)
        (versions_note / "ts.md").write_text("---\n---\n")
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes()
        paths = [n.file_path for n in page.items]
        assert not any(".versions" in p for p in paths)

    def test_sort_by_updated_descending_default(self, tmp_vault: Path):
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes(sort="updated")
        dates = [n.updated for n in page.items if n.updated is not None]
        if len(dates) >= 2:
            assert dates == sorted(dates, reverse=True)

    def test_sort_by_created_uses_created_not_updated(self, tmp_path: Path):
        """Verify that sort='created' uses ref.created, not ref.updated (descending order)."""
        vault = VaultLayer(tmp_path)
        # Create three notes with different created dates
        n1 = Note(file_path="a.md", title="First", body="", metadata=NoteMetadata(
            created=datetime.datetime(2025, 1, 1, 10, 0, tzinfo=datetime.timezone.utc)))
        n2 = Note(file_path="b.md", title="Second", body="", metadata=NoteMetadata(
            created=datetime.datetime(2025, 1, 3, 10, 0, tzinfo=datetime.timezone.utc)))
        n3 = Note(file_path="c.md", title="Third", body="", metadata=NoteMetadata(
            created=datetime.datetime(2025, 1, 2, 10, 0, tzinfo=datetime.timezone.utc)))
        
        vault.write_note("a.md", n1)
        time.sleep(0.01)
        vault.write_note("b.md", n2)
        time.sleep(0.01)
        vault.write_note("c.md", n3)
        
        # Sort by created (descending): b (jan3), c (jan2), a (jan1)
        page = vault.list_notes(sort="created")
        titles = [n.title for n in page.items]
        assert titles == ["Second", "Third", "First"]



    def test_empty_vault_returns_empty_page(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        page = vault.list_notes()
        assert page.total == 0
        assert page.items == []

    def test_sort_by_title_ascending(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        for title in ["Zara", "Alice", "Mike"]:
            n = Note(
                file_path=f"people/{title.lower()}.md",
                title=title,
                body="",
                metadata=NoteMetadata(type="person_note"),
            )
            vault.write_note(n.file_path, n)
        page = vault.list_notes(sort="title")
        titles = [ref.title for ref in page.items]
        assert titles == sorted(titles, key=str.lower)

    def test_noteref_review_status_propagated(self, tmp_vault: Path):
        """review_status from frontmatter must appear in the returned NoteRef."""
        vault = VaultLayer(tmp_vault)
        page = vault.list_notes()
        statuses = {ref.review_status for ref in page.items}
        # tmp_vault has both "approved" and "pending" notes
        assert "approved" in statuses
        assert "pending" in statuses


# ============================================================================
# _ms_timestamp / _slugify helpers
# ============================================================================


class TestHelpers:
    def test_ms_timestamp_format(self):
        ts = _ms_timestamp()
        # Should match YYYY-MM-DDTHH-MM-SS.mmmZ (Windows-safe, no colons in time)
        assert len(ts) == 24
        assert ts.endswith("Z")
        # The T separator should be present
        assert "T" in ts

    def test_ms_timestamp_is_sortable(self):
        t1 = _ms_timestamp()
        time.sleep(0.01)
        t2 = _ms_timestamp()
        assert t1 < t2  # lexicographic order = chronological order

    def test_slugify_basic(self):
        assert _slugify("Sarah Chen") == "sarah-chen"

    def test_slugify_special_chars(self):
        result = _slugify("Hello, World!")
        assert "," not in result
        assert "!" not in result

    def test_slugify_empty_returns_untitled(self):
        assert _slugify("") == "untitled"
        assert _slugify("!!!") == "untitled"

    def test_slugify_multiple_spaces(self):
        assert _slugify("  too   many  spaces  ") == "too-many-spaces"


# ============================================================================
# VaultLayer: list_templates
# ============================================================================


class TestVaultLayerListTemplates:
    def test_returns_ten_templates(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        schemas = vault.list_templates()
        assert len(schemas) == 11

    def test_each_template_has_sentence_starters(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        for schema in vault.list_templates():
            assert "sentence_starters" in schema, f"Missing sentence_starters in {schema.get('template')}"
            assert isinstance(schema["sentence_starters"], list)

    def test_template_names_all_present(self, tmp_path: Path):
        vault = VaultLayer(tmp_path)
        names = {s["template"] for s in vault.list_templates()}
        expected = {
            "person", "decision", "project", "meeting", "idea",
            "observation", "reference", "action_item", "blank", "weekly_summary",
            "organization",
        }
        assert names == expected
