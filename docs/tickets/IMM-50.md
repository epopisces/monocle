# IMM-50 — [M2] Persist and resume local Monocle conversations

**Source:** [Linear IMM-50](https://linear.app/immoil/issue/IMM-50/monocle-m2-persist-and-resume-local-monocle-conversations)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-47](IMM-47.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can reopen a conversation after restarting Obsidian or companion.

## Scope

Store conversation IDs, messages, execution IDs and contextual references locally; allow multiple executions per conversation; distinguish UI resume from provider-session resume.

## Acceptance criteria

Restart preserves history; new execution attaches to same conversation; unavailable provider state is represented truthfully; no vault sync of conversations.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No cross-device conversation sync or indefinite raw tool trace retention.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 03 Stream and cancel a Cravat execution through Copilot adapter.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

