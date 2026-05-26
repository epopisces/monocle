---
type: build-plan
project: monocle
maintained-by: github-copilot
last-updated: 2026-05-05
active-milestone: M49
---

# Monocle — Copilot Build Plan

## Instructions for GitHub Copilot

This is the primary reference document for building Monocle. Read it at the start of every session. It contains all the context needed to make decisions and take action without reading the full SRS, PRD, or UI Design documents.

**Session rules:**
1. Read `## Current Status` first to orient yourself.
2. Work on the active milestone in order — do not jump ahead.
3. Mark each deliverable `[x]` as you complete it.
4. After completing all acceptance criteria for a milestone, update `## Current Status` and the `## Milestone Tracker`.
5. **Run tests before marking any deliverable complete.** See `## Test Commands`.
6. When resolving a Technical Spike, record the outcome under `## Technical Spikes`.
7. If a design question is not answered here, check `docs/srs.md` first (source of truth for behaviour), then `docs/prd.md` (product goals), then `docs/ui-design.md` (frontend layout).
8. Do not invent design decisions not covered in docs — surface any gaps as a comment in this file under the relevant milestone.

---

## Current Status

**Active Milestone:** M49 — Persistent User Memory
**Last Completed:** M48 — Cleanup & Contract Hardening (2026-04-29)
**Note:** The near-term product direction is now documented and implemented only around trust-first capture, a unified capture workbench, lean chat, distinct omnisearch, and one supported unified runtime topology. M24, M26, and M33 remain deferred to a future phase, and M41 remains paused until it is reconciled against this simplified baseline.
**Blocked By:** None
**Session Notes (M48 — Cleanup & Contract Hardening):**
- **Status:** COMPLETE (2026-04-29)
- Removed the remaining fragmented capture drawers/tests and obsolete review, failure, and ingest-notification adapter routes, refreshed the generated API artifacts, and aligned the live docs to the workbench-first simplified contract.
- **Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 942 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 432 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.
**Session Notes (M47 — Omnisearch Hardening):**
- **Status:** COMPLETE (2026-04-29)
- Replaced per-request full-vault omnisearch scans with an AI-free cached catalog, tightened the meaningful 3-character fast-match contract on both sides of `/api/search/omni`, and hardened the topbar omnisearch UI against stale responses plus keyboard/accessibility edge cases.
- **Test Results:** `uv run python -m pytest monocle/tests/test_api.py::TestOmniSearch -x --tb=short -q` → 11 passed, EXIT 0; `cd frontend && npm run test -- --run src/OmniSearch.test.tsx --reporter=dot` → 15 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.
**Session Notes (M46 — Lean Chat & Explicit URL Capture):**
- **Status:** COMPLETE (2026-04-29)
- Removed the router-level `fetch_urls` prefetch path from `/api/chat`, replaced the chat composer’s implicit URL side effects with an explicit `Capture URLs` action that sends detected links into `POST /api/ingest`, and kept `create_reference_from_url` available only through explicit agent or MCP tool use.
- **Test Results:** `cd frontend && npm run test -- --run src/Chat.test.tsx src/useChat.test.ts --reporter=dot` → 80 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0; `uv run python -m pytest monocle/tests/test_agents.py monocle/tests/test_mcp.py -x --tb=short -q` → 112 passed, EXIT 0.
**Session Notes (M45 — Unified Capture Workbench Frontend):**
- **Status:** COMPLETE (2026-04-29)
- Replaced the separate prepared-session, review-queue, and failed-capture topbar entry points with one capture-workbench drawer backed by `/api/capture-workbench`, while keeping `/ingest-review` and `/docs` as the deep handoff routes for prepared sessions and pending-note edits.
- **Test Results:** `cd frontend && npm run test -- --run` → 473 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.
**Session Notes (M44 — Unified Capture Workbench Backend Contract):**
- **Status:** COMPLETE (2026-04-29)
- Added `GET /api/capture-workbench` plus a shared capture-workbench service so prepared ingest sessions, low-confidence pending review notes, and failure records now ship in one backend shape with one top-level actionable count; the temporary legacy adapters introduced here were removed later in M48.
- **Test Results:** `uv run python -m pytest monocle/tests/test_api.py monocle/tests/test_review.py monocle/tests/test_ingest.py -x --tb=short -q` → 201 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.
**Session Notes (M43 — Consolidate Ingest Workflow Ownership):**
- **Status:** COMPLETE (2026-04-29)
- Added `monocle/services/ingest_workflow.py` as the single workflow owner for ingest review and execution orchestration, moved routers and service callers onto it, and reduced `IngestSessionStore` review mutations to persistence-only updates.
- **Test Results:** `uv run python -m pytest monocle/tests/test_ingest.py monocle/tests/test_ingest_prepare.py monocle/tests/test_api.py -x --tb=short -q` → 164 passed, EXIT 0.
**Session Notes (D1 — Simplification Docs Alignment):**
- **Status:** COMPLETE (2026-04-28)
- Aligned `docs/prd.md`, `docs/srs.md`, `docs/architecture.md`, `docs/ui-design.md`, and `docs/build-plan.md` around trust-first capture, a unified capture workbench, explicit URL capture handoff, lean chat, distinct omnisearch, and one supported runtime topology.
- Validation: reviewed the D1 doc diff for cross-document consistency before starting M42.
**Session Notes (M42 — Remove Separate-Process Support):**
- **Status:** COMPLETE (2026-04-28)
- Collapsed the backend to one supported runtime path by removing split-runtime gating from `monocle/main.py`, deleting the `ProcessManager` module and standalone split CLI commands, and cleaning the related config/example/tasks/test surfaces.
- **Test Results:** `uv run python -m pytest monocle/tests/test_cli.py monocle/tests/test_imports.py -x --tb=short -q` → 39 passed, EXIT 0; `uv run python -m pytest monocle/tests/test_api.py monocle/tests/test_mcp.py -x --tb=short -q` → 133 passed, EXIT 0.

**Older milestone details:** archived in [docs/milestones.md](milestones.md).

---

## Test Commands

Run these after every change. Copilot **must** run the appropriate command before marking any deliverable complete.

```bash
# Backend unit tests
uv run python -m pytest monocle/tests/ -x --tb=short -q

# Frontend unit tests
cd frontend && npm run test -- --run

# E2E tests (requires server running at http://localhost:8000)
uv run playwright test

# Type-check frontend
cd frontend && npx tsc --noEmit

# Full check before marking a milestone complete
uv run python -m pytest monocle/tests/ -x --tb=short -q && cd frontend && npm run test -- --run
```

---

## Quick Reference

| Item | Value |
|---|---|
| Python package dir | `monocle/` (import as `import monocle`) |
| CLI entry | `uv run python -m monocle <command>` |
| Backend port | `8000` (binds `127.0.0.1` by default) |
| Frontend dev | `http://localhost:5173` (Vite) |
| Config file | `config.yaml` (gitignored) / `config.yaml.example` (committed) |
| Secrets | `.env` (gitignored) / `.env.example` (committed) |
| Vault | path from `config.yaml` → `vault.path` |
| Vault inbox | path from `config.yaml` → `vault.inbox_path` (default `./vault/inbox`) |
| Prompts dir | `prompts/` (default prompts committed; `prompts/local/` gitignored for user overrides) |
| Dev start | `uv run python -m monocle dev` (starts unified API + services with prefixed logging) |
| Version shadows | `<vault>/.versions/<path>/<timestamp_ms>.md` (millisecond-precision ISO timestamp) |
| Soft-delete trash | `<vault>/.trash/<path>.md` |
| ChromaDB data | `config.yaml` → `index.chroma_persist_path` |
| Ingest session store | `data/ingest/sessions.db` (SQLite session + notification state) |
| Source archive | `data/sources/` (immutable raw captures; excluded from semantic index) |
| Failed-ingest registry | `data/failed_ingests.json` (JSON array; stdlib only; gitignored; auto-created on first failure) |
| OpenAPI spec | Auto-generated: `GET http://localhost:8000/openapi.json` |
| Frontend type gen | `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts` |
| Commit openapi.json | `uv run python scripts/export_openapi.py` |
| OTLP endpoint | `config.yaml` → `telemetry.otlp_endpoint` (default `http://localhost:4317`; AI Toolkit gRPC port) |
| Log level | `config.yaml` → `telemetry.log_level` (default `INFO`; `DEBUG` in dev mode) |
| Log format | `config.yaml` → `telemetry.log_format` (`text` in dev, `json` in prod) |

---

## Milestone Tracker

| ID  | Milestone                                                      | Status      |
|-----|----------------------------------------------------------------|-------------|
| M1  | Foundation & Project Skeleton                                  | COMPLETE    |
| M2  | API Skeleton — all route stubs + OpenAPI                       | COMPLETE    |
| M3  | Vault Layer                                                    | COMPLETE    |
| M4  | Index Layer (ChromaDB + MemoryIndex)                           | COMPLETE    |
| M5  | File Watcher & Re-index Queue                                  | COMPLETE    |
| M6  | AI Provider Abstraction                                        | COMPLETE    |
| M7  | Ingest Pipeline & Plugin Registry                              | COMPLETE    |
| M8  | REST API Wiring — Core                                         | COMPLETE    |
| M9  | Graph Layer                                                    | COMPLETE    |
| M10 | Agent Framework & Chat API                                     | COMPLETE    |
| M11 | Scheduled Agents                                               | COMPLETE    |
| M12 | MCP Server                                                     | COMPLETE    |
| M13 | Settings & Review API                                          | COMPLETE    |
| M14 | CLI Commands                                                   | COMPLETE    |
| M15 | Frontend Scaffold & Typed API Wrappers                         | COMPLETE    |
| M16 | Chat UI                                                        | COMPLETE    |
| M17 | Document Browser & Search UI                                   | COMPLETE    |
| M18 | Graph UI                                                       | COMPLETE    |
| M19 | Voice Capture & Review Queue UI                                | COMPLETE    |
| M20 | Stats, Keyboard Shortcuts & Command Palette                    | COMPLETE    |
| M21 | Integration Testing & Obsidian Compatibility                   | COMPLETE    |
| M22 | Process Manager & Dev Automation                               | COMPLETE    |
| M23 | Organization Note Type & Cross-Linked People Backreferences    | COMPLETE    |
| M24 | OneNote Import Plugin                                          | DEFERRED    |
| M25 | Voice Feature Hardening & Cross-Browser Compatibility          | COMPLETE    |
| M26 | Teams Integration                                              | DEFERRED    |
| M27 | Topbar Omnisearch                                              | COMPLETE    |
| M28 | Provider & Model Status Detection                              | COMPLETE    |
| M29 | MCP-First: Contract Freeze & Canonical Tool Schema             | COMPLETE    |
| M30 | MCP-First: Shared Service Layer Extraction                     | COMPLETE    |
| M31 | MCP-First: MCP Canonicalization                                | COMPLETE    |
| M32 | MCP-First: Chat Tool Adapter & Orchestration Cleanup           | COMPLETE    |
| M33 | MCP-First: Third-Party MCP Composition                         | DEFERRED    |
| M34 | Ingest Session Schema & Persistence                            | COMPLETE    |
| M35 | Background Session Preparation & Notifications                 | COMPLETE    |
| M36 | Ingest Review Workspace & Proposal Flow                        | COMPLETE    |
| M37 | Ingest Execution, Validation & Source UX                       | COMPLETE    |
| M38 | Fast-Capture Path                                              | COMPLETE    |
| M39 | File History, Revert & Diff Viewer                             | COMPLETE    |
| M40 | Add Documents & Snippets To Chat Context                       | COMPLETE    |
| M41 | MCP Session-Based Capture                                      | PAUSED      |
| D1  | Simplification Docs Alignment                                  | COMPLETE    |
| M42 | Remove Separate-Process Support                                | COMPLETE    |
| M43 | Consolidate Ingest Workflow Ownership                          | COMPLETE    |
| M44 | Unified Capture Workbench Backend Contract                     | COMPLETE    |
| M45 | Unified Capture Workbench Frontend                             | COMPLETE    |
| M46 | Lean Chat & Explicit URL Capture                               | COMPLETE    |
| M47 | Omnisearch Hardening                                           | COMPLETE    |
| M48 | Cleanup & Contract Hardening                                   | COMPLETE    |
| M49 | Persistent User Memory                                         | IN PROGRESS |

---

## M49: Persistent User Memory

**Goal:** Give the chat agent durable, vault-native knowledge of who the user is and what they are working on, without loading large documents into every conversation. Memory is stored as editable Obsidian-compatible notes, auto-updated weekly from vault activity summaries, seeded via a guided setup wizard, and patchable mid-conversation via an explicit `remember_this` tool.

### Design

**Two-tier structure**

- **Tier 1 — Index note** (`vault/memory/index.md`, type `memory`, memory_section `index`): always prepended to the chat system prompt. Stays under ~250 tokens. Contains single-line facet summaries with wikilinks to tier-2 notes.
- **Tier 2 — Facet notes** (on-demand, read by agent via `read_note` tool when depth is needed):
  - `vault/memory/profile/identity.md` — name, role, org, timezone, bio
  - `vault/memory/profile/expertise.md` — domains, tools, skill level
  - `vault/memory/profile/interests.md` — hobbies, recurring topics
  - `vault/memory/profile/preferences.md` — response style, UI preferences
  - `vault/memory/context/projects.md` — active projects with status + wikilinks
  - `vault/memory/context/threads.md` — open questions, decisions in flight

All memory notes use `type: memory` frontmatter. `normalise_frontmatter()` treats `memory` notes as `review_status: approved` by default.

**Chat context injection**

`MemoryService.get_context_block()` reads `vault/memory/index.md` at agent startup and prepends a formatted block to the system prompt (after `prompts/chat.md`). If the index note does not exist, the block is empty — injection is a no-op. No embedding/retrieval involved; always synchronous.

**`remember_this` tool**

New `@tool` in `monocle/agents/tools.py`: `remember_this(content: str, section: str)`. `section` is one of `identity`, `expertise`, `interests`, `preferences`, `projects`, `threads`. Appends/patches the relevant tier-2 facet note and regenerates the index. The agent calls this when the user says "remember that…" or equivalent.

**Setup wizard**

- `POST /api/memory/setup` → opens a streaming chat session backed by `prompts/memory_setup.md`
- The prompt guides the LLM through identity → expertise → interests → preferences → active projects as a friendly conversation
- At conversation end the agent calls `write_memory_notes(data: dict)` (internal tool, not user-facing) which writes all facet notes and generates the index
- Frontend: wizard is a modal (reuses the chat streaming pattern from `useChat`); launched from the Memory settings tab empty state

**Weekly extraction (`MemoryUpdateAgent`)**

- Piggybacks on `WeeklySummaryAgent` scheduler slot — runs *after* the weekly summary note is written
- Reads: latest `vault/summaries/YYYY-Www.md` (already-compressed) + current memory facet notes (~5 notes)
- Prompt (`prompts/memory_extract.md`): structured-output patch — which facets changed, what to add/remove/update
- Token guard: if summary body > 4,000 tokens, pass only YAML frontmatter fields, not the full body
- Applies patches directly via `VaultLayer.write_note`; regenerates the index if any facet changed
- Configurable model: `ai.memory_model` (defaults to chat model; users can set e.g. `gpt-4o-mini` for cheaper batch extraction)

**`GET /api/memory`**

Returns: `{ index_exists: bool, index_content: str | null, facets: {name: str, path: str, exists: bool}[], last_extraction: str | null }`

**Settings modal — Memory tab**

- Status badge: `Active` / `Not set up`
- Last extraction date + `Re-extract now` button (triggers `MemoryUpdateAgent` on demand)
- Context injection toggle (maps to `memory.inject_context` config key; default `true`)
- Read-only rendered index preview
- `Edit in vault` link per facet note (opens vault-relative path)
- `Run setup wizard` button (always available, not just empty state)
- Extraction model field (text input; placeholder = current chat model name)

### New files

| File | Purpose |
|---|---|
| `monocle/services/memory.py` | `MemoryService`: `get_context_block()`, `write_memory_notes()`, `remember_this()`, `regenerate_index()` |
| `monocle/agents/memory_update.py` | `MemoryUpdateAgent`: weekly extraction logic |
| `monocle/routers/memory.py` | `GET /api/memory`, `POST /api/memory/setup`, `POST /api/memory/extract` |
| `monocle/vault/templates/memory_index.yaml` | Machine-readable schema for index note |
| `monocle/vault/templates/memory_facet.yaml` | Machine-readable schema for facet notes |
| `prompts/memory_setup.md` | Setup wizard conversation guide |
| `prompts/memory_extract.md` | Weekly extraction structured-output prompt |
| `monocle/tests/test_memory.py` | Unit tests |
| `frontend/src/components/Memory/MemoryWizard.tsx` | Wizard modal |
| `frontend/src/MemorySettings.test.tsx` | Frontend tests |

### Changed files

| File | Change |
|---|---|
| `monocle/agents/tools.py` | Add `remember_this` tool |
| `monocle/agents/__init__.py` | Inject `MemoryService.get_context_block()` into system prompt; register `remember_this` |
| `monocle/agents/scheduler.py` | Schedule `MemoryUpdateAgent` after `WeeklySummaryAgent` |
| `monocle/agents/weekly_summary.py` | After writing summary note, notify scheduler slot for memory update |
| `monocle/main.py` | Init `MemoryService` in lifespan; mount memory router |
| `monocle/config.py` | Add `memory.inject_context: bool = True`, `ai.memory_model: str | None = None` |
| `monocle/models.py` | Add `MemoryStatusResponse` model; add `"memory"` to `NoteType` enum |
| `frontend/src/components/SettingsModal/` | Add Memory tab |
| `openapi.json` | Regenerate |

### Deliverables

- [ ] `monocle/services/memory.py` — `MemoryService` with `get_context_block()`, `write_memory_notes()`, `remember_this(content, section)`, `regenerate_index()`
- [ ] `monocle/vault/templates/memory_index.yaml` and `memory_facet.yaml`
- [ ] `prompts/memory_setup.md` — setup wizard conversation guide
- [ ] `prompts/memory_extract.md` — weekly extraction structured-output prompt
- [ ] `monocle/agents/memory_update.py` — `MemoryUpdateAgent` with token-guard logic
- [ ] `monocle/routers/memory.py` — `GET /api/memory`, `POST /api/memory/setup`, `POST /api/memory/extract`
- [ ] Wire `remember_this` tool into `monocle/agents/tools.py` and agent factory
- [ ] Wire context injection into `create_chat_agent()` system prompt
- [ ] Schedule `MemoryUpdateAgent` after `WeeklySummaryAgent` in `scheduler.py`
- [ ] `monocle/config.py` — `memory.inject_context` + `ai.memory_model` config keys
- [ ] `monocle/models.py` — `MemoryStatusResponse`, `"memory"` note type
- [ ] `monocle/tests/test_memory.py` — unit tests covering: `get_context_block` (no index → empty string; index exists → formatted block), `remember_this` (patches correct facet note, regenerates index), `MemoryUpdateAgent` (happy path, token guard path, no summary yet → no-op)
- [ ] `GET /api/memory` wired and tested in `test_api.py`
- [ ] Frontend Memory tab in SettingsModal (status, last extraction, injection toggle, index preview, edit links, wizard button)
- [ ] Frontend `MemoryWizard` modal (streaming wizard conversation, calls `POST /api/memory/setup`)
- [ ] `frontend/src/MemorySettings.test.tsx` passing
- [ ] Regenerate `openapi.json`

### Acceptance Criteria

- [ ] With an empty vault, `GET /api/memory` returns `{ index_exists: false, ... }` and chat works normally (no crash, no empty system-prompt block)
- [ ] After setup wizard completes, `vault/memory/index.md` exists with ≤250 token content; all referenced facet notes exist
- [ ] Chat system prompt contains the index block when `memory.inject_context: true`; omits it when `false`
- [ ] Saying "remember that I prefer bullet points over tables" causes the agent to call `remember_this` and the preferences facet note is updated
- [ ] `POST /api/memory/extract` (manual trigger) reads the most recent weekly summary note and updates at least one facet note when given meaningful summary content
- [ ] Token guard: a summary body > 4,000 tokens is truncated to frontmatter-only before being passed to the extraction prompt
- [ ] `uv run python -m pytest monocle/tests/test_memory.py -x --tb=short -q` passes
- [ ] `uv run python -m pytest monocle/tests/ -x --tb=short -q` passes (no regressions)
- [ ] `cd frontend && npm run test -- --run` passes
- [ ] `cd frontend && npx tsc --noEmit` exits 0

### Test commands

```bash
uv run python -m pytest monocle/tests/test_memory.py -x --tb=short -q
uv run python -m pytest monocle/tests/ -x --tb=short -q
cd frontend && npm run test -- --run
cd frontend && npx tsc --noEmit
```

---

## Technical Spikes

Assumptions requiring early validation. Each spike is linked to the milestone where it must be resolved — record the outcome before marking that milestone complete.

### SPIKE-1: Ollama Whisper audio transcription

**Resolve by:** M6 (AI Provider)
**Status:** RESOLVED — 2026-03-17 (updated 2026-03-18)
**Outcome:** FAILED — Ollama has no stable transcription API. **Solution:** `TranscriptionProvider` ABC fully decoupled from `AIProvider` with three implementations (WhisperCpp, Subprocess, NativeOpenAI). Config: `ai.transcribe_backend` and `ai.transcribe_url`. See [full details](milestones.md#spike-1-ollama-whisper-audio-transcription).

---

### SPIKE-2: FastMCP `stateless_http=True` client compatibility

**Resolve by:** M12 (MCP Server)
**Status:** PARTIAL RESOLUTION — 2026-03-18
**Implementation:** `FastMCP("monocle", stateless_http=True)` mounted at `/mcp` via `mcp.streamable_http_app()` (Starlette). Key-based auth enforced via `_MCPAuthMiddleware` ASGI wrapper. The MCP Python SDK (`mcp[cli]`) is used; `streamable_http_app()` returns the MCP 2025-03-26 streamable HTTP transport app.
**Outcome per client:** *(requires live client testing — complete after server deployment)*
  - Claude Desktop: *(not yet tested)*
  - VS Code Copilot (GitHub Copilot): *(not yet tested)*
  - Cursor: *(not yet tested)*
**Fallback:** Standard SSE transport available via `mcp.sse_app()` if stateless HTTP proves incompatible with specific clients.

---

### SPIKE-3: Microsoft Agent Framework SSE streaming through FastAPI

**Resolve by:** M10 (Agent Framework & Chat API)
**Status:** RESOLVED — 2026-03-18
**Outcome:** CONFIRMED — `ChatAgent.run_stream()` returns `AsyncIterable[AgentRunResponseUpdate]` that streams tokens incrementally via FastAPI `StreamingResponse`. First-token latency with local Ollama: sub-2s. `@use_function_invocation` decorator handles multi-turn tool loops automatically. See [full details](milestones.md#spike-3-microsoft-agent-framework-sse-streaming-through-fastapi).

---

### SPIKE-4: ChromaDB Rust backend crash on Python 3.14 (Windows)

**Status: RESOLVED — 2026-03-17**
**Resolution:** Observable crash on 2026-03-16 but re-test on 2026-03-17 passed all tests. Transient environment issue or silent wheel re-release. Rust backend now fully operational. If crash reappears, apply `SegmentAPI` fallback. See [full details](milestones.md#spike-4-chromedb-rust-backend-crash-on-python-314-windows).

---

### SPIKE-5: Web Speech API Cross-Browser Validation

**Resolve by:** M25 (Voice Feature Hardening & Cross-Browser Compatibility)
**Status:** RESOLVED — 2026-04-20
**Decision:** Web Speech API is supported as best-effort opt-in (`voiceBackend='web_speech'`, server-configured via `ui.voice_input_backend`). Default production path is MediaRecorder+Whisper (universal). When `web_speech` is requested but `SpeechRecognition` is unavailable (Firefox, older Safari, iOS WebView), a `fallback-hint` element is shown during recording so the user understands why there is no live transcript.
**Cross-browser matrix:**
  - Chrome/Edge: full support — continuous + interimResults both work
  - Safari 16.4+: SpeechRecognition available but auto-stops on silence; continuous mode unreliable
  - Safari < 16.4 / iOS: webkitSpeechRecognition only; falls back to MediaRecorder in practice
  - Firefox: no SpeechRecognition — always falls back to MediaRecorder
  - Android Chrome: full support (matches desktop Chrome)
**Test coverage added:** 14 new Web Speech API tests in `VoiceCapture.test.tsx` covering `onresult` (interim/final/accumulation), `onend`, `onerror` (all error codes), `errorHandled` double-dispatch guard, and browser-fallback path.

---

### Source-of-Truth Hierarchy
1. Vault `.md` files = canonical data. ChromaDB = derived index (always rebuildable from vault).
2. `config.yaml` = server configuration (gitignored; no secrets). `.env` = secrets (gitignored).
3. Settings runtime state: **server-authoritative** (persisted via `PATCH /api/settings`). `localStorage` = UI cache only — used for instant first render, not as the authoritative value.
4. Review queue threshold source of truth: server config `review.queue_threshold`. Overridable at runtime via `PATCH /api/settings`.
5. Auto-approval source of truth: server config `review.auto_approve_threshold_pct` (`0` disables auto-approval; `90` means auto-approve notes with confidence >= 0.90).

### Security Defaults (enforce these everywhere)
- Server binds `127.0.0.1`; `0.0.0.0` requires explicit opt-in in `config.yaml`.
- MCP auth: `x-monocle-key` header (preferred) or `?key=` query param (accepted; logged by servers, so discouraged).
- Vault path validation: resolve `file_path` to absolute path via `os.path.realpath`; reject any path that does not start with the configured vault root. Return `403`. Reject symlinks that escape the vault.
- Audio upload max: 25 MB. Content field max: 50,000 characters.
- `GET /api/settings` never returns the full MCP key — mask to last 4 characters only.
- CORS: allow `http://localhost:{server.port}`, `http://127.0.0.1:{server.port}`, and (in dev mode only) `http://localhost:5173`, `http://127.0.0.1:5173` (Vite dev server). No wildcard origins.
- Rate limits: 30 req/min on `/api/ingest` and `/api/transcribe`; 60 req/min on `/api/chat`.

### Observability Strategy

Monocle uses **OpenTelemetry (OTel)** as the single cross-cutting observability layer for tracing, metrics, and log correlation. All three signals are exported via OTLP. The VS Code AI Toolkit is the default local sink (gRPC port 4317); any OTLP-compatible backend (Jaeger, Grafana, Honeycomb, Azure Monitor) can replace it via `config.yaml`.

**Guiding principle:** observability code must add zero blocking work to hot paths. All spans are created async-safely; metrics use pre-allocated OTel instruments (histograms, counters). Sampling is `AlwaysOn` locally (no overhead from sampling decisions); production can swap in a `ParentBased(TraceIdRatioBased(...))` sampler.

#### Packages (all added in M1 `pyproject.toml`)

| Package | Purpose |
|---|---|
| `opentelemetry-sdk` | Core SDK — `TracerProvider`, `MeterProvider`, sampling |
| `opentelemetry-exporter-otlp-proto-grpc` | OTLP gRPC export (AI Toolkit, Jaeger, etc.) |
| `opentelemetry-exporter-otlp-proto-http` | OTLP HTTP fallback (port 4318) |
| `opentelemetry-instrumentation-fastapi` | Auto-instrument all FastAPI routes — HTTP span + status + duration |
| `opentelemetry-instrumentation-logging` | Inject `trace_id` + `span_id` into every Python log record |
| `opentelemetry-instrumentation-httpx` | Auto-instrument outbound httpx calls (Ollama, OpenAI) |

#### Module: `monocle/telemetry.py` (created M1)

- `configure_telemetry(settings)` — called once in app lifespan; wires up `TracerProvider`, `MeterProvider`, and root-logger handler. No-ops gracefully if `telemetry.enabled: false`.
- `get_tracer(name) -> Tracer` — thin wrapper; modules import this instead of OTel directly.
- `get_meter(name) -> Meter` — same pattern for metrics.
- `span(name, **attrs)` — async context manager: `async with span("ingest.step.route", template=t):` wraps any coroutine in a child span without boilerplate.
- `timed(histogram, **attrs)` — async context manager: records wall-clock duration into an OTel `Histogram` instrument on exit.

#### Metric Instruments (created per milestone)

| Instrument | Type | Unit | Milestone | Description |
|---|---|---|---|---|
| `http.server.request_duration` | Histogram | ms | M2 | User-facing route latency (auto from FastAPI instrumentation) |
| `ai.embed_duration` | Histogram | ms | M6 | Per-call embed latency |
| `ai.chat_duration` | Histogram | ms | M6 | Per-call chat/completion latency |
| `ai.transcribe_duration` | Histogram | ms | M6 | Per-call transcription latency |
| `ingest.pipeline_duration` | Histogram | ms | M7 | End-to-end ingest pipeline per note |
| `ingest.step_duration` | Histogram | ms | M7 | Per-step ingest latency (attribute: `step` = 1–8) |
| `ingest.notes_total` | Counter | notes | M7 | Notes ingested, by `source` and `template` |
| `ingest.failures_total` | Counter | errors | M7 | Failed ingests, by `step` |
| `chat.ttft` | Histogram | ms | M10 | Time from POST `/api/chat` to first `token` SSE event |
| `chat.total_duration` | Histogram | ms | M10 | Time from POST `/api/chat` to `done` SSE event |
| `index.search_duration` | Histogram | ms | M4 | Vector search latency per query |
| `index.upsert_duration` | Histogram | ms | M4 | Chunk upsert latency per file |

#### Logging Defaults

- **Dev mode** (`python -m monocle dev`): `text` format, `DEBUG` level, prefix-tagged lines (`[API]`, `[WATCHER]`, `[SCHEDULER]`, `[INGEST]`, `[AGENT]`), human-readable.
- **Prod / JSON mode**: `json` format, `INFO` level, structured fields: `timestamp`, `level`, `logger`, `message`, `trace_id`, `span_id`.
- Root logger configured once by `configure_telemetry()`; sub-loggers use `logging.getLogger(__name__)` throughout.
- `opentelemetry-instrumentation-logging` injects `otelTraceID` and `otelSpanID` into every log record so log lines correlate to traces in the AI Toolkit.
- No `print()` calls in application code — always use the module-level logger.

### Key Abstractions & Components

| Class | Location | Notes |
|---|---|---|
| `AIProvider` | `monocle/ai/base.py` | `OllamaProvider`, `FoundryLocalProvider`, `AzureOpenAIProvider`, `OpenAIProvider`, `CompositeAIProvider` |
| `IndexLayer` | `monocle/index/base.py` | `ChromaIndex` (prod), `MemoryIndex` (tests only — no embeddings) |
| `IngestPlugin` | `monocle/ingest/plugin.py` | `TextPlugin`, `AudioPlugin`; deferred sources stay behind plugin seams rather than the near-term mainline |
| `RoutingAgent` | `monocle/agents/routing.py` | concrete class; checks `sentence_starters` first, then LLM via `prompts/routing.md` |

Factories: `get_provider(settings) -> AIProvider`, `get_index(settings) -> IndexLayer`.
Plugin registry: `IngestPluginRegistry` singleton — `register(plugin)`, `resolve(request) -> IngestPlugin`.

### Note Frontmatter Schema

```yaml
# Required fields written by ingest pipeline
type: "person_note"         # see Note Types table below
domain: "work"
people: ["Sarah Chen"]
tags: ["consulting"]
source: "web"               # web | voice | mcp | import
action_items: []
created: "2026-03-11T09:00:00Z"
updated: "2026-03-11T09:00:00Z"
confidence: 0.85            # 0.0–1.0; 1.0 for user-created notes
review_status: "pending"    # pending | approved
approved_by: null           # "system:auto" or user identity when approved
approved_at: null           # ISO 8601 timestamp when approval occurred
approval_mode: null         # auto | manual

# Optional link metadata (OQ1 resolution)
links:
  - target: "Sarah Chen"      # required; resolved by resolve_wikilink()
    relation: "manages"        # optional free-text relation type
    since: "2024-01"           # optional arbitrary k/v metadata
  - target: "Q4 Project"      # minimal entry (target only)
```

**Schema normalisation defaults** (applied by `normalise_frontmatter()` during read and re-index):
- Missing `type` → `"other"`
- Missing `people`, `tags`, `action_items` → `[]`
- Missing `confidence` → `1.0`
- Missing `confidence_rationale` → `null`
- Missing `review_status` → `"approved"` (existing notes assumed trusted)
- Missing `approved_by`, `approved_at`, `approval_mode` → `null`
- `links: null` → `[]`

### Note Types

| `type` value | Template | Description |
|---|---|---|
| `person_note` | `person` | Observation about a specific person |
| `decision` | `decision` | A decision made, with context and rationale |
| `idea` | `idea` | Speculative or creative thought |
| `observation` | `observation` | Factual observation about a situation or project |
| `reference` | `reference` | Pointer to a URL, document, or external resource |
| `meeting_note` | `meeting` | Notes from a meeting |
| `project` | `project` | Project overview and status |
| `action_item` | `action_item` | A specific follow-up task |
| `weekly_summary` | `weekly_summary` | Auto-generated weekly summary |
| `organization` | `organization` | Organization, company, or institution profile |
| `other` | `blank` | Catch-all; used when classification confidence < threshold |

### Chunking Config
- Tokenizer: `tiktoken` with `cl100k_base` encoding
- Chunk size: 512 tokens, overlap: 64 tokens
- Chunk ID format: `"{file_path}::{chunk_index}"`

### Graph Data Model (`GET /api/graph` response)

```json
{
  "focus": "people/sarah-chen.md",
  "nodes": [
    { "id": "people/sarah-chen.md", "label": "Sarah Chen", "type": "person", "degree": 0, "weight": 5 }
  ],
  "edges": [
    { "source": "people/sarah-chen.md", "target": "work/decisions/migrate.md",
      "edge_type": "structured",
      "relation": "mentioned-in", "weight": 3, "metadata": {} }
  ]
}
```

- `degree`: BFS distance from focus node (0 = focus). `null` in full-vault mode (no focus).
- Edge `relation`: from structured `links` frontmatter if available; otherwise `"mentioned-in"` (co-mention) or `"links-to"` (plain wikilink).
- Edge sources (in priority order): structured `links` frontmatter → body `[[wikilinks]]` → `people` co-mentions → shared `tags`.
- Graph is cached in memory; cache is invalidated on any file watcher event.

### Chat SSE Event Types

```
event: token        data: {"delta": "..."}
event: tool_call    data: {"name": "search_vault", "result_count": 4}
event: tool_error   data: {"name": "search_vault", "error": "Index not ready"}
event: note_created data: {"file_path": "projects/new-idea.md", "type": "idea"}
event: done         data: {"total_tokens": 420}
event: error        data: {"message": "Provider unavailable"}
```

### Ingest Pipeline Steps (in order)

1. Plugin resolution — `IngestPluginRegistry.resolve(request)` → matching `IngestPlugin`
2. Content extraction — `plugin.extract(request)` → plain text (includes `AIProvider.transcribe` for audio)
3. Routing — `RoutingAgent.route(text, template_hint)` → `RoutingDecision`; checks each template’s `sentence_starters` list first (fast path, no LLM); falls back to LLM classification via `prompts/routing.md`
4. Metadata extraction — `AIProvider.extract_note_metadata(text, template)` using `prompts/extract.md`
   *(when LLM routing is required, steps 3 and 4 run concurrently via `asyncio.gather`)*
5. Note construction — `VaultLayer.create_from_template(template, content, metadata)`
6. File write + immediate re-index — API calls `IndexLayer.upsert_chunks` directly (does not rely on inbox watcher for API-originated ingests); the body embedding produced here is retained in memory and passed forward to step 7.
7. Confidence scoring — `IngestConfidence` model evaluates written note using the deterministic scoring formula. The `tag_plausibility` component reuses the **body embedding already computed in step 6** — no additional AI call. Weights come from `review.confidence_weights`.
8. Frontmatter patch — write `confidence`, `review_status`, and approval metadata back via `VaultLayer.patch_frontmatter()`

**On failure (steps 3–5):** write `.error.md` sidecar alongside the source file (inbox or capture dir).

If routing confidence < 0.6, use `blank` template; set `review_status: pending`.

### File Layout Quick Map

```
monocle/           Python package
  main.py             FastAPI app + router registration + lifespan context (includes integrated watchdog + APScheduler in Phase 1)
  config.py           Settings (Pydantic v2) — loads config.yaml + .env
  models.py           All shared Pydantic models
  watcher.py          InboxWatcher — integrated async task managed by the unified FastAPI process
  graph.py            GraphBuilder + in-memory cache
  mcp_server.py       FastMCP tools + auth middleware
  cli.py              Typer CLI (all commands incl. dev, reindex, pull-models, export, versions)
  ai/base.py          AIProvider ABC
  index/base.py       IndexLayer ABC
  index/memory.py     MemoryIndex — tests only, no embeddings
  vault/__init__.py   VaultLayer (all filesystem operations)
  vault/normalise.py  normalise_frontmatter()
  vault/wikilinks.py  parse_wikilinks(), parse_links_field(), resolve_wikilink()
  vault/templates/    11 YAML note template schemas (each includes sentence_starters list + field definitions for form editor)
                       NOTE: these are machine-readable YAML schemas in the *Python package* at monocle/vault/templates/ —
                       distinct from the user-facing Markdown templates in vault/.templates/ (inside the vault directory).
  ingest/__init__.py  IngestPipeline + IngestPluginRegistry
  ingest/plugin.py    IngestPlugin ABC
  ingest/plugins/     TextPlugin, AudioPlugin, plus any deferred future plugins kept behind the registry seam
  ingest/chunker.py   chunk_text() — tiktoken cl100k_base
  ingest/confidence.py  IngestConfidence scoring (deterministic formula; no LLM call)
  agents/tools.py     @tool decorated agent tool library
  agents/routing.py   RoutingAgent — sentence-starter + LLM template dispatch
  agents/reindex.py   ReindexAgent — scheduled + on-demand full-vault re-index
  agents/weekly_summary.py  WeeklySummaryAgent — clustering (default: scikit-learn KMeans/Agglomerative)
  agents/scheduler.py  APScheduler setup for weekly summary + re-index cron tasks
  routers/            One file per API subsystem; `ingest_failures.py` is a separate router file from `ingest.py`
  tests/conftest.py   tmp_vault + memory_index + live_server pytest fixtures
prompts/              Agent system prompt files (committed; loaded at runtime)
  routing.md          RoutingAgent classification prompt
  extract.md          Metadata extraction prompt
  weekly_review.md    Weekly review / clustering summary prompt
  local/              User-local prompt overrides (gitignored)
frontend/src/api/     Typed API wrappers (generated from OpenAPI spec)
tests/e2e/            Playwright tests (require running server)
```

---

## Milestone Details

---

### M1: Foundation & Project Skeleton

**Status:** COMPLETE (2026-03-11)

**Summary:** Project structure, tooling, Pydantic models, test infrastructure, and frontend scaffold. All core dependencies pinned; uv environment operational; telemetry foundation in place.

**Full details:** [docs/milestones.md#m1-foundation--project-skeleton](milestones.md#m1-foundation--project-skeleton)

---

### M2: API Skeleton — All Route Stubs + OpenAPI

**Status:** COMPLETE (2026-03-12)

**Summary:** All 13 API routers registered as 501 stubs; OpenAPI spec auto-generated and committed. CORS, rate limiting, and OTel instrumentation in place.

**Full details:** [docs/milestones.md#m2-api-skeleton--all-route-stubs--openapi](milestones.md#m2-api-skeleton--all-route-stubs--openapi)

---

### M3: Vault Layer

**Status:** COMPLETE (2026-03-13)

**Summary:** VaultLayer CRUD, atomic writes, versioning (`.versions/`), soft-delete (`.trash/`), path traversal guards, schema normalisation, and wikilink resolution.

**Full details:** [docs/milestones.md#m3-vault-layer](milestones.md#m3-vault-layer)

---

### M4: Index Layer — ChromaDB + MemoryIndex

**Status:** COMPLETE (2026-03-13)

**Summary:** IndexLayer abstraction with ChromaDB (production) and MemoryIndex (testing). Semantic search, metadata filtering, dimension validation.

**Full details:** [docs/milestones.md#m4-index-layer--chromedb--memoryindex](milestones.md#m4-index-layer--chromedb--memoryindex)

---

### M5: Inbox Watcher & Scheduled Re-Index

**Status:** COMPLETE (2026-03-14)

**Summary:** Inbox file watcher (watchdog.Observer), ReindexQueue coalescing (10-second idle window), ReindexAgent (stale detection + startup check), APScheduler setup, and chunking utility.

**Full details:** [docs/milestones.md#m5-inbox-watcher--scheduled-re-index](milestones.md#m5-inbox-watcher--scheduled-re-index)

---

### M6: AI Provider Abstraction

**Status:** COMPLETE (2026-03-17)

**Summary:** AIProvider ABC with four implementations (Ollama, FoundryLocal, AzureOpenAI, OpenAI) plus composite chat/embed routing. TranscriptionProvider abstraction handles decoupled transcription backends (WhisperCpp, Subprocess, NativeOpenAI). SPIKE-1 resolved.

**Full details:** [docs/milestones.md#m6-ai-provider-abstraction](milestones.md#m6-ai-provider-abstraction) | [SPIKE-1 resolution](milestones.md#spike-1-ollama-whisper-audio-transcription)

---

### M7: Ingest Pipeline & Plugin Registry

**Status:** COMPLETE (2026-03-17)

**Summary:** Full 8-step IngestPipeline with IngestPlugin registry, RoutingAgent (sentence-starter fast path + LLM fallback), deterministic confidence scoring (no LLM call), duplicate detection (>0.95 similarity), and failed-ingest registry persistence.

**Full details:** [docs/milestones.md#m7-ingest-pipeline--plugin-registry](milestones.md#m7-ingest-pipeline--plugin-registry)

---

### M8: REST API Wiring — Core

**Status:** COMPLETE (2026-03-17)

**Summary:** All core endpoints wired to real implementations: notes CRUD, semantic/keyword search, ingest streaming, transcribe, health, stats, backlinks. Path traversal guards, 409 conflict detection, file size limits, and CORS isolation enforced.

**Full details:** [docs/milestones.md#m8-rest-api-wiring--core](milestones.md#m8-rest-api-wiring--core)

---

### M9: Graph Layer

**Status:** COMPLETE (2026-03-18)

**Summary:** GraphBuilder with ego-graph extraction from structured links, wikilinks, people co-mentions, and shared tags. In-memory caching with watcher-based invalidation. Backlinks endpoint for all incoming edges.

**Full details:** [docs/milestones.md#m9-graph-layer](milestones.md#m9-graph-layer)

---

### M10: Agent Framework & Chat API

**Status:** COMPLETE (2026-03-18)

**Summary:** Microsoft Agent Framework integration with 7 agent tools (search, read, write, create notes, get stats, list notes, get graph). ChatAgent factory with OTel correlation. SSE streaming chat endpoint with token/tool/error/note_created events. SPIKE-3 resolved.

**Full details:** [docs/milestones.md#m10-agent-framework--chat-api](milestones.md#m10-agent-framework--chat-api) | [SPIKE-3 resolution](milestones.md#spike-3-microsoft-agent-framework-sse-streaming-through-fastapi)
---


---

### M11: Scheduled Agents

**Status:** COMPLETE (2026-03-18)

**Summary:** `WeeklySummaryAgent` with sklearn clustering on pre-computed ChromaDB embeddings, LLM-grouping fallback for small batches, SSE streaming trigger endpoint, and `POST /api/agents/reindex` (202). All APScheduler cron jobs wired in lifespan.

**Full details:** [docs/milestones.md#m11-scheduled-agents](milestones.md#m11-scheduled-agents)

---

### M12: MCP Server

**Status:** COMPLETE (2026-03-18)

**Summary:** `FastMCP("monocle", stateless_http=True)` with 8 tools mounted at `/mcp`. Key-based auth middleware (x-monocle-key header / ?key= param) with HTTP 401 rejection. SPIKE-2 implementation complete; live client testing deferred to post-deployment.

**Full details:** [docs/milestones.md#m12-mcp-server](milestones.md#m12-mcp-server)

---

### M13: Settings & Review API

**Status:** COMPLETE (2026-03-18)

**Summary:** Historical milestone: `GET/PATCH /api/settings` with masked MCP key and atomic config.yaml persistence; `POST /api/settings/rotate-mcp-key`; an early review-queue CRUD surface was added here and later superseded by the unified capture-workbench plus approve/reject-only review actions in M44-M48. `patch_file_metadata` was added to IndexLayer, ChromaIndex, and MemoryIndex.

**Full details:** [docs/milestones.md#m13-settings--review-api](milestones.md#m13-settings--review-api)

---

### M14: CLI Commands

**Status:** COMPLETE (2026-03-18)

**Summary:** Full Typer CLI with 9 commands (`serve`, `dev`, `reindex`, `pull-models`, `stats`, `search`, `export`, `versions list/restore`, plus `watch`/`capture` stubs). `dev` prints `[TELEMETRY]` block before uvicorn. `live_server` session fixture added to conftest.py. 21 new CLI tests + test_dev_mode.py. `.vscode/tasks.json` + `launch.json` extended.

**Full details:** [docs/milestones.md#m14-cli-commands](milestones.md#m14-cli-commands)

---

### M15: Frontend Scaffold & Typed API Wrappers

**Status:** COMPLETE (2026-03-19)

React app skeleton with typed API layer from OpenAPI spec, all routes, theme management, design tokens, and health polling. 224 frontend tests passing.

**Full details:** [docs/milestones.md#m15-frontend-scaffold--typed-api-wrappers](milestones.md#m15-frontend-scaffold--typed-api-wrappers)

---

### M16: Chat UI

**Status:** COMPLETE (2026-03-19)

Fully functional chat screen with streaming, 6 chat starters, session history, theme toggle, and settings integration. 313 frontend tests passing.

**Full details:** [docs/milestones.md#m16-chat-ui](milestones.md#m16-chat-ui)

---

### M17: Document Browser, Search & Template Editor UI

**Status:** COMPLETE (2026-03-20)  
Vault file tree, CodeMirror YAML+Markdown editor with auto-save and 3-mode editing (YAML/Preview/Form), template-driven FormEditor, semantic/keyword search screen, backlinks panel, and wikilink navigation. 51 new frontend tests.

**Full details:** [docs/milestones.md#m17-document-browser-search--template-editor-ui](milestones.md#m17-document-browser-search--template-editor-ui)

---

### M18: Graph UI

**Status:** COMPLETE (2026-03-19)  
Force-directed graph screen with focus input (autocomplete), depth [1][2][3] toggle, type filter chips (Person/Note/Tag), degree-based visual decay, side panel with top-5 related notes, localStorage position persistence, and `react-force-graph` ForceGraph2D rendering. 31 new tests; `ResizeObserver` stub added to test-setup.ts; `react-force-graph` mocked in App.test.tsx to suppress `aframe-extras` AFRAME global requirement.

**Full details:** [docs/milestones.md#m18-graph-ui](milestones.md#m18-graph-ui)

---

### M19: Voice Capture & Review Queue UI

**Status:** COMPLETE (2026-03-21)
Added voice capture modal (Web Speech API primary, MediaRecorder + Whisper fallback) plus the original review/failure drawers. That fragmented app-shell surface was later replaced by the unified capture workbench in M45 and fully removed in M48. 224 frontend tests passing.
**Full details:** [docs/milestones.md#m19-voice-capture--review-queue-ui](milestones.md#m19-voice-capture--review-queue-ui)

---

### M20: Stats, Keyboard Shortcuts & Command Palette

**Status:** COMPLETE (2026-03-21)
Implemented StatsScreen with live stat cards and Recharts charts, useHotkeys hook for all SRS FR-WEB-12 keyboard shortcuts (Ctrl+K, Ctrl+/, Shift+, etc.), and CommandPalette with fuzzy search and keyboard navigation. 295 frontend tests passing (+71 new); TypeScript clean.
**Full details:** [docs/milestones.md#m20-stats-keyboard-shortcuts--command-palette](milestones.md#m20-stats-keyboard-shortcuts--command-palette)

---

### M21: Integration Testing & Obsidian Compatibility

**Status:** COMPLETE (2026-03-20)

**Summary:** 25 Playwright E2E tests across 6 spec files (`smoke`, `ingest_review`, `chat`, `graph`, `voice_modal`, `settings`). `playwright.config.ts` at repo root; root `package.json` provides `@playwright/test`. `.github/workflows/ci.yml` runs backend → frontend → E2E (E2E gated on same-repo PRs pending self-hosted Ollama runner). README rewritten with prerequisites, venv setup, config, first-run, Ollama model pull, MCP client setup, keyboard shortcuts, CLI reference, and Obsidian compatibility notes. `.vscode/tasks.json`: `test: e2e` and `test: ci-full` added. `.vscode/launch.json`: `E2E Tests (Playwright debug)` added. `.gitignore` updated for `node_modules/`, `playwright-report/`, `test-results/`. `vault/.obsidianignore` already had `.versions/` and `.trash/` — verified complete. 693 backend + 313 frontend tests passing.

**Full details:** [docs/milestones.md#m21-integration-testing--obsidian-compatibility](milestones.md#m21-integration-testing--obsidian-compatibility)

---

### M22: Dev Automation & Optional Process Separation

**Status:** COMPLETE (2026-03-21)
Implemented optional process separation: `ProcessManager` + `SubprocessHandle` with exponential-backoff crash-restart; `watch`, `scheduler`, `capture` CLI commands as standalone process entry points; and `--separate-processes` support on `serve`/`dev`. This topology was later removed from the supported mainline in M42. 715 tests passing (22 new in `test_process_manager.py`).
**Full details:** [docs/milestones.md#m22--dev-automation--optional-process-separation](milestones.md#m22--dev-automation--optional-process-separation)

---

### M23: Organization Note Type & Cross-Linked People Backreferences

**Status:** COMPLETE (2026-03-25)

Organization note type with structured membership data, person↔org cross-linking, graph-based backreferences, and 5 new org-linking tests. 786 backend tests passing.

**Full details:** [docs/milestones.md#m23-organization-note-type--cross-linked-people-backreferences](milestones.md#m23-organization-note-type--cross-linked-people-backreferences)

---

### M24: OneNote Import Plugin

**Goal:** Implement an `OneNotePlugin` ingest plugin that accepts OneNote HTML exports and converts them to vault notes. Extends the Phase 1 plugin registry with no changes to the core ingest pipeline.

**Prerequisite:** M7 (Ingest Pipeline & Plugin Registry) complete.

**Deliverables:**
- [ ] `monocle/ingest/plugins/onenote_plugin.py` — `OneNotePlugin(IngestPlugin)`:
  - `source_id = "onenote"`, `source_label = "OneNote Export"`
  - `can_handle(request)` — returns `True` when `request.content_type` is `text/html` **or** the content string starts with `<!DOCTYPE html` / `<html`
  - `extract(request) -> str` — converts OneNote-style HTML to clean Markdown using `html2text` (new dependency); strips OneNote-specific metadata tags, inline styles, and navigation chrome; preserves headings, bullet lists, tables, and image alt-text
  - Preserves OneNote section/page title as the leading heading (used by routing + title extraction)
- [ ] `html2text` added as a dependency in `pyproject.toml`
- [ ] `POST /api/ingest` accepts `Content-Type: text/html` multipart field (`html_content`) in addition to the existing fields — plugin resolver picks `OneNotePlugin` automatically
- [ ] CLI convenience command: `python -m monocle import-onenote <file_or_dir>` — reads one `.htm`/`.html` file or all `.html` files in a directory and submits each to the ingest pipeline; prints a summary (imported N / failed M)
- [ ] Source badge renders as `import` in the UI (reuses existing `source: "import"` badge)
- [ ] `monocle/tests/plugins/test_onenote_plugin.py` — unit tests using a fixture HTML file; assert heading extraction, list preservation, and stripped inline styles; assert `can_handle` returns False for plain text
- [ ] Extend `.vscode/tasks.json`:
  - `test: onenote` — `python -m pytest monocle/tests/plugins/test_onenote_plugin.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] `OneNotePlugin` is registered in the plugin registry and `can_handle` correctly identifies HTML content
- [ ] An exported OneNote HTML page produces a valid vault note with extracted title, headings, and lists; no raw HTML tags in the note body
- [ ] `python -m monocle import-onenote ./exports/` imports all `.html` files in the directory and prints a success count
- [ ] Adding the plugin required zero changes to `IngestPipeline` or `IngestPluginRegistry` core code
- [ ] `uv run python -m pytest monocle/tests/plugins/test_onenote_plugin.py -x --tb=short -q` passes

---

### M25: Voice Feature Hardening & Cross-Browser Compatibility

**Status:** COMPLETE (2026-04-20)

**Summary:** SPIKE-5 resolved. Web Speech API path now has comprehensive test coverage (14 new tests) covering all `onresult`/`onerror`/`onend` scenarios, the `errorHandled` double-dispatch guard, and verified fallback to MediaRecorder. Cross-browser matrix documented in `VoiceModal.tsx` file-level comment. `usedFallback` state added to show a hint when `web_speech` is requested but `SpeechRecognition` is unavailable. Decision: Web Speech API is supported as best-effort opt-in via `voiceBackend='web_speech'`; the default production path remains MediaRecorder+Whisper (universal). 432 frontend tests passing (+18 VoiceCapture, 80 total in file), EXIT 0.

**Full details:** [docs/milestones.md#m25-voice-feature-hardening--cross-browser-compatibility](milestones.md#m25-voice-feature-hardening--cross-browser-compatibility)

---

### M26: Teams Integration

**Goal:** Bot Framework webhook with JWT validation and slash command support.

**Deliverables:**
- [ ] `routers/teams.py` — Bot Framework Activity handler; JWT validation via `botbuilder-core` `BotFrameworkAuthentication`
- [ ] Slash commands: `/search <query>`, `/notes [type]`, `/weekly`, `/stats`
- [ ] `monocle/tests/test_teams.py` — mock Activity objects; assert note created; assert 401 without JWT

**Acceptance Criteria:**
- [ ] `POST /api/teams/messages` without valid Bot Framework JWT → 401
- [ ] Teams message ingest creates a note with `source: "teams"`
- [ ] `/search query` replies with top 3 results
- [ ] `uv run python -m pytest monocle/tests/test_teams.py -x --tb=short -q` passes

---

### M27: Topbar Omnisearch

**Status:** COMPLETE (2026-04-02)

Fast omnisearch feature with always-accessible topbar search bar. Backend: pagination loop (scans full vault), optimized parsing (filename/frontmatter use NoteRef fields only; body search only reads needed notes), 60 req/min rate limit. Frontend: OmniSearch component (Ctrl+E, 300ms debounce, keyboard nav), integrated Topbar, SearchScreen URL params. April 2 hardening: keyboard nav bug fixed, rate limiting added, full vault scan enabled, parse I/O optimized (90%+ of queries avoid vault.read_note).

**Full details:** [docs/milestones.md#m27-topbar-omnisearch](milestones.md#m27-topbar-omnisearch)

---

### M29: MCP-First: Contract Freeze & Canonical Tool Schema

**Status:** COMPLETE (2026-04-08)

Established single source-of-truth contract for all 7 canonical Monocle data operations. Audited both `VaultTools` (6 agent tools) and `mcp_server.py` (7 MCP tools), documented all behavioral divergences, and recorded the `fetch_and_summarize_url` → `create_reference_from_url` disposition decision. No code changes.

**Full details:** [docs/tool-contracts.md](tool-contracts.md)

---

### M30: MCP-First: Shared Service Layer Extraction

**Status:** COMPLETE (2026-04-09)
Extracted all business logic into `monocle/services/` (search, notes, graph, references, ingest). MCP tools and agent tools refactored to thin wrappers. 24 service-level tests added. 852 tests passing.
**Full details:** [docs/milestones.md#m30-mcp-first-shared-service-layer-extraction](milestones.md#m30-mcp-first-shared-service-layer-extraction)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M31: MCP-First: MCP Canonicalization

**Status:** COMPLETE (2026-04-09)
MCP tool surface established as the authoritative schema definition for all 7 Monocle data operations. Return contracts frozen in `docs/tool-contracts.md`. 32 contract parity tests added. `_normalize_tags` consolidated into `monocle/services/tags.py`. 884 tests passing.
**Full details:** [docs/milestones.md#m31-mcp-first-mcp-canonicalization](milestones.md#m31-mcp-first-mcp-canonicalization)

---

### M32: MCP-First: Chat Tool Adapter & Orchestration Cleanup

**Status:** COMPLETE (2026-04-09)
Agent tool names aligned with canonical MCP names (`fetch_and_summarize_url` → `create_reference_from_url`, `get_person_graph` → `get_graph`). VaultTools verified as thin adapters. Chat-only orchestration confirmed in `routers/chat.py`. 6 adapter↔MCP parity tests added. 8 obsolete duplicate tests removed. 881 backend tests, 416 frontend tests passing.
**Full details:** [docs/milestones.md#m32-mcp-first-chat-tool-adapter--orchestration-cleanup](milestones.md#m32-mcp-first-chat-tool-adapter--orchestration-cleanup)

**Test commands:**
```
uv run python -m pytest monocle/tests/ -x --tb=short -q
cd frontend && npm run test -- --run
```

---

### M33: MCP-First: Third-Party MCP Composition

**Status:** DEFERRED — future phase only

Add explicit support for agent composition across internal Monocle and external third-party MCP servers.

**Deliverables:**

- [ ] Agent planner distinguishes Monocle-owned vs third-party tools
- [ ] External MCP server configuration in `config.yaml`
- [ ] At least one third-party MCP integration tested E2E
- [ ] Documentation: how to add external MCP servers

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M34: Ingest Session Schema & Persistence

**Status:** COMPLETE (2026-04-24)

SQLite-backed ingest sessions, immutable `data/sources/` archival, session/source/action schemas, and the initial list/detail APIs are now implemented. `/api/ingest`, `/api/ingest/stream`, and the inbox watcher all capture durable queued sessions instead of writing pending notes directly, while queued notification/job scaffolding preserves the M35 handoff.

**Full details:** [docs/milestones.md#m34-ingest-session-schema--persistence](milestones.md#m34-ingest-session-schema--persistence)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M35: Background Session Preparation & Notifications

**Status:** COMPLETE (2026-04-24)

Idle-gated background preparation now turns queued ingest sessions into dormant-ready review items with persisted digest, related-note candidates, contradiction warnings, draft proposed actions, and true-up requeue support.
Separate ingest-ready notifications now surface through the app-shell badge and drawer plus the supporting notification APIs consumed by the frontend.
**Full details:** [docs/milestones.md#m35-background-session-preparation--notifications](milestones.md#m35-background-session-preparation--notifications)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M36: Ingest Review Workspace & Proposal Flow

**Status:** COMPLETE (2026-04-24)

Dedicated route-based ingest review now lets users inspect prepared sessions, answer follow-up questions, review contradiction warnings with linked notes, edit draft proposal content, and approve or reject actions without using the general chat surface.
Backend review orchestration now hydrates contradiction metadata and diff previews against current vault notes while persisting question answers, review-state transitions, editable proposals, per-action approvals, and `approve all` handoff state for M37.
**Full details:** [docs/milestones.md#m36-ingest-review-workspace--proposal-flow](milestones.md#m36-ingest-review-workspace--proposal-flow)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M37: Ingest Execution, Validation & Source UX

**Status:** COMPLETE (2026-04-24)

Approved ingest proposals now execute through the canonical MCP tool plane with post-apply validation via deterministic readback checks, and archived sources are discoverable in the document browser under a collapsed `Sources` section.

**Full details:** [docs/milestones.md#m37-ingest-execution-validation--source-ux](milestones.md#m37-ingest-execution-validation--source-ux)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M38: Fast-Capture Path

**Status:** COMPLETE (2026-04-24)

Fast-capture now provides an explicit opt-in path that auto-executes clean ingest sessions through the existing prepare/approve/execute lifecycle while falling back to the ingest review workspace whenever preparation surfaces blockers.
The implementation stays on the persisted ingest-session/source architecture, preserving provenance, source archival, validation, and reindex behavior without introducing a second write path.
**Full details:** [docs/milestones.md#m38-fast-capture-path](milestones.md#m38-fast-capture-path)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M39: File History, Revert & Diff Viewer

**Status:** COMPLETE (2026-04-24)

Added first-class note history on top of the existing vault `.versions` store, with configurable retention, history inspection/diff APIs, and restore support that keeps ingest-driven and manual edits on the same rollback mechanism.
The Document Viewer now exposes retained versions, per-version diffs, and revert actions, and settings can update retention live.
**Full details:** [docs/milestones.md#m39-file-history-revert--diff-viewer](milestones.md#m39-file-history-revert--diff-viewer)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M40: Add Documents & Snippets To Chat Context

**Status:** COMPLETE (2026-04-25)

Added explicit add-to-chat grounding flows from the Docs explorer and Document Viewer, including right-click document/section/sentence/selection actions plus file-tree drag-and-drop onto the persistent Chat nav target.
Chat sessions now persist user-added grounding as first-class localStorage entries and resend them as explicit user context in `/api/chat`, so manual grounding is visibly distinct from agent retrieval.
**Full details:** [docs/milestones.md#m40-add-documents--snippets-to-chat-context](milestones.md#m40-add-documents--snippets-to-chat-context)

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M41: MCP Session-Based Capture

**Status:** PAUSED (2026-04-27)

Move MCP `capture_thought` off the direct `IngestPipeline.run()` fast path and onto the persisted ingest-session architecture used by `/api/ingest`, so MCP capture shares the same archival, preparation, approval/fallback, execution, validation, and source-provenance behavior as the rest of the application.

This work is paused while the simplification track resets the mainline around a unified capture workbench and lean chat. The implemented session-backed pieces will be reconciled during M43-M46 rather than continued as a standalone active milestone.

**Deliverables:**

- [x] Re-route MCP `capture_thought` through `IngestSessionStore.create_api_session(..., fast_capture=True)` and `execute_fast_capture_session(...)`
- [x] Extend MCP state/init wiring so session-backed capture does not depend on FastAPI router globals
- [x] Version the frozen `capture_thought` contract in `docs/tool-contracts.md` from note-write output to session-state output
- [ ] Add MCP follow-up session inspection affordances or an equivalent contract for reading the resulting session outcome
- [x] Align docs/tests around the dual-mode history: session-backed MCP capture, while M33 third-party composition remains deferred

**Acceptance criteria:**

- `capture_thought` always creates a persisted ingest session and archives its raw source before any preparation or execution work begins.
- Clean MCP captures can still complete synchronously via fast capture, but blocker cases return a persisted session state instead of silently diverging into a second ingest path.
- Session-backed MCP capture preserves source provenance on created notes and exposes enough response state for external clients to continue the workflow deterministically.
- Focused MCP and contract tests cover both the completed fast-capture path and the fallback-to-review path.

**Test command:** `uv run python -m pytest monocle/tests/test_mcp.py monocle/tests/test_contracts.py -x --tb=short -q`

---

### D1: Simplification Docs Alignment

**Status:** COMPLETE (2026-04-28)
Aligned the product and system docs around trust-first capture, one unified capture workbench, explicit URL capture handoff, lean chat, distinct omnisearch, and one supported runtime topology.
This milestone also reset the execution sequence so simplification work now proceeds through M42-M48 instead of the previously broader integration-heavy track.
**Full details:** [docs/milestones.md#d1-simplification-docs-alignment](milestones.md#d1-simplification-docs-alignment)

---

### M42: Remove Separate-Process Support

**Status:** COMPLETE (2026-04-28)
Removed split-runtime support from the near-term mainline by collapsing startup to the unified app, deleting `ProcessManager` and the standalone split CLI commands, and cleaning the related config/example/tasks/test surfaces.
Health and startup behavior now follow one path only, and `uv run python -m monocle serve` is the single supported runtime entrypoint.
**Full details:** [docs/milestones.md#m42-remove-separate-process-support](milestones.md#m42-remove-separate-process-support)

---

### M43: Consolidate Ingest Workflow Ownership

**Status:** COMPLETE (2026-04-29)
Centralized ingest workflow ownership behind `monocle/services/ingest_workflow.py`, moved routers and service callers onto that layer, and reduced `IngestSessionStore` review mutations to storage-only primitives.
**Full details:** [docs/milestones.md#m43-consolidate-ingest-workflow-ownership](milestones.md#m43-consolidate-ingest-workflow-ownership)
**Test command:** `uv run python -m pytest monocle/tests/test_ingest.py monocle/tests/test_ingest_prepare.py monocle/tests/test_api.py -x --tb=short -q`

---

### M44: Unified Capture Workbench Backend Contract

**Status:** COMPLETE (2026-04-29)
Added `/api/capture-workbench` plus shared aggregation helpers so prepared sessions, threshold-filtered pending review notes, and failure records now ship in one backend shape with one actionable count while legacy review and failure routes remain adapters.
**Full details:** [docs/milestones.md#m44-unified-capture-workbench-backend-contract](milestones.md#m44-unified-capture-workbench-backend-contract)
**Test command:** `uv run python -m pytest monocle/tests/test_api.py monocle/tests/test_review.py monocle/tests/test_ingest.py -x --tb=short -q`

---

### M45: Unified Capture Workbench Frontend

**Status:** COMPLETE (2026-04-29)
Replaced the separate prepared-session, review-queue, and failed-capture app-shell surfaces with one capture-workbench drawer, one topbar badge, and one polling contract while keeping `/ingest-review` and `/docs` as deep workflow handoff routes.
**Full details:** [docs/milestones.md#m45-unified-capture-workbench-frontend](milestones.md#m45-unified-capture-workbench-frontend)
**Test command:** `cd frontend && npm run test -- --run`

---

### M46: Lean Chat & Explicit URL Capture

**Status:** COMPLETE (2026-04-29)
Removed the hidden `/api/chat` URL-prefetch path, added an explicit chat-composer `Capture URLs` handoff into the ingest workflow, and kept `create_reference_from_url` available only through explicit tool use.
**Full details:** [docs/milestones.md#m46-lean-chat--explicit-url-capture](milestones.md#m46-lean-chat--explicit-url-capture)
**Test command:** `uv run python -m pytest monocle/tests/test_agents.py monocle/tests/test_mcp.py -x --tb=short -q`

---

### M47: Omnisearch Hardening

**Status:** COMPLETE (2026-04-29)
Hardened omnisearch with an AI-free cached catalog, trimmed-query 3-character gating, and topbar UI stale-result/keyboard fixes while preserving the separate semantic-search handoff.
**Full details:** [docs/milestones.md#m47-omnisearch-hardening](milestones.md#m47-omnisearch-hardening)
**Test command:** `uv run python -m pytest monocle/tests/test_api.py::TestOmniSearch -x --tb=short -q`

---

### M48: Cleanup & Contract Hardening

**Status:** COMPLETE (2026-04-29)
Removed the last fragmented capture compatibility drawers, obsolete review/failure/notification adapters, and stale contract docs after the unified workbench, lean chat, and omnisearch simplifications were validated.
**Full details:** [docs/milestones.md#m48-cleanup--contract-hardening](milestones.md#m48-cleanup--contract-hardening)
**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

The following are committed design directions deferred beyond Phase 2. Architectural decisions made in Phase 1 MUST NOT foreclose them.

### LTR-4: Server-Side Agent Memory (Chat Sessions)

- Phase 1 chat sessions are stored in browser `localStorage` only (last 10 sessions). The agent has no cross-session memory; it starts fresh after a page reload. This is a deliberate Phase 1 simplification.
- Phase 3+ adds: server-side session store (SQLite or vault-backed `chat_sessions/` directory), session continuity across devices and reloads, and an opt-in mode where the agent can retrieve past sessions via `read_note`.
- **Architectural constraint enforced in Phase 1:** the `POST /api/chat` endpoint accepts a `session_id` field (echoed back) so the server-side wiring point is already defined. No session data is persisted server-side until LTR-4 is implemented.

### LTR-0: Plugin Architecture Framework

- Formalize the plugin system introduced in M7 (`IngestPluginRegistry`, `IngestPlugin` ABC) as an extensible framework for external developers.
- Phase 3 adds: plugin discovery via `pkg_resources` entry points, plugin dependency resolution, plugin.yaml manifests with metadata/version/author, and a plugin developer guide.
- First concrete plugins may include optional alternative clustering plugins, Logseq import/export plugin (LTR-1), and custom field type plugins for template editor (LTR-3).
- **Architectural constraint enforced in Phase 1:** Registry-based plugin loading is already the only mechanism; new plugins in Phase 3 require zero changes to core code.

### LTR-1: Logseq Compatibility

- Support Logseq-format daily notes, journal pages, and `((block-ref))` block references as an alternative to Obsidian.
- Vault format (standard `.md`) is already partially compatible. Phase 3 adds: Logseq import/export plugin (`LogseqPlugin` in the ingest registry), block-reference resolution in `parse_wikilinks`, and `resolve_wikilink` extension for Logseq UIDs.
- **Architectural constraint enforced in Phase 1:** `parse_wikilinks` and `resolve_wikilink` must not hard-code Obsidian-only link syntax. Adding a Logseq parser variant must be purely additive.

### LTR-2: Explicit Migration Documentation

- Publish a step-by-step guide covering:
  - **ChromaDB → Azure AI Search:** collection export format, `AzureSearchIndex` implementation swap, validation
  - **Ollama → Azure AI Services:** `ai.provider` config change only; zero code change required
  - **Local vault → Azure Blob / SharePoint:** volume mount equivalence; sync strategy
- **Architectural constraints enforced in Phase 1 (do not violate):**
  - `get_index(settings)` is the single construction site for `IndexLayer` implementations
  - `get_provider(settings)` is the single construction site for `AIProvider` implementations
  - `embed_dimensions: 1536` in `config.yaml` must remain fixed and consistent; if ever changed, a full re-index is required and must be documented
  - Switching `ai.provider` or `index.backend` in `config.yaml` requires zero code changes (NFR-EXT-01, NFR-EXT-02)

### LTR-3: Optional Process Separation for High-Volume Vaults

- For vaults exceeding ~10,000 notes, optionally extract `InboxWatcher`, `APScheduler`, and capture server as independent OS processes.
- Future-phase work may reintroduce conditional process separation via dedicated orchestration and standalone entry points if high-volume local deployments justify the extra complexity.
- Phase 1 Phase 2 unified single-process mode remains the default and fully supported; no performance regression for <10k vaults.
- **Architectural constraint enforced in the near-term mainline:** the unified runtime remains the only supported topology until this future-phase work is deliberately resumed.
