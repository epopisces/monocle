---
type: build-plan
project: monocle
maintained-by: github-copilot
last-updated: 2026-03-31
active-milestone: M23
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

**Active Milestone:** M23 — Organization Note Type & Cross-Linked People Backreferences
**Last Completed:** M22 — Process Manager & Dev Automation (2026-03-21)
**Blocked By:** None
**Session Notes (M22 — Process Manager & Dev Automation):**
- **Status:** COMPLETE (2026-03-21), post-review hardened (2026-03-26)
- Implemented `ProcessManager` + `SubprocessHandle` (exponential-backoff crash-restart); `watch`, `scheduler`, `capture` CLI commands operational; `--separate-processes` flag on `serve`/`dev`; lifespan gating in `main.py`.
- Post-review additions: `_is_separate_processes_enabled()` method for env var override (config OR `MONOCLE_SEPARATE_PROCESSES=1`); idempotency guard preventing duplicate spawning on repeated `start_all()` calls; 15 additional tests (env override scenarios, process lifecycle, handle leak prevention, crash recovery); converted weak integration tests to focused unit tests on ProcessManager effective flag computation.
- **730 backend tests passing (37 total process_manager tests), EXIT 0**
**Session Notes (M13 — Settings & Review API):** M13 fully executed + post-review hardened. `monocle/config.py`: `save_config_patch(patch: dict)` function — deep-merges allowed sections (`ai`, `vault`, `index`, `agents`, `review`, `server`, `telemetry`, `ui`) into `config.yaml` atomically via mkstemp+os.replace; respects `MONOCLE_CONFIG` env var. `monocle/index/base.py`: `patch_file_metadata(file_path, updates)` abstract method added. `monocle/index/chroma.py`: `patch_file_metadata` implementation uses `collection.get(where=file_path_filter)` + `collection.update()` with scalar-only metadata merge. `monocle/index/memory.py`: `patch_file_metadata` implementation updates `chunk.metadata` dict in-place. `monocle/routers/settings.py`: `GET /api/settings` returns all settings sections + `mcp_key_last4` (masked); `PATCH /api/settings` accepts `{review: ..., ai: ...}` partial patch — `AIPatch.provider` and `AIPatch.transcribe_backend` typed as `Literal` (invalid values → 422); `ReviewPatch` fields have `ge`/`le` range guards (out-of-range → 422); writes to config.yaml via `save_config_patch`, hot-reloads `AIProvider` when `ai.provider` changes; rate-limited 30/min; `POST /api/settings/rotate-mcp-key` generates `secrets.token_hex(32)`, writes to `.env` atomically, updates `os.environ`, rate-limited 10/min; `_write_env_key` strips newlines from value. `monocle/routers/review.py`: `GET /api/review` warms `app.state._review_pending_count` cache as side-effect; `GET /api/review/count` returns O(1) from cache when warm, falls back to vault scan; `PATCH /api/review/{path}/approve` rate-limited 60/min, decrements count cache; `POST /api/review/approve-all` parallelized via `asyncio.gather` + `asyncio.Semaphore(10)`, rate-limited 30/min, sets cache to remainder. `app.state._review_pending_count` initialized `None` in lifespan and in `_reindex_file` callback; `notes.py` PUT/PATCH/DELETE and `ingest.py` POST/stream also invalate cache on vault write. `monocle/tests/test_settings.py`: 28 tests (was 19); added `TestInputValidation` (9 tests: Literal constraints, range validators), `TestAIProviderHotReload` (2 tests: hot-reload triggered, not triggered), `TestRotateMcpKey.test_rotate_replaces_old_key_in_os_environ`. `monocle/tests/test_review.py`: 34 tests (was 25); added `test_approve_all_sets_all_approval_fields`, `test_approve_all_partial_failure_count`, `TestPendingCountCache` (3 tests), `TestPaginationEdgeCases` (1 test). `monocle/tests/test_security.py`: added `test_approve_path_traversal_blocked`, `test_approve_absolute_path_blocked`. **644 tests passing (18 new post-review), 6 deselected, EXIT 0.**
**Session Notes (M12 — MCP Server):** M12 fully executed. `monocle/mcp_server.py`: `FastMCP("monocle", stateless_http=True)` + 8 tools (`search_vault`, `read_note`, `browse_recent`, `capture_thought`, `create_note`, `update_note`, `get_graph`, `get_stats`); `_MCPState` singleton (instance attrs, `assert_ready()`, `reindex_queue` field) populated via `init_mcp_state(vault, index, ai, ingest_pipeline, graph_builder, reindex_queue)`; `_MCPAuthMiddleware` ASGI wrapper validates `x-monocle-key` header or `?key=` query param using `hmac.compare_digest` (constant-time); logs WARNING when `?key=` path is taken; returns HTTP 401 JSON if missing or invalid; `create_mcp_app(mcp_key)` → `_MCPAuthMiddleware`; MCP key loaded from env at `create_app()` time. `capture_thought` forwards `source` param to `IngestPipeline`. `create_note`/`update_note` push to `reindex_queue` after write; `update_note` sets `metadata.updated = datetime.now(utc)`. `get_stats` paginates via `_fetch_all_refs()` (500-note batches). `monocle/main.py`: `init_mcp_state(...)` called in lifespan with `reindex_queue=reindex_queue`; `create_mcp_app(mcp_key)` mounted at `/mcp`. `monocle/tests/test_mcp.py`: 40 tests across 4 classes — `TestMCPAuth` (6), `TestMCPTools` (26), `TestMCPSecurityBoundaries` (5), `TestMCPServerConfig` (3). SPIKE-2 outcome recorded. **589 tests passing (40 MCP), 6 deselected, EXIT 0.**
**Session Notes (M11 — Scheduled Agents):** M11 fully executed. `monocle/agents/weekly_summary.py`: `WeeklySummaryAgent.run(vault, index, ai, settings)` — collects notes updated within 7 days via `vault.list_notes(limit=500)`, fetches embeddings via new `index.get_embeddings_by_file()`, clusters with `AgglomerativeClustering(metric="cosine", linkage="average")` (scikit-learn) for batches ≥4; `_llm_group_notes` JSON-prompt fallback for small batches; `_summarise_cluster` per-cluster chat call using `prompts/weekly_review.md`; writes `summaries/YYYY-WW.md` via `vault.write_note(file_path, Note(...))`. `monocle/index/base.py`: new `get_embeddings_by_file(file_paths) -> dict[str, list[float]]` abstract method. `monocle/index/chroma.py`: pages `_GET_PAGE_SIZE` batches via `collection.get(where={"file_path": {"$in": batch}})`, returns `chunk_index=0` embedding per file. `monocle/index/memory.py`: returns `{}` (triggers LLM fallback in tests). `monocle/main.py`: weekly summary cron job wired — `_weekly_summary_agent` instance + `scheduler.add_cron_job("weekly_summary", ...)` + `app.state.weekly_summary_agent`. `monocle/routers/agents.py`: both endpoints implemented — `POST /api/agents/weekly-summary` StreamingResponse SSE (`start`/`done`/`error` events), `POST /api/agents/reindex` 202 via `BackgroundTasks`. `monocle/tests/test_scheduler.py`: 12 new tests — `TestWeeklySummaryAgent` (7 tests), `TestAgentAPIEndpoints` (5 tests). `tests/test_api.py`: agents routes removed from `STILL_STUB_ROUTES`. `.vscode/tasks.json`: `test: scheduler` task added. **542 tests passing (12 new), 6 deselected, EXIT 0.**
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
| M11 | Scheduled Agents | COMPLETE |
| M12 | MCP Server | COMPLETE |
| M13 | Settings & Review API | COMPLETE |
| M14 | CLI Commands | COMPLETE |
| M15 | Frontend Scaffold & Typed API Wrappers | COMPLETE |
| M16 | Chat UI | COMPLETE |
| M17 | Document Browser & Search UI | COMPLETE |
| M18 | Graph UI | COMPLETE |
| M19 | Voice Capture & Review Queue UI | COMPLETE |
| M20 | Stats, Keyboard Shortcuts & Command Palette | COMPLETE |
| M21 | Integration Testing & Obsidian Compatibility | COMPLETE |
| M22 | Process Manager & Dev Automation | COMPLETE |
| M23 | OneNote Import Plugin | NOT STARTED |
| M24 | Voice Feature Hardening & Cross-Browser Compatibility | NOT STARTED |
| M25 | Teams Integration | NOT STARTED |

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

**Resolve by:** M24 (Voice Feature Hardening & Cross-Browser Compatibility)
**Status:** PENDING — discovered during M19 code review (2026-03-20)
**Context:** The `VoiceModal` component has two recording paths:
  1. **Web Speech API** (primary when SpeechRecognition is available) — real-time interim transcript, no server call during recording
  2. **MediaRecorder + Whisper** (fallback) — always works, uploads audio blob for transcription

Currently the Web Speech API path has **zero test coverage**. The fallback always kicks in (particularly after the stale-closure bug fix), so untested code paths could hide production bugs for users with Web Speech enabled. Cross-browser support is also uncertain (Safari partial, Firefox spotty, mobile varies).

**Validation tasks:**
  - Write comprehensive tests for `recognition.onresult`, `recognition.onerror` (per error type), `recognition.onend`, and `errorHandled` flag
  - Cross-browser testing: Chrome/Edge (full support), Safari (partial), Firefox, mobile (iOS/Android)
  - Verify real-time interim transcript UX in supported browsers
  - Document browser-specific quirks

**Decision point:** Commit to full Web Speech API support with test coverage, or mark as "best-effort, primary path is MediaRecorder" with a UI warning?

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

**Summary:** `GET/PATCH /api/settings` with masked MCP key and atomic config.yaml persistence; `POST /api/settings/rotate-mcp-key`; full review queue CRUD (`GET /api/review`, `GET /api/review/count`, `PATCH /api/review/{path}/approve`, `POST /api/review/approve-all`) with frontmatter + ChromaDB metadata sync. `patch_file_metadata` added to IndexLayer, ChromaIndex, and MemoryIndex.

**Full details:** [docs/milestones.md#m13-settings--review-api](milestones.md#m13-settings--review-api)

---

### M14: CLI Commands

**Status:** COMPLETE (2026-03-18)

**Summary:** Full Typer CLI with 9 commands (`serve`, `dev`, `reindex`, `pull-models`, `stats`, `search`, `export`, `versions list/restore`, plus `watch`/`capture` stubs). `dev` prints `[TELEMETRY]` block before uvicorn. `live_server` session fixture added to conftest.py. 21 new CLI tests + test_dev_mode.py. `.vscode/tasks.json` + `launch.json` extended.

**Full details:** [docs/milestones.md#m14-cli-commands](milestones.md#m14-cli-commands)

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
Added voice capture modal (Web Speech API primary, MediaRecorder + Whisper fallback), review-queue slide-over sorted by confidence ascending, and failed-captures warning panel. Badge counts poll `GET /api/review/count` and ingest-failure list every 30 s. 224 frontend tests passing.
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
Implemented optional process separation: `ProcessManager` + `SubprocessHandle` with exponential-backoff crash-restart; `watch`, `scheduler`, `capture` CLI commands operational as standalone process entry points; `--separate-processes` flag on `serve`/`dev`; lifespan gating in `main.py`. 715 tests passing (22 new in `test_process_manager.py`).
**Full details:** [docs/milestones.md#m22--dev-automation--optional-process-separation](milestones.md#m22--dev-automation--optional-process-separation)

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
- [ ] `monocle/vault/templates/organization.yaml` — 15-25 fields organized in sections:
  - Identity & Contact: `name`, `short_name`, `url`, `location`, `domain`
  - Structure: `org_type` (company|nonprofit|govt|academic|other), `parent_org` (wikilink to parent if applicable), `founded_year`, `industry` (enum or free text)
  - Size & Scope: `employee_count`, `description` (100–500 chars)
  - Status: `active` (boolean), `status_reason` (if inactive), lifecycle fields
  - Metadata: `tags`, `domain` (work|personal), `source`
- [ ] `vault/.templates/organization.md` — User-facing markdown body template with sections:
  - Header (name, short_name, url, org_type as metadata)
  - About (mission/description, founded_year)
  - Contact (location, website, social handles)
  - Key Dates (founded, IPO/acquisition, milestones)
  - Leadership & Structure (table of notable leaders or teams, links to person notes)
  - Notable People / Alumni (table with name, role, tenure)
  - Notes (narrative details, history, partnerships)
- [ ] Extend person template's `organizations` field example and prompt in `prompts/extract.md`:
  - Document format: `organizations: [{name: "...", role: "...", join_date: "YYYY-MM", leave_date: "YYYY-MM", current: boolean}]`
  - Include instruction: "If a person has worked at multiple organizations, extract each as a separate entry. Use YYYY-MM format for partial dates."
  - Wire extraction prompt to pull org names and dates during person note metadata extraction.
- [ ] Wiring: when person note is created with `organizations` field, automatically generate/update `links` entries pointing to matching organization notes:
  - For each org in `organizations`, attempt `resolve_wikilink("organizations/" + slugify(org.name))`.
  - If org note exists, create a link: `{target: "organizations/...", relation: "works-at", join_date: org.join_date, leave_date: org.leave_date, current: org.current}`.
  - If org note does not exist, optionally auto-create a stub org note via `VaultLayer.create_from_template("organization", {name: org.name, domain: person.domain}, metadata)` — set `review_status: "pending"`.
  - Update person note's `links` field via `patch_frontmatter()`.
- [ ] Graph layer backreferences:
  - `GET /api/graph?focus=organizations/acme-corp.md&types=person` returns all person notes with incoming `works-at` links.
  - Graph edge includes `relation: "works-at"`, `metadata: {join_date, leave_date, current}` — reused from person links field.
  - Backlinks panel on organization note shows all people (sorted by who worked there most recently).
- [ ] Routing/sentence starters for organization notes:
  - Add to `organization.yaml`: `sentence_starters: ["This is a company", "This organization", "The company was founded", "We hired from", "Working at"]`
  - If routing confidence < 0.6 and routing suggests `person` but content mentions org names, consider routing to `organization` instead (optional heuristic).
- [ ] Test coverage in `monocle/tests/`:
  - `test_vault.py`: add tests for `create_from_template("organization", ...)` and `patch_frontmatter` with linked person notes
  - `test_graph.py`: add tests for backreferences — `GET /api/graph?focus=org_note` returns only person nodes with `works-at` edges
  - `test_ingest.py`: add tests for multi-org extraction during person ingest; stub org creation scenario
  - New file `monocle/tests/test_org_linking.py` (3–5 tests):
    - `test_person_ingest_creates_org_stub_if_missing`
    - `test_person_ingest_links_to_existing_org`
    - `test_org_backlinks_people_with_works_at_relation`
    - `test_org_graph_filters_by_relation_type`
- [ ] Frontend display (optional M23a follow-up):
  - Person notes show inline org badges (clickable → org note / graph view)
  - Organization notes show "People" panel listing all associated people (generated from backreferences)
  - Person's work history table in document viewer shows org name, role, dates (from `organizations` frontmatter + computed via `links`)
- [ ] Extend `.vscode/tasks.json`:
  - `test: org-linking` — `python -m pytest monocle/tests/test_org_linking.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] `monocle/vault/templates/organization.yaml` has 15+ fields; `sentence_starters` includes org-specific phrases
- [ ] `vault/.templates/organization.md` has 5+ sections with guidance for user-facing template; table examples for leaders/alumni
- [ ] `prompts/extract.md` documents multi-org extraction with example JSON format and partial date guidance
- [ ] A new person note with `organizations: [{name: "Acme Corp", role: "VP", join_date: "2020-01", current: true}]` triggers creation of a stub `organizations/acme-corp.md` or links to existing org
- [ ] Person note's `links` field includes a `{target: "organizations/acme-corp.md", relation: "works-at", join_date: "2020-01", current: true}` entry
- [ ] `GET /api/graph?focus=organizations/acme-corp.md` returns only person nodes in the ego-graph
- [ ] Backlinks panel on org note lists all associated people sorted by recency
- [ ] `uv run python -m pytest monocle/tests/test_org_linking.py -x --tb=short -q` passes (3–5 green tests)
- [ ] Full test suite: **730+ backend tests passing, EXIT 0**

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

**Goal:** Comprehensive testing and hardening of the voice capture feature across browsers and failure modes (SPIKE-5 validation tasks).

**Deliverables:**
- [ ] Comprehensive Web Speech API tests in `frontend/src/VoiceCapture.test.tsx`:
  - `recognition.onresult` handler with interim + final transcript sequences
  - `recognition.onerror` handler for all error types (not-allowed, network, audio-capture, no-speech, etc.)
  - `recognition.onend` handler and clean shutdown
  - `errorHandled` flag to prevent double-dispatch
- [ ] Cross-browser validation matrix (document results):
  - Chrome/Edge (expected: full support)
  - Safari (expected: partial)
  - Firefox (expected: partial)
  - iOS Safari (expected: fallback to MediaRecorder)
  - Android Chrome (expected: full or fallback)
- [ ] UI/UX hardening:
  - Real-time interim transcript display in Web Speech path
  - Error messaging specific to each browser capability and error code
  - Graceful fallback messaging if Web Speech is unavailable
  - Document browser-specific quirks in code comments
- [ ] Decision: commit to full Web Speech support with test coverage, OR mark as "best-effort" with UI warning

**Acceptance Criteria:**
- [ ] Web Speech API path has comprehensive test coverage matching MediaRecorder fallback
- [ ] Cross-browser testing documented (pass/fail per browser)
- [ ] All error handling tested (no-speech, not-allowed, network, etc.)
- [ ] Real-time interim transcript visible in supported browsers
- [ ] Fallback gracefully handles unsupported browsers with clear messaging
- [ ] `cd frontend && npm run test -- --run` all VoiceCapture tests pass

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
