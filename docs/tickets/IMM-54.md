# IMM-54 — [M3] Validate and apply managed changes with risk policy

**Source:** [Linear IMM-54](https://linear.app/immoil/issue/IMM-54/monocle-m3-validate-and-apply-managed-changes-with-risk-policy)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-53](IMM-53.md)  
**Blocks:** [IMM-55](IMM-55.md), [IMM-57](IMM-57.md), [IMM-62](IMM-62.md)  

## User story

As a user, low-risk allowed changes apply safely and high-risk edits await review.

## Scope

Implement progressive before/after schema validation, unique ID rule, risk policy, write permissions, optimistic version guards, lightweight mutation records; reject new violations while tolerating unrelated legacy ones.

## Acceptance criteria

Low-risk operation commits; high-risk operation stays pending; duplicate ID and unsafe overwrite rejected; changed note hash prevents unsafe application.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Not an OS-enforced sandbox for every trusted direct writer.

## Architecture references

Monocle MVP specification (D01–D08), M3. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 09 Persist session-scoped portable change proposals.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

