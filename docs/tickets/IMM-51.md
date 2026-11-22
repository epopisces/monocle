# IMM-51 — [M2] Route registered deterministic commands and agentic requests

**Source:** [Linear IMM-51](https://linear.app/immoil/issue/IMM-51/monocle-m2-route-registered-deterministic-commands-and-agentic-requests)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-48](IMM-48.md)  
**Blocks:** [IMM-52](IMM-52.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can use chat, command palette or contextual actions without invoking an agent for deterministic work.

## Scope

Implement common command registry and arguments; route /validate and read-only operations to Monocle, /lookup and free-form requests to Cravat; include context requirements and operation permissions.

## Acceptance criteria

Same registered operation reachable by chat/palette/context where appropriate; deterministic commands do not start Cravat; errors identify missing context.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not implement an entirely new general command language.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 04 Supply active-note context and restricted read-only vault tools.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

