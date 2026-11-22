# IMM-61 — [M4] Show compact index health and expandable maintenance controls

**Source:** [Linear IMM-61](https://linear.app/immoil/issue/IMM-61/monocle-m4-show-compact-index-health-and-expandable-maintenance-controls)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-58](IMM-58.md), [IMM-60](IMM-60.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can see indexing health at a glance and inspect maintenance controls only when needed.

## Scope

Add status-bar indicator healthy/indexing/degraded/unavailable, expandable queue/errors/freshness panel, deterministic current-note reindex, reconcile and rebuild actions with confirmations where needed.

## Acceptance criteria

Status accurately reflects queue/errors and backend availability; controls invoke deterministic services; closed panel does not occupy workspace.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No advanced graph explorer or database administration console.

## Architecture references

Monocle MVP specification (D01–D08), M4. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 14 Incrementally index synchronized notes in SQLite FTS5; 16 Add configurable optional ChromaDB semantic retrieval.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

