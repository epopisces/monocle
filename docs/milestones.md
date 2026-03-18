---
type: milestone-archive
project: monocle
maintained-by: github-copilot
last-updated: 2026-03-18
---

# Monocle — Completed Milestones & Technical Spike Resolutions

This document archives full details for completed milestones (M1–M11) and resolved technical spikes. For active work, refer to `docs/build-plan.md`.

---

## Table of Contents

### Completed Milestones
- [M1: Foundation & Project Skeleton](#m1-foundation--project-skeleton)
- [M2: API Skeleton — All Route Stubs + OpenAPI](#m2-api-skeleton--all-route-stubs--openapi)
- [M3: Vault Layer](#m3-vault-layer)
- [M4: Index Layer — ChromaDB + MemoryIndex](#m4-index-layer--chromedb--memoryindex)
- [M5: Inbox Watcher & Scheduled Re-Index](#m5-inbox-watcher--scheduled-re-index)
- [M6: AI Provider Abstraction](#m6-ai-provider-abstraction)
- [M7: Ingest Pipeline & Plugin Registry](#m7-ingest-pipeline--plugin-registry)
- [M8: REST API Wiring — Core](#m8-rest-api-wiring--core)
- [M9: Graph Layer](#m9-graph-layer)
- [M10: Agent Framework & Chat API](#m10-agent-framework--chat-api)
- [M11: Scheduled Agents](#m11-scheduled-agents)

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
- `monocle/config.py` — `Settings` Pydantic v2 model
- `monocle/models.py` — all shared Pydantic models
- `config.yaml.example` and `.env.example` committed; auto-copy flow implemented
- `vault/` skeleton with domain-based folder structure and `.obsidianignore`
- `prompts/` directory with stub files
- Stub module files: `watcher.py`, `process_manager.py`, `agents/routing.py`, `agents/reindex.py`
- `monocle/telemetry.py` — `configure_telemetry()`, `get_tracer()`, `get_meter()`, `span()`, `timed()` async context managers
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

### M2: API Skeleton — All Route Stubs + OpenAPI

**Goal:** Register every API endpoint as a stub. This is the scaffold all future milestones wire into.

**Deliverables (all completed):**
- `monocle/main.py` — FastAPI app with CORS middleware (production: `localhost` + `127.0.0.1` only; dev: +Vite)
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

**Goal:** All filesystem operations for vault notes — CRUD, atomic writes, versioning, soft-delete, schema normalisation.

**Deliverables (all completed):**
- `monocle/vault/__init__.py` — `VaultLayer` with full CRUD, versioning, soft-delete, templating
- `monocle/vault/normalise.py` — `normalise_frontmatter()` with schema defaults
- `monocle/vault/wikilinks.py` — `parse_wikilinks()`, `parse_links_field()`, `resolve_wikilink()`
- `monocle/vault/templates/` — 10 YAML schemas (person, decision, project, meeting, idea, observation, reference, action_item, blank, weekly_summary)
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

### M4: Index Layer — ChromaDB + MemoryIndex

**Goal:** IndexLayer abstraction with ChromaDB production implementation and in-memory test fake.

**Deliverables (all completed):**
- `monocle/index/base.py` — `IndexLayer` ABC
- `monocle/index/memory.py` — `MemoryIndex` for testing (no embeddings)
- `monocle/index/chroma.py` — `ChromaIndex` wrapping ChromaDB PersistentClient
- `monocle/index/__init__.py` — `get_index(settings)` factory
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
- `monocle/ingest/chunker.py` — `chunk_text()` with tiktoken cl100k_base (512 tokens, 64 overlap)
- `monocle/watcher.py`:
  - `InboxWatcher` — watchdog.Observer on `vault/inbox/`, 2-second debounce, direct pipeline call
  - `ReindexQueue` — asyncio coalescing queue, 10-second idle window per file
- `monocle/agents/reindex.py` — `ReindexAgent` with stale detection, `startup_check()`, `health_status`
- `monocle/agents/scheduler.py` — APScheduler setup for cron jobs
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
- `monocle/ai/base.py` — `AIProvider` ABC with `embed()`, `embed_batch()`, `chat()`, `transcribe()`, `extract_note_metadata()`
- `monocle/ai/ollama_provider.py` — `OllamaProvider` with auto-pull
- `monocle/ai/foundry_local_provider.py` — `FoundryLocalProvider` for Foundry local models
- `monocle/ai/azure_provider.py` — `AzureOpenAIProvider` for Azure OpenAI
- `monocle/ai/transcription.py` — `TranscriptionProvider` ABC with three implementations (WhisperCpp, Subprocess, NativeOpenAI)
- `monocle/ai/__init__.py` — `get_provider()` factory
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
- `monocle/ingest/plugin.py` — `IngestPlugin` ABC + `IngestPluginRegistry` singleton
- Three built-in plugins: `TextPlugin`, `AudioPlugin`, `TeamsPlugin` (in `plugins/` subdir)
- `monocle/agents/routing.py` — `RoutingAgent` with sentence-starter fast path and LLM fallback
- 10 template YAML schemas updated with `sentence_starters` list
- `monocle/ingest/__init__.py` — `IngestPipeline` with full 8-step implementation
- `monocle/ingest/confidence.py` — deterministic scoring (0.35×template + 0.30×coverage + 0.20×plausibility + 0.15×entity, no LLM call)
- `monocle/ingest/failed_registry.py` — JSON array persistence for `.error.md` failures
- `monocle/prompts.py` — `load_prompt()` with local override support
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

### M8: REST API Wiring — Core

**Goal:** Replace 501 stubs with real implementations for all core endpoints.

**Deliverables (all completed):**
- `monocle/main.py` lifespan: `configure_telemetry()` first; AIProvider + IndexLayer initialization; startup re-index trigger; integrated InboxWatcher, ReindexQueue
- `routers/health.py` — wired to watcher status, AI reachability, index stats
- `routers/notes.py` — full CRUD + backlinks + ReindexQueue enqueue on write
- `routers/search.py` — semantic (embed + index) and keyword (vault scan) search
- `routers/ingest.py` — POST with DuplicateSuspected→409; SSE streaming with step events
- `routers/ingest_failures.py` — GET/retry/DELETE fully wired
- `routers/transcribe.py` — multipart upload, 25 MB guard
- `routers/stats.py` — aggregated counts by type/domain/pending
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
- `monocle/graph.py` — `GraphBuilder` with full edge extraction:
  - Structured `links` frontmatter (edge_type="structured")
  - Body `[[wikilinks]]` (edge_type="wikilink")
  - `people` co-mentions (edge_type="co-mention")
  - Shared `tags` (edge_type="co-mention", capped at 20 notes/tag)
  - BFS degree computation from focus node
  - In-memory cache keyed on `(focus, max_degree, types, n)`
  - Invalidation on watcher events
- `routers/graph.py` — wired to GraphBuilder with query params
- `routers/notes.py` — `/api/notes/{path}/backlinks` fully wired: source, relation, context

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
- `monocle/agents/tools.py` — 7 `@tool` decorated functions:
  - `search_vault`, `read_note`, `write_note`, `create_note`, `get_stats`, `list_notes`, `get_person_graph`
  - Each wraps vault/index/AI operations with try/except
  - `_to_thread` helper for sync→async conversion
  - `.tools` list exposed for ChatAgent
- `monocle/agents/__init__.py`:
  - `_AIProviderChatClient(BaseChatClient)` adapter with `@use_function_invocation`
  - `_to_dict_messages()` converts ChatMessage list to OpenAI-style dicts
  - `_build_openai_tools()` builds tool schemas
  - `_inner_get_response()` + `_inner_get_streaming_response()` bridge to AIProvider
  - `_try_parse_tool_calls()` detects inline JSON tool invocations
  - `_configure_agent_otel()` sets up OTel once
  - `create_chat_agent(ai, vault, index, settings, graph_builder)` factory
- `routers/chat.py` — POST `/api/chat` with full SSE streaming:
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

### M11: Scheduled Agents

**Goal:** APScheduler weekly summary agent using lightweight built-in clustering on pre-computed embeddings. `ReindexAgent` wired into APScheduler for scheduled full-vault re-index.

**Deliverables (all completed):**
- `monocle/agents/weekly_summary.py` — `WeeklySummaryAgent` class with 8-step pipeline:
  1. Retrieve notes from vault modified in last 7 days (via `vault.list_notes`, filtering by `updated`)
  2. Optionally segment by `domain` (`agents.weekly_summary.domains` config list)
  3. Fetch pre-computed embeddings from ChromaDB via new `IndexLayer.get_embeddings_by_file()` method — no re-embedding
  4. Build numpy matrix; cluster with scikit-learn `AgglomerativeClustering` (cosine/average linkage); n_clusters = `max(2, min(n//3, 5, 8))`
  5. Fallback to LLM JSON grouping when batch < `_MIN_NOTES_FOR_CLUSTERING` (4) or no embeddings available (MemoryIndex)
  6. For each cluster: `AIProvider.chat` with `prompts/weekly_review.md` generates a paragraph summary
  7. Write `summaries/YYYY-WW.md` (ISO week) with `confidence: 1.0`, `review_status: approved`, `approval_mode: auto`, `approved_by: "system:weekly-summary"`
- `IndexLayer.get_embeddings_by_file(file_paths) -> dict[str, list[float]]` added to base, ChromaIndex, MemoryIndex
  - ChromaIndex: pages through collection in batches of `_GET_PAGE_SIZE`, returns first-chunk (chunk_index=0) embedding per file
  - MemoryIndex: returns `{}` — triggers LLM fallback in weekly summary
- `monocle/agents/scheduler.py` — weekly summary cron job wired from `agents.weekly_summary.cron` (default `"0 17 * * 5"`); replaces M5 stub
- `monocle/main.py` — weekly summary job fully registered in lifespan; `app.state.weekly_summary_agent` set
- `routers/agents.py` — `POST /api/agents/weekly-summary` (SSE streaming, emits `start`/`done`/`error`); `POST /api/agents/reindex` (202 + BackgroundTasks)
- `monocle/tests/test_scheduler.py` — 12 new tests (24 total): `TestWeeklySummaryAgent` (7 tests), `TestAgentAPIEndpoints` (5 tests)
- `.vscode/tasks.json` — `test: scheduler` task added

**Acceptance criteria met:**
- Manual trigger via `POST /api/agents/weekly-summary` creates `summaries/YYYY-WW.md` with `confidence: 1.0`, `review_status: approved`, `approved_by: "system:weekly-summary"`
- Summary note does NOT appear in review queue
- sklearn clustering used for ≥4 notes with embeddings; LLM grouping fallback for smaller batches or MemoryIndex
- `POST /api/agents/reindex` returns 202 and triggers `ReindexAgent.run()` in background
- `uv run python -m pytest monocle/tests/test_scheduler.py -x --tb=short -q` → **24 passed**
- Full suite: **542 passed, 6 deselected, EXIT 0**

---

## Resolved Technical Spikes

### SPIKE-1: Ollama Whisper audio transcription

**Original Hypothesis (M6):** Ollama can transcribe audio by passing a `.webm`/`.mp4` blob as an attachment to a Whisper model via `ollama.chat()` with a multimodal request.

**Validation Attempt:** POST a real audio blob to a locally running Ollama instance with a Whisper model; confirm a text transcript is returned.

**Status:** RESOLVED — 2026-03-17 (updated 2026-03-18)

**Outcome:** FAILED — the `ollama` Python client has no dedicated transcription method and does not support passing audio blobs via its chat/generate API in a documented, stable way.

**Final Architecture Implemented:**

`TranscriptionProvider` ABC in `monocle/ai/transcription.py` — fully decoupled from `AIProvider`. Three implementations:
1. `WhisperCppTranscriptionProvider` — HTTP POST to a local whisper.cpp server, configurable via `ai.transcribe_url`
2. `SubprocessTranscriptionProvider` — `openai-whisper` CLI subprocess, dev fallback
3. `NativeOpenAITranscriptionProvider` — OpenAI client wrapper, used by Foundry/Azure

**Factory Pattern:** `get_transcription_provider(settings)` returns:
- `None` for `"native"` backend (Foundry/Azure set their own default)
- Configured provider for `whisper_cpp`/`subprocess` backends

**Config:**
```yaml
ai:
  transcribe_backend: "native" | "whisper_cpp" | "subprocess"  # default: native
  transcribe_url: "http://localhost:9000"                       # default for whisper_cpp
```

**AIProvider Implementation:** `AIProvider.transcribe()` is now concrete — delegates to `self._transcription_provider`; raises `RuntimeError` if unset. All three provider implementations (`OllamaProvider`, `FoundryLocalProvider`, `AzureOpenAIProvider`) accept optional `transcription_provider=` parameter in constructor.

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

**Status:** RESOLVED — 2026-03-18

**Outcome:** CONFIRMED

**Key Findings:**
1. `ChatAgent.run_stream()` returns `AsyncIterable[AgentRunResponseUpdate]` that integrates cleanly with FastAPI `StreamingResponse`.
2. Each update carries a `.contents` list containing:
   - `TextContent` — token deltas
   - `FunctionCallContent` — tool invocations
   - `FunctionResultContent` — tool results
3. Tokens are yielded per-chunk as the underlying `AIProvider.chat(stream=True)` streams them.
4. `@use_function_invocation` decorator on `BaseChatClient` handles multi-turn tool-call loop automatically.
5. First-token latency is determined solely by upstream `AIProvider` (local Ollama: sub-2s as required).
6. **Note:** `agent_framework_azure_ai` package is broken (import error on `PromptAgentDefinitionText`) and not needed — the adapter is built directly on `BaseChatClient` from `agent_framework` core.

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

**Status:** RESOLVED — 2026-03-17

**Resolution Outcome:**
Re-tested on same `chromadb==1.5.5`, `cpython-3.14.3`, Windows. Rust `PersistentClient` now passes full smoke test (upsert, count, query, delete). All tests pass. The crash appears to have been a transient environment issue or a silent re-release of the chromadb 1.5.5 wheel.

**Investigation:**
- Referenced issue [#5937](https://github.com/chroma-core/chroma/issues/5937) in `chroma-core/chroma`
- Identified `SegmentAPI` workaround in related issue, but Rust backend passes without it

**Configuration Update:**
- `.python-version` updated from `3.12` → `3.14`
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
