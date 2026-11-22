# IMM-49 — [M2] Configure model, context window and thinking effort in Monocle

**Source:** [Linear IMM-49](https://linear.app/immoil/issue/IMM-49/monocle-m2-configure-model-context-window-and-thinking-effort-in-monocle)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-47](IMM-47.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can select execution options in Monocle while Cravat validates and applies provider-supported settings.

## Scope

Expose model, context budget and effort in panel; query adapter capabilities; pass parameters through execution contract; report unsupported settings rather than silently ignoring.

## Acceptance criteria

Supported settings appear in adapter request; invalid settings return actionable errors; switching models does not change Monocle knowledge services.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No custom model gateway or assumption of provider feature parity.

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

