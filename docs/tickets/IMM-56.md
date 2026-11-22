# IMM-56 — [M3] Approve all pending eligible changes in current execution session

**Source:** [Linear IMM-56](https://linear.app/immoil/issue/IMM-56/monocle-m3-approve-all-pending-eligible-changes-in-current-execution-session)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-55](IMM-55.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can approve the remaining pending changes from one execution in one action.

## Scope

Implement explicit session-scoped bulk approval; call guarded writes for eligible changes; summarize applied/skipped/conflicted/failed; ensure new rebased proposals are not implicitly accepted.

## Acceptance criteria

Bulk approve touches only selected execution ID; other sessions untouched; partial results shown; errors retained for review.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No vault-wide approve-all.

## Architecture references

Monocle MVP specification (D01–D08), M3. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 11 Review session changes in native Obsidian diff view.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

