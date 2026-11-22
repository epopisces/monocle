# Offline progress tracking

This is a local checklist; it does **not** reflect live Linear status. Export statuses were all `Backlog`.

- [x] [IMM-45](tickets/IMM-45.md) — M0: Inspect assets and bootstrap Monocle monorepo
- [x] [IMM-46](tickets/IMM-46.md) — M1: Connect Obsidian panel to independent companion
- [x] [IMM-47](tickets/IMM-47.md) — M1: Stream and cancel a Cravat execution through Copilot adapter
- [ ] [IMM-48](tickets/IMM-48.md) — M1: Supply active-note context and restricted read-only vault tools
- [x] [IMM-49](tickets/IMM-49.md) — M2: Configure model, context window and thinking effort in Monocle
- [x] [IMM-50](tickets/IMM-50.md) — M2: Persist and resume local Monocle conversations
- [ ] [IMM-51](tickets/IMM-51.md) — M2: Route registered deterministic commands and agentic requests
- [ ] [IMM-52](tickets/IMM-52.md) — M2: Create schema-valid notes via existing Curator skill
- [ ] [IMM-53](tickets/IMM-53.md) — M3: Persist session-scoped portable change proposals
- [ ] [IMM-54](tickets/IMM-54.md) — M3: Validate and apply managed changes with risk policy
- [ ] [IMM-55](tickets/IMM-55.md) — M3: Review session changes in native Obsidian diff view
- [ ] [IMM-56](tickets/IMM-56.md) — M3: Approve all pending eligible changes in current execution session
- [ ] [IMM-57](tickets/IMM-57.md) — M3: Rebase stale changes into new pending proposals
- [x] [IMM-58](tickets/IMM-58.md) — M4: Incrementally index synchronized notes in SQLite FTS5
- [x] [IMM-59](tickets/IMM-59.md) — M4: Query metadata, persistent identities and explicit note relationships
- [x] [IMM-60](tickets/IMM-60.md) — M4: Add configurable optional ChromaDB semantic retrieval
- [x] [IMM-61](tickets/IMM-61.md) — M4: Show compact index health and expandable maintenance controls
- [ ] [IMM-62](tickets/IMM-62.md) — M5: Verify Monocle MVP end to end and on second host

## Sync-back log

| Date | Issue | Change/commit | Tests | Linear synchronized? |
|---|---|---|---|---|
| 2026-11-22 | IMM-45 | Bootstrap TS monorepo, contracts/boundary tests, fixture vault, asset inventory, real-vault discovery plan (branch `epopisces-imm-45-bootstrap-monorepo`) | `npm ci && npm run check`: 22/22 passed | No |
| 2026-11-22 | IMM-58 | SQLite FTS5 note index (`node:sqlite`) with reconcile/rebuild/search, ID/path/move tracking, duplicate-ID diagnosis, debounced watcher (branch `epopisces-imm-58-sqlite-fts5-index`) | `npm ci && npm run check`: 37/37 passed | No |
| 2026-11-22 | IMM-46 | Loopback companion (`/v1/health`, CLI), plugin panel/status/settings with connection state machine, esbuild bundle, isolated Obsidian smoke script (branch `epopisces-imm-46-obsidian-panel`) | `npm ci && npm run check`: 43/43 passed pre-merge, 58/58 after merging IMM-58; `npm run smoke:obsidian` (Obsidian 1.8.9): 8/8 passed | No |
| 2026-11-22 | IMM-59 | Explicit relationship index (wikilinks, embeds, frontmatter links; path/name/alias resolution to rowid-backed identities), backlinks, broken/ambiguous diagnosis, metadata filter; SCHEMA_VERSION 2 (branch `epopisces-imm-59-metadata-relationships`) | `npm ci && npm run check`: 46/46 passed pre-merge, 67/67 after merging IMM-46 | No |
| 2026-11-22 | IMM-60 | Optional semantic retrieval: heading-aware chunker with content-hash passage IDs, local-default Ollama + policy-gated OpenAI-compatible embedding adapters, Chroma v2 REST store, bounded background queue with embedding cache and model-change rebuild, unified retriever with RRF fusion and lexical fallback (branch `epopisces-imm-60-chromadb-semantic-retrieval`) | `npm ci && npm run check`: 90/90 passed (23 new) | No |
| 2026-11-22 | IMM-61 | Index health service (core), `/v1/index/*` companion routes + `--vault/--state-dir/--exclude/--semantic-config` CLI, status-bar health indicator with modal maintenance panel (reindex note, reconcile, confirmed rebuild) (branch `epopisces-imm-61-index-health-ui`) | `npm ci && npm run check`: 103/103 passed pre-merge, 132/132 after merging IMM-47; `npm run smoke:obsidian`: 14/14 pre-merge, 20/20 after merge | No |
| 2026-11-22 | IMM-47 | Execution contract 0.2.0, Cravat ExecutionManager + Copilot CLI adapter, streamed NDJSON/cancel routes with Origin guard, panel prompt/stream/cancel UI (branch `epopisces-imm-47-cravat-stream-and-cancel`) | `npm ci && npm run check`: 87/87 passed pre-merge, 119/119 after merging IMM-59/60; `npm run smoke:obsidian`: 14/14 (fake CLI), 11/11 live Copilot | No |
| 2026-11-22 | IMM-49 | Optional execution settings (model, reasoning effort, context window) in contract 0.2.x, `GET /v1/capabilities` discovered from the Copilot CLI's help, pre-run validation with actionable `invalid_request`, panel selects (branch `epopisces-imm-49-model-settings`) | `npm ci && npm run check`: 129/129 passed (10 new), 142/142 after merging IMM-61; `npm run smoke:obsidian`: 19/19 (fake CLI), 25/25 after merge, 16/16 live Copilot | No |
| 2026-11-22 | IMM-50 | Companion-side machine-local conversation store (`--data-dir`/`MONOCLE_DATA_DIR`), `/v1/conversations` routes, optional `conversationId`/`providerSession` contract fields (still 0.2.0), Copilot session resume via `--session-id`/`--resume` with truthful continuity, panel transcript/picker (branch `epopisces-imm-50-conversation-persistence`) | `npm ci && npm run check`: 161/161 after merging IMM-49/61; `npm run smoke:obsidian`: fake CLI pass, 31/31 live Copilot | No |
