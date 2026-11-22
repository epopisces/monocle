# IMM-46 — [M1] Connect Obsidian panel to independent companion

**Source:** [Linear IMM-46](https://linear.app/immoil/issue/IMM-46/monocle-m1-connect-obsidian-panel-to-independent-companion)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-45](IMM-45.md)  
**Blocks:** [IMM-47](IMM-47.md)  

## User story

As an Obsidian user, I can open a Monocle panel and connect to the independently running local companion.

## Scope

Implement minimal plugin panel and loopback companion endpoint; configurable host-specific endpoint and health check; lifecycle independent of Obsidian; errors shown without blocking native editing.

## Acceptance criteria

Plugin connects to companion; closing Obsidian does not stop companion; disconnected/reconnected states visible; integration test and restart smoke test pass.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No agent execution, indexing or vault mutation yet.

## Architecture references

Monocle MVP specification (D01–D08), M1. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 01 Inspect assets and bootstrap Monocle monorepo.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

