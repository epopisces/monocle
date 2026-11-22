# IMM-61 — [M4] Show compact index health and expandable maintenance controls

**Source:** [Linear IMM-61](https://linear.app/immoil/issue/IMM-61/monocle-m4-show-compact-index-health-and-expandable-maintenance-controls)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-58](IMM-58.md), [IMM-60](IMM-60.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can see indexing health at a glance and inspect maintenance controls only when needed.

## Scope

Add status-bar indicator healthy/indexing/degraded/unavailable, expandable queue/errors/freshness panel, deterministic current-note reindex, reconcile and rebuild actions with confirmations where needed.

## Acceptance criteria

Status accurately reflects queue/errors and backend availability; controls invoke deterministic services; closed panel does not occupy workspace.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No advanced graph explorer or database administration console.

## Architecture references

Monocle MVP specification (D01–D08), M4. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 14 Incrementally index synchronized notes in SQLite FTS5; 16 Add configurable optional ChromaDB semantic retrieval.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed (record command and outcome)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

- **Core:** `openIndexService()` (`packages/monocle-core/src/index-service.ts`) owns the note index, optional semantic
  index and watcher, and exposes `health()`, `reconcile()`, `rebuild()`, `reindexNote(path)`. Health level:
  `unavailable` until a reconcile succeeds; `degraded` when reconcile/watcher/semantic errors exist; `indexing` while
  the semantic queue is pending/indexing; otherwise `healthy`. Frontmatter/duplicate-ID warnings are listed but do not
  degrade. `NoteIndex.reindexNote(path)` re-reads one note regardless of mtime (rejects absolute/drive/traversal paths).
- **Contracts:** `packages/contracts/src/index-health.ts` — `IndexHealth`, `IndexActionResponse`, route constants,
  `isIndexHealth`. Additive; `CONTRACT_VERSION` not bumped (older companions answer 404 → plugin shows unavailable).
- **Companion:** `GET /v1/index/health`, `POST /v1/index/{reconcile,rebuild,reindex-note}` (POSTs require
  `application/json`; with IMM-47's Origin guard only Obsidian's renderer origin passes CORS — CSRF guard). CLI gains `--vault`
  (or `MONOCLE_VAULT`), `--state-dir` (default `~/.monocle/state/<hash>`), repeatable `--exclude`, and
  `--semantic-config <json>`. Without `--vault` the routes return 404.
- **Plugin:** Obsidian-free `IndexHealthMonitor` polls every 5 s while connected; `index-ui.ts` adds the status-bar
  indicator (healthy / indexing (N queued) / degraded / unavailable), a modal panel with freshness, queue, errors,
  warnings and buttons (reindex current note, reconcile, rebuild with confirmation), plus four commands. The panel is a
  modal, so it takes no workspace when closed.
- **Automated checks:** `npm ci && npm run check` — 103/103 passed pre-merge, 132/132 after merging IMM-47 (new: index-service 4, note-index reindex 1,
  companion routes 4 + process 1, plugin monitor 3; bundle test stub gained `Modal`/`Notice`).
- **Obsidian verification:** `npm run smoke:obsidian` (real Obsidian, fixture vault) — 14/14 passed pre-merge, 20/20 after merging IMM-47, including
  healthy indicator, expanded panel contents, reconcile control, closed panel adds no leaves, reindex-current-note
  command after an edit, and "Index unavailable" after the companion stops.
- **Not done:** auto-reading Obsidian's templates folder (pass `--exclude templates`); live Chroma/Ollama
  verification of the semantic health path (IMM-62); auth token.