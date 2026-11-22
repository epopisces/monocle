# IMM-57 — [M3] Rebase stale changes into new pending proposals

**Source:** [Linear IMM-57](https://linear.app/immoil/issue/IMM-57/monocle-m3-rebase-stale-changes-into-new-pending-proposals)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-54](IMM-54.md), [IMM-55](IMM-55.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I get a new reviewable change when the note has moved ahead since proposal generation.

## Scope

Detect source hash mismatch; try deterministic three-way rebase against current content; optionally request Cravat reconciliation for ambiguous cases; generate new proposal ID and lineage, never transfer prior approval.

## Acceptance criteria

Original proposal marked superseded; new proposal targets current hash; approved predecessor does not authorize successor; ambiguous merge remains pending.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No silent force overwrite or distributed locking.

## Architecture references

Monocle MVP specification (D01–D08), M3. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 10 Validate and apply managed changes with risk policy; 11 Review session changes in native Obsidian diff view.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

