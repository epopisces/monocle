# IMM-52 — [M2] Create schema-valid notes via existing Curator skill

**Source:** [Linear IMM-52](https://linear.app/immoil/issue/IMM-52/monocle-m2-create-schema-valid-notes-via-existing-curator-skill)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-48](IMM-48.md), [IMM-51](IMM-51.md)  
**Blocks:** [IMM-53](IMM-53.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can create a note using Obsidian Curator and create-obsidian-note with the vault's established conventions.

## Scope

Inspect and integrate existing skill/script including Python dependencies; define deterministic note generation/ID semantics after vault inspection; test against fixture vault and same templates as Obsidian; use safe managed mutation as applicable.

## Acceptance criteria

New note has valid unique persistent frontmatter ID and expected template; deterministic generated fields match existing conventions; no overwrite of existing path/ID; failures are actionable.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not rewrite existing Curator agent or invent vault schema.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 04 Supply active-note context and restricted read-only vault tools; 07 Route registered deterministic commands and agentic requests.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

