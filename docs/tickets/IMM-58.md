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

- [x] Implementation completed
- [x] Automated checks passed (record command and outcome)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

- **Code:** `packages/monocle-core/src/note-index/` — `openNoteIndex()` (SQLite FTS5 index: scanner, reconcile,
  rebuild, exact search, note ID/path tracking, duplicate-ID diagnosis, `assertNoteIdAvailable` for managed
  mutations) and `watchVault()` (recursive `fs.watch`, debounce, startup reconciliation, periodic safety-net rescan).
  Exported from `@monocle/core`.
- **SQLite driver: `node:sqlite`** (built into Node ≥ 22.5; verified FTS5 on Node 22.20.0 / SQLite 3.50.4 without a
  flag). Chosen over `better-sqlite3` to avoid a native build on each host (Windows/second host) and keep the
  companion dependency-free; trade-off is that it is still experimental in Node 22 (prints an `ExperimentalWarning`).
  It is isolated in `note-index.ts`, so swapping drivers is local. Frontmatter is parsed with `yaml` (new dependency).
- **Design:** the watcher never applies events incrementally; every debounced burst runs a full `reconcile()`
  (mtime/size fast path, then SHA-256), so missed or out-of-order events cannot corrupt the index. Moves are paired by
  persistent ID first, then by content hash. A schema/config fingerprint (schema version, ID field, excluded folders)
  forces a rebuild from Markdown on change.
- **Note ID field** is configurable (`idField`, default `id` — provisional until real-vault discovery).
- **Automated checks:** `npm ci && npm run check` — build OK, 37/37 tests passed (15 new in
  `packages/monocle-core/test/note-index.test.ts` and `vault-watcher.test.ts`).
- **Acceptance:** create/edit/move/delete after reconciliation, folder renames via the watcher, changes made while
  stopped recovered on startup reconciliation, exact token search (`lanternfish-7731`), and full rebuild equal to the
  incremental index on the fixture vault are all covered by tests. Manual Obsidian verification is not applicable (no
  Obsidian/agent runtime in this ticket). Not verified on Linux/macOS (`fs.watch` recursive is supported on Node 22).

