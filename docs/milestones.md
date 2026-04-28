---
type: milestone-archive
project: monocle
maintained-by: github-copilot
last-updated: 2026-04-24
---

# Monocle – Completed Milestones & Technical Spike Resolutions

This document archives full details for completed milestones (M1–M11, M19–M20, M23, M25, M27–M32, M34) and resolved technical spikes. For active work, refer to `docs/build-plan.md`.

---

## Table of Contents

### Completed Milestones
- [Monocle – Completed Milestones \& Technical Spike Resolutions](#monocle–-completed-milestones--technical-spike-resolutions)
  - [Table of Contents](#table-of-contents)
    - [Completed Milestones](#completed-milestones)
    - [Resolved Technical Spikes](#resolved-technical-spikes)
  - [Completed Milestones](#completed-milestones-1)
    - [M1: Foundation \& Project Skeleton](#m1-foundation--project-skeleton)
    - [M2: API Skeleton – All Route Stubs + OpenAPI](#m2-api-skeleton–-all-route-stubs--openapi)
    - [M3: Vault Layer](#m3-vault-layer)
    - [M4: Index Layer – ChromaDB + MemoryIndex](#m4-index-layer–-chromadb--memoryindex)
    - [M5: Inbox Watcher \& Scheduled Re-Index](#m5-inbox-watcher--scheduled-re-index)
    - [M6: AI Provider Abstraction](#m6-ai-provider-abstraction)
    - [M7: Ingest Pipeline \& Plugin Registry](#m7-ingest-pipeline--plugin-registry)
    - [M8: REST API Wiring – Core](#m8-rest-api-wiring–-core)
    - [M9: Graph Layer](#m9-graph-layer)
    - [M10: Agent Framework \& Chat API](#m10-agent-framework--chat-api)
    - [M12: MCP Server](#m12-mcp-server)
    - [M13: Settings \& Review API](#m13-settings--review-api)
  - [Resolved Technical Spikes](#resolved-technical-spikes-1)
    - [SPIKE-1: Ollama Whisper audio transcription](#spike-1-ollama-whisper-audio-transcription)
    - [SPIKE-3: Microsoft Agent Framework SSE streaming through FastAPI](#spike-3-microsoft-agent-framework-sse-streaming-through-fastapi)
    - [SPIKE-4: ChromaDB Rust backend crash on Python 3.14 (Windows)](#spike-4-chromadb-rust-backend-crash-on-python-314-windows)
    - [M14: CLI Commands](#m14-cli-commands)
    - [M19: Voice Capture \& Review Queue UI](#m19-voice-capture--review-queue-ui)
  - [**Test Results:** 224 frontend tests passing (38 new), EXIT 0.](#test-results-224-frontend-tests-passing-38-new-exit-0)
    - [M20: Stats, Keyboard Shortcuts \& Command Palette](#m20-stats-keyboard-shortcuts--command-palette)
    - [M21: Integration Testing \& Obsidian Compatibility](#m21-integration-testing--obsidian-compatibility)
  - [**Test Results:** 693 backend tests + 313 frontend tests passing; 25 E2E tests discovered (require live server to run).](#test-results-693-backend-tests--313-frontend-tests-passing-25-e2e-tests-discovered-require-live-server-to-run)
    - [M27: Topbar Omnisearch](#m27-topbar-omnisearch)
    - [M30: MCP-First: Shared Service Layer Extraction](#m30-mcp-first-shared-service-layer-extraction)
    - [M31: MCP-First: MCP Canonicalization](#m31-mcp-first-mcp-canonicalization)
    - [M32: MCP-First: Chat Tool Adapter \& Orchestration Cleanup](#m32-mcp-first-chat-tool-adapter--orchestration-cleanup)
    - [M25: Voice Feature Hardening \& Cross-Browser Compatibility](#m25-voice-feature-hardening--cross-browser-compatibility)

### Resolved Technical Spikes
- [SPIKE-1: Ollama Whisper audio transcription](#spike-1-ollama-whisper-audio-transcription)
- [SPIKE-3: Microsoft Agent Framework SSE streaming through FastAPI](#spike-3-microsoft-agent-framework-sse-streaming-through-fastapi)
- [SPIKE-4: ChromaDB Rust backend crash on Python 3.14 (Windows)](#spike-4-chromedb-rust-backend-crash-on-python-314-windows)

---

## Completed Milestones

### M1: Foundation & Project Skeleton

**Goal:** Set up project structure, tooling, config models, and test infrastructure. No business logic yet.

**Deliverables (all completed):**
- `pyproject.toml` with all backend dependencies pinned
- `monocle/` package with all subdirectory `__init__.py` files
- `monocle/config.py` – `Settings` Pydantic v2 model
- `monocle/models.py` – all shared Pydantic models
- `config.yaml.example` and `.env.example` committed; auto-copy flow implemented
- `vault/` skeleton with domain-based folder structure and `.obsidianignore`
- `prompts/` directory with stub files
- Stub module files: `watcher.py`, `process_manager.py`, `agents/routing.py`, `agents/reindex.py`
- `monocle/telemetry.py` – `configure_telemetry()`, `get_tracer()`, `get_meter()`, `span()`, `timed()` async context managers
- `frontend/` scaffold: `package.json`, `vite.config.ts`, `tsconfig.json`, `src/` structure
- `pytest.ini` with correct settings
- `monocle/tests/conftest.py` with `tmp_vault` and `memory_index` fixtures
- `.vscode/tasks.json` and `.launch.json` foundational configurations

**Acceptance Criteria (all met):**
- Backend and frontend tests exit 0
- All imports succeed without errors
- F5 launches with debugger attached
- uv environment fully operational

---

### M2: API Skeleton – All Route Stubs + OpenAPI

**Goal:** Register every API endpoint as a stub. This is the scaffold all future milestones wire into.

**Deliverables (all completed):**
- `monocle/main.py` – FastAPI app with CORS middleware (production: `localhost` + `127.0.0.1` only; dev: +Vite)
- All 13 routers with 501 stubs:
  - health, notes, search, ingest, ingest_failures, transcribe, graph, stats, chat, agents, review, settings, teams
- Rate limiting via `slowapi`: 30 req/min on `/api/ingest` + `/api/transcribe`; 60 req/min on `/api/chat`
- `OpenTelemetryMiddleware` auto-instruments all requests
- `openapi.json` exported to repo root and committed
- `.vscode/tasks.json` extensions: `api: export openapi`, `api: start server`
- `.vscode/launch.json` extensions: `API Server (debug)` launch config

**Acceptance Criteria (all met):**
- GET `http://localhost:8000/api/health` returns 200 JSON
- GET `http://localhost:8000/openapi.json` returns valid OpenAPI 3.x document with all 30 endpoints
- Every non-health endpoint returns exactly 501
- Uvicorn starts cleanly
- test_api.py passes (31 tests)

---

### M3: Vault Layer

**Goal:** All filesystem operations for vault notes – CRUD, atomic writes, versioning, soft-delete, schema normalisation.

**Deliverables (all completed):**
- `monocle/vault/__init__.py` – `VaultLayer` with full CRUD, versioning, soft-delete, templating
- `monocle/vault/normalise.py` – `normalise_frontmatter()` with schema defaults
- `monocle/vault/wikilinks.py` – `parse_wikilinks()`, `parse_links_field()`, `resolve_wikilink()`
- `monocle/vault/templates/` – 10 YAML schemas (person, decision, project, meeting, idea, observation, reference, action_item, blank, weekly_summary)
- All path traversal guards in place (`os.path.realpath` validation)
- Atomic writes via `tempfile.mkstemp` + `os.replace`
- Versioning: `.versions/<path>/<timestamp>.md` shadow copies before write
- Soft-delete: `.trash/<path>.md` instead of filesystem deletion

**Acceptance Criteria (all met):**
- Atomic writes verified; temp files created in system tempdir
- Versioning creates `.versions/` entries on write
- Deleted notes appear in `.trash/`; original path absent
- Path traversal attempts blocked with 403
- Mtime conflicts return 409
- test_vault.py passes (88 tests)

---

### M4: Index Layer – ChromaDB + MemoryIndex

**Goal:** IndexLayer abstraction with ChromaDB production implementation and in-memory test fake.

**Deliverables (all completed):**
- `monocle/index/base.py` – `IndexLayer` ABC
- `monocle/index/memory.py` – `MemoryIndex` for testing (no embeddings)
- `monocle/index/chroma.py` – `ChromaIndex` wrapping ChromaDB PersistentClient
- `monocle/index/__init__.py` – `get_index(settings)` factory
- `DimensionMismatch` exception for embedding dimension validation

**Acceptance Criteria (all met):**
- Parametrized tests pass against both MemoryIndex and ChromaIndex
- `delete_file()` removes all chunks for a file path
- Search respects `type`, `domain`, `source` filters
- test_index.py passes

---

### M5: Inbox Watcher & Scheduled Re-Index

**Goal:** Inbox file watcher integration (Phase 1: async task), scheduled full-vault re-indexing, chunk utility.

**Deliverables (all completed):**
- `monocle/ingest/chunker.py` – `chunk_text()` with tiktoken cl100k_base (512 tokens, 64 overlap)
- `monocle/watcher.py`:
  - `InboxWatcher` – watchdog.Observer on `vault/inbox/`, 2-second debounce, direct pipeline call
  - `ReindexQueue` – asyncio coalescing queue, 10-second idle window per file
- `monocle/agents/reindex.py` – `ReindexAgent` with stale detection, `startup_check()`, `health_status`
- `monocle/agents/scheduler.py` – APScheduler setup for cron jobs
- Thread-safe implementations with proper shutdown/cleanup

**Acceptance Criteria (all met):**
- New file in inbox triggers exactly one ingest call (debounced)
- ReindexQueue coalesces multiple pushes for the same file
- Failed ingest writes `.error.md` sidecar
- Files outside inbox produce no watcher events
- Proper logging with `[WATCHER]` prefix
- test_watcher.py + test_reindex.py pass

---

### M6: AI Provider Abstraction

**Goal:** `AIProvider` ABC and provider implementations. SPIKE-1 resolved.

**Deliverables (all completed):**
- `monocle/ai/base.py` – `AIProvider` ABC with `embed()`, `embed_batch()`, `chat()`, `transcribe()`, `extract_note_metadata()`
- `monocle/ai/ollama_provider.py` – `OllamaProvider` with auto-pull
- `monocle/ai/foundry_local_provider.py` – `FoundryLocalProvider` for Foundry local models
- `monocle/ai/azure_provider.py` – `AzureOpenAIProvider` for Azure OpenAI
- `monocle/ai/transcription.py` – `TranscriptionProvider` ABC with three implementations (WhisperCpp, Subprocess, NativeOpenAI)
- `monocle/ai/__init__.py` – `get_provider()` factory
- OTel instrumentation on all methods: spans + metrics

**Acceptance Criteria (all met):**
- Factory selects correct provider based on `settings.ai.provider`
- All providers implement full ABC interface
- Mock-based unit tests pass; no live Ollama required
- SPIKE-1 resolved (see resolved spike details)
- test_ai.py passes (27 tests, integration tests behind `@pytest.mark.integration`)

---

### M7: Ingest Pipeline & Plugin Registry

**Goal:** Full 8-step ingest pipeline with plugin registry, routing agent, deterministic confidence scoring.

**Deliverables (all completed):**
- `monocle/ingest/plugin.py` – `IngestPlugin` ABC + `IngestPluginRegistry` singleton
- Three built-in plugins: `TextPlugin`, `AudioPlugin`, `TeamsPlugin` (in `plugins/` subdir)
- `monocle/agents/routing.py` – `RoutingAgent` with sentence-starter fast path and LLM fallback
- 10 template YAML schemas updated with `sentence_starters` list
- `monocle/ingest/__init__.py` – `IngestPipeline` with full 8-step implementation
- `monocle/ingest/confidence.py` – deterministic scoring (0.35×template + 0.30×coverage + 0.20×plausibility + 0.15×entity, no LLM call)
- `monocle/ingest/failed_registry.py` – JSON array persistence for `.error.md` failures
- `monocle/prompts.py` – `load_prompt()` with local override support
- Default prompts: `routing.md`, `extract.md` (working content); `confidence.md` no longer needed
- OTel instrumentation: per-step spans and metrics

**Acceptance Criteria (all met):**
- Text ingest produces valid `.md` with correct frontmatter, review metadata, auto-approval
- Audio ingest calls transcribe; note has `source: "voice"`
- Sentence-starter routing bypasses LLM call
- Falls back to `blank` template when routing confidence < 0.6
- New plugins register without touching core code
- Failed ingests write `.error.md` sidecars
- Deterministic confidence score computed (no LLM call)
- Auto-approved notes include `approval_mode: auto`, `approved_by: "system:auto"`, `approved_at`
- Duplicate detection with 409 response; override with `allow_duplicate=true`
- test_ingest.py passes (66 tests)

---

### M8: REST API Wiring – Core

**Goal:** Replace 501 stubs with real implementations for all core endpoints.

**Deliverables (all completed):**
- `monocle/main.py` lifespan: `configure_telemetry()` first; AIProvider + IndexLayer initialization; startup re-index trigger; integrated InboxWatcher, ReindexQueue
- `routers/health.py` – wired to watcher status, AI reachability, index stats
- `routers/notes.py` – full CRUD + backlinks + ReindexQueue enqueue on write
- `routers/search.py` – semantic (embed + index) and keyword (vault scan) search
- `routers/ingest.py` – POST with DuplicateSuspected→409; SSE streaming with step events
- `routers/ingest_failures.py` – GET/retry/DELETE fully wired
- `routers/transcribe.py` – multipart upload, 25 MB guard
- `routers/stats.py` – aggregated counts by type/domain/pending
- Integration tests via TestClient with MemoryIndex + mock AIProvider
- Security tests: path traversal, file size limits, 409 handling, CORS, rate limiting

**Acceptance Criteria (all met):**
- POST `/api/ingest` ingests and returns 201
- 409 Conflict on duplicate (>0.95 similarity, <7 days); override with `allow_duplicate=true`
- Pagination works on `/api/notes?sort=updated&limit=10&offset=0`
- `/api/ingest/failures` returns failures in newest-first order
- PUT with stale mtime returns 409
- Rapid PUTs coalesce to one background re-index (ReindexQueue)
- Path traversal blocked with 403
- 25 MB audio limit enforced
- Health endpoint includes telemetry_endpoint
- test_api.py + test_security.py pass

---

### M9: Graph Layer

**Goal:** Ego-graph builder with all edge sources, caching, and wired endpoint.

**Deliverables (all completed):**
- `monocle/graph.py` – `GraphBuilder` with full edge extraction:
  - Structured `links` frontmatter (edge_type="structured")
  - Body `[[wikilinks]]` (edge_type="wikilink")
  - `people` co-mentions (edge_type="co-mention")
  - Shared `tags` (edge_type="co-mention", capped at 20 notes/tag)
  - BFS degree computation from focus node
  - In-memory cache keyed on `(focus, max_degree, types, n)`
  - Invalidation on watcher events
- `routers/graph.py` – wired to GraphBuilder with query params
- `routers/notes.py` – `/api/notes/{path}/backlinks` fully wired: source, relation, context

**Acceptance Criteria (all met):**
- GET `/api/graph?focus=people/sarah.md&max_degree=2` returns correct ego-graph
- Structured links carry relation and metadata
- `types=person` filter works correctly
- Cache hit on second identical request; invalidated after file change
- Backlinks endpoint returns all incoming links via structured/wikilinks/co-mention
- test_graph.py passes (33 tests)

---

### M10: Agent Framework & Chat API

**Goal:** Microsoft Agent Framework integration with SSE streaming chat. SPIKE-3 resolved.

**Deliverables (all completed):**
- `monocle/agents/tools.py` – 7 `@tool` decorated functions:
  - `search_vault`, `read_note`, `update_note`, `create_note`, `get_stats`, `list_notes`, `get_person_graph`
  - Each wraps vault/index/AI operations with try/except
  - `_to_thread` helper for syncâ†’async conversion
  - `.tools` list exposed for ChatAgent
- `monocle/agents/__init__.py`:
  - `_AIProviderChatClient(BaseChatClient)` adapter with `@use_function_invocation`
  - `_to_dict_messages()` converts ChatMessage list to OpenAI-style dicts
  - `_build_openai_tools()` builds tool schemas
  - `_inner_get_response()` + `_inner_get_streaming_response()` bridge to AIProvider
  - `_try_parse_tool_calls()` detects inline JSON tool invocations
  - `_configure_agent_otel()` sets up OTel once
  - `create_chat_agent(ai, vault, index, settings, graph_builder)` factory
- `routers/chat.py` – POST `/api/chat` with full SSE streaming:
  - Emits: `token`, `tool_call`, `tool_error`, `note_created`, `done` events
  - Handles `session_id` (echo back only; client-side storage)
  - Records `chat.ttft` (first token latency) + `chat.total_duration` histograms
  - 60/minute rate limit
  - Exception handling with error events
- Tool error handling: each tool catches exceptions and emits `tool_error` event
- OTel integration: agent spans flow into the same trace as surrounding FastAPI request

**Acceptance Criteria (all met):**
- POST `/api/chat` with message returns `text/event-stream`
- Stream contains `token` events followed by `done`
- Tool failures emit `tool_error`; stream continues
- `note_created` events emitted when agent creates notes
- SPIKE-3 resolved (see resolved spike details)
- `chat.ttft` and `chat.total_duration` histograms recorded in OTel
- test_agents.py passes (14 tests for SSE, 3 for tools, 2 for factory)

---

### M12: MCP Server

**Goal:** FastMCP tools exposed at `/mcp` with key-based auth. Resolve SPIKE-2.

**Deliverables (all completed):**
- `monocle/mcp_server.py` – `FastMCP("monocle", stateless_http=True)` with 7 tools + auth middleware + factory:
  - `_MCPState` dataclass holds module-level references to vault/index/ai/pipeline/graph_builder
  - `init_mcp_state(vault, index, ai, ingest_pipeline, graph_builder)` – called from app lifespan
  - `_MCPAuthMiddleware(app, key)` – ASGI wrapper; validates `x-monocle-key` header then `?key=` query param; returns HTTP 401 JSON `{"detail":"Unauthorized"}` if missing or invalid; passes non-HTTP scope types (lifespan, websocket) through unchanged
  - `create_mcp_app(mcp_key) -> _MCPAuthMiddleware` – wraps `mcp.streamable_http_app()` with auth
  - 7 `@mcp.tool()` decorated async functions using `_state` singleton:
    1. `search_vault(query, n_results, note_type, domain)` – embeds query via AI, calls `index.search()`, returns JSON array with `file_path`, `similarity`, `chunk` (≤500 chars)
    2. `read_note(file_path)` – reads via `vault.read_note()`, returns JSON with title/type/domain/tags/people/body
    3. `capture_thought(content, source)` – runs full `IngestPipeline.run(IngestRequest)`, returns JSON with file_path/type/confidence/review_status
    4. `create_note(title, body, note_type, domain, tags)` – `create_from_template` + `write_note`; sets `review_status="pending"` (MCP-created notes go to review queue)
    5. `create_reference_from_url(url, extra_context)` – fetches web page, AI summarizes, creates reference note with review_status=pending
    6. `update_note(file_path, body)` – reads note, patches body, writes back; sets updated timestamp; `_MAX_BODY_LENGTH = 50_000`
    7. `get_graph(focus, max_degree)` – `graph_builder.build()` in thread, returns `GraphData.model_dump_json()`

- `monocle/main.py` – `init_mcp_state(...)` called in lifespan after IngestPipeline + GraphBuilder init; `create_mcp_app(mcp_key)` mounted at `/mcp` in `create_app()` using `os.environ.get(cfg.server.mcp_access_key_env, "")`

- `monocle/tests/test_mcp.py` – 40 tests across 4 classes:
  - `TestMCPAuth`: no key → 401; wrong key header → 401; wrong key query → 401; valid header passes; valid query param passes; no env key configured → all requests rejected
  - `TestMCPTools`: all 7 tools exercised via `mcp.call_tool()` with real VaultLayer + MemoryIndex; field presence assertions; `create_note` sets pending review status; `update_note` body-too-long raises; `capture_thought` returns file_path
  - `TestMCPServerConfig`: `init_mcp_state` sets all 5 fields; `create_mcp_app` returns `_MCPAuthMiddleware`; server has exactly 7 tools
  - `TestMCPSecurityBoundaries`: enforces MCP security boundaries (e.g. vault path restrictions, cross-tenant isolation, and HTTP surface hardening) around tools and routes

- `.vscode/tasks.json` – `test: mcp` task added

**Acceptance criteria met:**
- Request to `/mcp` without a key → 401 ✓
- `search_vault` returns list with `file_path`, `similarity`, `chunk` fields ✓
- `capture_thought` creates a vault note and returns its `file_path` ✓
- SPIKE-2 outcome recorded (implementation complete; live client testing deferred) ✓
- `uv run python -m pytest monocle/tests/test_mcp.py -x --tb=short -q` → **40 passed** ✓
- Full suite: **all tests passing (EXIT 0)** âœ“

---

### M13: Settings & Review API

**Goal:** Runtime settings management (with hot-reload and config.yaml persistence) and review queue CRUD.

**Deliverables (all completed):**
- `monocle/config.py` – `save_config_patch(patch: dict)` public function: deep-merges allowed section keys (`ai`, `vault`, `index`, `agents`, `review`, `server`, `telemetry`, `ui`) into `config.yaml` atomically via mkstemp + os.replace; respects `MONOCLE_CONFIG` env var; skips `None` values.
- `monocle/index/base.py` – `patch_file_metadata(file_path, updates)` abstract method added to `IndexLayer`.
- `monocle/index/chroma.py` – `patch_file_metadata` uses `collection.get(where=file_path_filter, include=["metadatas"])` + `collection.update()` with scalar-only metadata merge.
- `monocle/index/memory.py` – `patch_file_metadata` updates `chunk.metadata` dict in-place for all matching chunks.
- `monocle/routers/settings.py` – full implementation:
  - `GET /api/settings` – returns `settings.model_dump()` (secrets excluded by Pydantic `Field(exclude=True)`) + `mcp_key_last4` (masked via `"****" + key[-4:]`; `None` if key absent).
  - `PATCH /api/settings` – accepts `{review: {...}, ai: {...}}` partial patch; applies via `model_copy(update=...)` on sub-configs; writes to `config.yaml` via `save_config_patch`; hot-reloads `AIProvider` when `ai.provider` changes; updates `app.state.settings`.
  - `POST /api/settings/rotate-mcp-key` – generates `secrets.token_hex(32)`; writes to `.env` (path configurable via `MONOCLE_ENV_FILE` env var) atomically; updates `os.environ`; returns `{mcp_key_last4: "****xxxx"}`.
- `monocle/routers/review.py` – full implementation:
  - `GET /api/review` – scans vault via `vault.list_notes(limit=10000)`, filters `review_status=="pending"`, returns paginated list.
  - `GET /api/review/count` – same scan, returns `{"count": N}`.
  - `PATCH /api/review/{path}/approve` – calls `vault.patch_frontmatter(path, {review_status, approval_mode, approved_by, approved_at})` (auto-404 via `NoteNotFound` HTTPException); mirrors `review_status: approved` to ChromaDB via `index.patch_file_metadata`; returns `ApprovalResult`.
  - `POST /api/review/approve-all` – approves all pending notes in batch; returns `{"approved": N}`.
- `monocle/tests/test_settings.py` – 19 tests: `TestGetSettings` (6), `TestPatchSettings` (8), `TestRotateMcpKey` (5). `_temp_config` autouse fixture redirects config writes to a per-test temp file (via `MONOCLE_CONFIG` env var) so the real `config.yaml` is never mutated.
- `monocle/tests/test_review.py` – 25 tests: `TestListReview` (7), `TestReviewCount` (4), `TestApproveNote` (9), `TestApproveAll` (5).
- `monocle/tests/test_api.py` – `STILL_STUB_ROUTES` pruned to only `POST /api/teams/messages`.
- `.vscode/tasks.json` – `test: settings` task added.

**Acceptance criteria met:**
- `GET /api/settings` returns MCP key masked to last 4 characters only âœ“
- `PATCH /api/settings {"review": {"queue_threshold": 0.75, "auto_approve_threshold_pct": 90}}` takes effect immediately on `app.state.settings` and is persisted to `config.yaml` âœ“
- `PATCH /api/review/{path}/approve` sets `review_status: approved`, `approval_mode: manual`, `approved_by`, `approved_at` in frontmatter and mirrors `review_status` to ChromaDB metadata âœ“
- `uv run python -m pytest monocle/tests/test_settings.py monocle/tests/test_review.py -x --tb=short -q` â†’ **44 passed** âœ“
- Full suite: **626 passed, 6 deselected, EXIT 0** âœ“

---
### M15: Frontend Scaffold & Typed API Wrappers

**Goal:** React app skeleton with all routes and a typed API layer generated from the committed OpenAPI spec.

**Deliverables:**
- [x] `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts` (requires running M8 server)
- [x] `frontend/src/api/client.ts` — typed `fetch` wrapper: handles JSON, SSE streams, 4xx/5xx errors; uses `schema.d.ts` types
- [x] `frontend/src/api/` — individual typed functions for all documented frontend-consumed endpoints generated from the committed OpenAPI spec (no uncovered endpoint families)
- [x] `frontend/src/App.tsx` — React Router routes: `/` (Chat), `/docs` (Document Browser), `/search`, `/graph`, `/stats`
- [x] `frontend/src/components/layout/` — `AppShell`, `Topbar` (polls `GET /api/health` every 10s; shows green/amber/red indicator per status field), `LeftNav` (collapses at ≤1200px viewport)
- [x] `frontend/src/components/SettingsModal/` — wired to `GET/PATCH /api/settings`, key rotation — functional but minimal styling
- [x] `frontend/src/styles/tokens.css` — all CSS custom property tokens from UI Design doc §3 (colors, typography, spacing, border-radius, shadows)
- [x] `frontend/src/hooks/useTheme.ts` — theme state management: detect system preference via `prefers-color-scheme` media query; persist selection to `localStorage`; provide context hook for all components to subscribe to theme changes
- [x] `frontend/tests/api.test.ts` — mock fetch; assert type-safe API calls
- [x] `frontend/tests/App.test.tsx` — renders without crash, nav links present
- [x] Add `openapi-typescript` as a `devDependency` and as a `package.json` script: `"gen-api": "openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts"`
- [x] Extend `.vscode/tasks.json`:
  - `frontend: dev` — `npm run dev` (cwd: `frontend/`; runs Vite dev server)
  - `frontend: type-check` — `npx tsc --noEmit` (cwd: `frontend/`)
  - `frontend: gen-api` — `npm run gen-api` (cwd: `frontend/`; regenerates `schema.d.ts`; requires server running at `:8000`)
- [x] Extend `.vscode/launch.json`:
  - `Frontend Dev Server` — runs `frontend: dev` task and opens `http://localhost:5173` in the browser
  - `Full Stack (debug)` — compound configuration: `Dev Server (debug)` + `Frontend Dev Server`; the **default developer launch** once both tiers are functional

**Acceptance Criteria:**
- [x] `cd frontend && npm run dev` serves `http://localhost:5173` with no console errors
- [x] All CSS tokens defined and applied to at least the layout shell
- [x] Topbar health indicator reflects live `GET /api/health` response
- [x] `cd frontend && npx tsc --noEmit` exits 0 (no TypeScript errors)
- [x] `cd frontend && npm run test -- --run` passes
- [x] `Full Stack (debug)` compound launch config starts both backend (with debugger) and frontend dev server; `http://localhost:5173` loads in the browser

---

### M16: Chat UI

**Goal:** Fully functional chat screen — streaming, chat starters, session history, settings modal.

**Deliverables:**
- [x] `frontend/src/components/Chat/ChatScreen.tsx` — message thread, 6 chat starter tiles (2×3 grid), session picker dropdown (last 10 sessions from localStorage)
- [x] `frontend/src/components/Chat/ChatInput.tsx` — multiline textarea; `Enter` sends; `Shift+Enter` newlines; microphone button (opens VoiceModal); send button
- [x] `frontend/src/components/Chat/ChatMessage.tsx` — Markdown rendering; tool call disclosure (collapsible); inline note card for `note_created` events
- [x] `frontend/src/hooks/useChat.ts` — `EventSource`-based SSE streaming; session management (localStorage, last 10 sessions)
- [x] Settings modal: fully wired to API — backend selector, threshold slider, key rotation, and theme toggle (wired to `useTheme()` hook from M15)
- [x] Theme switching: Settings modal adds a **Theme** section with radio buttons [● Dark ○ Light ○ System]. Integrates with `useTheme()` hook created in M15. Selection persisted to localStorage. Changes take effect immediately across the app.
- [x] `frontend/tests/Chat.test.tsx`

**Acceptance Criteria:**
- [x] Clicking a chat starter sends a pre-filled message that streams a response
- [x] Tool call renders as collapsible: "Used `search_vault` — 4 results"
- [x] Session picker shows ≤10 sessions; switching sessions restores thread
- [x] Settings modal shows masked key; Rotate calls `POST /api/settings/rotate-mcp-key` and updates display
- [x] Theme toggle in Settings modal immediately applies dark or light mode; selection persists across page reloads
- [x] `cd frontend && npm run test -- --run` passes

---

### M23: Organization Note Type & Cross-Linked People Backreferences

**Goal:** Create an `organization` note type with structured membership data, enable cross-linking from person notes to organizations, and implement backreferences (graph-based inverse links showing all people associated with an organization).

**Prerequisite:** M9 (Graph Layer) complete; person template already created in M8 post-review sessions with support for `organizations` nested field.

**Design Rationale (Option 3 from Phase 9):**
- **Frontmatter:** Store stable high-level org metadata (name, founded_year, location, domain, type [company/nonprofit/govt/academic/other]).
- **Body:** Narrative details (mission, description, notable events).
- **Links field:** Structured relationships via person notes' `links` field pointing to org notes (relation: "works-at", "founded", "manages", carrying temporal metadata like `join_date`, `leave_date`, `current`).
- **Backreferences:** Graph layer computes inverse links — `GET /api/graph?focus=organizations/acme-corp.md` returns all people connected via any `works-at`/`founded`/`manages` relation.

**Deliverables:**
- [x] `monocle/vault/templates/organization.yaml` — 15-25 fields organized in sections:
  - Identity & Contact: `name`, `short_name`, `url`, `location`, `domain`
  - Structure: `org_type` (company|nonprofit|govt|academic|other), `parent_org` (wikilink to parent if applicable), `founded_year`, `industry` (enum or free text)
  - Size & Scope: `employee_count`, `description` (100–500 chars)
  - Status: `active` (boolean), `status_reason` (if inactive), lifecycle fields
  - Metadata: `tags`, `domain` (work|personal), `source`
- [x] `vault/.templates/organization.md` — User-facing markdown body template with sections:
  - Header (name, short_name, url, org_type as metadata)
  - About (mission/description, founded_year)
  - Contact (location, website, social handles)
  - Key Dates (founded, IPO/acquisition, milestones)
  - Leadership & Structure (table of notable leaders or teams, links to person notes)
  - Notable People / Alumni (table with name, role, tenure)
  - Notes (narrative details, history, partnerships)
- [x] Extend person template's `organizations` field example and prompt in `prompts/extract.md`:
  - Document format: `organizations: [{name: "...", role: "...", join_date: "YYYY-MM", leave_date: "YYYY-MM", current: boolean}]`
  - Include instruction: "If a person has worked at multiple organizations, extract each as a separate entry. Use YYYY-MM format for partial dates."
  - Wire extraction prompt to pull org names and dates during person note metadata extraction.
- [x] Wiring: when person note is created with `organizations` field, automatically generate/update `links` entries pointing to matching organization notes:
  - For each org in `organizations`, attempt `resolve_wikilink("organizations/" + slugify(org.name))`.
  - If org note exists, create a link: `{target: "organizations/...", relation: "works-at", join_date: org.join_date, leave_date: org.leave_date, current: org.current}`.
  - If org note does not exist, optionally auto-create a stub org note via `VaultLayer.create_from_template("organization", {name: org.name, domain: person.domain}, metadata)` — set `review_status: "pending"`.
  - Update person note's `links` field via `patch_frontmatter()`.
- [x] Graph layer backreferences:
  - `GET /api/graph?focus=organizations/acme-corp.md&types=person` returns all person notes with incoming `works-at` links.
  - Graph edge includes `relation: "works-at"`, `metadata: {join_date, leave_date, current}` — reused from person links field.
  - Backlinks panel on organization note shows all people (sorted by who worked there most recently).
- [x] Routing/sentence starters for organization notes:
  - Add to `organization.yaml`: `sentence_starters: ["This is a company", "This organization", "The company was founded", "We hired from", "Working at"]`
  - If routing confidence < 0.6 and routing suggests `person` but content mentions org names, consider routing to `organization` instead (optional heuristic).
- [x] Test coverage in `monocle/tests/`:
  - `test_vault.py`: add tests for `create_from_template("organization", ...)` and `patch_frontmatter` with linked person notes
  - `test_graph.py`: add tests for backreferences — `GET /api/graph?focus=org_note` returns only person nodes with `works-at` edges
  - `test_ingest.py`: add tests for multi-org extraction during person ingest; stub org creation scenario
  - New file `monocle/tests/test_org_linking.py` (3–5 tests):
    - `test_person_ingest_creates_org_stub_if_missing`
    - `test_person_ingest_links_to_existing_org`
    - `test_org_backlinks_people_with_works_at_relation`
    - `test_org_graph_filters_by_relation_type`
- [x] Frontend display (optional M23a follow-up):
  - Person notes show inline org badges (clickable → org note / graph view)
  - Organization notes show "People" panel listing all associated people (generated from backreferences)
  - Person's work history table in document viewer shows org name, role, dates (from `organizations` frontmatter + computed via `links`)
- [x] Extend `.vscode/tasks.json`:
  - `test: org-linking` — `python -m pytest monocle/tests/test_org_linking.py -x --tb=short -q`

**Acceptance Criteria:**
- [x] `monocle/vault/templates/organization.yaml` has 15+ fields; `sentence_starters` includes org-specific phrases
- [x] `vault/.templates/organization.md` has 5+ sections with guidance for user-facing template; table examples for leaders/alumni
- [x] `prompts/extract.md` documents multi-org extraction with example JSON format and partial date guidance
- [x] A new person note with `organizations: [{name: "Acme Corp", role: "VP", join_date: "2020-01", current: true}]` triggers creation of a stub `organizations/acme-corp.md` or links to existing org
- [x] Person note's `links` field includes a `{target: "organizations/acme-corp.md", relation: "works-at", join_date: "2020-01", current: true}` entry
- [x] `GET /api/graph?focus=organizations/acme-corp.md` returns only person nodes in the ego-graph
- [x] Backlinks panel on org note lists all associated people sorted by recency
- [x] `uv run python -m pytest monocle/tests/test_org_linking.py -x --tb=short -q` passes (3–5 green tests)
- [x] Full test suite: **786 backend tests passing, EXIT 0**

---
**Goal:** APScheduler weekly summary agent using lightweight built-in clustering on pre-computed embeddings. `ReindexAgent` wired into APScheduler for scheduled full-vault re-index.

**Deliverables (all completed):**
- `monocle/agents/weekly_summary.py` – `WeeklySummaryAgent` class with 8-step pipeline:
  1. Retrieve notes from vault modified in last 7 days (via `vault.list_notes`, filtering by `updated`)
  2. Optionally segment by `domain` (`agents.weekly_summary.domains` config list)
  3. Fetch pre-computed embeddings from ChromaDB via new `IndexLayer.get_embeddings_by_file()` method – no re-embedding
  4. Build numpy matrix; cluster with scikit-learn `AgglomerativeClustering` (cosine/average linkage); n_clusters = `min(max(2, n//3, 5), 8)` (floor 2, target 5, cap 8)
  5. Fallback to LLM JSON grouping when batch < `_MIN_NOTES_FOR_CLUSTERING` (4) or no embeddings available (MemoryIndex)
  6. For each cluster: `AIProvider.chat` with `prompts/weekly_review.md` generates a paragraph summary
  7. Write `summaries/YYYY-WW.md` (ISO week) with `confidence: 1.0`, `review_status: approved`, `approval_mode: auto`, `approved_by: "system:weekly-summary"`
- `IndexLayer.get_embeddings_by_file(file_paths) -> dict[str, list[float]]` added to base, ChromaIndex, MemoryIndex
  - ChromaIndex: pages through collection in batches of `_GET_PAGE_SIZE`, returns first-chunk (chunk_index=0) embedding per file
  - MemoryIndex: returns `{}` – triggers LLM fallback in weekly summary
- `monocle/main.py` – weekly summary cron job registered in lifespan from `agents.weekly_summary.cron` config (default `"0 17 * * 5"`); `WeeklySummaryAgent` instance stored in `app.state.weekly_summary_agent`
- `routers/agents.py` – `POST /api/agents/weekly-summary` (SSE streaming, emits `start`/`done`/`error`); `POST /api/agents/reindex` (202 + BackgroundTasks)
- `monocle/tests/test_scheduler.py` – 12 new tests (24 total): `TestWeeklySummaryAgent` (7 tests), `TestAgentAPIEndpoints` (5 tests)
- `.vscode/tasks.json` – `test: scheduler` task added

**Acceptance criteria met:**
- Manual trigger via `POST /api/agents/weekly-summary` creates `summaries/YYYY-WW.md` with `confidence: 1.0`, `review_status: approved`, `approved_by: "system:weekly-summary"`
- Summary note does NOT appear in review queue
- sklearn clustering used for â‰¥4 notes with embeddings; LLM grouping fallback for smaller batches or MemoryIndex
- `POST /api/agents/reindex` returns 202 and triggers `ReindexAgent.run()` in background
- `uv run python -m pytest monocle/tests/test_scheduler.py -x --tb=short -q` â†’ **24 passed**
- Full suite: **542 passed, 6 deselected, EXIT 0**

---

## Resolved Technical Spikes

### SPIKE-1: Ollama Whisper audio transcription

**Original Hypothesis (M6):** Ollama can transcribe audio by passing a `.webm`/`.mp4` blob as an attachment to a Whisper model via `ollama.chat()` with a multimodal request.

**Validation Attempt:** POST a real audio blob to a locally running Ollama instance with a Whisper model; confirm a text transcript is returned.

**Status:** RESOLVED – 2026-03-17 (updated 2026-03-18)

**Outcome:** FAILED – the `ollama` Python client has no dedicated transcription method and does not support passing audio blobs via its chat/generate API in a documented, stable way.

**Final Architecture Implemented:**

`TranscriptionProvider` ABC in `monocle/ai/transcription.py` – fully decoupled from `AIProvider`. Three implementations:
1. `WhisperCppTranscriptionProvider` – HTTP POST to a local whisper.cpp server, configurable via `ai.transcribe_url`
2. `SubprocessTranscriptionProvider` – `openai-whisper` CLI subprocess, dev fallback
3. `NativeOpenAITranscriptionProvider` – OpenAI client wrapper, used by Foundry/Azure

**Factory Pattern:** `get_transcription_provider(settings)` returns:
- `None` for `"native"` backend (Foundry/Azure set their own default)
- Configured provider for `whisper_cpp`/`subprocess` backends

**Config:**
```yaml
ai:
  transcribe_backend: "native" | "whisper_cpp" | "subprocess"  # default: native
  transcribe_url: "http://localhost:9000"                       # default for whisper_cpp
```

**AIProvider Implementation:** `AIProvider.transcribe()` is now concrete – delegates to `self._transcription_provider`; raises `RuntimeError` if unset. All three provider implementations (`OllamaProvider`, `FoundryLocalProvider`, `AzureOpenAIProvider`) accept optional `transcription_provider=` parameter in constructor.

**To Start whisper.cpp Server:**
```bash
./server --model ggml-base.en.bin --host 0.0.0.0 --port 9000
# Then set ai.transcribe_backend: whisper_cpp in config.yaml
```

**Tests:** 12 new tests in `test_ai.py` covering all three `TranscriptionProvider` implementations plus the three `AIProvider` delegations.

---

### SPIKE-3: Microsoft Agent Framework SSE streaming through FastAPI

**Original Hypothesis (M10):** Microsoft Agent Framework (Python) streams tokens incrementally through a FastAPI `StreamingResponse` with `text/event-stream` content-type, achieving sub-2-second first-token latency with a local Ollama model.

**Validation:** Create a minimal agent with one tool; wire it to a FastAPI endpoint; confirm token-by-token delivery via browser `EventSource`.

**Status:** RESOLVED – 2026-03-18

**Outcome:** CONFIRMED

**Key Findings:**
1. `ChatAgent.run_stream()` returns `AsyncIterable[AgentRunResponseUpdate]` that integrates cleanly with FastAPI `StreamingResponse`.
2. Each update carries a `.contents` list containing:
   - `TextContent` – token deltas
   - `FunctionCallContent` – tool invocations
   - `FunctionResultContent` – tool results
3. Tokens are yielded per-chunk as the underlying `AIProvider.chat(stream=True)` streams them.
4. `@use_function_invocation` decorator on `BaseChatClient` handles multi-turn tool-call loop automatically.
5. First-token latency is determined solely by upstream `AIProvider` (local Ollama: sub-2s as required).
6. **Note:** `agent_framework_azure_ai` package is broken (import error on `PromptAgentDefinitionText`) and not needed – the adapter is built directly on `BaseChatClient` from `agent_framework` core.

**Fallback Strategy (not needed):** Queue-based approach would queue tokens in `asyncio.Queue` if streaming proved problematic. Not implemented; streaming works directly without buffering.

**Implementation Details:**
- `monocle/agents/__init__.py` contains the `_AIProviderChatAdapter(BaseChatClient)` implementation
- `routers/chat.py` consumes `agent.run_stream()` in a FastAPI `StreamingResponse` with SSE formatting
- Server span from FastAPI `OpenTelemetryMiddleware` and agent spans from `configure_otel_providers()` correlate into one trace visible in AI Toolkit

---

### SPIKE-4: ChromaDB Rust backend crash on Python 3.14 (Windows)

**Original Status (M5):** Unresolved; observed crash

**Crash Details (2026-03-16):**
- Environment: `chromadb==1.5.5`, `cpython-3.14.3`, Windows
- Symptom: Access violation `0xC0000005` on any `upsert`/`add` call to ChromaDB's Rust extension
- Blockage: Unit tests could not run

**Status:** RESOLVED – 2026-03-17

**Resolution Outcome:**
Re-tested on same `chromadb==1.5.5`, `cpython-3.14.3`, Windows. Rust `PersistentClient` now passes full smoke test (upsert, count, query, delete). All tests pass. The crash appears to have been a transient environment issue or a silent re-release of the chromadb 1.5.5 wheel.

**Investigation:**
- Referenced issue [#5937](https://github.com/chroma-core/chroma/issues/5937) in `chroma-core/chroma`
- Identified `SegmentAPI` workaround in related issue, but Rust backend passes without it

**Configuration Update:**
- `.python-version` updated from `3.12` â†’ `3.14`
- `pyproject.toml` requires `chromadb>=1.5.5`

**If Crash Reappears:**
Use `SegmentAPI` fallback in `monocle/index/chroma.py`:
```python
from chromadb.config import Settings as ChromaSettings

client = chromadb.Client(ChromaSettings(
    chroma_api_impl="chromadb.api.segment.SegmentAPI",
    is_persistent=True,
    persist_directory=path
))
```

**Test Isolation:**
- `_FakeChromaClient` retained in `test_index.py` for unit test isolation (no real I/O in tests)
- Not a crash workaround; just good test hygiene

**Status Going Forward:**
- No blocker for M5 or beyond
- Monitor for regressions; apply SegmentAPI workaround only if crash returns

---

### M14: CLI Commands

**Goal:** Core CLI commands operational via `python -m monocle`, including the unified local dev runner and shared live-server test harness needed before M22.

**Deliverables (all completed):**
- `monocle/cli.py` – Full Typer app with all commands:
  - `serve` – uvicorn with host/port from config
  - `dev` – development mode; prints `[TELEMETRY] OTLP endpoint: ... | log_level: ... | format: ...` block before starting uvicorn; sets `MONOCLE_DEV=true`
  - `reindex [--force]` – `ReindexAgent.run(force=...)` via `asyncio.run()`; attempts real AI embed, falls back gracefully with warning
  - `pull-models` – Ollama model pull for `chat_model` + `embed_model`; no-ops for non-Ollama providers
  - `stats` – vault + index stats printed to stdout (notes total, chunks, pending review, by-type, by-domain)
  - `search <query> [--limit N]` – embed query via AIProvider, pretty-print top-N hits
  - `export [--output <path>]` – zip vault excluding `.versions/`, `.trash/`
  - `versions list <file_path>` – calls `vault.list_versions()`, prints timestamps oldest-first
  - `versions restore <file_path> <timestamp>` – calls `vault.restore_version()`
  - `watch` / `capture` – reserved stubs
- `monocle/__main__.py` – already implemented (M1); no changes needed
- `monocle/tests/conftest.py` – `live_server` session-scoped fixture: starts uvicorn subprocess on random port, polls `/api/health` (15s timeout), yields base URL, graceful SIGINT shutdown (5s, then kill)
- `monocle/tests/test_dev_mode.py` – 7 tests across 3 classes: `TestUnifiedDevStartup` (health endpoint, multiple endpoints reachable, clean shutdown), `TestWatcherAndSchedulerStartup` (watcher_running field, scheduler no crash), `TestDevTelemetryBlock` (`[TELEMETRY]` in dev output)
- `monocle/tests/test_cli.py` – 21 tests using `typer.testing.CliRunner` across 8 classes
- `.vscode/tasks.json` – 4 new tasks: `cli: reindex`, `cli: reindex --force`, `cli: stats`, `cli: export`
- `.vscode/launch.json` – `CLI: Reindex (debug)` launch config (order 4 in monocle group)

**Test Results:** 675 tests passing (21 new), 6 deselected, EXIT 0.

**Notes:**
- `os.environ["MONOCLE_DEV"] = "true"` set by `dev()` CLI command can leak into test process when using `CliRunner`. The `TestDevTelemetryBlock` test uses `patch.dict(os.environ)` + `monkeypatch.delenv` to prevent leakage into subsequent CORS tests.
- `test_dev_mode.py` tests that start real subprocesses are excluded from the standard `pytest monocle/tests/` run if they fail to start in CI (they `pytest.skip` rather than fail).
- `ReindexAgent` uses `embed_fn=None` when AI provider unavailable; safe with MemoryIndex which ignores embeddings.

---

### M19: Voice Capture & Review Queue UI

**Goal:** Add voice capture (Web Speech API + Whisper fallback), a review-queue slide-over, and a failed-captures panel to the frontend.

**Deliverables (all completed):**
- frontend/src/api/transcribe.ts — transcribeAudio(blob, mimeType) wrapper for POST /api/transcribe multipart upload
- frontend/src/components/VoiceModal/VoiceModal.tsx — full recording state machine (idle → recording → transcribing → review → saving); Web Speech API primary path (real-time interim transcript via recognition.onresult); accumulatedRef avoids stale-closure in onresult; MediaRecorder + Whisper fallback when SpeechRecognition is unavailable; 8-template type selector; textarea for editing transcript; Save/Discard actions
- frontend/src/components/VoiceModal/VoiceModal.css — pulse animation for recording indicator; spinner for transcribing; centered overlay at z-index: 200
- frontend/src/components/ReviewQueue/ReviewQueue.tsx — right-side slide-over; fetches GET /api/review on open; sorts items by confidence ascending (lowest first); per-item Approve/Fix actions; Approve All; empty state; useReducer pattern; useNavigate to /docs?path=… for Fix action
- frontend/src/components/ReviewQueue/ReviewQueue.css — position: fixed; right: 0; top: var(--topbar-height); semi-transparent backdrop; confidence color coding (green = 0.85, warning = 0.60, error < 0.60)
- frontend/src/components/FailedCaptures/FailedCaptures.tsx — warning slide-over; Retry calls POST /api/ingest/failures/retry; Dismiss calls DELETE /api/ingest/failures/{id}; both remove the card and call onUpdate?.()
- frontend/src/components/FailedCaptures/FailedCaptures.css — orange left border on failed cards; warning-themed header
- frontend/src/App.tsx — useState for voiceOpen, reviewOpen, failedOpen, reviewCount, failedCount; useEffect polling (30 s) for both counts; VoiceModal, ReviewQueue, FailedCaptures rendered at root level; ChatScreen route receives onVoiceOpen prop
- frontend/src/components/layout/AppShell.tsx — passes onVoiceOpen, onReviewOpen, onFailedOpen, reviewCount, failedCount props to Topbar
- frontend/src/components/layout/Topbar.tsx — voice button always visible; review badge button (only when reviewCount > 0); failed badge button (only when failedCount > 0)
- frontend/src/components/layout/Topbar.css — .topbar-badge-btn, .topbar-badge, .topbar-badge--warning styles
- frontend/src/components/Chat/ChatScreen.tsx — onVoiceOpen? prop; voice starter calls onVoiceOpen?.(); ChatInput receives onVoiceClick={onVoiceOpen}
- frontend/src/VoiceCapture.test.tsx — 38 tests covering VoiceModal (closed/idle/ESC/backdrop), ReviewQueue (loading/empty/sorted/approve/approve-all/ESC), FailedCaptures (loading/empty/retry/dismiss/ESC), and Topbar badge visibility
- rontend/src/components/layout/Topbar.tsx — voice ?? button always visible; review ?? badge button (only when 
eviewCount > 0); failed ? badge button (only when ailedCount > 0)
- rontend/src/components/layout/Topbar.css — .topbar-badge-btn, .topbar-badge, .topbar-badge--warning styles
- rontend/src/components/Chat/ChatScreen.tsx — onVoiceOpen? prop; voice starter calls onVoiceOpen?.(); ChatInput receives onVoiceClick={onVoiceOpen}
- rontend/src/VoiceCapture.test.tsx — 38 tests covering VoiceModal (closed/idle/ESC/backdrop), ReviewQueue (loading/empty/sorted/approve/approve-all/ESC), FailedCaptures (loading/empty/retry/dismiss/ESC), and Topbar badge visibility

**Test Results:** 224 frontend tests passing (38 new), EXIT 0.
---

### M20: Stats, Keyboard Shortcuts & Command Palette

**Goal:** Display live analytics dashboard, implement all keyboard shortcuts from SRS FR-WEB-12, and provide searchable command palette for quick navigation.

**Deliverables (all completed):**
- `frontend/src/components/Stats/StatsScreen.tsx` — Full analytics dashboard with:
  - 4 stat cards (total_notes, person_note count, pending_review, failed_ingests) using live data from `GET /api/stats`
  - Recharts `BarChart` for notes_by_type distribution (person_note, decision, idea, other)
  - Recharts `BarChart` for notes_by_domain distribution (work, personal)
  - Source Quality Index section with star ratings (0–5 stars) derived from type distribution
  - Latency table showing p50/p95 milliseconds for embed and chat operations
  - Loading/error states with fallback empty content guard
  - `StatCard`, `QualityRow`, `LatencyTable` subcomponents; `toChartData()` and `qualityStars()` helpers
  - Responsive `ResponsiveContainer` from Recharts for mobile compatibility
- `frontend/src/components/Stats/StatsScreen.css` — CSS Grid layout for 4-column stat cards, 2-column chart row, quality index grid, latency table styling
- `frontend/src/hooks/useHotkeys.ts` — Global keyboard shortcut registration (useEffect on window keydown) with:
  - Ctrl+/ → CommandPalette open
  - Ctrl+K → Search input focus (skipped in input elements)
  - Ctrl+Shift+K → Keyword search (skipped in input elements)
  - Ctrl+N → New note (skipped in input elements)
  - Ctrl+S → Save note (NOT skipped in inputs — allows native save in textarea)
  - Ctrl+\ → Toggle sidebar (skipped in input elements)
  - Escape → Close modal/palette
  - `HotkeyHandlers` interface for optional callback registration
  - `inEditableContext()` guard prevents shortcuts in `<input>`/`<textarea>` (except where noted)
  - macOS Cmd support via `e.metaKey` fallback for Ctrl
  - Cleanup via return unmount handler (removes listener)
- `frontend/src/components/CommandPalette/CommandPalette.tsx` — Searchable action palette with:
  - Triggered by Ctrl+/ (via useHotkeys integration)
  - Modal overlay with backdrop click and Escape to close
  - Fuzzy search scoring: prefix=3pts, substring=2pts, keyword=1pt, initials=0.5pts, no-match=0
  - `PaletteAction` interface `{id, label, keywords?, icon?, onExecute}`
  - Base navigation actions: Chat, Documents, Search, Graph, Stats
  - `extraActions` prop for runtime-injected custom actions (open-settings, open-voice, run-weekly-summary, trigger-reindex, etc.)
  - Keyboard navigation: ArrowUp/Down cycles selection, Enter executes, Escape closes
  - Click-to-execute on any action
  - ARIA compliant: `role="dialog"`, `role="listbox"`, `aria-selected`, `aria-autocomplete="list"`, `aria-activedescendant`
  - Active item auto-scrolls into view with `scrollIntoView({block:'nearest'})`
- `frontend/src/components/CommandPalette/CommandPalette.css` — Modal overlay styles, panel centering, input field, action list, active/hover states
- `frontend/src/api/agents.ts` — API wrappers for agent endpoints:
  - `triggerWeeklySummary()` — POST /api/agents/weekly-summary
  - `triggerWeeklySummaryUrl()` — returns URL for SSE streaming
  - `triggerReindex()` — POST /api/agents/reindex
- `frontend/src/App.tsx` — Complete rewrite with:
  - `AppContent` inner component (requires `<BrowserRouter>` context for `useNavigate`)
  - Outer `App` wraps `ThemeContext.Provider` + `BrowserRouter`
  - `commandPaletteOpen` state + `closeAllModals()` callback
  - `useHotkeys` registration with navigation callbacks and search focus
  - `extraActions` array for CommandPalette (open-settings, open-voice, open-review, run-weekly-summary, trigger-reindex)
  - `<CommandPalette>` rendered at app root level with state wired
  - StatsScreen import and route (not placeholder const)
- `frontend/src/speech.d.ts` — Type declarations for Web Speech API types not in TypeScript DOM lib:
  - `SpeechRecognitionEvent` extends Event with `readonly results: SpeechRecognitionResultList`
  - `SpeechRecognitionErrorEvent` extends Event with `readonly error: string`, `readonly message: string`
- `frontend/src/Stats.test.tsx` — 33 comprehensive tests across 3 suites:
  - `StatsScreen` (11 tests): loading state, stat cards with live data, notes-by-type chart, notes-by-domain chart, quality index, latency table, error state, no-data guard
  - `useHotkeys` (9 tests): Ctrl+K fires handler, Ctrl+/ fires handler, shortcuts skipped in inputs, Ctrl+S NOT skipped in inputs, unmount removes listener, macOS Cmd support
  - `CommandPalette` (13 tests): closed state, base nav actions, extra actions, filter by keyword, no-results message, Escape closes, backdrop click closes, arrow key navigation, Enter execute, click execute, role=dialog ARIA, aria-autocomplete, aria-activedescendant
- `frontend/src/test-setup.ts` — Added stub: `Element.prototype.scrollIntoView = function () {}` (jsdom compatibility)
- `frontend/src/App.test.tsx` — Added mocks: `./api/health`, `./api/settings`, `./api/stats`, `./api/agents` (prevent uncaught async calls)

**Bug Fixes (pre-existing):**
- `frontend/src/components/VoiceModal/VoiceModal.tsx` — Fixed missing `content_type: 'text/plain'` in ingest call; fixed SpeechRecognitionEvent / SpeechRecognitionErrorEvent type casting via new `speech.d.ts`
- `frontend/src/VoiceCapture.test.tsx` — Fixed: BrowserRouter unused import removed; `breakdown` field replaced with proper `IngestConfidence` fields (template_match, metadata_coverage, tag_plausibility, entity_match); missing `mime_type: 'audio/wav'` added to transcribeAudio mock

**Test Results:** 295 frontend tests passing (+71 new: 33 M20 tests + adjustments to App.test.tsx), EXIT 0; TypeScript clean (all M20 files error-free).

**Post-completion addition (2026-03-20):** Chat input history navigation

- `frontend/src/components/Chat/ChatInput.tsx` — Shell-like ArrowUp/Down history:
  - `historyRef` stores all sent messages (most-recent last); deduplicates consecutive identical entries
  - `historyIndexRef` cursor (-1 = not browsing); `draftRef` preserves unsent text before browsing starts
  - **ArrowUp** (when cursor is on first line): saves current draft, walks back through history
  - **ArrowDown** (when cursor is on last line): walks forward; once past newest restores the draft
  - Multi-line messages are supported — cursor arrow key moves within text on non-boundary lines
  - `_adjustHeight` helper resizes the textarea and moves cursor to end after each navigation step
- `frontend/src/Chat.test.tsx` — 7 new tests in `ChatInput history navigation` suite:
  - ArrowUp empty history no-op, ArrowUp shows last sent, ArrowUp twice shows older, clamp at oldest, ArrowDown restores draft, ArrowDown no-op when not browsing, consecutive-duplicate deduplication

**Revised test count:** 313 frontend tests passing.

---

### M21: Integration Testing & Obsidian Compatibility

**Goal:** Full Playwright E2E test suite, Obsidian compatibility verification, GitHub Actions CI pipeline, and comprehensive README.

**Deliverables (all completed):**

**E2E Test Suite (`tests/e2e/` — 25 Playwright tests in 6 spec files)**
- `playwright.config.ts` (repo root) — Chromium, 1 worker (serial), 60 s timeout, `baseURL: http://localhost:5173`, screenshots on failure, trace on retry; `testDir: ./tests/e2e`; CI mode: `github` reporter + 1 retry
- `package.json` (repo root) — minimal Node package with `@playwright/test ^1.46.1`; scripts `test:e2e` and `test:e2e:debug`
- `tests/e2e/smoke.spec.ts` — 8 tests: `GET /api/health` shape, frontend root loads without JS errors, `/docs` navigation, `/search` navigation (search input visible), `/graph` navigation, `/stats` navigation (stat card visible), `Ctrl+/` opens command palette, topbar health indicator visible
- `tests/e2e/ingest_review.spec.ts` — 2 tests: `POST /api/ingest` returns 200/409 and review count endpoint returns `count` field; review queue slide-over can be opened (shows Review heading) and closed via Escape
- `tests/e2e/chat.spec.ts` — 3 tests: chat starter tiles visible on home screen; typing + Enter shows message in thread; `Ctrl+/` opens command palette
- `tests/e2e/graph.spec.ts` — 3 tests: graph screen renders heading; focus input accepts text + Enter stays on `/graph`; depth toggle buttons visible
- `tests/e2e/voice_modal.spec.ts` — 3 tests: mic button opens voice modal; Cancel button closes it; Escape closes it (context grants microphone permission)
- `tests/e2e/settings.spec.ts` — 5 tests: `GET /api/settings` shape with masked MCP key; `Ctrl+,` opens settings modal; settings modal opens from topbar and shows AI provider section; Escape closes modal; `PATCH /api/settings` idempotent round-trip returns 200

**Obsidian Compatibility**
- `vault/.obsidianignore` was already present with `.versions/` and `.trash/` — verified complete
- `monocle/vault/templates/` is inside the Python package (not the vault dir) — not visible to Obsidian
- `vault/.templates/` contains user-facing Markdown templates — intentionally visible in Obsidian
- All frontmatter fields (`confidence`, `review_status`, `approval_mode`, etc.) are standard YAML scalars — Obsidian renders without errors
- `[[wikilinks]]` written by agents resolve correctly in Obsidian's link graph

**CI (`.github/workflows/ci.yml`)**
- Three jobs: `backend` (pytest), `frontend` (tsc + vitest), `e2e` (playwright; needs backend+frontend; gated on same-repo PRs until self-hosted Ollama runner configured)
- E2E job: installs Playwright browsers via `npx playwright install --with-deps chromium`, creates config.yaml with `watch: false` and stub vault, starts uvicorn background server (health-poll loop), builds frontend and serves via `npx serve`, runs `npx playwright test --reporter=github`, uploads artifact on failure

**README** — Complete rewrite with:
- Prerequisites table (Python, uv, Node.js, Ollama, Git)
- Quick Start (7-step: clone → uv sync → ollama pull → config files → npm install → serve → first-run checklist)
- MCP Client Setup (Claude Desktop JSON, VS Code MCP JSON)
- Keyboard shortcuts reference table
- CLI reference table (all 9 commands)
- Test commands block (backend, frontend, E2E, typecheck)
- Obsidian Compatibility section
- Architecture overview diagram
- Observability section (OTel OTLP endpoint config)

**VS Code integration**
- `.vscode/tasks.json`: added `test: e2e` (`npx playwright test` from root) and `test: ci-full` (sequential backend → frontend → E2E)
- `.vscode/launch.json`: added `E2E Tests (Playwright debug)` (`npx playwright test --headed --debug` from root)
- `.gitignore`: added `node_modules/`, `package-lock.json`, `playwright-report/`, `test-results/`

**Test Results:** 693 backend tests + 313 frontend tests passing; 25 E2E tests discovered (require live server to run).
---

### M27: Topbar Omnisearch

**Goal:** Replace the static health indicator in the topbar center with an always-accessible omnisearch bar. Default search is a fast, AI-free full-text scan of the vault (filename ? frontmatter ? body priority order); a semantic search escape hatch hands off to the existing Search screen.

**Status:** COMPLETE (2026-04-02)

**Backend Implementation:**
- monocle/routers/search.py: Added GET /api/search/omni endpoint with:
  - Query params: q (min 3 chars), limit (default 20, max 100)
  - Pure text scan � no AI, no embeddings
  - Result ordering: filename matches first, then frontmatter (title/tags/people/type/domain), then body; each note appears in only the highest-priority matching bucket
  - Returns OmniResult list with ile_path, 	itle, excerpt, match_location ("filename" | "frontmatter" | "body")
  - Rate limit: 60 req/min (via @limiter.limit("60/minute"))
  - **April 2 hardening:** Added pagination loop (offset/limit, page_size=1000) to scan complete vault regardless of size; optimized parsing strategy:
    - Filename match: extracts basename from NoteRef.file_path (zero I/O)
    - Frontmatter match: constructs searchable text from NoteRef fields (title, type, domain, tags) � zero I/O
    - Body match: only calls vault.read_note() when filename+frontmatter checks fail (~90% of queries avoid I/O)
- monocle/tests/test_api.py: TestOmniSearch class with 7 tests covering min_length validation, filename/frontmatter/body matches, priority order, and result field validation

**Frontend Implementation:**
- rontend/src/api/search.ts: Added omniSearch(params) function with inline OmniResult type
- rontend/src/components/layout/OmniSearch.tsx: New component with:
  - Ctrl+E global keydown listener focuses the input
  - 300ms debounce on query; fires omniSearch when query = 3 chars
  - Dropdown closes on Escape, click outside, or result selection
  - Keyboard navigation: ?/? move selected index; Enter navigates to selected (or first) result
  - "Search semantically" option always visible at dropdown bottom when query = 3 chars; navigates to /search?q=<query>&mode=semantic
  - Data testids: omni-search, omni-search-input, omni-search-dropdown, omni-result, omni-semantic-btn
  - **April 1 bug fix:** Fixed keyboard navigation index collision (semanticIdx was evaluating before JSX render, causing first result + semantic option to both be selected; changed to const semanticIdx = results.length for correct slot after grouped items)
- rontend/src/components/layout/OmniSearch.css: Styles per docs/ui-design.md �5.6
- rontend/src/components/layout/Topbar.tsx: Mounted OmniSearch in center; moved compact health dot to right side
- rontend/src/components/layout/Topbar.css: Updated .topbar-center to flex-grow; shrink health indicator to dot-only
- rontend/src/components/Search/SearchScreen.tsx: Reads ?q and ?mode URL params for initial state; auto-triggers search on mount if ?q is non-empty
- rontend/src/OmniSearch.test.tsx: 12 tests covering input render, Ctrl+E focus, debounce/dropdown open, result navigation, semantic option navigation, Escape close, and click-outside close
- .vscode/tasks.json: Added 	est: omnisearch task running omni-specific backend tests

**Acceptance Criteria (all met):**
- Ctrl+E from any screen focuses the topbar search input ?
- Typing = 3 chars triggers a search after 300 ms (no Enter required); results appear in a dropdown ?
- Results are ordered: filename matches ? frontmatter matches ? body matches (each note in one bucket only) ?
- Clicking a result navigates to /docs?path=<encoded_path> ?
- "Search semantically" option navigates to /search?q=<query>&mode=semantic and auto-runs the search ?
- Typing < 3 chars shows no dropdown ?
- Escape closes dropdown ?
- Backend tests pass (7 omni tests, 793 total) ?
- Frontend tests pass (12 omni tests, 408 total) ?
- Frontend type checks pass ?

**Test Results:** 793 backend tests passing (7 omnisearch-specific), 408 frontend tests passing (12 omnisearch-specific); all acceptance criteria validated.

---

### M30: MCP-First: Shared Service Layer Extraction

**Goal:** Move all Monocle business logic out of both tool layers into shared service functions under `monocle/services/`. Both MCP tools and agent tools become thin wrappers that delegate to canonical services.

**Completed:** 2026-04-09

**Deliverables:**

- [x] **D1:** `monocle/services/__init__.py` — package init with module docstrings
- [x] **D2:** `monocle/services/search.py` — `search_vault(index, ai, query, n_results, note_type, domain)` with n-clamping (1–10), embedding via `ai.embed()`, thread-delegated `index.search()`
- [x] **D3:** `monocle/services/notes.py` — `read_note(vault, file_path)`, `create_note(vault, rq, title, body, note_type, domain, tags)` with `review_status="pending"`, `update_note(vault, rq, file_path, body)` with `updated` timestamp; body length validation (50K chars)
- [x] **D4:** `monocle/services/graph.py` — `get_graph(graph_builder, focus, max_degree, types, n)` delegating to `GraphBuilder.build()`
- [x] **D5:** `monocle/services/references.py` — `create_reference_from_url(vault, ai, rq, url, extra_context)` consolidating fetch→strip→summarise→JSON-extract→create-note pipeline; `fetch_url_text(url)` with scheme validation; `_strip_html()` with boilerplate removal; `_normalize_tags()` for LLM output normalization
- [x] **D6:** `monocle/services/ingest.py` — `capture_thought(pipeline, content, source)` with content length validation, constructs `IngestRequest` and delegates to `pipeline.run()`
- [x] **D7:** MCP tools (7 functions in `mcp_server.py`) and agent tools (6 methods in `agents/tools.py`) refactored to thin wrappers. MCP wrappers: `_state.assert_ready()` + service call + JSON serialize. Agent wrappers: preserve chat-only adapter logic (query resolution, AI merge, MemoryIndex fallback, wikilink name resolution) while delegating data operations to services. Dead code removed from both files.
- [x] **D8:** 24 service-level tests in `monocle/tests/test_services.py` covering: search (happy, clamp low/high, filters, no-filters), read_note (happy, missing), create_note (happy, review_status, body limit, no-rq), update_note (happy, timestamp, body limit, missing), get_graph (happy, no-focus, custom params), references (happy, bad scheme, no-JSON fallback), ingest (happy, content limit, source passthrough)
- [x] **D9:** Wrapper-level test imports updated to reference new service locations (`_MAX_SEARCH_RESULTS` from `services.search`, `_fetch_url_text` patches from `services.references`)

**Implementation Notes:**

- Each service function is a standalone `async def` accepting explicit dependencies (vault, index, ai, etc.) — no global state or singletons.
- Services own: vault reads/writes, reindex queue pushes, timestamp updates, template creation, metadata handling, body validation.
- MCP wrappers own: auth/state assertion, MCP-specific input validation, JSON serialization.
- Agent wrappers own: chat-specific adapter logic (query resolution via wikilink→title→semantic chain, `_merge_body()` AI merge, MemoryIndex fallback for no-AI case, wikilink name resolution for graph).
- `_normalize_tags()` remains in both `mcp_server.py` (for `BeforeValidator` on `create_note`) and `services/references.py` (for LLM output normalization). Will be consolidated in M31/M32.

**Test Results:** 852 backend tests passing (24 service-level), 0 failures, all acceptance criteria validated.

### M31: MCP-First: MCP Canonicalization

**Goal:** Make the MCP tool layer the authoritative schema definition for all Monocle-owned data operations. Freeze return contracts. Verify external MCP client backward compatibility.

**Completed:** 2026-04-09

**Deliverables:**

- [x] **D1:** Each MCP tool maps 1:1 to a shared service function with no inline business logic (verified — all 7 tools delegate to `monocle.services.*` per M30, only wrapper-level code remaining: `_state.assert_ready()`, `ai is None` guards, `_normalize_tags` BeforeValidator, JSON serialization)
- [x] **D2:** MCP tool return contracts documented and frozen — `docs/tool-contracts.md` frontmatter updated to `status: frozen`, frozen contract banner added requiring versioned acceptance for breaking changes
- [x] **D3:** External MCP client backward compatibility verified — `TestBackwardCompatibility` (4 tests) asserts stable tool names, required parameters, and meaningful descriptions; `TestInputSchemas` (10 tests) validates all parameter names/types/defaults match canonical schemas
- [x] **D4:** Contract parity tests added — `monocle/tests/test_contracts.py` with 32 tests across 6 classes:
  - `TestToolRegistry` (2): exactly 7 canonical tools registered, no extras
  - `TestInputSchemas` (10): parameter names, types, required/optional, defaults for all 7 tools
  - `TestOutputSchemas` (7): JSON output keys match frozen contract for each tool
  - `TestServiceDelegation` (4): both MCP and agent tools import from `monocle.services.*`; all service functions are async
  - `TestBehavioralParity` (6): review_status=pending on both surfaces; reindex push from both; MCP hard overwrite; search output shape identical
  - `TestBackwardCompatibility` (4): stable tool names, required params, descriptions
- [x] **D5:** MCP tool docstrings updated — module docstring rewritten to state authoritative/canonical status with cross-references to `docs/tool-contracts.md` and `monocle/services/`; each tool docstring updated with canonical operation reference line

**Additional work:**

- **`_normalize_tags` consolidated:** Three duplicate definitions (in `mcp_server.py`, `agents/tools.py`, `services/references.py`) replaced with a single canonical `normalize_tags()` in `monocle/services/tags.py`. All three consumers import via `from monocle.services.tags import normalize_tags as _normalize_tags`. The canonical version adopts the most defensive behavior (str coercion on list elements, None filtering).
- Unused `Any` import cleaned up from `mcp_server.py` and `services/references.py`.

**Test Results:** 884 backend tests passing (32 contract parity), 0 failures, all acceptance criteria validated.

---

### M32: MCP-First: Chat Tool Adapter & Orchestration Cleanup

**Goal:** Align agent tool names with canonical MCP names, verify VaultTools are thin adapters to the service layer, confirm chat-only orchestration remains cleanly separated in `routers/chat.py`, and add adapter↔MCP output parity tests.

**Completed:** 2026-04-09

**Deliverables:**

- [x] **D1:** Agent tool names aligned with canonical MCP names:
  - `fetch_and_summarize_url` → `create_reference_from_url` (method, docstring, error message, self.tools list, system prompt, `_ALLOWED_TOOL_HINTS`, chat router prefetch call)
  - `get_person_graph` → `get_graph` (method, docstring, logger message, self.tools list, system prompt, `_ALLOWED_TOOL_HINTS`)
  - All test references updated in `test_agents.py` (16 occurrences)

- [x] **D2:** VaultTools verified as thin adapters — each tool delegates to `monocle.services.*`. Adapter-only responsibilities correctly retained per `docs/tool-contracts.md` §6:
  - Query-based note discovery (wikilink → title scan → semantic search) in `update_note`
  - AI content merge (LLM-assisted body merging) in `update_note`
  - Wikilink name resolution in `get_graph`
  - MemoryIndex substring fallback for no-AI search in `search_vault`
  - Tag normalization from LLM-produced formats in `create_note`

- [x] **D3:** `fetch_and_summarize_url` resolved per M29 D3 decision — renamed to `create_reference_from_url`, delegates to `monocle.services.references.create_reference_from_url`

- [x] **D4:** Chat-only orchestration verified in `routers/chat.py`:
  - URL detection and opt-in policy (ChatRequest.fetch_urls field)
  - Parallel prefetch batching (max 5, asyncio.gather)
  - Context injection into last user message
  - SSE event shaping (token, tool_call, tool_error, note_created, done, error)
  - Session and timeout policy (5-minute timeout, session_id tracking)
  - Tool-hint policy (_ALLOWED_TOOL_HINTS in agents/__init__.py, _is_first_tool_call_turn)
  - None of these concerns leaked into tools.py or services/

- [x] **D5:** 6 adapter↔MCP output parity tests added to `TestAdapterMCPOutputParity` in `test_contracts.py`:
  - `test_read_note_output_keys_match` — exact key set match
  - `test_create_note_output_keys_match` — exact key set match
  - `test_update_note_agent_superset_of_mcp_keys` — agent adds `title` for LLM context
  - `test_get_graph_agent_superset_of_mcp_keys` — agent adds `node_count`, `edge_count` for LLM context
  - `test_create_reference_from_url_output_keys_match` — exact key set match
  - `test_agent_tool_names_match_canonical_minus_capture_thought` — 6 agent tools == 7 MCP tools minus capture_thought

- [x] **D6:** 8 obsolete duplicate tests removed from `TestVaultToolsExecution`:
  - `test_search_vault_returns_json_list` — covered by contract output parity
  - `test_read_note_returns_json_with_body` — covered by `TestAdapterMCPOutputParity.test_read_note_output_keys_match`
  - `test_update_note_updates_body` — covered by `TestUpdateNote.test_happy_path` in test_services.py
  - `test_update_note_body_length_cap` — covered by `TestUpdateNote.test_body_too_long_raises`
  - `test_update_note_updates_timestamp` — covered by `TestUpdateNote.test_updated_timestamp_set`
  - `test_create_note_returns_file_path` — covered by `TestAdapterMCPOutputParity.test_create_note_output_keys_match`
  - `test_create_note_sets_review_status_pending` — covered by `TestBehavioralParity.test_create_note_sets_review_pending_via_agent`
  - `test_get_graph_with_builder` — covered by `TestAdapterMCPOutputParity.test_get_graph_agent_superset_of_mcp_keys`

**Files modified:**

- `monocle/agents/tools.py` — module docstring, tool method renames, self.tools list, logger messages
- `monocle/agents/__init__.py` — `_ALLOWED_TOOL_HINTS`, system prompt, factory docstring
- `monocle/routers/chat.py` — prefetch call: `create_reference_from_url`
- `monocle/tests/test_agents.py` — all old name references updated, 8 duplicate tests removed
- `monocle/tests/test_contracts.py` — 6 new tests in `TestAdapterMCPOutputParity`

**Test Results:** 881 backend tests passing (38 contract parity), 416 frontend tests passing, 0 failures.

---

### M25: Voice Feature Hardening & Cross-Browser Compatibility

**Goal:** Comprehensive testing and hardening of the voice capture feature across browsers and failure modes (SPIKE-5 validation tasks).

**Completed:** 2026-04-20

**Decision:** Web Speech API is supported as best-effort opt-in via `voiceBackend='web_speech'` (server-configurable via `ui.voice_input_backend`). The default production path remains `voiceBackend='whisper'` (MediaRecorder + server-side Whisper), which works universally. When `web_speech` is requested but `SpeechRecognition` is unavailable in the browser, a `fallback-hint` element is shown so the user understands why there is no live transcript.

**Cross-browser matrix:**
- **Chrome / Edge**: Full support — `continuous=true` + `interimResults=true` both work. All `onerror` codes observed in practice.
- **Safari 16.4+**: `SpeechRecognition` available but auto-stops on silence; continuous mode unreliable. Interim results work.
- **Safari < 16.4 / iOS**: `webkitSpeechRecognition` only; no reliable continuous mode on iOS. Falls back to MediaRecorder in practice.
- **Firefox**: No `SpeechRecognition` — always falls back to MediaRecorder.
- **Android Chrome**: Full support (matches desktop Chrome).

**Deliverables completed:**

- [x] **14 new Web Speech API tests** added to `frontend/src/VoiceCapture.test.tsx` in `describe('VoiceModal — Web Speech API path', ...)`:
  - `recognition.start()` called on recording start; `continuous=true`, `interimResults=true` configured
  - `onresult` with interim-only, final-only, and mixed transcripts — interim shown in `live-transcript`
  - `onresult` accumulating multiple final segments from a single event
  - `onend` — transitions to review state with accumulated final text; empty case tested
  - `stop-recording` button calls `recognition.stop()`
  - `onerror` for all error codes: `not-allowed`, `service-not-allowed`, `network`, `audio-capture`, `no-speech`, `aborted`
  - `errorHandled` flag: `onerror` followed by `onend` does NOT dispatch `TO_REVIEW` (double-dispatch guard verified)
  - Fallback hint shown when `SpeechRecognition` unavailable with `voiceBackend='web_speech'`

- [x] **`usedFallback` state** added to `VoiceModal` — `MARK_FALLBACK` action dispatched when `web_speech` is requested but `SpeechRecognition` is absent; `fallback-hint` element shown during recording.

- [x] **Cross-browser compatibility comments** added to `VoiceModal.tsx` file-level JSDoc block documenting browser support matrix and the two-path architecture.

- [x] **SPIKE-5 resolved** — recorded in `docs/build-plan.md` Technical Spikes section.

**Files modified:**
- `frontend/src/components/VoiceModal/VoiceModal.tsx` — `usedFallback` state, `MARK_FALLBACK` action, fallback hint UI, cross-browser JSDoc
- `frontend/src/VoiceCapture.test.tsx` — 14 new Web Speech API tests

**Test Results:** 432 frontend tests passing (80 in `VoiceCapture.test.tsx`, up from 62), EXIT 0.

---

### M34: Ingest Session Schema & Persistence

**Goal:** Replace direct ingest-note creation with a durable ingest-session capture model that archives raw sources outside the vault and survives app restarts.

**Completed:** 2026-04-24

**Deliverables completed:**

- [x] Added canonical session-side models in `monocle/models.py`: `IngestSession`, `SourceRecord`, `ProposedAction`, `DiffPreview`, `IngestNotification`, `IngestSessionDetailResponse`, plus lifecycle enums for session/source/action state.
- [x] Added `monocle/services/ingest_sessions.py` with a SQLite-backed `IngestSessionStore` and managed filesystem layout under `data/ingest/` and `data/sources/`.
- [x] Implemented immutable source archival for API and inbox captures, including `payload` binary/text storage, `metadata.json` provenance mirrors, SHA-256 checksums, and normalized voice MIME types.
- [x] Created persistent tables and indexes for `ingest_sessions`, `source_records`, `proposed_actions`, `ingest_notifications`, and `background_prepare_jobs` so later M35/M36 work can layer on preparation without schema churn.
- [x] Rewired `POST /api/ingest` to return `202 Accepted` with an ingest-session summary instead of a created note.
- [x] Rewired `POST /api/ingest/stream` to emit capture-progress SSE events for source archival and session persistence rather than note-pipeline steps.
- [x] Added `GET /api/ingest/sessions` and `GET /api/ingest/sessions/{session_id}` for review-workspace and notification consumers.
- [x] Switched the unified-process inbox watcher in `monocle/main.py` and the standalone `monocle watch` CLI entry to archive inbox items into persisted ingest sessions instead of running the note pipeline directly.
- [x] Updated the shared test app lifespan fixture in `monocle/tests/conftest.py` so API tests run against the new ingest-session store with isolated temporary persistence roots.

**Acceptance Criteria met:**

- Inbox items and API-originated ingest requests now produce persisted ingest sessions rather than directly creating pending notes.
- Raw sources are archived outside the vault under `data/sources/` and are not indexed into the semantic note corpus.
- Session and source lifecycle states are queryable through the canonical models and the new list/detail APIs.
- Persisted sessions survive restarts; verified by re-opening the same SQLite/db-backed store in tests and reloading the captured session.

**Implementation notes:**

- `IngestSessionStore` keeps small, queryable state in SQLite and stores the immutable payload + metadata mirror on disk. This keeps M34 low-memory while avoiding premature coupling to later digest/proposal artifacts.
- Session origin is currently captured as `api`, `chat`, or `inbox`, with `api` used as the default to avoid forcing an immediate client migration while keeping the explicit `chat` path available for future callers.
- Duplicate detection is intentionally deferred beyond M34. `/api/ingest` now captures sessions quickly and durably instead of running the full AI pipeline synchronously; later ingest-review milestones can surface duplicate/contradiction analysis against the persisted session.
- The store records queued notification and background-job rows now, but execution of those jobs is still deferred to M35.

**Files modified:**

- `monocle/models.py`
- `monocle/services/ingest_sessions.py`
- `monocle/routers/ingest.py`
- `monocle/main.py`
- `monocle/cli.py`
- `monocle/tests/conftest.py`
- `monocle/tests/test_api.py`
- `monocle/tests/test_security.py`
- `monocle/tests/test_rate_limit.py`
- `monocle/tests/test_ingest_sessions.py`

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 961 passed, 8 deselected, EXIT 0.

---

### D1: Simplification Docs Alignment

**Goal:** Rewrite the source-of-truth docs so the near-term product is explicitly a trust-first capture system with one unified workbench, lean chat, explicit URL capture handoff, distinct omnisearch, and one supported runtime topology.

**Completed:** 2026-04-28

**Deliverables completed:**

- [x] Updated `docs/prd.md` to remove near-term Teams/OneNote/channel-breadth positioning and replace it with trust-first capture, a unified capture workbench, and explicit URL capture handoff.
- [x] Updated `docs/srs.md` to describe one supported runtime topology, deferred channel integrations, explicit URL capture instead of automatic chat prefetch, and the unified capture workbench direction.
- [x] Updated `docs/architecture.md` to remove ProcessManager/separate-process mainline diagrams and reflect the workbench + lean chat target architecture.
- [x] Updated `docs/ui-design.md` so topbar, review, and failure surfaces converge on one capture workbench design.
- [x] Updated `docs/build-plan.md` milestone sequencing so D1 precedes M42-M48 and M24/M26/M33 become deferred future-phase work.

**Acceptance Criteria met:**

- The PRD, SRS, build plan, architecture doc, and UI design doc now describe the same near-term product shape.
- Separate-process runtime support is documented as deferred work rather than as a mainline deliverable.
- Teams, OneNote, and third-party MCP composition are clearly deferred out of the near-term track.
- Chat is documented as lean retrieval and authoring with explicit capture handoffs instead of hidden URL-prefetch automation.
- The unified capture workbench is the documented destination for prepared sessions, pending review work, and failures.

**Files modified:**

- `docs/prd.md`
- `docs/srs.md`
- `docs/architecture.md`
- `docs/ui-design.md`
- `docs/build-plan.md`
- `GHC-ACTION-LOG.md`

**Validation:** Reviewed the D1 docs diff for cross-document consistency before starting M42.

---

### M42: Remove Separate-Process Support

**Goal:** Remove separate-process runtime support from the near-term mainline backend and CLI so Monocle supports one runtime topology only.

**Completed:** 2026-04-28

**Deliverables completed:**

- [x] Removed `ProcessManager` and capture-only runtime branches from `monocle/main.py` and CLI entrypoints.
- [x] Removed `server.separate_processes` and `MONOCLE_SEPARATE_PROCESSES` from supported mainline config/runtime paths.
- [x] Deleted process-manager-specific code/tests and replaced them with unified-runtime CLI/import coverage.

**Acceptance Criteria met:**

- `uv run python -m monocle serve` now starts the only supported runtime topology.
- No documented or supported `--separate-processes`, `capture`, `watch`, or `scheduler` mainline runtime path remains in the live code/config surface.
- Health and startup behavior no longer branch on capture-only or separate-process mode.

**Files modified:**

- `monocle/main.py`
- `monocle/cli.py`
- `monocle/config.py`
- `monocle/watcher.py`
- `monocle/tests/test_cli.py`
- `monocle/tests/test_imports.py`
- `.vscode/tasks.json`
- `config.yaml`
- `config.yaml.example`

**Files removed:**

- `monocle/process_manager.py`
- `monocle/tests/test_process_manager.py`

**Test Results:** `uv run python -m pytest monocle/tests/test_cli.py monocle/tests/test_imports.py -x --tb=short -q` → 39 passed, EXIT 0; `uv run python -m pytest monocle/tests/test_api.py monocle/tests/test_mcp.py -x --tb=short -q` → 133 passed, EXIT 0.

---

### M35: Background Session Preparation & Notifications

**Goal:** Turn persisted ingest sessions into dormant, review-ready work items by preparing them during idle time and surfacing ready notifications through a dedicated app-shell entry point.

**Completed:** 2026-04-24

**Deliverables completed:**

- [x] Added `IngestConfig` to `monocle/config.py` and `config.yaml.example` so background preparation cadence, concurrency, related-note breadth, and source excerpt size are server-configurable.
- [x] Added `monocle/services/activity.py` with `ActivityMonitor`, then wired it through `monocle/main.py`, `monocle/routers/chat.py`, and `monocle/routers/notes.py` so background prep only runs when chat streams and foreground note writes are idle.
- [x] Added `monocle/services/ingest_prepare.py` with `IngestPreparationWorker`, persisted-job claiming, idle-gated loop execution, deterministic fallback behavior, and artifact output under `data/ingest/artifacts/<session>/prepare_result.json`.
- [x] Extended `IngestSessionStore` in `monocle/services/ingest_sessions.py` with job-claiming, prepare completion/failure handling, ready-notification persistence, notification list/count/status helpers, and `enqueue_true_up()` for refreshable dormant sessions.
- [x] Exposed new ingest APIs in `monocle/routers/ingest.py`: `GET /api/ingest/notifications`, `GET /api/ingest/notifications/count`, `POST /api/ingest/notifications/{id}/read`, `POST /api/ingest/notifications/{id}/dismiss`, and `POST /api/ingest/sessions/{session_id}/true-up`.
- [x] Added `prompts/ingest_prepare.md` and reused `IngestPipeline.analyze_content()` so background prep can combine LLM-assisted digesting with deterministic routing, metadata extraction, and fallback behavior.
- [x] Added a separate app-shell notification surface: topbar ingest badge, `IngestInbox` drawer, unread-count polling, detail rendering, dismiss/read actions, and true-up action wiring in the frontend.
- [x] Regenerated `openapi.json` and `frontend/src/api/schema.d.ts` so the frontend typed API layer matches the new M35 backend surface.

**Acceptance Criteria met:**

- Persisted ingest sessions can now be prepared later without re-running the initial capture flow; prepared outputs are stored on disk and reloaded through the session/detail APIs.
- Background preparation only runs during idle windows, using activity-gated dispatch instead of competing with active chat streams or foreground note writes.
- Users now see ready-session notification counts and a dedicated prepared-session drawer in the app shell.
- Prepared sessions remain dormant until opened and can be requeued with a true-up action that returns the session to the queued state.

**Implementation notes:**

- The selected Phase 1.5 design was the persisted SQLite-backed job queue executed in-process, which preserved resumability and simple operations while avoiding a second worker service.
- Background preparation uses a hybrid path: reuse existing ingest analysis for routing/metadata, then enrich with one LLM JSON prompt and deterministic related-note search, with graceful fallback when AI or search is unavailable.
- Notification handling is intentionally separate from the review queue so ingest-ready work items have their own count, drawer, and dismissal lifecycle before the dedicated M36 review workspace lands.
- `enqueue_true_up()` dismisses stale `ingest_ready` notifications and creates or reuses a queued preparation job so the same session can be refreshed against newer vault state.

**Files modified:**

- `config.yaml.example`
- `monocle/config.py`
- `monocle/ingest/__init__.py`
- `monocle/main.py`
- `monocle/models.py`
- `monocle/routers/chat.py`
- `monocle/routers/ingest.py`
- `monocle/routers/notes.py`
- `monocle/services/activity.py`
- `monocle/services/ingest_prepare.py`
- `monocle/services/ingest_sessions.py`
- `monocle/tests/test_api.py`
- `monocle/tests/test_ingest_prepare.py`
- `openapi.json`
- `prompts/ingest_prepare.md`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/IngestInbox.test.tsx`
- `frontend/src/api/ingest.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/components/IngestInbox/IngestInbox.tsx`
- `frontend/src/components/IngestInbox/IngestInbox.css`
- `frontend/src/components/VoiceModal/VoiceModal.tsx`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/Topbar.tsx`

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 971 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 448 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.

---

### M36: Ingest Review Workspace & Proposal Flow

**Goal:** Build the dedicated ingest-review workflow where users inspect a prepared ingest session, answer follow-up questions, review contradictions, and edit or approve proposed deltas.

**Completed:** 2026-04-24

**Deliverables completed:**

- [x] Added `monocle/services/ingest_review.py` to hydrate prepared ingest sessions for review, enrich contradiction metadata from the vault, generate diff previews for create/update proposals, and coordinate M36 review-state transitions.
- [x] Extended `IngestSessionStore` in `monocle/services/ingest_sessions.py` with review-session mutation helpers for question answering, editable proposed-action persistence, per-action approval state changes, session-state transitions, and approve-all handoff state.
- [x] Exposed dedicated review APIs in `monocle/routers/ingest.py`: `POST /api/ingest/sessions/{session_id}/start-review`, `PATCH /api/ingest/sessions/{session_id}/questions/{question_id}`, `PATCH /api/ingest/sessions/{session_id}/actions/{action_id}`, `POST /api/ingest/sessions/{session_id}/actions/{action_id}/approve`, `POST /api/ingest/sessions/{session_id}/actions/{action_id}/reject`, and `POST /api/ingest/sessions/{session_id}/approve-all`.
- [x] Updated `GET /api/ingest/sessions/{session_id}` to return hydrated review detail with contradiction titles/excerpts and generated diff previews instead of raw prepared-session rows alone.
- [x] Added a dedicated frontend review workspace at `/ingest-review` with session list, review-state aware header, follow-up question answering, contradiction cards with links to `/docs`, editable proposal drafts, visible diff rendering, per-action approve/reject controls, approve-all, and true-up refresh.
- [x] Switched the prepared-session app-shell affordance to launch the dedicated review route and refreshed the typed frontend ingest client plus generated OpenAPI/schema artifacts.

**Acceptance Criteria met:**

- Users now review prepared ingest sessions in a dedicated `/ingest-review` workflow rather than in the general chat interface.
- Proposed updates to existing documents now surface explicit diff previews with visible before/after hunks instead of only prose rationale.
- Users can edit draft proposals before approval, approve or reject individual actions, and approve all actions for the current session.
- Contradiction warnings now include explanatory summary text plus links back to the conflicting note in the document browser.
- Dormant sessions can be refreshed with a true-up action before proposal approval, returning them to the queued preparation flow.

**Implementation notes:**

- M36 intentionally stops at `approved_pending_execution`; execution through the canonical MCP tool plane remains deferred to M37 so review and execution concerns stay separated.
- Diff previews are generated deterministically from current vault note content when review detail is loaded or a draft proposal is edited, which keeps proposal rendering stable even before document history lands in M39.
- Open questions are stored as JSON payloads on the ingest session itself, with M36 appending `answer` and `answered_at` fields rather than introducing a second table before execution semantics are needed.
- The existing prepared-session drawer from M35 remains test-covered as a notification surface, but the primary user workflow now lives on the dedicated route launched from the topbar badge and command palette.

**Files modified:**

- `monocle/models.py`
- `monocle/routers/ingest.py`
- `monocle/services/ingest_review.py`
- `monocle/services/ingest_sessions.py`
- `monocle/tests/test_api.py`
- `monocle/tests/test_ingest_sessions.py`
- `openapi.json`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/IngestReview.test.tsx`
- `frontend/src/api/ingest.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/components/IngestReview/IngestReviewScreen.tsx`
- `frontend/src/components/IngestReview/IngestReviewScreen.css`

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 973 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 449 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.

---

### M37: Ingest Execution, Validation & Source UX

**Goal:** Execute approved ingest proposals using the canonical MCP tool plane, validate the resulting vault writes through deterministic readback checks, and expose archived raw sources as discoverable UI elements in the document browser.

**Completed:** 2026-04-24

**Deliverables completed:**

- [x] Created `monocle/services/ingest_execute.py` with `execute_review_session()` orchestration that applies all approved actions by calling the canonical MCP `create_note` and `update_note` operations (never direct vault writes), records per-action execution results, and emits execution summary with succeeded/failed/skipped counts.
- [x] Implemented post-apply validation via deterministic readback checks: after each create/update completes, grep-style substring search confirms that the expected note content now exists in the vault; if validation fails, the note is reverted from `.trash/` and the action is marked failed with a detailed validation message.
- [x] Added `POST /api/ingest/sessions/{session_id}/execute` endpoint that validates the session is in `approved_pending_execution` state, executes all approved actions, collects execution results, records completion timestamps, emits HTTP 200 with detailed per-action execution outcome summary, and persists final session state.
- [x] Added `GET /api/ingest/sources`, `GET /api/ingest/sources/{source_id}`, `GET /api/ingest/sources/{source_id}/content`, and `GET /api/ingest/sources/{source_id}/download` endpoints in `monocle/routers/ingest.py` that enumerate archived sources from `data/sources/`, support text/binary payloads, truncate large text with a `truncated` flag, and return deterministic source metadata including source name and author when known.
- [x] Added `Sources` collapsed `<details>` section to the document browser with a source-list renderer that links back to archived raw sources for each ingested note via the `metadata.sources` backref array.
- [x] Added source-opening behavior in the document browser: clicking an archived text source opens it inline in a read-only preview within the Document Viewer; binary sources (audio, images) show a download button that uses system defaults; non-ingestible sources (Teams, MCP) display a summary card instead of opening.
- [x] Styled the sources section with CSS tokens (`var(--border)`, `var(--text-secondary)`, `var(--accent)`) integrated into `frontend/src/components/DocumentBrowser/DocumentBrowserScreen.css`.

**Acceptance Criteria met:**

- Approved actions are applied ONLY through MCP-owned `create_note` and `update_note` operations; no parallel direct-write ingest path exists.
- Post-apply validation confirms expected document changes via readback substring search; if validation fails, notes are rolled back to `.trash/` and the action is marked failed instead of silently succeeding.
- The execution summary reports which approved actions succeeded, failed, or were skipped and offers immediate opening of affected notes in the Document Viewer.
- Archived sources are discoverable via `/api/ingest/sources` list and browsable in the document UI under a collapsed `Sources` section that displays source name/author when available.
- Text-based sources open inline in the Document Viewer with read-only preview; other file types trigger system defaults or show download buttons; archived sources remain excluded from default search and embedding flows.

**Implementation notes:**

- M37 closes the gap between M36's approved-pending state and final note writes; execution now happens through the canonical MCP tools instead of a separate ingest path, preserving the single-plane architecture.
- Readback validation happens line-by-line via simple substring search (no regex), which makes validation deterministic and independent of note body parsing fragility.
- Response records per-action state (`execution_result.status`: `succeeded`, `failed`, or `skipped`), execution timestamp, and error/validation-failure messages so the frontend can render granular feedback.
- Source archival remains immutable and outside the vault, so sources can be referenced from multiple ingest sessions without duplication and can be garbage-collected independently of the vault lifecycle.
- The `Sources` section in the document UI is styled as a collapsed `<details>` drawer beneath the note body so it's discoverable but doesn't clutter the primary editing surface.

**Files modified:**

- `monocle/models.py` (added `ExecutionSummary`, `ExecutionResult`, extended `IngestSessionDetailResponse`)
- `monocle/routers/ingest.py` (added `execute_actions`, `list_archived_sources`, `get_archived_source`, `get_archived_source_content`, `download_archived_source`)
- `monocle/services/ingest_execute.py` (new — orchestration and MCP invocation)
- `monocle/services/ingest_sessions.py` (minor: added execution result persistence)
- `monocle/tests/test_api.py` (added 6 M37 tests: MCP execution, validation failure rollback, rejection edge cases, archived source list/read/content/download/truncate)
- `monocle/tests/test_ingest_sessions.py` (integration tests)
- `openapi.json`
- `frontend/src/components/DocumentBrowser/DocumentBrowserScreen.tsx` (added sources drawer and source detail handlers)
- `frontend/src/components/DocumentBrowser/DocumentBrowserScreen.css` (added `.doc-browser__sources-*` styles)
- `frontend/src/api/ingest.ts` (typed archived-source endpoints)
- `frontend/src/api/schema.d.ts`
- `frontend/src/DocumentBrowser.test.tsx` (added source-list and source-preview test cases)

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 992 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 450+ passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.

---

### M38: Fast-Capture Path

**Goal:** Provide a low-friction path for users who are highly confident in the source state and want to bypass the full ingest-review workflow while preserving provenance and compatibility with the ingest-session model.

**Completed:** 2026-04-24

**Deliverables completed:**

- [x] Added fast-capture orchestration on top of the existing ingest-session lifecycle: `POST /api/ingest` now honors `fast_capture=true`, persists the session/source archive exactly once, synchronously prepares the captured source through the existing preparation worker, and then either falls back to review or advances into the existing approve-and-execute path.
- [x] Added lighter confirmation semantics for high-confidence captures: the voice modal now exposes a distinct `Fast Capture` action alongside the standard review path, and clean sessions auto-approve their prepared actions and execute immediately through the canonical MCP-backed `create_note` / `update_note` flow.
- [x] Preserved provenance, source archival, reindex, and post-write validation for fast-capture by reusing the existing `metadata.sources` linkage, archived `data/sources/` payloads, deterministic execution validation, and reindex queue instead of introducing a second write implementation.

**Acceptance Criteria met:**

- Fast-capture is clearly separate from the full ingest-review workflow: the capture UI presents a dedicated `Fast Capture` action and fast-capture fallbacks are labeled in the ingest review workspace.
- The ingest architecture does not require duplicate storage or write paths to support fast-capture: the feature reuses persisted ingest sessions, the background preparation worker, the review-state model, and the existing MCP execution service.
- Users can still trace resulting notes back to their raw source and revert later if needed: successful fast-capture writes still attach `metadata.sources` backrefs to archived source payloads, and the notes remain compatible with the existing document history/versioning mechanisms.

**Implementation notes:**

- `IngestSession.fast_capture` is now surfaced through the session API so the frontend can distinguish standard review sessions from fast-capture fallbacks without inventing a parallel DTO.
- Fast-capture follows the safer fallback rule chosen during implementation: if preparation returns open questions, contradiction warnings, or no actionable proposal, the session is moved back into the normal review-state machine instead of forcing execution.
- Clean fast-capture sessions dismiss the intermediate `ingest_ready` notification after successful execution so the user does not see a stale review badge for work that already completed.
- If fast-capture execution fails validation, the session is returned to `proposal_ready` for manual recovery instead of being stranded in a terminal failed state.

**Files modified:**

- `monocle/models.py`
- `monocle/routers/ingest.py`
- `monocle/services/ingest_execute.py`
- `monocle/services/ingest_prepare.py`
- `monocle/services/ingest_review.py`
- `monocle/services/ingest_sessions.py`
- `monocle/tests/conftest.py`
- `monocle/tests/test_api.py`
- `openapi.json`
- `frontend/src/App.tsx`
- `frontend/src/api/ingest.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/components/IngestReview/IngestReviewScreen.tsx`
- `frontend/src/components/VoiceModal/VoiceModal.tsx`
- `frontend/src/VoiceCapture.test.tsx`

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 994 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 457 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.

---

### M39: File History, Revert & Diff Viewer

**Goal:** Give users first-class note history so they can inspect retained versions, compare diffs against the current note, and restore a prior state after manual or ingest-driven edits.

**Completed:** 2026-04-24

**Deliverables completed:**

- [x] Extended the vault-backed `.versions` snapshot system with configurable retention, validated version resolution helpers, history reads, and diff generation so the canonical history store stays in one place.
- [x] Added note history API endpoints for listing retained versions, reading a specific historical version, diffing that version against the current note, and restoring a retained version through the normal vault/reindex path.
- [x] Added Document Viewer history UI with retained-version browsing, diff inspection, and one-click restore, plus a settings control for live editing `history.retention_versions`.
- [x] Ensured ingest-driven and manual note updates share the same history and rollback path by keeping snapshot creation in `VaultLayer` and updating write/restore flows to stamp fresh `metadata.updated` values.

**Acceptance Criteria met:**

- Retention is configurable in settings/config: `history.retention_versions` is now part of the server settings model, persisted by `PATCH /api/settings`, applied live to the in-memory vault, and documented in `config.yaml.example`.
- Users can open historical diffs for a document in the Document Viewer: the history drawer loads retained versions, shows diff hunks against the current note, and supports quick switching between versions.
- Users can revert a document to a prior retained version after ingest or manual changes: restore runs through the vault layer, invalidates review counts, queues reindex, and refreshes the open note content in the editor.

**Implementation notes:**

- The history store remains `<vault>/.versions/<path>/<timestamp>.md`; M39 formalizes access and retention around the existing snapshot layout instead of introducing a second persistence mechanism.
- Retention pruning happens per-note path after new snapshots are written, deleting only the oldest retained files beyond the configured limit.
- History diffs are generated against the current note and include both frontmatter and body hunks so users can inspect metadata-only changes as well as content edits.
- The settings router now propagates `history.retention_versions` changes directly into `app.state.vault`, so retention edits take effect immediately without a restart.
- The Document Viewer loads history details lazily after a version is selected, keeping the default note-editing surface responsive while still exposing full rollback context when needed.

**Files modified:**

- `config.yaml.example`
- `monocle/cli.py`
- `monocle/config.py`
- `monocle/main.py`
- `monocle/models.py`
- `monocle/routers/notes.py`
- `monocle/routers/settings.py`
- `monocle/tests/test_api.py`
- `monocle/tests/test_cli.py`
- `monocle/tests/test_settings.py`
- `monocle/tests/test_vault.py`
- `monocle/vault/__init__.py`
- `openapi.json`
- `frontend/src/api/notes.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/api/settings.ts`
- `frontend/src/components/DocumentBrowser/NoteEditor.css`
- `frontend/src/components/DocumentBrowser/NoteEditor.tsx`
- `frontend/src/components/SettingsModal/SettingsModal.css`
- `frontend/src/components/SettingsModal/index.tsx`
- `frontend/src/DocumentBrowser.test.tsx`
- `frontend/src/SettingsModal.test.tsx`

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 1002 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 460 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.

---

### M40: Add Documents & Snippets To Chat Context

**Goal:** Let users explicitly add documents or document snippets into a new or existing chat session from the Docs explorer or Document Viewer without relying on implicit retrieval.

**Completed:** 2026-04-25

**Deliverables completed:**

- [x] Added explicit chat grounding persistence for client-side chat sessions so user-provided context is stored as a first-class localStorage entry instead of being folded into a normal message or hidden behind retrieval.
- [x] Added Document Viewer context-menu actions for the current document, section, sentence, or selected text, with new-chat and existing-chat flows wired from preview, YAML, and form modes.
- [x] Added Docs explorer drag-and-drop from file-tree documents onto the persistent Chat nav target, then routed the dropped document through the same new-or-existing session picker flow.
- [x] Updated chat rendering and session hydration so destination chat sessions visibly label grounding as `User-added context` and reopen the correct session through the existing `session_id` URL handoff.

**Acceptance Criteria met:**

- Users can add whole documents from the Docs explorer to a new or existing chat session: file rows are draggable and dropping them onto the Chat nav target opens a session picker that can create a new grounded chat or append the document to an existing one.
- Right-click in the Document Viewer exposes add-to-chat actions for document/section/sentence when no text is selected: the custom NoteEditor context menu offers both new-chat and existing-chat variants in preview, YAML, and form modes.
- Right-click on a selection exposes add-selection-to-chat actions for a new or existing session: the NoteEditor context menu collapses to selection-specific actions whenever there is an active text selection.
- Added context is clearly represented as user-provided context inside the destination chat session: grounding renders as a distinct `User-added context` card and is serialized into `/api/chat` as an explicit structured user message.

**Implementation notes:**

- The M40 implementation stays entirely within the existing Phase 1 client-side chat-session model. No server-side chat persistence was introduced, which preserves the LTR-4 constraint that server memory remains deferred.
- Explicit grounding is represented by a dedicated `kind: "grounding"` thread entry plus structured `GroundingEntry` metadata. When a grounded session is sent to `/api/chat`, each grounding entry becomes a separate user-role message prefixed with `[User-added grounding]`, the source path/title, and the grounding scope.
- The same `ChatSessionPickerDialog` is reused for both right-click add-to-chat actions and docs-to-chat drag-and-drop, so the user-facing decision between new and existing sessions stays consistent across entry points.
- Document Viewer section/sentence extraction intentionally uses the nearest text context available in each mode: rendered block text in preview mode, CodeMirror selection/cursor context in YAML mode, and active input selection/value context in form mode.

**Files modified:**

- `frontend/src/App.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/Chat.test.tsx`
- `frontend/src/DocumentBrowser.test.tsx`
- `frontend/src/components/Chat/ChatMessage.css`
- `frontend/src/components/Chat/ChatMessage.tsx`
- `frontend/src/components/Chat/ChatScreen.tsx`
- `frontend/src/components/Chat/ChatSessionPickerDialog.css`
- `frontend/src/components/Chat/ChatSessionPickerDialog.tsx`
- `frontend/src/components/Chat/chatGroundingDnd.ts`
- `frontend/src/components/Chat/sessionStore.ts`
- `frontend/src/components/DocumentBrowser/FileTree.tsx`
- `frontend/src/components/DocumentBrowser/DocumentBrowserScreen.tsx`
- `frontend/src/components/DocumentBrowser/NoteEditor.css`
- `frontend/src/components/DocumentBrowser/NoteEditor.tsx`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/LeftNav.css`
- `frontend/src/components/layout/LeftNav.tsx`
- `frontend/src/hooks/useChat.ts`

**Test Results:** `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 1007 passed, 8 deselected, EXIT 0; `cd frontend && npm run test -- --run` → 468 passed, EXIT 0; `cd frontend && npx tsc --noEmit` → EXIT 0.

