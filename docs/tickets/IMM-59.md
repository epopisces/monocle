# IMM-59 — [M4] Query metadata, persistent identities and explicit note relationships

**Source:** [Linear IMM-59](https://linear.app/immoil/issue/IMM-59/monocle-m4-query-metadata-persistent-identities-and-explicit-note-relationships)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-58](IMM-58.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As an agent or user, I can deterministically find notes by metadata and traverse explicit links.

## Scope

Resolve wikilinks/frontmatter references to immutable note IDs; store relation edges and source locations; expose read/search/filter/relationship API with source references; do not promote inferred links.

## Acceptance criteria

Rename changes path but not identity; backlink/edge queries return grounded note references; broken/ambiguous links reported; tests cover aliases.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No automatically inferred relationship graph.

## Architecture references

Monocle MVP specification (D01–D08), M4. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 14 Incrementally index synchronized notes in SQLite FTS5.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

