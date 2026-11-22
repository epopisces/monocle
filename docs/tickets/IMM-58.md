# IMM-58 — [M4] Incrementally index synchronized notes in SQLite FTS5

**Source:** [Linear IMM-58](https://linear.app/immoil/issue/IMM-58/monocle-m4-incrementally-index-synchronized-notes-in-sqlite-fts5)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-45](IMM-45.md)  
**Blocks:** [IMM-59](IMM-59.md), [IMM-60](IMM-60.md), [IMM-61](IMM-61.md), [IMM-62](IMM-62.md)  

## User story

As a user, my locally synchronized notes become searchable without manual reindexing.

## Scope

Implement scanner, watcher with debounce, startup reconciliation, note ID/path tracking, frontmatter and full-text FTS5; track moves/deletes/content hashes; index rebuilt from Markdown; reject duplicate IDs for managed mutations and diagnose legacy duplicates.

## Acceptance criteria

Create/edit/move/delete reflected after reconciliation; missed watcher events recovered; exact search works; full rebuild matches incremental index on fixture.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No vectors or semantic API in this ticket.

## Architecture references

Monocle MVP specification (D01–D08), M4. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 01 Inspect assets and bootstrap Monocle monorepo.

---

## Offline execution record (local, not synchronized to Linear)

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

