# IMM-45 asset inventory — keep / replace / defer

**Inspected:** 2026-11-22, on the implementing host, read-only.  
**Legend:** **Keep** = reuse/port the idea or code selectively · **Replace** = new implementation in the TS monorepo ·
**Defer** = not needed before a later milestone, or cannot be assessed yet.

## 1. Availability of external assets

| Asset | Found? | Notes |
|---|---|---|
| Legacy Monocle app | Yes, `legacy/` | Python/FastAPI backend + React/Vite frontend. Read-only reference. |
| Obsidian Curator agent | **No** | Searched `~/.copilot`, `~/.agents`, `~/.claude`, `C:\development` for `*curator*`. Not present. |
| `create-obsidian-note` skill/scripts | **No** | Same search for `*create-obsidian-note*`, `SKILL.md`. Not present. |
| Real vault | **No** | Only `.obsidian` found was `C:\development\prj_second_brain\vault`, an empty scaffold (1 `Dashboard.md`, `.gitkeep`s) from an older project, not the production vault. |

Anything that depends on Curator, the skill, or real vault conventions is **unverified**. See
[REAL-VAULT-DISCOVERY.md](REAL-VAULT-DISCOVERY.md) and the provisional-conventions section in `fixtures/README.md`.

## 2. Legacy Monocle (`legacy/`)

| Area | Location | Verdict | Rationale |
|---|---|---|---|
| Wikilink parsing (`[[x]]`, `[[x\|alias]]`), case-insensitive resolution | `monocle/vault/wikilinks.py` | **Keep (port logic)** | Small, well-specified; port to TS in `@monocle/core` for IMM-48/IMM-59. The regex ignores `#heading`/`^block` suffixes and embeds, so extend it. |
| Structured `links:` frontmatter (`LinkRef`) | `monocle/models.py`, `wikilinks.parse_links_field` | **Keep (idea)** | Matches the spec's explicit relationships. Confirm against the real vault first. |
| Note templates (YAML field specs: `template`, `note_type`, `default_folder`, `fields[]`) | `monocle/vault/templates/*.yaml` | **Defer → verify** | Useful input for IMM-52 schema validation, but Curator/`create-obsidian-note` is authoritative. Do not adopt until reconciled. Some fields (e.g. person care/prayer fields) are sensitive and must never appear in fixtures. |
| Frontmatter normalisation defaults | `monocle/vault/normalise.py` | **Replace** | Tied to legacy review-queue/confidence fields (`review_status`, `confidence`) that the new proposal model supersedes. |
| Note identity | `models.py` (`Note.file_path`) | **Replace** | Legacy identifies notes by **file path only**; no persistent frontmatter ID exists. The spec's stable ID is new work and needs a migration plan. |
| AI provider abstraction (Ollama/Azure/OpenAI/Foundry; `chat` stream, `embed`, `embed_batch`, `detect_embed_dimensions`) | `monocle/ai/*.py` | **Keep (design), Replace (code)** | Split it: chat/tool streaming becomes Cravat provider adapters (IMM-47); `embed*` becomes Monocle's embedding adapter with a local default (IMM-60). Both are rewritten in TS. |
| OTel span helpers / telemetry | `monocle/ai/base.py`, `telemetry.py` | **Defer** | Tracing is not in MVP scope. Reuse the async-generator-safe span idea later. |
| Index abstraction (`IndexLayer`: `upsert_chunks`, `delete_file`, `search`; Chroma + memory impls) | `monocle/index/*.py` | **Keep (interface idea)** | The memory/Chroma dual-implementation pattern fits the "optional Chroma" requirement (IMM-60). SQLite/FTS5 (IMM-58) is new. |
| Chunker | `monocle/ingest/chunker.py` | **Defer** | Evaluate for IMM-60 semantic chunking. |
| File watcher | `monocle/watcher.py` | **Replace** | Re-implement in TS with debounce plus startup reconciliation (IMM-58). |
| MCP server (`search_vault`, `read_note`, `capture_thought`, `create_note`) | `monocle/mcp_server.py` | **Defer (keep tool shape)** | The read/search tool names are a good model for read-only vault tools (IMM-48) and a future MCP surface. Write tools must go through managed mutations (IMM-54). |
| Ingest pipeline, confidence scoring, review queue, Teams/audio plugins, scheduler, weekly summary | `monocle/ingest`, `services/ingest*`, `agents/*` | **Replace / out of scope** | Superseded by proposals + risk policy. M365/Teams is deferred beyond MVP. |
| FastAPI routers / OpenAPI | `monocle/routers`, `openapi.json` | **Replace** | The companion transport is a new design (IMM-46). |
| Chat UI: `ChatMessage` streaming cursor, tool-call rendering, `useChat` async-iterator streaming with `AbortController` cancel, session picker, `sessionStore` | `frontend/src/components/Chat`, `hooks/useChat.ts` | **Keep (selective salvage)** | The best UI salvage for the plugin panel (IMM-46/47/50). It is React; the plugin must decide on React or Obsidian-native DOM. Port the streaming/cancel state machine, not the styling. |
| `CommandPalette` | `frontend/src/components/CommandPalette` | **Replace** | Use Obsidian's native command palette (IMM-51). |
| DocumentBrowser / NoteEditor / FileTree / FormEditor (CodeMirror) | `frontend/src/components/DocumentBrowser` | **Replace (do not rebuild)** | The spec excludes a bespoke editor and vault navigator. Obsidian provides these. |
| Graph (react-force-graph/aframe), Stats, Search screens | `frontend/src/components/*` | **Defer** | Advanced graph/search UI is post-MVP. |
| Tests: pytest suite incl. `test_contracts.py`, Playwright e2e | `monocle/tests`, `tests/e2e` | **Defer (reference)** | Not reusable directly (Python/FastAPI). The contract-test idea carries over to `test/workspace-boundaries.test.ts`. |
| `.gitignore` | `legacy/.gitignore` | **Replace** | New root `.gitignore` is TS-oriented, ignores derived index state (`*.db`, `chroma_data/`) and host-local config/secrets. |

## 3. What IMM-45 bootstrapped

- npm workspaces (`packages/*`), TypeScript project references (`tsc -b`), vitest. Node ≥ 22. pnpm is not installed
  on the host, so npm is used.
- Packages and allowed dependencies (enforced by `test/workspace-boundaries.test.ts`):
  - `@monocle/contracts` → none
  - `@monocle/core` (Monocle knowledge services) → contracts
  - `@monocle/cravat` (execution) → contracts (**never** `@monocle/core`)
  - `@monocle/companion` → contracts, core, cravat
  - `@monocle/obsidian-plugin` → contracts only (plus the `obsidian` API dev dependency)
- `@monocle/contracts` exports `CONTRACT_VERSION` and `isContractCompatible` (semver; 0.x minors are breaking), plus
  the `PackageDescriptor` that every package exports.
- Synthetic fixture vault at `fixtures/vault/`.

## 4. Assumptions and open questions for later tickets

- **IMM-46:** the plugin currently compiles with `tsc` only. Bundling to `main.js` (esbuild, CJS, `obsidian` external)
  and installing into a test vault are IMM-46's job. UI technology (React salvage vs native DOM) is undecided.
  Companion transport (HTTP/WebSocket on loopback) is undecided; `isContractCompatible` is meant for the health
  handshake.
- **IMM-58:** the persistent ID field name/format is **unverified**. The fixture uses `id: fx-NNNN` as a placeholder,
  so keep the ID field configurable. SQLite driver choice is open: `node:sqlite` is built into Node 22.5+ (still
  experimental in 22) and needs no native build, while `better-sqlite3` is a native module. Check FTS5 availability
  on target hosts. Legacy has no frontmatter ID, so any real vault may need an ID migration plan.
- **IMM-52:** Curator and `create-obsidian-note` were not inspected. Do not hard-code legacy templates as the schema.
- Package naming: Cravat is scoped as `@monocle/cravat` for now. Rename it if Cravat is published independently.
