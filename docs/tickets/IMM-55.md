# IMM-55 — [M3] Review session changes in native Obsidian diff view

**Source:** [Linear IMM-55](https://linear.app/immoil/issue/IMM-55/monocle-m3-review-session-changes-in-native-obsidian-diff-view)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-53](IMM-53.md), [IMM-54](IMM-54.md)  
**Blocks:** [IMM-56](IMM-56.md), [IMM-57](IMM-57.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can inspect and act on changes from my current session in Obsidian.

## Scope

Use maintained CodeMirror/editor diff primitives for inline and side-by-side preview; previous/next navigation; accept/reject individual proposal changes; companion retains mutation authority.

## Acceptance criteria

Each changed document displays old/new correctly; navigation is session-scoped; individual approval/rejection persists; no raw file rewrite from UI bypasses guard.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not recreate complete VS Code editor or depend on community diff plugin.

## Architecture references

Monocle MVP specification (D01–D08), M3. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 09 Persist session-scoped portable change proposals; 10 Validate and apply managed changes with risk policy.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

