# IMM-47 — [M1] Stream and cancel a Cravat execution through Copilot adapter

**Source:** [Linear IMM-47](https://linear.app/immoil/issue/IMM-47/monocle-m1-stream-and-cancel-a-cravat-execution-through-copilot-adapter)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-46](IMM-46.md)  
**Blocks:** [IMM-48](IMM-48.md), [IMM-49](IMM-49.md), [IMM-50](IMM-50.md)  

## User story

As an Obsidian user, I can submit a prompt and see a streamed answer with execution identity and cancellation.

## Scope

Define versioned Monocle→Cravat execution request/event contract; keep Cravat separate module inside companion; implement one supported installed Copilot CLI/SDK adapter; stream outputs and terminal states; enforce requested cancellation and error reporting.

## Acceptance criteria

Prompt round-trip streams tokens/events to panel; execution ID and provider errors shown; cancellation stops work and completes terminally; provider adapter tests include failed launch.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No second provider, long-term trace store or write tools.

## Architecture references

Monocle MVP specification (D01–D08), M1. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 02 Connect Obsidian panel to independent companion.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

