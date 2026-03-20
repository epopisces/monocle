---
type: milestone-archive
project: monocle
maintained-by: github-copilot
last-updated: 2026-03-18
---

# Monocle â€” Completed Milestones & Technical Spike Resolutions

This document archives full details for completed milestones (M1–M11, M19–M20) and resolved technical spikes. For active work, refer to `docs/build-plan.md`.

---

## Table of Contents

### Completed Milestones
- [Monocle â€” Completed Milestones \& Technical Spike Resolutions](#monocle--completed-milestones--technical-spike-resolutions)
  - [Table of Contents](#table-of-contents)
    - [Completed Milestones](#completed-milestones)
    - [Resolved Technical Spikes](#resolved-technical-spikes)
  - [Completed Milestones](#completed-milestones-1)
    - [M1: Foundation \& Project Skeleton](#m1-foundation--project-skeleton)
    - [M2: API Skeleton â€” All Route Stubs + OpenAPI](#m2-api-skeleton--all-route-stubs--openapi)
    - [M3: Vault Layer](#m3-vault-layer)
    - [M4: Index Layer â€” ChromaDB + MemoryIndex](#m4-index-layer--chromadb--memoryindex)
    - [M5: Inbox Watcher \& Scheduled Re-Index](#m5-inbox-watcher--scheduled-re-index)
    - [M6: AI Provider Abstraction](#m6-ai-provider-abstraction)
    - [M7: Ingest Pipeline \& Plugin Registry](#m7-ingest-pipeline--plugin-registry)
    - [M8: REST API Wiring â€” Core](#m8-rest-api-wiring--core)
    - [M9: Graph Layer](#m9-graph-layer)
    - [M10: Agent Framework \& Chat API](#m10-agent-framework--chat-api)
    - [M11: Scheduled Agents](#m11-scheduled-agents)
  - [Resolved Technical Spikes](#resolved-technical-spikes-1)
    - [SPIKE-1: Ollama Whisper audio transcription](#spike-1-ollama-whisper-audio-transcription)
    - [SPIKE-3: Microsoft Agent Framework SSE streaming through FastAPI](#spike-3-microsoft-agent-framework-sse-streaming-through-fastapi)
    - [SPIKE-4: ChromaDB Rust backend crash on Python 3.14 (Windows)](#spike-4-chromadb-rust-backend-crash-on-python-314-windows)

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
- `monocle/config.py` â€” `Settings` Pydantic v2 model
- `monocle/models.py` â€” all shared Pydantic models
- `config.yaml.example` and `.env.example` committed; auto-copy flow implemented
- `vault/` skeleton with domain-based folder structure and `.obsidianignore`
- `prompts/` directory with stub files
- Stub module files: `watcher.py`, `process_manager.py`, `agents/routing.py`, `agents/reindex.py`
- `monocle/telemetry.py` â€” `configure_telemetry()`, `get_tracer()`, `get_meter()`, `span()`, `timed()` async context managers
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

### M2: API Skeleton â€” All Route Stubs + OpenAPI

**Goal:** Register every API endpoint as a stub. This is the scaffold all future milestones wire into.

**Deliverables (all completed):**
- `monocle/main.py` â€” FastAPI app with CORS middleware (production: `localhost` + `127.0.0.1` only; dev: +Vite)
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

**Goal:** All filesystem operations for vault notes â€” CRUD, atomic writes, versioning, soft-delete, schema normalisation.

**Deliverables (all completed):**
- `monocle/vault/__init__.py` â€” `VaultLayer` with full CRUD, versioning, soft-delete, templating
- `monocle/vault/normalise.py` â€” `normalise_frontmatter()` with schema defaults
- `monocle/vault/wikilinks.py` â€” `parse_wikilinks()`, `parse_links_field()`, `resolve_wikilink()`
- `monocle/vault/templates/` â€” 10 YAML schemas (person, decision, project, meeting, idea, observation, reference, action_item, blank, weekly_summary)
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

### M4: Index Layer â€” ChromaDB + MemoryIndex

**Goal:** IndexLayer abstraction with ChromaDB production implementation and in-memory test fake.

**Deliverables (all completed):**
- `monocle/index/base.py` â€” `IndexLayer` ABC
- `monocle/index/memory.py` â€” `MemoryIndex` for testing (no embeddings)
- `monocle/index/chroma.py` â€” `ChromaIndex` wrapping ChromaDB PersistentClient
- `monocle/index/__init__.py` â€” `get_index(settings)` factory
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
- `monocle/ingest/chunker.py` â€” `chunk_text()` with tiktoken cl100k_base (512 tokens, 64 overlap)
- `monocle/watcher.py`:
  - `InboxWatcher` â€” watchdog.Observer on `vault/inbox/`, 2-second debounce, direct pipeline call
  - `ReindexQueue` â€” asyncio coalescing queue, 10-second idle window per file
- `monocle/agents/reindex.py` â€” `ReindexAgent` with stale detection, `startup_check()`, `health_status`
- `monocle/agents/scheduler.py` â€” APScheduler setup for cron jobs
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
- `monocle/ai/base.py` â€” `AIProvider` ABC with `embed()`, `embed_batch()`, `chat()`, `transcribe()`, `extract_note_metadata()`
- `monocle/ai/ollama_provider.py` â€” `OllamaProvider` with auto-pull
- `monocle/ai/foundry_local_provider.py` â€” `FoundryLocalProvider` for Foundry local models
- `monocle/ai/azure_provider.py` â€” `AzureOpenAIProvider` for Azure OpenAI
- `monocle/ai/transcription.py` â€” `TranscriptionProvider` ABC with three implementations (WhisperCpp, Subprocess, NativeOpenAI)
- `monocle/ai/__init__.py` â€” `get_provider()` factory
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
- `monocle/ingest/plugin.py` â€” `IngestPlugin` ABC + `IngestPluginRegistry` singleton
- Three built-in plugins: `TextPlugin`, `AudioPlugin`, `TeamsPlugin` (in `plugins/` subdir)
- `monocle/agents/routing.py` â€” `RoutingAgent` with sentence-starter fast path and LLM fallback
- 10 template YAML schemas updated with `sentence_starters` list
- `monocle/ingest/__init__.py` â€” `IngestPipeline` with full 8-step implementation
- `monocle/ingest/confidence.py` â€” deterministic scoring (0.35Ã—template + 0.30Ã—coverage + 0.20Ã—plausibility + 0.15Ã—entity, no LLM call)
- `monocle/ingest/failed_registry.py` â€” JSON array persistence for `.error.md` failures
- `monocle/prompts.py` â€” `load_prompt()` with local override support
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

### M8: REST API Wiring â€” Core

**Goal:** Replace 501 stubs with real implementations for all core endpoints.

**Deliverables (all completed):**
- `monocle/main.py` lifespan: `configure_telemetry()` first; AIProvider + IndexLayer initialization; startup re-index trigger; integrated InboxWatcher, ReindexQueue
- `routers/health.py` â€” wired to watcher status, AI reachability, index stats
- `routers/notes.py` â€” full CRUD + backlinks + ReindexQueue enqueue on write
- `routers/search.py` â€” semantic (embed + index) and keyword (vault scan) search
- `routers/ingest.py` â€” POST with DuplicateSuspectedâ†’409; SSE streaming with step events
- `routers/ingest_failures.py` â€” GET/retry/DELETE fully wired
- `routers/transcribe.py` â€” multipart upload, 25 MB guard
- `routers/stats.py` â€” aggregated counts by type/domain/pending
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
- `monocle/graph.py` â€” `GraphBuilder` with full edge extraction:
  - Structured `links` frontmatter (edge_type="structured")
  - Body `[[wikilinks]]` (edge_type="wikilink")
  - `people` co-mentions (edge_type="co-mention")
  - Shared `tags` (edge_type="co-mention", capped at 20 notes/tag)
  - BFS degree computation from focus node
  - In-memory cache keyed on `(focus, max_degree, types, n)`
  - Invalidation on watcher events
- `routers/graph.py` â€” wired to GraphBuilder with query params
- `routers/notes.py` â€” `/api/notes/{path}/backlinks` fully wired: source, relation, context

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
- `monocle/agents/tools.py` â€” 7 `@tool` decorated functions:
  - `search_vault`, `read_note`, `write_note`, `create_note`, `get_stats`, `list_notes`, `get_person_graph`
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
- `routers/chat.py` â€” POST `/api/chat` with full SSE streaming:
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
- `monocle/mcp_server.py` â€” `FastMCP("monocle", stateless_http=True)` with 8 tools + auth middleware + factory:
  - `_MCPState` dataclass holds module-level references to vault/index/ai/pipeline/graph_builder
  - `init_mcp_state(vault, index, ai, ingest_pipeline, graph_builder)` â€” called from app lifespan
  - `_MCPAuthMiddleware(app, key)` â€” ASGI wrapper; validates `x-monocle-key` header then `?key=` query param; returns HTTP 401 JSON `{"detail":"Unauthorized"}` if missing or invalid; passes non-HTTP scope types (lifespan, websocket) through unchanged
  - `create_mcp_app(mcp_key) -> _MCPAuthMiddleware` â€” wraps `mcp.streamable_http_app()` with auth
  - 8 `@mcp.tool()` decorated async functions using `_state` singleton:
    1. `search_vault(query, n_results, note_type, domain)` â€” embeds query via AI, calls `index.search()`, returns JSON array with `file_path`, `similarity`, `chunk` (â‰¤500 chars)
    2. `read_note(file_path)` â€” reads via `vault.read_note()`, returns JSON with title/type/domain/tags/people/body
    3. `browse_recent(limit, note_type, domain)` â€” calls `vault.list_notes(sort="updated")`, returns JSON array with file_path/title/type/domain/updated fields
    4. `capture_thought(content, source)` â€” runs full `IngestPipeline.run(IngestRequest)`, returns JSON with file_path/type/confidence/review_status
    5. `create_note(title, body, note_type, domain, tags)` â€” `create_from_template` + `write_note`; sets `review_status="pending"` (MCP-created notes go to review queue)
    6. `update_note(file_path, body)` â€” reads note, patches body, writes back; `_MAX_BODY_LENGTH = 50_000`
    7. `get_graph(focus, max_degree)` â€” `graph_builder.build()` in thread, returns `GraphData.model_dump_json()`
    8. `get_stats()` â€” aggregates vault + index stats; returns total_notes/by_type/by_domain/pending_review/index_chunks/index_backend

- `monocle/main.py` â€” `init_mcp_state(...)` called in lifespan after IngestPipeline + GraphBuilder init; `create_mcp_app(mcp_key)` mounted at `/mcp` in `create_app()` using `os.environ.get(cfg.server.mcp_access_key_env, "")`

- `monocle/tests/test_mcp.py` â€” 40 tests across 4 classes:
  - `TestMCPAuth`: no key â†’ 401; wrong key header â†’ 401; wrong key query â†’ 401; valid header passes; valid query param passes; no env key configured â†’ all requests rejected
  - `TestMCPTools`: all 8 tools exercised via `mcp.call_tool()` with real VaultLayer + MemoryIndex; field presence assertions; `create_note` sets pending review status; `update_note` body-too-long raises; `capture_thought` returns file_path
  - `TestMCPServerConfig`: `init_mcp_state` sets all 5 fields; `create_mcp_app` returns `_MCPAuthMiddleware`; server has exactly 8 tools
  - `TestMCPSecurityBoundaries`: enforces MCP security boundaries (e.g. vault path restrictions, cross-tenant isolation, and HTTP surface hardening) around tools and routes

- `.vscode/tasks.json` â€” `test: mcp` task added

**Acceptance criteria met:**
- Request to `/mcp` without a key â†’ 401 âœ“
- `search_vault` returns list with `file_path`, `similarity`, `chunk` fields âœ“
- `capture_thought` creates a vault note and returns its `file_path` âœ“
- SPIKE-2 outcome recorded (implementation complete; live client testing deferred) âœ“
- `uv run python -m pytest monocle/tests/test_mcp.py -x --tb=short -q` â†’ **40 passed** âœ“
- Full suite: **all tests passing (EXIT 0)** âœ“

---

### M13: Settings & Review API

**Goal:** Runtime settings management (with hot-reload and config.yaml persistence) and review queue CRUD.

**Deliverables (all completed):**
- `monocle/config.py` â€” `save_config_patch(patch: dict)` public function: deep-merges allowed section keys (`ai`, `vault`, `index`, `agents`, `review`, `server`, `telemetry`, `ui`) into `config.yaml` atomically via mkstemp + os.replace; respects `MONOCLE_CONFIG` env var; skips `None` values.
- `monocle/index/base.py` â€” `patch_file_metadata(file_path, updates)` abstract method added to `IndexLayer`.
- `monocle/index/chroma.py` â€” `patch_file_metadata` uses `collection.get(where=file_path_filter, include=["metadatas"])` + `collection.update()` with scalar-only metadata merge.
- `monocle/index/memory.py` â€” `patch_file_metadata` updates `chunk.metadata` dict in-place for all matching chunks.
- `monocle/routers/settings.py` â€” full implementation:
  - `GET /api/settings` â€” returns `settings.model_dump()` (secrets excluded by Pydantic `Field(exclude=True)`) + `mcp_key_last4` (masked via `"****" + key[-4:]`; `None` if key absent).
  - `PATCH /api/settings` â€” accepts `{review: {...}, ai: {...}}` partial patch; applies via `model_copy(update=...)` on sub-configs; writes to `config.yaml` via `save_config_patch`; hot-reloads `AIProvider` when `ai.provider` changes; updates `app.state.settings`.
  - `POST /api/settings/rotate-mcp-key` â€” generates `secrets.token_hex(32)`; writes to `.env` (path configurable via `MONOCLE_ENV_FILE` env var) atomically; updates `os.environ`; returns `{mcp_key_last4: "****xxxx"}`.
- `monocle/routers/review.py` â€” full implementation:
  - `GET /api/review` â€” scans vault via `vault.list_notes(limit=10000)`, filters `review_status=="pending"`, returns paginated list.
  - `GET /api/review/count` â€” same scan, returns `{"count": N}`.
  - `PATCH /api/review/{path}/approve` â€” calls `vault.patch_frontmatter(path, {review_status, approval_mode, approved_by, approved_at})` (auto-404 via `NoteNotFound` HTTPException); mirrors `review_status: approved` to ChromaDB via `index.patch_file_metadata`; returns `ApprovalResult`.
  - `POST /api/review/approve-all` â€” approves all pending notes in batch; returns `{"approved": N}`.
- `monocle/tests/test_settings.py` â€” 19 tests: `TestGetSettings` (6), `TestPatchSettings` (8), `TestRotateMcpKey` (5). `_temp_config` autouse fixture redirects config writes to a per-test temp file (via `MONOCLE_CONFIG` env var) so the real `config.yaml` is never mutated.
- `monocle/tests/test_review.py` â€” 25 tests: `TestListReview` (7), `TestReviewCount` (4), `TestApproveNote` (9), `TestApproveAll` (5).
- `monocle/tests/test_api.py` â€” `STILL_STUB_ROUTES` pruned to only `POST /api/teams/messages`.
- `.vscode/tasks.json` â€” `test: settings` task added.

**Acceptance criteria met:**
- `GET /api/settings` returns MCP key masked to last 4 characters only âœ“
- `PATCH /api/settings {"review": {"queue_threshold": 0.75, "auto_approve_threshold_pct": 90}}` takes effect immediately on `app.state.settings` and is persisted to `config.yaml` âœ“
- `PATCH /api/review/{path}/approve` sets `review_status: approved`, `approval_mode: manual`, `approved_by`, `approved_at` in frontmatter and mirrors `review_status` to ChromaDB metadata âœ“
- `uv run python -m pytest monocle/tests/test_settings.py monocle/tests/test_review.py -x --tb=short -q` â†’ **44 passed** âœ“
- Full suite: **626 passed, 6 deselected, EXIT 0** âœ“

---

**Goal:** APScheduler weekly summary agent using lightweight built-in clustering on pre-computed embeddings. `ReindexAgent` wired into APScheduler for scheduled full-vault re-index.

**Deliverables (all completed):**
- `monocle/agents/weekly_summary.py` â€” `WeeklySummaryAgent` class with 8-step pipeline:
  1. Retrieve notes from vault modified in last 7 days (via `vault.list_notes`, filtering by `updated`)
  2. Optionally segment by `domain` (`agents.weekly_summary.domains` config list)
  3. Fetch pre-computed embeddings from ChromaDB via new `IndexLayer.get_embeddings_by_file()` method â€” no re-embedding
  4. Build numpy matrix; cluster with scikit-learn `AgglomerativeClustering` (cosine/average linkage); n_clusters = `min(max(2, n//3, 5), 8)` (floor 2, target 5, cap 8)
  5. Fallback to LLM JSON grouping when batch < `_MIN_NOTES_FOR_CLUSTERING` (4) or no embeddings available (MemoryIndex)
  6. For each cluster: `AIProvider.chat` with `prompts/weekly_review.md` generates a paragraph summary
  7. Write `summaries/YYYY-WW.md` (ISO week) with `confidence: 1.0`, `review_status: approved`, `approval_mode: auto`, `approved_by: "system:weekly-summary"`
- `IndexLayer.get_embeddings_by_file(file_paths) -> dict[str, list[float]]` added to base, ChromaIndex, MemoryIndex
  - ChromaIndex: pages through collection in batches of `_GET_PAGE_SIZE`, returns first-chunk (chunk_index=0) embedding per file
  - MemoryIndex: returns `{}` â€” triggers LLM fallback in weekly summary
- `monocle/main.py` â€” weekly summary cron job registered in lifespan from `agents.weekly_summary.cron` config (default `"0 17 * * 5"`); `WeeklySummaryAgent` instance stored in `app.state.weekly_summary_agent`
- `routers/agents.py` â€” `POST /api/agents/weekly-summary` (SSE streaming, emits `start`/`done`/`error`); `POST /api/agents/reindex` (202 + BackgroundTasks)
- `monocle/tests/test_scheduler.py` â€” 12 new tests (24 total): `TestWeeklySummaryAgent` (7 tests), `TestAgentAPIEndpoints` (5 tests)
- `.vscode/tasks.json` â€” `test: scheduler` task added

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

**Status:** RESOLVED â€” 2026-03-17 (updated 2026-03-18)

**Outcome:** FAILED â€” the `ollama` Python client has no dedicated transcription method and does not support passing audio blobs via its chat/generate API in a documented, stable way.

**Final Architecture Implemented:**

`TranscriptionProvider` ABC in `monocle/ai/transcription.py` â€” fully decoupled from `AIProvider`. Three implementations:
1. `WhisperCppTranscriptionProvider` â€” HTTP POST to a local whisper.cpp server, configurable via `ai.transcribe_url`
2. `SubprocessTranscriptionProvider` â€” `openai-whisper` CLI subprocess, dev fallback
3. `NativeOpenAITranscriptionProvider` â€” OpenAI client wrapper, used by Foundry/Azure

**Factory Pattern:** `get_transcription_provider(settings)` returns:
- `None` for `"native"` backend (Foundry/Azure set their own default)
- Configured provider for `whisper_cpp`/`subprocess` backends

**Config:**
```yaml
ai:
  transcribe_backend: "native" | "whisper_cpp" | "subprocess"  # default: native
  transcribe_url: "http://localhost:9000"                       # default for whisper_cpp
```

**AIProvider Implementation:** `AIProvider.transcribe()` is now concrete â€” delegates to `self._transcription_provider`; raises `RuntimeError` if unset. All three provider implementations (`OllamaProvider`, `FoundryLocalProvider`, `AzureOpenAIProvider`) accept optional `transcription_provider=` parameter in constructor.

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

**Status:** RESOLVED â€” 2026-03-18

**Outcome:** CONFIRMED

**Key Findings:**
1. `ChatAgent.run_stream()` returns `AsyncIterable[AgentRunResponseUpdate]` that integrates cleanly with FastAPI `StreamingResponse`.
2. Each update carries a `.contents` list containing:
   - `TextContent` â€” token deltas
   - `FunctionCallContent` â€” tool invocations
   - `FunctionResultContent` â€” tool results
3. Tokens are yielded per-chunk as the underlying `AIProvider.chat(stream=True)` streams them.
4. `@use_function_invocation` decorator on `BaseChatClient` handles multi-turn tool-call loop automatically.
5. First-token latency is determined solely by upstream `AIProvider` (local Ollama: sub-2s as required).
6. **Note:** `agent_framework_azure_ai` package is broken (import error on `PromptAgentDefinitionText`) and not needed â€” the adapter is built directly on `BaseChatClient` from `agent_framework` core.

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

**Status:** RESOLVED â€” 2026-03-17

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
- `monocle/cli.py` â€” Full Typer app with all commands:
  - `serve` â€” uvicorn with host/port from config
  - `dev` â€” development mode; prints `[TELEMETRY] OTLP endpoint: ... | log_level: ... | format: ...` block before starting uvicorn; sets `MONOCLE_DEV=true`
  - `reindex [--force]` â€” `ReindexAgent.run(force=...)` via `asyncio.run()`; attempts real AI embed, falls back gracefully with warning
  - `pull-models` â€” Ollama model pull for `chat_model` + `embed_model`; no-ops for non-Ollama providers
  - `stats` â€” vault + index stats printed to stdout (notes total, chunks, pending review, by-type, by-domain)
  - `search <query> [--limit N]` â€” embed query via AIProvider, pretty-print top-N hits
  - `export [--output <path>]` â€” zip vault excluding `.versions/`, `.trash/`
  - `versions list <file_path>` â€” calls `vault.list_versions()`, prints timestamps oldest-first
  - `versions restore <file_path> <timestamp>` â€” calls `vault.restore_version()`
  - `watch` / `capture` â€” reserved stubs
- `monocle/__main__.py` â€” already implemented (M1); no changes needed
- `monocle/tests/conftest.py` â€” `live_server` session-scoped fixture: starts uvicorn subprocess on random port, polls `/api/health` (15s timeout), yields base URL, graceful SIGINT shutdown (5s, then kill)
- `monocle/tests/test_dev_mode.py` â€” 7 tests across 3 classes: `TestUnifiedDevStartup` (health endpoint, multiple endpoints reachable, clean shutdown), `TestWatcherAndSchedulerStartup` (watcher_running field, scheduler no crash), `TestDevTelemetryBlock` (`[TELEMETRY]` in dev output)
- `monocle/tests/test_cli.py` â€” 21 tests using `typer.testing.CliRunner` across 8 classes
- `.vscode/tasks.json` â€” 4 new tasks: `cli: reindex`, `cli: reindex --force`, `cli: stats`, `cli: export`
- `.vscode/launch.json` â€” `CLI: Reindex (debug)` launch config (order 4 in monocle group)

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