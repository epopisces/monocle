# IMM-48 — [M1] Supply active-note context and restricted read-only vault tools

**Source:** [Linear IMM-48](https://linear.app/immoil/issue/IMM-48/monocle-m1-supply-active-note-context-and-restricted-read-only-vault-tools)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-47](IMM-47.md)  
**Blocks:** [IMM-51](IMM-51.md), [IMM-52](IMM-52.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can ask the agent about the active note and let it read additional relevant vault notes without modifying them.

## Scope

Pass active note/selection and explicit context inclusions/exclusions; add read-only note/list/search-lite tools via Monocle contract; test containment on test vault and forbid write-capable filesystem tools in this execution mode.

## Acceptance criteria

Summarize active note succeeds; agent reads another allowed note; excluded context not transmitted; path traversal and write attempts fail; test vault hashes unchanged.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No note mutation or full index needed.

## Architecture references

Monocle MVP specification (D01–D08), M1. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 03 Stream and cancel a Cravat execution through Copilot adapter.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

