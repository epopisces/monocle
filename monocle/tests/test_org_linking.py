"""
monocle/tests/test_org_linking.py — Tests for M23 organization note type and
cross-linked people backreferences.

Covers:
- ``wire_org_links`` creates stub org notes when none exist
- ``wire_org_links`` links to existing org notes without creating stubs
- ``wire_org_links`` is a no-op for non-person notes
- ``wire_org_links`` skips already-linked orgs (idempotency)
- ``wire_org_links`` handles multiple orgs in one person note
- Organization template schema loads and has required fields
- Graph layer returns person nodes as backreferences from an org note focus
- Graph edge carries ``relation: works-at`` from structured links
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml


# ---------------------------------------------------------------------------
#region #*   Helpers
# ---------------------------------------------------------------------------


def _write_note(root: Path, rel: str, fm: dict[str, Any], body: str = "") -> Path:
    """Write a YAML-frontmatter Markdown note to *root / rel*."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    merged = {"created": now, "updated": now, **fm}
    path.write_text(
        f"---\n{yaml.dump(merged, default_flow_style=False, allow_unicode=True)}---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def _make_person_note(root: Path, name: str, organizations: list[dict]) -> Any:
    """Create a person Note object with an `organizations` field via VaultLayer."""
    from monocle.vault import VaultLayer

    vault = VaultLayer(root)
    slug = name.lower().replace(" ", "-")
    rel = f"people/{slug}.md"
    _write_note(
        root,
        rel,
        {
            "title": name,
            "type": "person_note",
            "domain": "work",
            "source": "web",
            "confidence": 0.9,
            "review_status": "approved",
            "tags": [],
            "people": [name],
            "organizations": organizations,
        },
        f"{name} is a person.",
    )
    return vault.read_note(rel)


#endregion

# ===========================================================================
# Organization template schema
# ===========================================================================


class TestOrganizationTemplate:
    def test_template_file_exists(self):
        from pathlib import Path as _Path

        tpl = _Path(__file__).parent.parent / "vault" / "templates" / "organization.yaml"
        assert tpl.exists(), "organization.yaml template is missing"

    def test_template_has_required_fields(self):
        import yaml as _yaml
        from pathlib import Path as _Path

        tpl = _Path(__file__).parent.parent / "vault" / "templates" / "organization.yaml"
        schema = _yaml.safe_load(tpl.read_text(encoding="utf-8"))

        assert schema["template"] == "organization"
        assert schema["note_type"] == "organization"
        assert schema["default_folder"] == "organizations"
        assert len(schema.get("sentence_starters", [])) >= 5, "Need ≥5 sentence starters"

        field_names = {f["name"] for f in schema.get("fields", [])}
        required_fields = {"name", "org_type", "founded_year", "domain", "tags", "active"}
        missing = required_fields - field_names
        assert not missing, f"Missing fields in organization.yaml: {missing}"
        assert len(field_names) >= 15, f"Expected ≥15 fields, got {len(field_names)}"

    def test_vault_create_from_template_organization(self, tmp_path: Path):
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        note = vault.create_from_template(
            "organization",
            {"name": "Acme Corp", "org_type": "company", "domain": "work"},
        )
        assert note.metadata.type == "organization"
        assert note.file_path.startswith("organizations/")
        assert "acme" in note.file_path


# ===========================================================================
# wire_org_links — core linking logic
# ===========================================================================


class TestWireOrgLinks:
    def test_noop_for_non_person_note(self, tmp_path: Path):
        """Non-person notes should be left unchanged."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        _write_note(
            tmp_path,
            "work/decision.md",
            {"type": "decision", "domain": "work", "source": "web",
             "organizations": [{"name": "Acme"}]},
            "We decided to use Python.",
        )
        note = vault.read_note("work/decision.md")
        wire_org_links(note, vault)

        # No org stub should have been created
        assert not (tmp_path / "organizations").exists() or not list(
            (tmp_path / "organizations").glob("*.md")
        )

    def test_noop_when_no_organizations_field(self, tmp_path: Path):
        """Person note without organizations field → no-op."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        note = _make_person_note(tmp_path, "Alice Smith", organizations=[])
        wire_org_links(note, vault)

        read_back = vault.read_note(note.file_path)
        assert read_back.metadata.links == []

    def test_creates_stub_org_when_missing(self, tmp_path: Path):
        """Person note with organizations → stub org note auto-created."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        note = _make_person_note(
            tmp_path,
            "Bob Jones",
            organizations=[
                {"name": "Acme Corp", "role": "VP", "join_date": "2020-01", "current": True}
            ],
        )

        wire_org_links(note, vault)

        # A new org stub should exist under organizations/
        org_stubs = list((tmp_path / "organizations").glob("*.md"))
        assert len(org_stubs) == 1
        stub_note = vault.read_note(f"organizations/{org_stubs[0].name}")
        assert stub_note.metadata.type == "organization"
        assert stub_note.metadata.review_status == "pending"

    def test_links_to_existing_org(self, tmp_path: Path):
        """When org note already exists, link person → org without creating a new stub."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)

        # Pre-create an org note
        _write_note(
            tmp_path,
            "organizations/acme-corp.md",
            {"title": "Acme Corp", "type": "organization", "domain": "work",
             "source": "web", "review_status": "approved"},
            "Acme Corp is a tech company.",
        )

        note = _make_person_note(
            tmp_path,
            "Carol White",
            organizations=[
                {"name": "Acme Corp", "role": "Engineer", "join_date": "2021-03", "current": True}
            ],
        )

        wire_org_links(note, vault)

        # Only one org note should exist (the pre-created one)
        all_org_md = list((tmp_path / "organizations").glob("*.md"))
        assert len(all_org_md) == 1

        # Person note should have a works-at link
        updated = vault.read_note(note.file_path)
        assert len(updated.metadata.links) == 1
        lnk = updated.metadata.links[0]
        assert lnk.target == "organizations/acme-corp.md"
        assert lnk.relation == "works-at"
        assert lnk.metadata.get("join_date") == "2021-03"
        assert lnk.metadata.get("current") is True

    def test_person_links_field_has_works_at_entry(self, tmp_path: Path):
        """After wiring, person note contains a works-at structured link."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        note = _make_person_note(
            tmp_path,
            "Dan Brown",
            organizations=[
                {"name": "Initech", "role": "Developer", "join_date": "2019-06",
                 "leave_date": "2022-12", "current": False}
            ],
        )

        wire_org_links(note, vault)

        updated = vault.read_note(note.file_path)
        assert len(updated.metadata.links) == 1
        lnk = updated.metadata.links[0]
        assert lnk.relation == "works-at"
        assert lnk.metadata.get("role") == "Developer"
        assert lnk.metadata.get("leave_date") == "2022-12"
        assert lnk.metadata.get("current") is False

    def test_skips_already_linked_org(self, tmp_path: Path):
        """Calling wire_org_links twice should not create duplicate links."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        note = _make_person_note(
            tmp_path,
            "Eve Davis",
            organizations=[{"name": "TechCo", "role": "CTO", "current": True}],
        )

        wire_org_links(note, vault)
        # Re-read and run again (simulates re-ingest)
        note2 = vault.read_note(note.file_path)
        wire_org_links(note2, vault)

        final = vault.read_note(note.file_path)
        assert len(final.metadata.links) == 1, "Should not add duplicate links"

    def test_multi_org_creates_multiple_stubs(self, tmp_path: Path):
        """Person note with multiple orgs creates multiple stubs + links."""
        from monocle.ingest.org_linker import wire_org_links
        from monocle.vault import VaultLayer

        vault = VaultLayer(tmp_path)
        note = _make_person_note(
            tmp_path,
            "Frank Miller",
            organizations=[
                {"name": "Alpha Inc", "role": "Engineer", "join_date": "2015-01",
                 "leave_date": "2018-06", "current": False},
                {"name": "Beta Ltd", "role": "Lead", "join_date": "2018-07", "current": True},
            ],
        )

        wire_org_links(note, vault)

        updated = vault.read_note(note.file_path)
        assert len(updated.metadata.links) == 2

        relations = {lnk.relation for lnk in updated.metadata.links}
        assert relations == {"works-at"}

        targets = {lnk.target for lnk in updated.metadata.links}
        assert len(targets) == 2

        # Both org stubs should exist
        org_stubs = list((tmp_path / "organizations").glob("*.md"))
        assert len(org_stubs) == 2


# ===========================================================================
# Graph backreferences from org note
# ===========================================================================


class TestOrgGraphBackreferences:
    def _write_org_and_person(self, root: Path) -> tuple[str, str]:
        """Create a pre-linked person → org pair; returns (person_path, org_path)."""
        _write_note(
            root,
            "organizations/acme-corp.md",
            {"title": "Acme Corp", "type": "organization", "domain": "work",
             "source": "web", "review_status": "approved"},
            "Acme Corp is a tech company.",
        )
        _write_note(
            root,
            "people/grace-hopper.md",
            {
                "title": "Grace Hopper",
                "type": "person_note",
                "domain": "work",
                "source": "web",
                "review_status": "approved",
                "links": [
                    {"target": "organizations/acme-corp.md", "relation": "works-at",
                     "join_date": "2020-01", "current": True}
                ],
            },
            "Grace is a principal engineer at Acme Corp.",
        )
        return "people/grace-hopper.md", "organizations/acme-corp.md"

    def test_org_graph_contains_person_node(self, tmp_path: Path):
        """GET /api/graph?focus=org returns person nodes with works-at edges."""
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        person_path, org_path = self._write_org_and_person(tmp_path)
        vault = VaultLayer(tmp_path)
        gb = GraphBuilder(vault)
        gd = gb.build(focus=org_path, max_degree=2)

        node_ids = {n.id for n in gd.nodes}
        assert org_path in node_ids
        assert person_path in node_ids

    def test_org_graph_edge_has_works_at_relation(self, tmp_path: Path):
        """Graph edge from person → org carries relation=works-at."""
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        person_path, org_path = self._write_org_and_person(tmp_path)
        vault = VaultLayer(tmp_path)
        gb = GraphBuilder(vault)
        gd = gb.build(focus=org_path, max_degree=2)

        works_at_edges = [
            e for e in gd.edges
            if e.relation == "works-at" and e.source == person_path and e.target == org_path
        ]
        assert len(works_at_edges) >= 1, "Expected at least one works-at edge"

    def test_org_graph_type_filter_returns_only_people(self, tmp_path: Path):
        """types=[person_note] filter on org focus returns only person nodes (besides the focus org itself). Organization node may be present as the focus."""
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        # Write an extra non-person note also linked to the org
        _write_note(
            tmp_path,
            "organizations/acme-corp.md",
            {"title": "Acme Corp", "type": "organization", "domain": "work",
             "source": "web", "review_status": "approved"},
            "Acme Corp.",
        )
        _write_note(
            tmp_path,
            "people/alice.md",
            {
                "title": "Alice",
                "type": "person_note",
                "domain": "work",
                "source": "web",
                "review_status": "approved",
                "links": [
                    {"target": "organizations/acme-corp.md", "relation": "works-at"}
                ],
            },
            "Alice works at Acme.",
        )
        _write_note(
            tmp_path,
            "projects/acme-project.md",
            {
                "title": "Acme Project",
                "type": "project",
                "domain": "work",
                "source": "web",
                "review_status": "approved",
                "links": [
                    {"target": "organizations/acme-corp.md", "relation": "client"}
                ],
            },
            "Client project for Acme.",
        )

        vault = VaultLayer(tmp_path)
        gb = GraphBuilder(vault)
        # Filter to person_note types only
        gd = gb.build(
            focus="organizations/acme-corp.md",
            max_degree=2,
            types=["person_note", "organization"],
        )

        node_types = {n.type for n in gd.nodes}
        assert "project" not in node_types
        assert "person_note" in node_types or "organization" in node_types
