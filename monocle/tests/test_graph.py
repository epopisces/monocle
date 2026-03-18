"""
monocle/tests/test_graph.py — Tests for the M9 Graph Layer.

Uses the ``tmp_vault`` fixture (5 pre-written fixture notes).
Additional notes are written inline for wikilink and structured-link tests.
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_note(vault_root: Path, rel_path: str, frontmatter: dict, body: str = "") -> None:
    """Write a plain Markdown note with YAML frontmatter to *vault_root*."""
    note_file = vault_root / rel_path
    note_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    fm = {"created": now, "updated": now, **frontmatter}
    note_file.write_text(
        f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n",
        encoding="utf-8",
    )


def _build(vault_root: Path, **kwargs) -> Any:
    """Helper: create a VaultLayer + GraphBuilder and call build()."""
    from monocle.graph import GraphBuilder
    from monocle.vault import VaultLayer

    vault = VaultLayer(str(vault_root))
    gb = GraphBuilder(vault)
    return gb.build(**kwargs)


def _node_ids(graph_data) -> set[str]:
    return {n.id for n in graph_data.nodes}


def _edge_pairs(graph_data) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in graph_data.edges}


# ---------------------------------------------------------------------------
# Full-vault graph (no focus)
# ---------------------------------------------------------------------------


class TestGraphBuilderFullVault:
    """Full-vault graph — no focal node, all notes included."""

    def test_returns_all_fixture_nodes(self, tmp_vault: Path):
        gd = _build(tmp_vault)
        ids = _node_ids(gd)
        assert "people/alice-example.md" in ids
        assert "work/kickoff-meeting.md" in ids
        assert "work/decide-python-stack.md" in ids
        assert "technologies/idea-graph-viz.md" in ids
        assert "inbox/raw-capture.md" in ids

    def test_node_has_expected_fields(self, tmp_vault: Path):
        gd = _build(tmp_vault)
        alice = next(n for n in gd.nodes if n.id == "people/alice-example.md")
        assert alice.label  # non-empty
        assert alice.type == "person_note"
        assert alice.degree is None  # no focus → null degree

    def test_focus_is_none_in_full_vault(self, tmp_vault: Path):
        gd = _build(tmp_vault)
        assert gd.focus is None

    def test_all_degrees_none_in_full_vault(self, tmp_vault: Path):
        gd = _build(tmp_vault)
        for node in gd.nodes:
            assert node.degree is None


# ---------------------------------------------------------------------------
# Co-mention edges
# ---------------------------------------------------------------------------


class TestCoMentionEdges:
    """Edges from the ``people:`` frontmatter list (source 3)."""

    def test_comention_edge_from_meeting_to_alice(self, tmp_vault: Path):
        """kickoff-meeting mentions Alice Example → edge to alice-example.md."""
        gd = _build(tmp_vault)
        pairs = _edge_pairs(gd)
        # The meeting note mentions Alice; expect a co-mention edge
        assert (
            "work/kickoff-meeting.md",
            "people/alice-example.md",
        ) in pairs

    def test_comention_edge_type_and_relation(self, tmp_vault: Path):
        gd = _build(tmp_vault)
        edge = next(
            (
                e
                for e in gd.edges
                if e.source == "work/kickoff-meeting.md"
                and e.target == "people/alice-example.md"
            ),
            None,
        )
        assert edge is not None, "Expected co-mention edge from meeting to alice"
        assert edge.edge_type == "co-mention"
        assert edge.relation == "mentioned-in"

    def test_unresolvable_person_creates_no_edge(self, tmp_vault: Path):
        """Bob Smith has no corresponding note → no edge created."""
        gd = _build(tmp_vault)
        bob_edges = [e for e in gd.edges if "bob" in e.target.lower()]
        assert bob_edges == []


# ---------------------------------------------------------------------------
# Wikilink edges
# ---------------------------------------------------------------------------


class TestWikilinkEdges:
    """Edges from ``[[wikilinks]]`` in note bodies (source 2)."""

    def test_wikilink_edge_created(self, tmp_vault: Path):
        """A note body with [[alice-example]] → edge to alice-example.md."""
        _write_note(
            tmp_vault,
            "work/wikilink-test.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": ["test"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
            body="See also [[alice-example]] for context.",
        )
        gd = _build(tmp_vault)
        pairs = _edge_pairs(gd)
        assert ("work/wikilink-test.md", "people/alice-example.md") in pairs

    def test_wikilink_edge_type_and_relation(self, tmp_vault: Path):
        _write_note(
            tmp_vault,
            "work/wikilink-test.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
            body="See [[alice-example]] for more.",
        )
        gd = _build(tmp_vault)
        edge = next(
            (
                e
                for e in gd.edges
                if e.source == "work/wikilink-test.md"
                and e.target == "people/alice-example.md"
            ),
            None,
        )
        assert edge is not None
        assert edge.edge_type == "wikilink"
        assert edge.relation == "links-to"


# ---------------------------------------------------------------------------
# Structured-link edges
# ---------------------------------------------------------------------------


class TestStructuredLinkEdges:
    """Edges from the ``links:`` frontmatter field (source 1, highest priority)."""

    def test_structured_link_edge_with_relation(self, tmp_vault: Path):
        _write_note(
            tmp_vault,
            "work/structured-test.md",
            {
                "type": "decision",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
                "links": [{"target": "alice-example", "relation": "managed-by"}],
            },
        )
        gd = _build(tmp_vault)
        edge = next(
            (
                e
                for e in gd.edges
                if e.source == "work/structured-test.md"
                and e.target == "people/alice-example.md"
            ),
            None,
        )
        assert edge is not None
        assert edge.edge_type == "structured"
        assert edge.relation == "managed-by"

    def test_structured_link_metadata_preserved(self, tmp_vault: Path):
        _write_note(
            tmp_vault,
            "work/structured-meta.md",
            {
                "type": "decision",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
                "links": [
                    {"target": "alice-example", "relation": "reports-to", "since": "2024-01"}
                ],
            },
        )
        gd = _build(tmp_vault)
        edge = next(
            (
                e
                for e in gd.edges
                if e.source == "work/structured-meta.md"
                and e.target == "people/alice-example.md"
            ),
            None,
        )
        assert edge is not None
        assert edge.relation == "reports-to"
        assert edge.metadata.get("since") == "2024-01"


# ---------------------------------------------------------------------------
# Shared-tag edges
# ---------------------------------------------------------------------------


class TestSharedTagEdges:
    """Edges from shared ``tags:`` frontmatter field (source 4)."""

    def test_shared_tag_creates_edge(self, tmp_vault: Path):
        """Two notes sharing a tag → co-mention edge with relation='shares-tag'."""
        _write_note(
            tmp_vault,
            "work/note-a.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": ["shared-tag-xyz"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
        )
        _write_note(
            tmp_vault,
            "work/note-b.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": ["shared-tag-xyz"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
        )
        gd = _build(tmp_vault)
        # Edge should exist in canonical (sorted) direction
        ids = {"work/note-a.md", "work/note-b.md"}
        tag_edges = [
            e
            for e in gd.edges
            if e.relation == "shares-tag"
            and {e.source, e.target} == ids
        ]
        assert len(tag_edges) >= 1

    def test_no_self_loops(self, tmp_vault: Path):
        gd = _build(tmp_vault)
        for edge in gd.edges:
            assert edge.source != edge.target


# ---------------------------------------------------------------------------
# BFS degrees (focused graph)
# ---------------------------------------------------------------------------


class TestFocusedGraph:
    """BFS degree computation when a focal node is provided."""

    def test_focus_node_at_degree_0(self, tmp_vault: Path):
        gd = _build(tmp_vault, focus="people/alice-example.md", max_degree=3)
        alice = next((n for n in gd.nodes if n.id == "people/alice-example.md"), None)
        assert alice is not None
        assert alice.degree == 0

    def test_comention_source_at_degree_1(self, tmp_vault: Path):
        """kickoff-meeting co-mentions Alice → it should appear at degree 1."""
        gd = _build(tmp_vault, focus="people/alice-example.md", max_degree=2)
        meeting = next(
            (n for n in gd.nodes if n.id == "work/kickoff-meeting.md"), None
        )
        assert meeting is not None, "kickoff-meeting should be reachable at degree 1"
        assert meeting.degree == 1

    def test_focus_set_in_response(self, tmp_vault: Path):
        gd = _build(tmp_vault, focus="people/alice-example.md", max_degree=2)
        assert gd.focus == "people/alice-example.md"

    def test_unreachable_nodes_excluded(self, tmp_vault: Path):
        """Notes with no edges to alice are excluded when max_degree is 1."""
        # idea-graph-viz has no edges to alice
        gd = _build(tmp_vault, focus="people/alice-example.md", max_degree=1)
        ids = _node_ids(gd)
        assert "technologies/idea-graph-viz.md" not in ids

    def test_focus_missing_returns_empty_graph(self, tmp_vault: Path):
        """Non-existent focus → empty GraphData returned gracefully."""
        gd = _build(tmp_vault, focus="people/nonexistent.md", max_degree=2)
        assert gd.nodes == []
        assert gd.edges == []

    def test_max_degree_one_still_includes_focus(self, tmp_vault: Path):
        """max_degree=1 still includes the focus node at degree 0."""
        gd = _build(tmp_vault, focus="people/alice-example.md", max_degree=1)
        ids = _node_ids(gd)
        assert "people/alice-example.md" in ids


# ---------------------------------------------------------------------------
# Types filter
# ---------------------------------------------------------------------------


class TestTypesFilter:
    """Only nodes whose `type` is in the requested list are returned."""

    def test_types_person_returns_only_person_nodes(self, tmp_vault: Path):
        gd = _build(tmp_vault, types=["person_note"])
        for node in gd.nodes:
            assert node.type == "person_note"

    def test_types_filter_excludes_edges_to_filtered_nodes(self, tmp_vault: Path):
        gd = _build(tmp_vault, types=["person_note"])
        node_ids = _node_ids(gd)
        for edge in gd.edges:
            assert edge.source in node_ids
            assert edge.target in node_ids

    def test_multiple_types_filter(self, tmp_vault: Path):
        gd = _build(tmp_vault, types=["person_note", "decision"])
        allowed = {"person_note", "decision"}
        for node in gd.nodes:
            assert node.type in allowed

    def test_no_types_returns_all(self, tmp_vault: Path):
        gd_all = _build(tmp_vault)
        gd_unfiltered = _build(tmp_vault, types=None)
        assert len(gd_all.nodes) == len(gd_unfiltered.nodes)


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------


class TestGraphCache:
    """Cache hits and invalidation."""

    def test_cache_hit_returns_same_object(self, tmp_vault: Path):
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        result1 = gb.build()
        result2 = gb.build()
        assert result1 is result2  # exact same object from cache

    def test_cache_hit_with_same_params(self, tmp_vault: Path):
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        r1 = gb.build(focus="people/alice-example.md", max_degree=2)
        r2 = gb.build(focus="people/alice-example.md", max_degree=2)
        assert r1 is r2

    def test_different_params_different_cache_entry(self, tmp_vault: Path):
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        r1 = gb.build(max_degree=2)
        r2 = gb.build(max_degree=3)
        # Different params → different objects (both are freshly built)
        assert r1 is not r2

    def test_invalidate_clears_cache(self, tmp_vault: Path):
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        result1 = gb.build()
        gb.invalidate()
        result2 = gb.build()
        # After invalidation, a new object is built
        assert result1 is not result2

    def test_invalidate_empties_internal_cache(self, tmp_vault: Path):
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        gb.build()
        gb.build(focus="people/alice-example.md")
        assert len(gb._cache) == 2

        gb.invalidate()
        assert len(gb._cache) == 0

    def test_invalidate_increments_generation(self, tmp_vault: Path):
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        assert gb._generation == 0
        gb.invalidate()
        assert gb._generation == 1
        gb.invalidate()
        assert gb._generation == 2

    def test_stale_build_discarded_after_invalidation(self, tmp_vault: Path):
        """Simulate the race: build() starts, invalidate() fires, build() writes back.

        The write-back must be silently discarded (generation mismatch) so the
        cache stays empty (correct) rather than being filled with a stale result.
        """
        import threading
        from unittest.mock import patch
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        original_build = gb._build_uncached

        def build_then_invalidate(*args, **kwargs):
            # Simulate invalidate() firing *during* _build_uncached
            gb.invalidate()
            return original_build(*args, **kwargs)

        with patch.object(gb, "_build_uncached", side_effect=build_then_invalidate):
            result = gb.build()

        # The result is still returned to the caller (correct behaviour)
        assert result is not None
        # But the cache must stay empty because the generation changed mid-build
        assert len(gb._cache) == 0

    def test_concurrent_builds_same_key_no_data_race(self, tmp_vault: Path):
        """Two threads building the same cache key must both return valid
        GraphData and leave the cache in a consistent state (not corrupt)."""
        import threading
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)

        results: list = []
        errors: list = []

        def worker():
            try:
                results.append(gb.build())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Threads raised exceptions: {errors}"
        assert len(results) == 4
        # All results must be structurally valid GraphData
        for r in results:
            assert hasattr(r, "nodes")
            assert hasattr(r, "edges")
        # Cache must contain exactly one entry for this key
        assert len(gb._cache) == 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestGraphAPIEndpoint:
    """Integration tests for GET /api/graph via TestClient."""

    def test_get_full_graph_returns_200(self, api_client):
        resp = api_client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data

    def test_get_full_graph_returns_nodes(self, api_client):
        resp = api_client.get("/api/graph")
        data = resp.json()
        # api_client fixture creates alice.md and decision-one.md
        ids = [n["id"] for n in data["nodes"]]
        assert any("alice" in nid for nid in ids)

    def test_get_graph_focus_param(self, api_client):
        resp = api_client.get("/api/graph?focus=people/alice.md&max_degree=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["focus"] == "people/alice.md"

    def test_get_graph_types_filter(self, api_client):
        resp = api_client.get("/api/graph?types=person_note")
        assert resp.status_code == 200
        data = resp.json()
        for node in data["nodes"]:
            assert node["type"] == "person_note"

    def test_get_graph_types_comma_separated(self, api_client):
        """?types=person_note,decision must filter correctly (comma in one param)."""
        resp = api_client.get("/api/graph?types=person_note,decision")
        assert resp.status_code == 200
        data = resp.json()
        allowed = {"person_note", "decision"}
        for node in data["nodes"]:
            assert node["type"] in allowed

    def test_get_graph_types_repeated_params(self, api_client):
        """?types=person_note&types=decision (repeated param) must filter correctly."""
        resp = api_client.get("/api/graph?types=person_note&types=decision")
        assert resp.status_code == 200
        data = resp.json()
        allowed = {"person_note", "decision"}
        for node in data["nodes"]:
            assert node["type"] in allowed

    def test_get_graph_structured_links_carry_relation(self, tmp_vault: Path):
        """Structured link edges have relation and metadata in graph response."""
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        _write_note(
            tmp_vault,
            "work/with-relation.md",
            {
                "type": "decision",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
                "links": [{"target": "alice-example", "relation": "approved-by"}],
            },
        )
        vault = VaultLayer(str(tmp_vault))
        gb = GraphBuilder(vault)
        gd = gb.build()
        edge = next(
            (
                e
                for e in gd.edges
                if e.source == "work/with-relation.md"
                and e.target == "people/alice-example.md"
            ),
            None,
        )
        assert edge is not None
        assert edge.edge_type == "structured"
        assert edge.relation == "approved-by"


# ---------------------------------------------------------------------------
# New gap-coverage tests (code-review additions)
# ---------------------------------------------------------------------------


class TestFocusIsolatedNode:
    """Focus node with no edges must return a single-node graph at degree 0."""

    def test_isolated_focus_returns_single_node(self, tmp_vault: Path):
        # Write a note that has no links, no wikilinks, no shared tags
        _write_note(
            tmp_vault,
            "inbox/isolated.md",
            {
                "type": "idea",
                "domain": "personal",
                "tags": ["unique-tag-xyz-isolated"],
                "source": "voice",
                "confidence": 0.9,
                "review_status": "approved",
            },
            body="No references to anything.",
        )
        gd = _build(tmp_vault, focus="inbox/isolated.md", max_degree=2)
        assert _node_ids(gd) == {"inbox/isolated.md"}
        assert gd.edges == []
        isolated = gd.nodes[0]
        assert isolated.degree == 0

    def test_isolated_focus_degree_is_zero(self, tmp_vault: Path):
        _write_note(
            tmp_vault,
            "inbox/isolated2.md",
            {
                "type": "idea",
                "domain": "personal",
                "tags": ["unique-tag-xyz-isolated2"],
                "source": "voice",
                "confidence": 0.9,
                "review_status": "approved",
            },
        )
        gd = _build(tmp_vault, focus="inbox/isolated2.md", max_degree=3)
        node = next(n for n in gd.nodes if n.id == "inbox/isolated2.md")
        assert node.degree == 0


class TestNodeWeight:
    """Node weight should reflect total edge connections."""

    def test_node_weight_increases_with_incoming_edges(self, tmp_vault: Path):
        # Write two notes that both mention alice-example
        _write_note(
            tmp_vault,
            "work/weight-note-a.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 0.9,
                "review_status": "approved",
                "people": ["Alice Example"],
            },
        )
        _write_note(
            tmp_vault,
            "work/weight-note-b.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 0.9,
                "review_status": "approved",
                "people": ["Alice Example"],
            },
        )
        gd = _build(tmp_vault)
        alice = next(n for n in gd.nodes if n.id == "people/alice-example.md")
        # alice should have weight >= 2 (at least the two mentions we just added)
        assert alice.weight >= 2

    def test_unconnected_node_has_weight_zero(self, tmp_vault: Path):
        _write_note(
            tmp_vault,
            "inbox/no-connections.md",
            {
                "type": "idea",
                "domain": "personal",
                "tags": ["unique-weight-zero-tag"],
                "source": "voice",
                "confidence": 0.8,
                "review_status": "approved",
            },
        )
        gd = _build(tmp_vault)
        node = next(n for n in gd.nodes if n.id == "inbox/no-connections.md")
        assert node.weight == 0


class TestMultipleSharedTagsEdgeWeight:
    """Two notes sharing N tags produce an edge with weight == N."""

    def test_three_shared_tags_produce_weight_three(self, tmp_vault: Path):
        _write_note(
            tmp_vault,
            "work/multi-tag-a.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": ["multi-tag-alpha", "multi-tag-beta", "multi-tag-gamma"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
        )
        _write_note(
            tmp_vault,
            "work/multi-tag-b.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": ["multi-tag-alpha", "multi-tag-beta", "multi-tag-gamma"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
        )
        gd = _build(tmp_vault)
        ids = {"work/multi-tag-a.md", "work/multi-tag-b.md"}
        tag_edge = next(
            (
                e
                for e in gd.edges
                if {e.source, e.target} == ids and e.relation == "shares-tag"
            ),
            None,
        )
        assert tag_edge is not None, "Expected a shares-tag edge between multi-tag notes"
        assert tag_edge.weight == 3


class TestFocusOutsideTopN:
    """Focus note that is not in the top-n list_notes results must still appear."""

    def test_focus_loaded_even_when_beyond_n_limit(self, tmp_vault: Path):
        """The fixture vault has 5 notes; n=2 would normally exclude 3 of them.

        We pass focus=a note that is NOT in the top-2 by updated date and
        confirm it still appears in the result.
        """
        from monocle.graph import GraphBuilder
        from monocle.vault import VaultLayer

        vault = VaultLayer(str(tmp_vault))

        # Use n=1 — only 1 note loaded normally; focus must be fetched explicitly
        # We specify a note that is unlikely to be the top-1 by updated:
        focus = "technologies/idea-graph-viz.md"
        gb = GraphBuilder(vault)
        gd = gb.build(focus=focus, n=1, max_degree=2)

        # Focus must always be present even with n=1
        assert focus in _node_ids(gd), (
            "Focus note must be included even when n truncates it from the list"
        )
        focal = next(n for n in gd.nodes if n.id == focus)
        assert focal.degree == 0  # might have no reachable neighbours at n=1


class TestFocusWithTypesFilter:
    """Focus + types combined: if focus has type not in filter, result is empty."""

    def test_focus_excluded_by_types_filter_returns_empty(self, tmp_vault: Path):
        """Focus is alice-example (person_note); types=["decision"] excludes it."""
        gd = _build(
            tmp_vault,
            focus="people/alice-example.md",
            types=["decision"],
            max_degree=3,
        )
        # Alice is a person_note → filtered out → empty graph
        assert gd.nodes == []
        assert gd.edges == []

    def test_focus_included_by_types_filter_remains(self, tmp_vault: Path):
        """Focus is alice-example (person_note); types=["person_note"] keeps it."""
        gd = _build(
            tmp_vault,
            focus="people/alice-example.md",
            types=["person_note"],
            max_degree=3,
        )
        ids = _node_ids(gd)
        assert "people/alice-example.md" in ids
        # No non-person nodes should appear
        for node in gd.nodes:
            assert node.type == "person_note"


# ---------------------------------------------------------------------------
# Regression tests — edge-key identity bugs
# ---------------------------------------------------------------------------


class TestEdgeKeyIdentity:
    """Regression: edges with different relations must never be merged."""

    def test_different_relations_same_pair_produce_separate_edges(
        self, tmp_vault: Path
    ):
        """A note that both wikilinks *and* structured-links to the same target
        must produce two distinct edges (edge_type='wikilink', edge_type='structured'),
        not a single merged entry with a blended relation."""
        _write_note(
            tmp_vault,
            "work/dual-rel-source.md",
            {
                "type": "decision",
                "domain": "work",
                "tags": [],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
                "links": [{"target": "alice-example", "relation": "approved-by"}],
            },
            body="See also [[alice-example]] for context.",
        )
        gd = _build(tmp_vault)
        edges = [
            e
            for e in gd.edges
            if e.source == "work/dual-rel-source.md"
            and e.target == "people/alice-example.md"
        ]
        # Both a structured and a wikilink edge must appear independently
        edge_types = {e.edge_type for e in edges}
        assert "structured" in edge_types, "structured edge missing"
        assert "wikilink" in edge_types, "wikilink edge missing"
        # Relations must not be blended
        structured_edge = next(e for e in edges if e.edge_type == "structured")
        assert structured_edge.relation == "approved-by"
        wikilink_edge = next(e for e in edges if e.edge_type == "wikilink")
        assert wikilink_edge.relation == "links-to"

    def test_shared_tag_and_comention_same_pair_produce_separate_edges(
        self, tmp_vault: Path
    ):
        """A pair of notes that BOTH share a tag AND one mentions the other via
        people: must produce two separate edges (relation='shares-tag' and
        relation='mentioned-in'), not a single merged entry."""
        _write_note(
            tmp_vault,
            "people/alice-overlap.md",
            {
                "type": "person_note",
                "domain": "work",
                "tags": ["collab-overlap-tag"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
            },
        )
        _write_note(
            tmp_vault,
            "work/overlap-source.md",
            {
                "type": "observation",
                "domain": "work",
                "tags": ["collab-overlap-tag"],
                "source": "web",
                "confidence": 1.0,
                "review_status": "approved",
                "people": ["alice-overlap"],
            },
        )
        gd = _build(tmp_vault)
        pair = {"work/overlap-source.md", "people/alice-overlap.md"}
        pair_edges = [e for e in gd.edges if {e.source, e.target} == pair]
        relations = {e.relation for e in pair_edges}
        assert "mentioned-in" in relations, (
            "people co-mention edge lost due to key collision with shares-tag"
        )
        assert "shares-tag" in relations, (
            "shares-tag edge lost due to key collision with co-mention"
        )
