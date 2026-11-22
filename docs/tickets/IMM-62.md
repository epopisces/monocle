# IMM-62 — [M5] Verify Monocle MVP end to end and on second host

**Source:** [Linear IMM-62](https://linear.app/immoil/issue/IMM-62/monocle-m5-verify-monocle-mvp-end-to-end-and-on-second-host)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-48](IMM-48.md), [IMM-49](IMM-49.md), [IMM-50](IMM-50.md), [IMM-51](IMM-51.md), [IMM-52](IMM-52.md), [IMM-53](IMM-53.md), [IMM-54](IMM-54.md), [IMM-55](IMM-55.md), [IMM-56](IMM-56.md), [IMM-57](IMM-57.md), [IMM-58](IMM-58.md), [IMM-59](IMM-59.md), [IMM-60](IMM-60.md), [IMM-61](IMM-61.md)  
**Blocks:** None  

## User story

As an operator, I can reproduce the full create/curate/review/index experience on a second supported machine.

## Scope

Exercise D07.7 acceptance checklist on representative fixture vault; verify sync is external, local config/secret split, portable non-secret settings, companion restart, blocked writes, stale rebases, index rebuild, and read-only first path. Document install/upgrade commands.

## Acceptance criteria

Automated integration suite and manual Obsidian smoke test pass; second host setup documented/tested; no production-vault migration required; known limitations captured.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No Microsoft 365 or Top Hat integration; no cross-device proposal/chat sync.

## Architecture references

Monocle MVP specification (D01–D08), M5. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 04 Supply active-note context and restricted read-only vault tools; 05 Configure model, context window and thinking effort in Monocle; 06 Persist and resume local Monocle conversations; 07 Route registered deterministic commands and agentic requests; 08 Create schema-valid notes via existing Curator skill; 09 Persist session-scoped portable change proposals; 10 Validate and apply managed changes with risk policy; 11 Review session changes in native Obsidian diff view; 12 Approve all pending eligible changes in current execution session; 13 Rebase stale changes into new pending proposals; 14 Incrementally index synchronized notes in SQLite FTS5; 15 Query metadata, persistent identities and explicit note relationships; 16 Add configurable optional ChromaDB semantic retrieval; 17 Show compact index health and expandable maintenance controls.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

