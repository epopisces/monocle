# IMM-45 — [M0] Inspect assets and bootstrap Monocle monorepo

**Source:** [Linear IMM-45](https://linear.app/immoil/issue/IMM-45/monocle-m0-inspect-assets-and-bootstrap-monocle-monorepo)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** None  
**Blocks:** [IMM-46](IMM-46.md), [IMM-58](IMM-58.md)  

## User story

As an implementer, I can build and test a fresh TypeScript workspace while preserving reusable legacy assets.

## Scope

Inspect read-only where available: legacy Monocle UI/trace/model abstractions; Obsidian Curator; create-obsidian-note scripts; vault frontmatter, templates, IDs and links. Create TS workspace with plugin, companion, Monocle core/index, Cravat and contracts boundaries. Document unverifiable assumptions rather than inventing schemas.

## Acceptance criteria

Clean install/build/test command succeeds; basic package contract test runs; inventory identifies keep/replace/defer; fixture vault and explicit read-only real-vault discovery plan exist.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not edit production vault, migrate legacy app wholesale, or rebuild markdown editor.

## Architecture references

Monocle MVP specification (D01–D08), M0. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Entry point; no implementation predecessors.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

