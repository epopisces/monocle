# IMM-53 — [M3] Persist session-scoped portable change proposals

**Source:** [Linear IMM-53](https://linear.app/immoil/issue/IMM-53/monocle-m3-persist-session-scoped-portable-change-proposals)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-52](IMM-52.md)  
**Blocks:** [IMM-54](IMM-54.md), [IMM-55](IMM-55.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can retain review-worthy curation proposals across restarts without applying them.

## Scope

Define versioned portable proposal schema: proposal/change-set IDs, execution ID, note IDs, base hashes, patch, risk, status. Store locally; expose change set listing per execution; no authoritative index ingestion.

## Acceptance criteria

Multiple changes linked to one execution; restart preserves pending proposals; changes from other sessions isolated; serialization round-trip test.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No cross-device synchronization or comprehensive agent trace storage.

## Architecture references

Monocle MVP specification (D01–D08), M3. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 08 Create schema-valid notes via existing Curator skill.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

