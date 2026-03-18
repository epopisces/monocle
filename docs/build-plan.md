---
type: build-plan
project: monocle
maintained-by: github-copilot
last-updated: 2026-03-18
active-milestone: M11
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
7. If a design question is not answered here, check `docs/srs.md` first (source of truth for behaviour), then `docs/prd.md` (product goals), then `docs/ui-design.md` (frontend layout). **Exception:** SRS §2.6 FR-PROC-01–05 describes an outdated multi-process Phase 1 architecture (separate OS processes for watcher and capture server). The authoritative Phase 1 architecture is the single unified process described in this build plan and PRD v2.4 — treat this build plan as the override for any process topology question.
8. Do not invent design decisions not covered in docs — surface any gaps as a comment in this file under the relevant milestone.

---

## Current Status

**Active Milestone:** M11 — Scheduled Agents
**Last Completed:** M10 — Agent Framework & Chat API (2026-03-18)
**Blocked By:** Nothing
**Session Notes (2026-03-18 M10 post-review):** M10 code review resolved 13 issues. **Bugs**: `AIProvider.chat()` ABC now accepts `tools: list[dict] | None = None`; all 3 providers (`OllamaProvider`, `FoundryLocalProvider`, `AzureOpenAIProvider`) forward `tools=`, check `response.message.tool_calls` / `choices[0].message.tool_calls`, and serialize non-empty tool_calls to JSON string; `_inner_get_response` and `_inner_get_streaming_response` in `agents/__init__.py` pass `tools=tools` directly; streaming adapter detects and yields `FunctionCallContent` via `_try_parse_tool_calls`; `create_from_template` now followed by `write_note` in `create_note` tool (notes were never written to disk). **Security**: `create_note` sets `review_status="pending"` so agent-created notes land in the review queue; `_MAX_BODY_LENGTH = 50_000` constant enforced in both `write_note` and `create_note`. **Minor**: `tags=[]` mutable default changed to `tags: list[str] | None = None`; `import asyncio` moved to module-level in `tools.py`; OTel port detection uses `urlparse` instead of fragile string match. **Tests**: 9 new tests in `test_ai.py` (`TestOllamaChatWithTools`, `TestFoundryLocalChatWithTools`, `TestAzureChatWithTools`); ~30 new tests in `test_agents.py` (`TestVaultToolsExecution` 14 tests, `TestToDictMessages` 5 tests, `TestTryParseToolCalls` 5 tests, `TestChatSSEErrorContract` 2 tests); existing mocks updated with `tool_calls=None` to prevent MagicMock auto-attribute false-positive. **530 tests passing (33 new), EXIT 0.**
**Session Notes (2026-03-18 M10):** M10 fully executed. `monocle/agents/tools.py`: `VaultTools` class with 7 `@ai_function` decorated tools (`search_vault`, `read_note`, `write_note`, `create_note`, `get_stats`, `list_notes`, `get_person_graph`); each tool wraps vault/index/ai operations with try/except; `_to_thread` helper for sync→async conversion; `.tools` list exposed for `ChatAgent`. `monocle/agents/__init__.py`: `_AIProviderChatClient(BaseChatClient)` adapter with `@use_function_invocation` — `_to_dict_messages()` converts ChatMessage list (including FunctionCallContent/FunctionResultContent) to OpenAI-style dicts; `_build_openai_tools()` calls `.to_json_schema_spec()` on each AIFunction; `_inner_get_response()` and `_inner_get_streaming_response()` bridge to `AIProvider.chat()`; `_try_parse_tool_calls()` detects inline JSON tool calls; `_configure_agent_otel()` calls `configure_otel_providers` once; `create_chat_agent(ai, vault, index, settings, graph_builder)` factory returns ready `ChatAgent`. `routers/chat.py`: full SSE streaming `POST /api/chat`; `ChatRequest(messages, session_id)`; creates agent per request via `create_chat_agent`; translates `AgentRunResponseUpdate` contents to SSE events (TextContent→`token`, FunctionCallContent→`tool_call`, FunctionResultContent with status=created→`note_created`); records `chat.ttft` and `chat.total_duration` OTel histograms; echoes `session_id` in `done` event; 60/minute rate limit; exceptions emit `error` event. `monocle/tests/test_agents.py`: 14 tests across 3 classes (TestChatSSEStream 10 tests, TestVaultTools 3 tests, TestCreateChatAgent 2 tests). `tests/test_api.py`: `POST /api/chat` removed from `STILL_STUB_ROUTES`. `.vscode/tasks.json`: `test: agents` task added. SPIKE-3 RESOLVED — see Technical Spikes. **497 tests passing (14 new + 10 from test_api adjustment), EXIT 0.**
**Session Notes (2026-03-18 M9):** M9 fully executed. `monocle/graph.py`: `GraphBuilder` class with `build(focus, max_degree, types, n) -> GraphData`; reads all vault notes via `VaultLayer`; extracts edges from (1) structured `links` frontmatter (`edge_type="structured"`), (2) body `[[wikilinks]]` (`edge_type="wikilink"`, relation=`"links-to"`), (3) `people` co-mentions (`edge_type="co-mention"`, relation=`"mentioned-in"`), (4) shared tags (`edge_type="co-mention"`, relation=`"shares-tag"`; capped at 20 notes-per-tag to prevent O(n²) explosion); name resolution via `resolve_wikilink()`; BFS degree computation from focus node (unreachable nodes/edges pruned); `types` filter applied post-BFS; weights tracked via internal dict before converting to `GraphEdge`; in-memory cache keyed on `(focus, max_degree, types_tuple, n)` — full invalidation on `invalidate()`. `routers/graph.py`: wired to `GraphBuilder` with `focus`, `max_degree`, `types`, `n` query params; runs in `asyncio.to_thread`. `monocle/main.py`: `GraphBuilder` created after `VaultLayer` in lifespan; stored on `app.state.graph_builder`; `_reindex_file` callback calls `graph_builder.invalidate()` at the top so any vault file change (write, delete, re-index) clears the cache. `monocle/tests/conftest.py`: `api_client` fixture test lifespan now sets `app.state.graph_builder`. `monocle/tests/test_api.py`: `GET /api/graph` removed from `STILL_STUB_ROUTES`. `monocle/tests/test_graph.py`: 33 tests across 8 test classes (`TestGraphBuilderFullVault`, `TestCoMentionEdges`, `TestWikilinkEdges`, `TestStructuredLinkEdges`, `TestSharedTagEdges`, `TestFocusedGraph`, `TestTypesFilter`, `TestGraphCache`, `TestGraphAPIEndpoint`). `.vscode/tasks.json`: `test: graph` task added. **469 tests passing (33 new), EXIT 0.**
**Session Notes (2026-03-18 M8 post-review):** M8 code review resolved 12 issues across 8 files. **Security**: raw exception strings replaced with generic user-facing messages in `routers/ingest.py`, `routers/transcribe.py`, and `routers/ingest_failures.py` (internal details still logged). **Bugs fixed**: `_note_to_markdown` in `vault/__init__.py` iterated over `raw["links"]` (already-dumped dicts from `model_dump()`) and tried to call `.model_dump()` on them again — fixed to iterate over `note.metadata.links` (live `LinkRef` objects) and pop `links` from raw after; `routers/health.py` now returns `"degraded"` instead of `"ready"` when `ai_reachable=False` or watcher is down; `overall_status` no longer uses `__import__("asyncio")` (now imports normally); `routers/ingest.py` SSE stream now emits step events as each pipeline step completes via an `on_step` async callback instead of firing all events upfront — `IngestPipeline.run()` extended with optional `on_step: Callable[[int], Awaitable[None]] | None` parameter and calls it after each of the 8 steps; SSE `_run_pipeline` task now uses `try/finally` to always put the sentinel on the queue even on exception; `routers/ingest_failures.py` retry response now includes `content_truncated: bool` flag; `main.py` `_reindex_file` callback uses the note's `metadata.updated` (or `created`) timestamp for `updated_at` instead of the re-index wall clock; `import re` inside inner loop and dead `parse_links_field` import removed from `routers/notes.py`. **Build-plan**: `stats.py` latency fields deferred explicitly to M11 (in-process OTel MetricReader readback). **Tests**: 10 new tests added — `test_backlinks_structured_link`, `test_backlinks_people_co_mention` (backlinks M9-prep), backlink identity assertion fixed in `test_backlinks_returns_list`, `test_ingest_stream_emits_step_and_done_events` (SSE event content), `test_semantic_search_type_filter`, `test_semantic_search_domain_filter`, `test_semantic_search_source_filter`, `test_keyword_search_domain_filter` (search filters), `test_retry_success_creates_note` (ingest failure retry), `test_cors_dev_origin_excluded_in_non_dev_mode` (CORS isolation), `test_move_note_to_path_traversal_blocked` (move security). **436 tests passing (10 new), EXIT 0.**
**Session Notes (2026-03-18 M8):** M8 fully executed. All 7 stub routers replaced with real implementations wired to `VaultLayer`, `IngestPipeline`, `FailedIngestRegistry`, `IndexLayer`, and `AIProvider`. `monocle/main.py` lifespan fully rewritten: `AIProvider` init (non-fatal), `FailedIngestRegistry`, `IngestPipeline`, `ReindexQueue._reindex_file` callback (embed chunks → upsert), `InboxWatcher._inbox_ingest_callback` (reads file → IngestRequest → pipeline), `ReindexAgent(embed_fn=ai.embed)`. `monocle/models.py`: `IngestResponse(note, confidence)` added; `BrainStats` gains `latency_p50_ms` + `latency_p95_ms` fields; `audio_bytes` changed to custom `AudioBytesField` (`Annotated[bytes | None, BeforeValidator]`) that decodes base64 strings from JSON but passes raw bytes through unchanged. `routers/health.py`: pings AI via embed, reads watcher status, includes `telemetry_endpoint` and `watcher_running`. `routers/notes.py`: full CRUD + backlinks (structured links + wikilinks + people co-mention) + optimistic-concurrency 409. `routers/search.py`: semantic (embed + index.search) + keyword (vault text scan). `routers/ingest.py`: POST wired with `DuplicateSuspected→409`; SSE stream emits step events. `routers/ingest_failures.py`: GET/retry/DELETE all wired. `routers/transcribe.py`: multipart upload + 25 MB guard. `routers/stats.py`: aggregates vault counts by type/domain/pending, index chunk count, failed count. `tests/conftest.py`: added `mock_ai` and `api_client` fixtures (test lifespan patches `monocle.main.lifespan` with `_test_lifespan` using temp VaultLayer + MemoryIndex). `tests/test_api.py`: complete M8 integration test suite (7 test classes, ~40 tests). `tests/test_security.py`: 17 tests across 5 classes (path traversal, audio size, optimistic concurrency, CORS, duplicate detection) — path traversal tests use `%2e%2e` percent-encoding so httpx doesn't normalise `..` before routing. `.vscode/tasks.json`: `test: api` and `test: security` tasks added. **426 tests passing (32 new), EXIT 0.**
**Session Notes (2026-03-18 M7):** M7 fully executed: `monocle/ingest/plugin.py` (`IngestPlugin` ABC + `IngestPluginRegistry` singleton — `source_id/source_label` ClassVars, `can_handle()`, `extract()`; first-match-wins `resolve()`; `.reset()` for tests); `monocle/ingest/plugins/text_plugin.py`, `audio_plugin.py`, `teams_plugin.py` (three built-in plugins, priority-registered via `register_default_plugins()`); `monocle/prompts.py` — `load_prompt(name)` checks `prompts/local/<name>.md` before `prompts/<name>.md`, strips frontmatter; `monocle/agents/routing.py` — `RoutingAgent` with sentence-starter fast path (no LLM, confidence=0.9), template_hint shortcut (confidence=1.0), LLM JSON fallback via `load_prompt("routing")`; all 10 template YAMLs already had `sentence_starters` (no change needed); `monocle/ingest/confidence.py` — deterministic `score_confidence()` (0.35×template_match + 0.30×metadata_coverage + 0.20×tag_plausibility + 0.15×entity_match; tag plausibility is text substring match, NOT embedding; entity_match via `vault.resolve_wikilink`) + `compute_approval_metadata()`; `monocle/ingest/failed_registry.py` — JSON array persistence with atomic write (mkstemp + os.replace), add/get/mark_retried/delete/count; `monocle/ingest/__init__.py` — full `IngestPipeline` 8-step run(); `DuplicateSuspected` exception; duplicate detection (score≥0.95 AND within 7 days); OTel histograms + counters per step; `.error.md` sidecar + failed_registry on steps 3–5 failure; `monocle/models.py` extended — `IngestConfidence` gains `similar_note_detected: bool` and `similar_note_path: str | None`; `monocle/tests/test_ingest.py` — 66 tests across 14 test classes; `.vscode/tasks.json` — `test: ingest` task. **385 tests passing (66 new + 5 deselected/prior), EXIT 0.**
**Session Notes (2026-03-18 M7 post-review):** Code review resolved 9 issues: greedy regex in `_parse_routing_response` (non-greedy `{.*?}` truncated nested JSON — changed to `{.*}`); LLM-returned unknown template names now normalised to `blank`; routing decision template overwritten by NoteMetadata default `"blank"` in `_construct_note` — `"template"` key excluded from `metadata_dict`; Windows-illegal chars in sidecar filenames now stripped via `_UNSAFE_FILENAME_RE`; OTel instruments moved to module-level lazy singleton (eliminate per-instance duplicate-instrument warnings); `RoutingAgent` cached as `self._routing_agent` in `__init__` (eliminates per-run YAML I/O); error message wrapped in fenced code block in sidecar body (prevent `---` frontmatter injection); `threading.Lock` added to all `FailedIngestRegistry` mutation methods; `register_default_plugins` made idempotent (skips `source_id` already present). 9 new tests added (7-day cutoff, `DuplicateSuspected` skips registry, step-8 propagation, unparseable date conservative path, `register_default_plugins` idempotency, unknown LLM template, greedy-regex nested JSON × 2); fixed no-op assertion. **394 tests passing, EXIT 0.**
**Session Notes (2026-03-18):** Pluggable `TranscriptionProvider` abstraction implemented. `monocle/ai/transcription.py`: `TranscriptionProvider` ABC; `WhisperCppTranscriptionProvider` (httpx POST to whisper.cpp `POST /inference`); `SubprocessTranscriptionProvider` (openai-whisper CLI executor); `NativeOpenAITranscriptionProvider` (OpenAI client adapter for Foundry/Azure); `get_transcription_provider(settings)` factory (returns `None` for `"native"`). `AIProvider.transcribe()` made concrete — delegates to `self._transcription_provider`. `OllamaProvider` subprocess transcription removed; accepts `transcription_provider=` param. `FoundryLocalProvider` + `AzureOpenAIProvider` accept `transcription_provider=`; default to `NativeOpenAITranscriptionProvider`. `get_provider()` factory calls `get_transcription_provider()` and passes provider to all three constructors. `config.py` extended with `ai.transcribe_backend` + `ai.transcribe_url`. `pyproject.toml` adds `httpx` to runtime deps. 12 new tests in `test_ai.py` (`TestWhisperCppTranscriptionProvider`, `TestSubprocessTranscriptionProvider`, `TestNativeOpenAITranscriptionProvider`, `TestGetTranscriptionProvider`, `TestOllamaTranscription`). **314 tests passing, EXIT 0.**
**Session Notes (2026-03-17):** M6 fully executed: `monocle/ai/base.py` (`AIProvider` ABC with `embed`, `embed_batch`, `chat`, `transcribe`, `extract_note_metadata`; `_open_span` sync span helper for async-generator compatibility; `_load_extract_prompt()` loads `prompts/extract.md` with frontmatter stripping and inline default fallback; `_parse_json_response()` handles markdown-fenced and plain JSON); `monocle/ai/ollama_provider.py` (`OllamaProvider` — `ollama.AsyncClient`, auto-pull on first use via `_ensure_model()`, streaming via `_stream_chat()` async generator without await, SPIKE-1 fallback via `openai-whisper` subprocess in `_whisper_subprocess()`); `monocle/ai/foundry_local_provider.py` (`FoundryLocalProvider` — `openai.AsyncOpenAI` with custom base_url, `embed_dimensions` parameter support, OpenAI-compatible transcription); `monocle/ai/azure_provider.py` (`AzureOpenAIProvider` — `openai.AsyncAzureOpenAI`, `dimensions` on embed, Azure Whisper transcription); `monocle/ai/__init__.py` (`get_provider(settings)` factory selecting all three providers); `monocle/config.py` extended with `ai.transcribe_model` field; OTel instrumentation: `span()` + `timed()` on all methods, `_open_span()` sync helper for streaming generators; **SPIKE-1 RESOLVED (FAILED)**: Ollama Python client has no transcription API; fallback is `openai-whisper` subprocess; `monocle/tests/test_ai.py` (27 tests, 3 integration tests deselected by default via `addopts`); `monocle/telemetry.py` `span()` fixed for Python 3.14 double-yield bug (`_yielded` flag prevents re-yield after `athrow()`); `pyproject.toml` updated with `addopts = "-m 'not integration'"` and `integration` marker registration; `.vscode/tasks.json` extended with `test: ai` task. **All 302 tests passing (27 new), EXIT 0.**
**Session Notes:** M5 fully executed: `monocle/ingest/chunker.py` (`chunk_text()` via tiktoken cl100k_base, 512-token chunks, 64-token overlap); `monocle/watcher.py` (`ReindexQueue` — asyncio-based per-file coalescing queue with 10-second idle window, thread-safe `push()` via `call_soon_threadsafe`; `InboxWatcher` — watchdog.Observer non-recursive on inbox dir, 2-second per-file debounce via threading.Timer, `_InboxEventHandler` with dynamic watchdog base-class inheritance, `.error.md` sidecar on failure); `monocle/agents/reindex.py` (`ReindexAgent` — stale detection via `get_file_timestamps()`, `run(vault, index, force=False)`, `startup_check(vault, index)`, `health_status` attribute); `monocle/agents/scheduler.py` (`MonocleScheduler` wrapping `AsyncIOScheduler`, `add_cron_job()` from 5-field cron string); `monocle/index/base.py`, `memory.py`, `chroma.py` extended with `get_file_timestamps() -> dict[str, str]`; `monocle/main.py` lifespan wired with VaultLayer, IndexLayer, ReindexQueue, ReindexAgent, MonocleScheduler, InboxWatcher, and startup_check. Post-M5 code review resolved 14 issues: timestamp Z/+00:00 normalisation (`_normalise_ts()`), `.error.md` exclusion from `_collect_md_files()`, `status()` timer-lock race, ReindexQueue callback exception logging, `MonocleScheduler` typo rename (alias retained), symlink traversal guard in `_collect_md_files()`, YAML injection fix in `_write_error_sidecar()`, `push()` trust-boundary doc, tiktoken encoder caching; 21 new tests in `test_scheduler.py` + additions to `test_watcher.py` and `test_reindex.py`; pinned `apscheduler<4`. Second-pass review resolved 4 more issues: `.error.md` cascade dispatch filter, vault-relative hidden-dir guard in `_collect_md_files()`, per-note try/except in `ReindexAgent.run()`, `os.path.basename` dedup; 4 more tests added. Post-review hardening: `_fire()` shutdown-race (loop.is_running() guard + RuntimeError TOCTOU catch + coroutine close) and unobserved-Future fix (`_log_future_exception` done-callback); 5 more tests. `ReindexQueue.stop()` now gathers cancelled tasks to completion (no pending-task teardown warnings); 1 more test. `ChromaIndex.get_file_timestamps()` now pages through chunks in batches of 1 000 (`_GET_PAGE_SIZE`) instead of one unbounded `collection.get()`; fake updated; 2 pagination tests. `_reindex_note()` now returns `bool` (`True`=chunks upserted, `False`=empty body); `run()` gates `reindexed += 1` on the return value so empty-body notes (chunk-deleted but nothing written) no longer inflate the count; 1 new test. `_collect_md_files()` hidden-dir check narrowed to `rel_parts[:-1]` so dotfiles (e.g. `.frontmatter.md`) are no longer silently excluded — only hidden *directory* components are filtered; docstring updated; 1 new test. Staleness comparison fix: skip condition now requires `note_updated` to be non-empty so notes without an `updated` frontmatter field are always re-indexed rather than frozen in the index; 1 new test. `InboxWatcher` now accepts `debounce_s` constructor arg; `main.py` passes `cfg.vault.debounce_ms / 1000` eliminating drift between the class constant and `vault.debounce_ms` config; 2 new tests. `ReindexAgent.run()` now guards against `embed_fn=None` + non-memory backend at the top of `run()`: if `get_stats().backend != "memory"` and no `embed_fn`, it logs a WARNING and returns 0 immediately — preventing the delete-before-upsert wipe cycle that would silently destroy all indexed chunks on every startup_check/scheduled run until M6 wires a real AIProvider. `_reindex_note()` reordered to **prepare-then-swap**: all chunks are built (and embedded) before `delete_file()` is called, so if chunk preparation fails the existing index data is preserved; `main.py` `ReindexAgent()` call annotated with TODO comment for M6 embed_fn wiring; 4 new tests in `TestReindexAgentEmbedGuard`. `main.py` lifespan now respects `cfg.vault.watch`: `InboxWatcher` creation, `start()`, and `stop()` are all gated behind `if cfg.vault.watch`; when disabled a `[WATCHER]` INFO log is emitted and `app.state.watcher` is set to `None`; shutdown guard changed to `if watcher is not None`. No new tests needed (covered by existing watcher tests and API lifecycle tests). **All 275 tests passing** on Python 3.14.3, EXIT 0.

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
| Failed-ingest registry | `data/failed_ingests.json` (JSON array; stdlib only; gitignored; auto-created on first failure) |
| OpenAPI spec | Auto-generated: `GET http://localhost:8000/openapi.json` |
| Frontend type gen | `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts` |
| Commit openapi.json | `uv run python scripts/export_openapi.py` |
| OTLP endpoint | `config.yaml` → `telemetry.otlp_endpoint` (default `http://localhost:4317`; AI Toolkit gRPC port) |
| Log level | `config.yaml` → `telemetry.log_level` (default `INFO`; `DEBUG` in dev mode) |
| Log format | `config.yaml` → `telemetry.log_format` (`text` in dev, `json` in prod) |

---

## Milestone Tracker

| ID | Milestone | Status |
|---|---|---|
| M1 | Foundation & Project Skeleton | COMPLETE |
| M2 | API Skeleton — all route stubs + OpenAPI | COMPLETE |
| M3 | Vault Layer | COMPLETE |
| M4 | Index Layer (ChromaDB + MemoryIndex) | COMPLETE |
| M5 | File Watcher & Re-index Queue | COMPLETE |
| M6 | AI Provider Abstraction | COMPLETE |
| M7 | Ingest Pipeline & Plugin Registry | COMPLETE |
| M8 | REST API Wiring — Core | COMPLETE |
| M9 | Graph Layer | COMPLETE |
| M10 | Agent Framework & Chat API | COMPLETE |
| M11 | Scheduled Agents | NOT STARTED |
| M12 | MCP Server | NOT STARTED |
| M13 | Settings & Review API | NOT STARTED |
| M14 | CLI Commands | NOT STARTED |
| M15 | Frontend Scaffold & Typed API Wrappers | NOT STARTED |
| M16 | Chat UI | NOT STARTED |
| M17 | Document Browser & Search UI | NOT STARTED |
| M18 | Graph UI | NOT STARTED |
| M19 | Voice Capture & Review Queue UI | NOT STARTED |
| M20 | Stats, Keyboard Shortcuts & Command Palette | NOT STARTED |
| M21 | Teams Integration | NOT STARTED |
| M22 | Integration Testing & Obsidian Compatibility | NOT STARTED |
| M23 | Process Manager & Dev Automation | NOT STARTED |
| M24 | OneNote Import Plugin | NOT STARTED |

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
**Hypothesis:** A FastMCP server with `stateless_http=True` works correctly with Claude Desktop, VS Code Copilot (GitHub Copilot), and Cursor as MCP clients.
**Validation:** Stand up a minimal FastMCP server with one tool; connect each MCP client and invoke the tool; confirm no handshake or streaming errors.
**Status:** UNRESOLVED
**Outcome:** *(fill in per client: CONFIRMED / FAILED / PARTIAL)*
**Fallback:** Standard SSE-based MCP transport (deprecated in spec 2025-03-26 but may still be required by some clients).

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
- Bot Framework JWT validation required on `POST /api/teams/messages`.
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
| `AIProvider` | `monocle/ai/base.py` | `OllamaProvider`, `FoundryLocalProvider`, `AzureOpenAIProvider` |
| `IndexLayer` | `monocle/index/base.py` | `ChromaIndex` (prod), `MemoryIndex` (tests only — no embeddings) |
| `IngestPlugin` | `monocle/ingest/plugin.py` | `TextPlugin`, `AudioPlugin`, `TeamsPlugin` |
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
source: "web"               # web | voice | teams | mcp | import
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
  watcher.py          InboxWatcher — (Phase 1: integrated async task; Phase 3+: optional standalone process)
  process_manager.py  ProcessManager — (Phase 3+ only for optional process separation; stubbed M1, optionally implemented M23)
  graph.py            GraphBuilder + in-memory cache
  mcp_server.py       FastMCP tools + auth middleware
  cli.py              Typer CLI (all commands incl. dev, reindex, pull-models, export, versions)
  ai/base.py          AIProvider ABC
  index/base.py       IndexLayer ABC
  index/memory.py     MemoryIndex — tests only, no embeddings
  vault/__init__.py   VaultLayer (all filesystem operations)
  vault/normalise.py  normalise_frontmatter()
  vault/wikilinks.py  parse_wikilinks(), parse_links_field(), resolve_wikilink()
  vault/templates/    10 YAML note template schemas (each includes sentence_starters list + field definitions for form editor)
                       NOTE: these are machine-readable YAML schemas in the *Python package* at monocle/vault/templates/ —
                       distinct from the user-facing Markdown templates in vault/.templates/ (inside the vault directory).
  ingest/__init__.py  IngestPipeline + IngestPluginRegistry
  ingest/plugin.py    IngestPlugin ABC
  ingest/plugins/     TextPlugin, AudioPlugin, TeamsPlugin
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

**Summary:** AIProvider ABC with three implementations (Ollama, FoundryLocal, AzureOpenAI). TranscriptionProvider abstraction for decoupled transcription backends (WhisperCpp, Subprocess, NativeOpenAI). SPIKE-1 resolved.

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

**Goal:** APScheduler weekly summary agent using lightweight built-in clustering on pre-computed embeddings. `ReindexAgent` wired into APScheduler for scheduled full-vault re-index.

**Deliverables:**
- [ ] `monocle/agents/weekly_summary.py` — weekly summary pipeline:
  1. Retrieve notes modified in last 7 days; fetch their 1536-dim embeddings from ChromaDB (no re-embedding)
  2. Build numpy embedding matrix; cluster with scikit-learn (`KMeans` or `AgglomerativeClustering`, selected by implementation detail)
  3. For each cluster: `AIProvider.chat` with `prompts/weekly_review.md` generates a paragraph summary
  4. Optionally segment by `domain` (if `agents.weekly_summary.domains` configured)
  5. Write `summaries/YYYY-WW.md` with `confidence: 1.0`, `review_status: approved`, `approval_mode: auto`, `approved_by: "system:weekly-summary"`, `approved_at: <now>`
- [ ] Fallback for very small batches or poor cluster quality: LLM-based grouping via structured prompt instead of model-based clustering
- [ ] `prompts/weekly_review.md` written with working summarisation prompt
- [ ] `monocle/agents/scheduler.py` — APScheduler:
  - Weekly summary cron from `agents.weekly_summary.cron` (default `"0 17 * * 5"`)
  - Scheduled re-index cron from `agents.reindex.cron` (default `"0 3 * * 0"`)
- [ ] `routers/agents.py` — `POST /api/agents/weekly-summary` (202 + SSE completion) and `POST /api/agents/reindex` (202) wired
- [ ] `monocle/tests/test_scheduler.py`
- [ ] Extend `.vscode/tasks.json`:
  - `test: scheduler` — `python -m pytest monocle/tests/test_scheduler.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] Manual trigger via `POST /api/agents/weekly-summary` creates `summaries/YYYY-WW.md` with correct frontmatter
- [ ] Summary note does NOT appear in review queue (`confidence: 1.0`, `review_status: approved`)
- [ ] Weekly summary clustering works with the built-in lightweight clustering implementation; very small batches fall back to LLM grouping
- [ ] `POST /api/agents/reindex` triggers `ReindexAgent.run()` async, returns 202
- [ ] `uv run python -m pytest monocle/tests/test_scheduler.py -x --tb=short -q` passes

---

### M12: MCP Server

**Goal:** FastMCP tools exposed at `/mcp` with key-based auth. Resolve SPIKE-2.

**Deliverables:**
- [ ] `monocle/mcp_server.py` — `FastMCP("monocle", stateless_http=True)` mounted at `/mcp`
- [ ] All 8 MCP tools: `search_vault`, `read_note`, `browse_recent`, `capture_thought`, `create_note`, `update_note`, `get_graph`, `get_stats`
- [ ] Auth middleware: verify `x-monocle-key` header or `?key=` query param; return `401` if missing or invalid
- [ ] **SPIKE-2 resolution:** Test with Claude Desktop, VS Code Copilot, Cursor. Record outcome per client in `## Technical Spikes`.
- [ ] `monocle/tests/test_mcp.py`
- [ ] Extend `.vscode/tasks.json`:
  - `test: mcp` — `python -m pytest monocle/tests/test_mcp.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] Request to `/mcp` without a key → 401
- [ ] `search_vault` returns `list[dict]` with `file_path`, `similarity`, `chunk` fields
- [ ] `capture_thought` creates a vault note and returns its `file_path`
- [ ] SPIKE-2 outcome recorded per client
- [ ] `uv run python -m pytest monocle/tests/test_mcp.py -x --tb=short -q` passes

---

### M13: Settings & Review API

**Goal:** Runtime settings management (with hot-reload) and review queue CRUD.

**Deliverables:**
- [ ] `routers/settings.py` — `GET /api/settings` (masked MCP key); `PATCH /api/settings` (hot-reloads `AIProvider` on provider change; **writes updated values back to `config.yaml` atomically so changes survive restart**); `POST .../rotate-mcp-key` (writes to `.env`)
- [ ] `routers/review.py` — `GET /api/review`, `PATCH /api/review/{path}/approve`, `POST /api/review/approve-all`, `GET /api/review/count`; approving updates frontmatter and ChromaDB metadata
- [ ] `monocle/tests/test_settings.py` + `test_review.py`
- [ ] Extend `.vscode/tasks.json`:
  - `test: settings` — `python -m pytest monocle/tests/test_settings.py monocle/tests/test_review.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] `GET /api/settings` returns MCP key masked to last 4 characters only
- [ ] `PATCH /api/settings {"review": {"queue_threshold": 0.75, "auto_approve_threshold_pct": 90}}` takes effect immediately
- [ ] `PATCH /api/review/{path}/approve` sets `review_status: approved`, `approval_mode: manual`, `approved_by`, and `approved_at` in the file and in ChromaDB metadata
- [ ] `uv run python -m pytest monocle/tests/test_settings.py monocle/tests/test_review.py -x --tb=short -q` passes

---

### M14: CLI Commands

**Goal:** Core CLI commands operational via `python -m monocle`, including the unified local dev runner and shared live-server test harness needed before M22.

**Deliverables:**
- [ ] `monocle/cli.py` — Typer app:
  - `serve` — start uvicorn with host/port from config
  - `reindex [--force]` — calls `ReindexAgent.run(force=...)`; `--force` clears existing index first
  - `pull-models` — download configured AI models via Ollama
  - `stats` — print vault stats to stdout
  - `search <query>` — semantic search, pretty-print results
  - `export [--output <path>]` — zip vault contents (excluding `.versions/`, `.trash/`, `data/`)
  - `versions list <file_path>` — list stored versions
  - `versions restore <file_path> <timestamp>` — restore a version
  - `dev` — starts the unified FastAPI + watcher + scheduler process with prefixed logging; on startup prints a telemetry status block: OTLP endpoint (or `disabled`), log level, log format
  - `watch` / `capture` — reserved stubs for future optional process separation
- [ ] `monocle/__main__.py` — `python -m monocle` entry point connecting to `cli.py`
- [ ] `monocle/tests/conftest.py` — add `live_server` session-scoped fixture:
  - Starts a single unified process on a random available port
  - Polls `GET /api/health` until ready/indexed (timeout: 15s)
  - Stores the base URL (`http://127.0.0.1:{port}`) for integration tests and Playwright
  - `yield`-based teardown sends Ctrl+C and waits up to 5s for clean shutdown
- [ ] `monocle/tests/test_dev_mode.py` — assert unified dev startup, clean shutdown, and watcher/scheduler startup
- [ ] `monocle/tests/test_cli.py` — using `typer.testing.CliRunner`
- [ ] Extend `.vscode/tasks.json`:
  - `cli: reindex` — `python -m monocle reindex`
  - `cli: reindex --force` — `python -m monocle reindex --force`
  - `cli: stats` — `python -m monocle stats`
  - `cli: export` — `python -m monocle export --output ./export.zip`
- [ ] Extend `.vscode/launch.json`:
  - `CLI: Reindex (debug)` — debugpy launch of `python -m monocle reindex`; useful for stepping through index logic interactively

**Acceptance Criteria:**
- [ ] `python -m monocle --help` shows all commands (including stubbed dev/watch/capture)
- [ ] `python -m monocle reindex --force` completes without error (using `MemoryIndex`)
- [ ] `python -m monocle export --output /tmp/export.zip` creates a valid zip
- [ ] `python -m monocle versions list <path>` lists stored version timestamps
- [ ] `python -m monocle dev` starts a single unified process and shuts down cleanly on Ctrl+C
- [ ] `python -m monocle dev` prints a telemetry block on startup, e.g. `[TELEMETRY] OTLP endpoint: http://localhost:4317 | log_level: DEBUG | format: text`
- [ ] `live_server` fixture is available for integration tests and Playwright before M22 begins
- [ ] `CLI: Reindex (debug)` launch config runs `reindex` with the debugger attached
- [ ] `uv run python -m pytest monocle/tests/test_cli.py -x --tb=short -q` passes

---

### M15: Frontend Scaffold & Typed API Wrappers

**Goal:** React app skeleton with all routes and a typed API layer generated from the committed OpenAPI spec.

**Deliverables:**
- [ ] `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts` (requires running M8 server)
- [ ] `frontend/src/api/client.ts` — typed `fetch` wrapper: handles JSON, SSE streams, 4xx/5xx errors; uses `schema.d.ts` types
- [ ] `frontend/src/api/` — individual typed functions for all documented frontend-consumed endpoints generated from the committed OpenAPI spec (no uncovered endpoint families)
- [ ] `frontend/src/App.tsx` — React Router routes: `/` (Chat), `/docs` (Document Browser), `/search`, `/graph`, `/stats`
- [ ] `frontend/src/components/layout/` — `AppShell`, `Topbar` (polls `GET /api/health` every 10s; shows green/amber/red indicator per status field), `LeftNav` (collapses at ≤1200px viewport)
- [ ] `frontend/src/components/SettingsModal/` — wired to `GET/PATCH /api/settings`, key rotation — functional but minimal styling
- [ ] `frontend/src/styles/tokens.css` — all CSS custom property tokens from UI Design doc §3 (colors, typography, spacing, border-radius, shadows)
- [ ] `frontend/src/hooks/useTheme.ts` — theme state management: detect system preference via `prefers-color-scheme` media query; persist selection to `localStorage`; provide context hook for all components to subscribe to theme changes
- [ ] `frontend/tests/api.test.ts` — mock fetch; assert type-safe API calls
- [ ] `frontend/tests/App.test.tsx` — renders without crash, nav links present
- [ ] Add `openapi-typescript` as a `devDependency` and as a `package.json` script: `"gen-api": "openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts"`
- [ ] Extend `.vscode/tasks.json`:
  - `frontend: dev` — `npm run dev` (cwd: `frontend/`; runs Vite dev server)
  - `frontend: type-check` — `npx tsc --noEmit` (cwd: `frontend/`)
  - `frontend: gen-api` — `npm run gen-api` (cwd: `frontend/`; regenerates `schema.d.ts`; requires server running at `:8000`)
- [ ] Extend `.vscode/launch.json`:
  - `Frontend Dev Server` — runs `frontend: dev` task and opens `http://localhost:5173` in the browser
  - `Full Stack (debug)` — compound configuration: `Dev Server (debug)` + `Frontend Dev Server`; the **default developer launch** once both tiers are functional

**Acceptance Criteria:**
- [ ] `cd frontend && npm run dev` serves `http://localhost:5173` with no console errors
- [ ] All CSS tokens defined and applied to at least the layout shell
- [ ] Topbar health indicator reflects live `GET /api/health` response
- [ ] `cd frontend && npx tsc --noEmit` exits 0 (no TypeScript errors)
- [ ] `cd frontend && npm run test -- --run` passes
- [ ] `Full Stack (debug)` compound launch config starts both backend (with debugger) and frontend dev server; `http://localhost:5173` loads in the browser

---

### M16: Chat UI

**Goal:** Fully functional chat screen — streaming, chat starters, session history, settings modal.

**Deliverables:**
- [ ] `frontend/src/components/Chat/ChatScreen.tsx` — message thread, 6 chat starter tiles (2×3 grid), session picker dropdown (last 10 sessions from localStorage)
- [ ] `frontend/src/components/Chat/ChatInput.tsx` — multiline textarea; `Enter` sends; `Shift+Enter` newlines; microphone button (opens VoiceModal); send button
- [ ] `frontend/src/components/Chat/ChatMessage.tsx` — Markdown rendering; tool call disclosure (collapsible); inline note card for `note_created` events
- [ ] `frontend/src/hooks/useChat.ts` — `EventSource`-based SSE streaming; session management (localStorage, last 10 sessions)
- [ ] Settings modal: fully wired to API — backend selector, threshold slider, key rotation, and theme toggle (wired to `useTheme()` hook from M15)
- [ ] Theme switching: Settings modal adds a **Theme** section with radio buttons [● Dark ○ Light ○ System]. Integrates with `useTheme()` hook created in M15. Selection persisted to localStorage. Changes take effect immediately across the app.
- [ ] `frontend/tests/Chat.test.tsx`

**Acceptance Criteria:**
- [ ] Clicking a chat starter sends a pre-filled message that streams a response
- [ ] Tool call renders as collapsible: "Used `search_vault` — 4 results"
- [ ] Session picker shows ≤10 sessions; switching sessions restores thread
- [ ] Settings modal shows masked key; Rotate calls `POST /api/settings/rotate-mcp-key` and updates display
- [ ] Theme toggle in Settings modal immediately applies dark or light mode; selection persists across page reloads
- [ ] `cd frontend && npm run test -- --run` passes

---

### M17: Document Browser, Search & Template Editor UI

**Goal:** Vault file tree, CodeMirror markdown editor with auto-save, template editor UI for non-developers, search screen.

**Deliverables:**
- [ ] `frontend/src/components/DocumentBrowser/` — file tree (expand/collapse, type icons), right panel with rendered preview, CodeMirror editor (Markdown + YAML frontmatter syntax highlighting), rich preview mode, AI Assist slide-over
- [ ] Auto-save: `useDebounce` 2s → `PUT /api/notes/{path}` with `if_mtime` header; server-side re-index work is coalesced per file
- [ ] Frontmatter editing modes:
  - **YAML mode (default):** CodeMirror with YAML syntax highlighting for advanced users
  - **Rich preview mode:** rendered Markdown surface with inline formatting affordances for lightweight WYSIWYG-like editing of common text operations; designed to share the same Markdown document model as YAML mode
  - **Form mode (new):** Template Editor UI displaying note frontmatter as interactive form inputs—text fields for string values, toggles for booleans, multiselect for arrays, datetime picker for timestamps—derived from template schema
  - Mode toggle button in editor toolbar (`YAML` / `Preview` / `Form`); form mode validates against the note's type-specific template schema before save
- [ ] Template Editor UI reads field definitions from template YAML (e.g., `person.yaml`, `decision.yaml`): field name, type, required, descriptions, enum options
- [ ] Form validation: required fields marked with `*`; non-string/non-array/non-boolean types trigger validation error toast before save
- [ ] `[[Wikilink]]` click: navigate to that note in Document Browser
- [ ] Review Approve button in editor toolbar (visible when `review_status: pending`)
- [ ] `frontend/src/components/Search/SearchScreen.tsx` — mode toggle (Semantic / Keyword), semantic threshold slider, result note cards with open/approve inline actions
- [ ] Backlinks side panel in Document Browser: shows incoming/outgoing links with relation types and preview snippets
- [ ] `frontend/tests/DocumentBrowser.test.tsx` + `Search.test.tsx` + `TemplateEditor.test.tsx`

**Acceptance Criteria:**
- [ ] File tree renders vault structure; clicking a file shows rendered content
- [ ] Edit mode: CodeMirror with YAML frontmatter highlighting; auto-save triggers after 2s idle
- [ ] Form mode: note with type `person` displays form with fields defined in `person.yaml` template; non-developers can edit without knowing YAML
- [ ] Form validation prevents save if required fields are empty; error toast displayed
- [ ] Switching between YAML, rich preview, and form modes preserves unsaved changes (prompt if user tries to switch with pending saves)
- [ ] Rapid consecutive saves while typing result in one eventual re-index for the file, not one embed pass per save
- [ ] 409 conflict on save shows an error toast (no silent data loss)
- [ ] `Ctrl+S` saves immediately
- [ ] Backlinks panel lists all notes that link to the current note; double-click navigates to backlink source
- [ ] Semantic search returns ranked results with similarity percentages
- [ ] `cd frontend && npm run test -- --run` passes

---

### M18: Graph UI

**Goal:** Ego-graph visualization with degree-based visual decay, type filters, and wired graph API.

**Deliverables:**
- [ ] `frontend/src/components/Graph/GraphScreen.tsx` — React Force Graph instance
- [ ] Focus input with autocomplete across person/note/tag names
- [ ] Depth toggle [1][2][3] — updates `max_degree` param; re-fetches graph
- [ ] Type filter chips [Person ✓][Note ✓][Tag ✓] — updates `types=` param; re-fetches
- [ ] Reset View button — clears focus, returns to full-vault mode
- [ ] Degree-based visual encoding: degree 0 = 100% opacity/max size; each degree: −25% opacity, −15% size
- [ ] Edge labels: `relation` value rendered as midpoint label (hidden for unlabeled edges)
- [ ] Node click: side panel with top 5 related notes; double-click: navigate to Document Browser
- [ ] Drag: node positions persisted to localStorage
- [ ] `frontend/tests/Graph.test.tsx`

**Acceptance Criteria:**
- [ ] Selecting a focus node fetches `GET /api/graph?focus=<id>&max_degree=<n>&types=<csv>` and redraws
- [ ] Focus node (degree 0) is visually largest with full opacity
- [ ] Type filter correctly removes node types from rendered graph
- [ ] Graph renders within 2 seconds for a vault with up to 2,000 notes
- [ ] `cd frontend && npm run test -- --run` passes

---

### M19: Voice Capture & Review Queue UI

**Deliverables:**   
- [ ] `frontend/src/components/VoiceModal/` — recording state machine; Web Speech API (primary); Whisper fallback (`POST /api/transcribe`; shows "Transcribing…" spinner); template selector; Save/Edit/Discard actions
- [ ] `frontend/src/components/ReviewQueue/` — slide-over panel; sorted by confidence ascending; per-item Approve/Fix actions; Approve All button; badge count; empty state with auto-close
- [ ] `frontend/src/components/FailedCaptures/` — warning button + slide-over panel; inspect/retry/dismiss actions wired to ingest-failure endpoints
- [ ] Badge count: poll `GET /api/review/count` on page load + after every ingest API call

**Acceptance Criteria:**
- [ ] Voice modal shows real-time transcript during recording
- [ ] Whisper fallback correctly fills transcript after `POST /api/transcribe` returns
- [ ] Review queue sorts lowest-confidence first; approve removes card and decrements badge
- [ ] Failed captures warning only appears when failures exist; Retry removes the item after successful re-ingest
- [ ] Approve All button clears all cards and shows "All reviewed" state
- [ ] `cd frontend && npm run test -- --run` passes

---

### M20: Stats, Keyboard Shortcuts & Command Palette

**Deliverables:**
- [ ] `frontend/src/components/Stats/StatsScreen.tsx` — 4 stat cards, Recharts ingestion-by-source bar, notes-by-type bar, 8-week sparkline, source quality star ratings
- [ ] `frontend/src/hooks/useHotkeys.ts` — all shortcuts from SRS FR-WEB-12 (Ctrl+K, Ctrl+Shift+K, Ctrl+N, Ctrl+S, Ctrl+/, Ctrl+\, Escape, Enter, Shift+Enter)
- [ ] `frontend/src/components/CommandPalette/` — `Ctrl+/` trigger; fuzzy-search all actions (search, create note, run weekly summary, open settings, etc.); keyboard navigation (arrows + Enter)

**Acceptance Criteria:**
- [ ] Stats screen renders all charts with live data from `GET /api/stats`
- [ ] `Ctrl+K` moves focus to semantic search input from any screen
- [ ] `Ctrl+/` opens command palette; typing "weekly" surfaces "Run weekly summary"
- [ ] `Escape` closes command palette and all modals
- [ ] `cd frontend && npm run test -- --run` passes

---

### M21: Teams Integration

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

### M22: Integration Testing & Obsidian Compatibility

**Goal:** Full E2E test suite, Obsidian compatibility verified, CI pipeline, complete README.

**Prerequisite:** `dev` command and `live_server` fixture from M14 must already be complete before M22 begins.

**Deliverables:**
- [ ] `tests/e2e/` Playwright tests: ingest → review queue flow; chat starter sends message and gets response; graph focus navigation; voice modal dismiss; settings round-trip
- [ ] Obsidian compatibility checklist (see below)
- [ ] `.github/workflows/ci.yml` — runs on every PR: `pytest`, `npm run test -- --run`, `playwright test`
- [ ] `README.md` — prerequisites, venv setup, config, first run, Ollama model pull, MCP client setup
- [ ] Extend `.vscode/tasks.json`:
  - `test: e2e` — `playwright test` (requires server running at `:8000`)
  - `test: ci-full` — sequential: `test: backend` → `test: frontend` → `test: e2e` (mirrors CI pipeline)
- [ ] Extend `.vscode/launch.json`:
  - `E2E Tests (Playwright debug)` — Playwright test runner with `--headed --debug`; requires server already running via `Dev Server (debug)` or `API Server (debug)`

**Obsidian Compatibility Checklist:**
- [ ] Vault opens in Obsidian with no warnings or errors
- [ ] `confidence: 0.72`, `review_status: pending`, and approval metadata fields render without errors in Obsidian
- [ ] `.versions/` and `.trash/` are absent from Obsidian's file list (`.obsidianignore` effective)
- [ ] `monocle/vault/templates/` YAML files are not visible as notes in Obsidian
- [ ] Agent-written `[[wikilinks]]` resolve correctly in Obsidian

**CI Command:**
```bash
python -m pytest monocle/tests/ -x --tb=short && \
cd frontend && npm run test -- --run && \
cd .. && playwright test
```

**Acceptance Criteria:**
- [ ] CI pipeline passes clean on a fresh clone (with Ollama running and models pulled)
- [ ] All E2E tests pass
- [ ] Obsidian compatibility checklist 100% complete
- [ ] README setup procedure is accurate and complete
- [ ] `test: ci-full` task runs all three test suites in sequence and reports pass/fail for each
- [ ] `E2E Tests (Playwright debug)` launch config opens a headed browser with Playwright's debug stepping enabled

---

### M23: Dev Automation & Optional Process Separation

**Goal:** Optional process separation and additional developer ergonomics beyond the already-operational unified dev flow delivered in M14.

**Deliverables:**

**Phase 3+ (Optional—Deferred for Performance):**
- [ ] Conditional process separation (if vault exceeds ~10k notes):
  - `ProcessManager` class: orchestrates separate `InboxWatcher`, `APScheduler`, and main API as optional subprocesses
  - `watch` / `capture` / `scheduler` CLI commands become operational entry points for standalone processes
  - Only activated by explicit `--separate-processes` flag or `server.separate_processes: true` in `config.yaml`
  - Fallback: Phase 1 unified mode is always available as the default and recommended configuration

**Acceptance Criteria:**
- [ ] Future separate-process implementation does not require code changes to M1–M22 (ProcessManager is opt-in)

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
- Phase 3 optionally enables: conditional process separation via `server.separate_processes: true` in `config.yaml`, `ProcessManager` orchestration (M23 implementation), and related CLI commands (`watch`, `capture`, `scheduler`) as standalone entry points.
- Phase 1 Phase 2 unified single-process mode remains the default and fully supported; no performance regression for <10k vaults.
- **Architectural constraint enforced in Phase 1:** `main.py` lifespan hooks must be agnostic to process topology (all async tasks are thread-safe and can run in single process or separate processes transparently)
