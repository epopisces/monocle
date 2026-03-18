---
type: build-plan
project: monocle
maintained-by: github-copilot
last-updated: 2026-03-18
active-milestone: M8
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

**Active Milestone:** M8 — REST API Wiring — Core
**Last Completed:** M7 — Ingest Pipeline & Plugin Registry (2026-03-18)
**Blocked By:** Nothing
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
| M8 | REST API Wiring — Core | NOT STARTED |
| M9 | Graph Layer | NOT STARTED |
| M10 | Agent Framework & Chat API | NOT STARTED |
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
**Hypothesis:** Ollama can transcribe audio by passing a `.webm`/`.mp4` blob as an attachment to a Whisper model via `ollama.chat()` with a multimodal request.
**Validation:** POST a real audio blob to a locally running Ollama instance with a Whisper model; confirm a text transcript is returned.
**Status:** RESOLVED — 2026-03-17 (updated 2026-03-18)
**Outcome:** FAILED — the `ollama` Python client has no dedicated transcription method and does not support passing audio blobs via its chat/generate API in a documented, stable way.
**Final architecture:** `TranscriptionProvider` ABC in `monocle/ai/transcription.py` — fully decoupled from `AIProvider`. Three implementations: `WhisperCppTranscriptionProvider` (HTTP POST to a local whisper.cpp server, configurable via `ai.transcribe_url`); `SubprocessTranscriptionProvider` (openai-whisper CLI subprocess, dev fallback); `NativeOpenAITranscriptionProvider` (OpenAI client wrapper, used by Foundry/Azure). Factory `get_transcription_provider(settings)` returns `None` for `"native"` backend (Foundry/Azure set their own default) and the configured provider for `whisper_cpp`/`subprocess` backends. `AIProvider.transcribe()` is now concrete — delegates to `self._transcription_provider`; raises `RuntimeError` if unset. Config: `ai.transcribe_backend` (`native`|`whisper_cpp`|`subprocess`, default `native`), `ai.transcribe_url` (default `http://localhost:9000`). **Start whisper.cpp server:** `./server --model ggml-base.en.bin --host 0.0.0.0 --port 9000` then set `ai.transcribe_backend: whisper_cpp`.

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
**Hypothesis:** Microsoft Agent Framework (Python) streams tokens incrementally through a FastAPI `StreamingResponse` with `text/event-stream` content-type, achieving sub-2-second first-token latency with a local Ollama model.
**Validation:** Create a minimal agent with one tool; wire it to a FastAPI endpoint; confirm token-by-token delivery via browser `EventSource`.
**Status:** UNRESOLVED
**Outcome:** *(fill in: CONFIRMED / FAILED — latency observed, any workarounds needed)*
**Fallback:** Queue-based approach: agent runs in a background thread and pushes tokens to an `asyncio.Queue` that the SSE endpoint drains.

---

### SPIKE-4: ChromaDB Rust backend crash on Python 3.14 (Windows)

**Status: RESOLVED — 2026-03-17**

**Original hypothesis:** ChromaDB 1.5.5 Rust extension crashes at runtime on Python 3.14 (Windows) with access violation `0xC0000005` on any `upsert`/`add` call.
**Crash observed:** 2026-03-16 on `chromadb==1.5.5`, `cpython-3.14.3`.
**Resolution (2026-03-17):** Re-tested on same chromadb==1.5.5, cpython-3.14.3. Rust `PersistentClient` now passes full smoke test (upsert, count, query, delete). All 195 tests pass. The crash may have been a transient environment issue or a silent re-release of the chromadb 1.5.5 wheel.
- Investigated `chroma-core/chroma` issue [#5937](https://github.com/chroma-core/chroma/issues/5937) — a related `SegmentAPI` workaround was identified, but the Rust backend passes without it.
- `.python-version` updated from `3.12` → `3.14`.
- `_FakeChromaClient` retained in `test_index.py` for test isolation (no real I/O in unit tests); not required as a crash workaround.
**If the crash reappears:** Use `SegmentAPI` fallback: `chromadb.Client(Settings(chroma_api_impl="chromadb.api.segment.SegmentAPI", is_persistent=True, persist_directory=path))`.

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

**Goal:** Set up project structure, tooling, config models, and test infrastructure. No business logic yet.

**Deliverables:**
- [x] `pyproject.toml` with all backend dependencies pinned:
  - `fastapi>=0.115`, `uvicorn[standard]`, `chromadb>=0.6`, `watchdog>=4`, `apscheduler>=3.10`,
  - `agent-framework-azure-ai==1.0.0b260107`, `agent-framework-core==1.0.0b260107`,
  - `mcp[cli]`, `botbuilder-core`, `pyyaml`, `python-dotenv`, `python-frontmatter`, `tiktoken`,
  - `ollama`, `openai`, `typer`, `slowapi`,
  - `scikit-learn`,
  - `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-exporter-otlp-proto-http`,
    `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-logging`, `opentelemetry-instrumentation-httpx`,
  - `pytest>=8`, `pytest-asyncio`, `playwright`
- [x] `monocle/` package with all subdirectory `__init__.py` files (ai/, index/, vault/, ingest/, ingest/plugins/, agents/, routers/, tests/)
- [x] `monocle/config.py` — `Settings` Pydantic v2 model. All fields from SRS §6. Loads `config.yaml` + `.env`. Validates `server.host`, `vault.path`, `vault.inbox_path`, `ai.provider`, `index.chroma_persist_path`.
- [x] `monocle/models.py` — all shared Pydantic models: `Note`, `NoteRef`, `NoteChunk`, `NoteMetadata`, `Page`, `BrainStats`, `IngestRequest`, `IngestConfidence`, `IndexStats`, `ScoredChunk`, `LinkRef`, `GraphData`, `GraphNode`, `GraphEdge`, `RoutingDecision`. **`IngestRequest` must include `allow_duplicate: bool = False`** — required for the duplicate-detection advisory flow (FR-ING-11).
- [x] `config.yaml.example` and `.env.example` committed; `config.yaml` and `.env` in `.gitignore`. On first run (i.e., `config.yaml` does not exist), `Settings` loader SHALL copy `config.yaml.example` to `config.yaml` automatically and log a notice, so a fresh clone is immediately runnable with sensible defaults. `config.yaml.example` includes a `telemetry:` section:
  ```yaml
  telemetry:
    enabled: true
    otlp_endpoint: "http://localhost:4317"   # AI Toolkit gRPC (or any OTLP backend)
    otlp_transport: grpc                      # grpc | http
    log_level: INFO                           # DEBUG | INFO | WARNING | ERROR
    log_format: text                          # text (dev) | json (prod)
    enable_sensitive_data: true               # include prompts/completions in traces
  ```
- [x] `vault/` skeleton with flexible domain-based organization (note types are indexed via frontmatter metadata, not folder structure). **Default domains** (customizable; folders are optional):
  ```
  vault/
  ├── people/               # Entity hub: individuals, contacts
  ├── organizations/        # Entity hub: companies, teams, orgs (optional)
  ├── work/                 # Domain: all work-related notes (org/role metadata in frontmatter)
  ├── technologies/         # Domain: languages, tools, frameworks, how-tos, architecture
  ├── theology/             # Domain: beliefs, philosophy, spiritual exploration
  ├── entertainment/        # Domain: games, books, shows, music (or split into subfolders)
  ├── projects/             # Cross-domain hub: active learning, side, or hobby projects (optional)
  ├── summaries/            # Auto-generated weekly summaries (flat or can organize by domain)
  ├── inbox/                # Unclassified captures awaiting the ingest pipeline
  ├── .templates/           # User-facing Markdown templates (visible in Obsidian)
  ├── .versions/            # Shadow copies (excluded from index and Obsidian)
  ├── .trash/               # Soft-deleted notes (excluded from index)
  └── .obsidianignore       # Excludes .versions/, .trash/
  ```
  **Flexibility Principles (enforced by M1 design):**
  - Folder structure is optional/advisory — pure UX convenience for browsing.
  - Note type/domain/metadata is the source of truth (flagged in frontmatter); queries use metadata, not folder paths.
  - Users can add/remove/rename domains freely without code changes — domains are just directories.
  - Future (Phase 2+): Settings UI allows users to customize domain list, pin favorites, and auto-create subfolders from templates.
  - Multi-org handling: use `org: "Acme Corp"` frontmatter field rather than folder nesting — keeps structure flat and flexible.
  - Example: A user with multiple employers can keep all work notes in `work/` and distinguish via `org` metadata + backlinks/graph navigation.
- [x] `prompts/` directory with stub files: `routing.md`, `extract.md`, `weekly_review.md`, `confidence.md` (each with YAML frontmatter + placeholder prompt body); `prompts/local/` listed in `.gitignore`. **Note:** `confidence.md` is retained as a documentation placeholder only — M7 replaces LLM-based confidence scoring with a deterministic formula, so this file is never loaded by any agent.
- [x] Stub module files: `monocle/watcher.py`, `monocle/process_manager.py`, `monocle/agents/routing.py`, `monocle/agents/reindex.py` (empty classes / `pass` implementations — wired in later milestones). **Note:** `capture.py` is not created — the capture server role is fulfilled by `POST /api/ingest` REST endpoint in Phase 1 (per PRD v2.4); optional separate process deferred to Phase 3+ via `ProcessManager`.
- [x] `monocle/telemetry.py` — `configure_telemetry(settings)`, `get_tracer(name)`, `get_meter(name)`, `span(name, **attrs)` async ctx manager, `timed(histogram, **attrs)` async ctx manager. No-ops when `telemetry.enabled: false`. Called once from `main.py` lifespan before any other subsystem starts.
- [x] `.obsidianignore` containing: `.versions/`, `.trash/`
- [x] `frontend/` scaffold: `package.json`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`, `src/App.tsx` (empty shell with one route)
- [x] `frontend/vitest.config.ts`
- [x] `frontend/package.json` dependencies: `react`, `react-dom`, `react-router-dom`, `react-markdown`, `react-force-graph`, `recharts`, `@codemirror/state`, `@codemirror/view`, `@codemirror/commands`, `@codemirror/lang-markdown`, `@codemirror/lang-yaml`, `typescript`, `vite`, `vitest`, `@playwright/test`
- [x] `pytest.ini` with `testpaths = monocle/tests` and `asyncio_mode = auto` (implemented via `[tool.pytest.ini_options]` in `pyproject.toml`)
- [x] `monocle/tests/conftest.py` with:
  - `tmp_vault` fixture — temp dir with 5 fixture notes (one per template type: person, decision, meeting, idea, blank)
  - `memory_index` fixture — returns a fresh `MemoryIndex` instance
- [x] `.vscode/tasks.json` — foundational build task definitions:
  - `install: backend deps` — `uv sync`
  - `install: frontend deps` — `npm install` (cwd: `frontend/`)
  - `test: backend` — `uv run python -m pytest monocle/tests/ -x --tb=short -q`
  - `test: frontend` — `npm run test -- --run` (cwd: `frontend/`)
- [x] `.vscode/launch.json` — foundational debug launch configurations:
  - `Dev Server (debug)` — debugpy launch of `python -m monocle dev`; primary developer launch
  - `Backend Tests (debug)` — debugpy launch of pytest against `monocle/tests/`

**Acceptance Criteria:**
- [x] `uv run python -m pytest monocle/tests/ -x --tb=short -q` exits 0 (9 tests passed)
- [x] `cd frontend && npm run test -- --run` exits 0 (1 test passed)
- [x] `uv run python -c "from monocle.config import Settings"` succeeds (no import errors)
- [x] `uv run python -c "from monocle.models import Note, BrainStats, IngestRequest, GraphData, LinkRef"` succeeds
- [x] `.gitignore` covers `config.yaml`, `.env`, `data/`, `frontend/dist/`, `__pycache__/`, `.venv/`
- [x] `F5` in VS Code with `Dev Server (debug)` as the active configuration starts the unified server with the debugger attached
- [x] `uv run python -c "from monocle.telemetry import configure_telemetry"` succeeds (no import errors)

**Notes:**
- Python minimum version: 3.11. Set `requires-python = ">=3.11"` in `pyproject.toml` (uv reads this to select the interpreter).
- Pin agent-framework versions — the package renames identifiers between preview builds.
- Use `uv` for all Python environment and dependency management. `uv sync` creates `.venv/` at project root and installs all deps (including dev extras). Never use `pip` directly or install into system Python.
- `monocle` is the Python package name (directory is `monocle/`). `uv run python -m monocle` works via `monocle/__main__.py`.
- On first run, if `config.yaml` is missing, `Settings` auto-copies `config.yaml.example` → `config.yaml` and logs a one-time notice. This ensures a fresh clone works immediately without manual setup while preserving the user's ability to override any value.
- `allow_duplicate: bool = False` in `IngestRequest` must be present from M1 even though the duplicate-detection logic is not wired until M7. Stubs in M2 must accept the field without error.

---

### M2: API Skeleton — All Route Stubs + OpenAPI

**Goal:** Register every API endpoint as a stub. This is the scaffold all future milestones wire into. The OpenAPI spec must be complete before frontend work begins.

**Deliverables:**
- [x] `monocle/main.py` — FastAPI app, all routers included, CORS middleware (**production**: allow only `http://localhost:{server.port}` and `http://127.0.0.1:{server.port}`; **dev mode only**: additionally allow `http://localhost:5173` and `http://127.0.0.1:5173` for the Vite dev server — no wildcard origins; controlled by `server.dev_cors` flag set by `uv run python -m monocle dev`), lifespan hook (placeholder startup/shutdown)
- [x] `monocle/routers/health.py` — `GET /api/health` returns `{"status": "starting", "version": "0.1.0", "ai_reachable": false, "index_status": "empty"}`
- [x] `monocle/routers/notes.py` — `GET /api/notes`, `GET /api/notes/{path}`, `PUT /api/notes/{path}`, `PATCH /api/notes/{path}`, `DELETE /api/notes/{path}`, `POST /api/notes/{path}/move`, `GET /api/templates`, `GET /api/notes/{path}/backlinks` — all return `501`
- [x] `monocle/routers/search.py` — `GET /api/search`, `GET /api/search/keyword` — return `501`
- [x] `monocle/routers/ingest.py` — `POST /api/ingest`, `POST /api/ingest/stream` — return `501`
- [x] `monocle/routers/ingest_failures.py` — `GET /api/ingest/failures`, `POST /api/ingest/failures/retry`, `DELETE /api/ingest/failures/{id}` — all return `501`
- [x] `monocle/routers/transcribe.py` — `POST /api/transcribe` — returns `501`
- [x] `monocle/routers/graph.py` — `GET /api/graph` — returns `501`
- [x] `monocle/routers/stats.py` — `GET /api/stats` — returns `501`
- [x] `monocle/routers/chat.py` — `POST /api/chat` — returns `501`
- [x] `monocle/routers/agents.py` — `POST /api/agents/weekly-summary`, `POST /api/agents/reindex` — return `501`
- [x] `monocle/routers/review.py` — `GET /api/review`, `PATCH /api/review/{path}/approve`, `POST /api/review/approve-all`, `GET /api/review/count` — return `501`
- [x] `monocle/routers/settings.py` — `GET /api/settings`, `PATCH /api/settings`, `POST /api/settings/rotate-mcp-key` — return `501`
- [x] `monocle/routers/teams.py` — `POST /api/teams/messages` — returns `501`
- [x] All stubs use correct Pydantic request/response models from `models.py`
- [x] Rate limiting via `slowapi`: `/api/ingest` + `/api/transcribe` = 30 req/min; `/api/chat` = 60 req/min
- [x] FastAPI static files mount at `/` (serves `frontend/dist/`; noop if not built)
- [x] `OpenTelemetryMiddleware` (from `opentelemetry-instrumentation-fastapi`) registered in `main.py`; automatically creates a server span per request with `http.method`, `http.route`, `http.status_code`, and duration. Provides the user-facing latency signal for every endpoint with zero per-route code.
- [x] `openapi.json` exported to repo root and committed
- [x] `monocle/tests/test_api.py` — `TestClient` tests verifying every route returns 200 or 501, never 404 or 500
- [x] Extend `.vscode/tasks.json`:
  - `api: export openapi` — `uv run python -c "import json; from monocle.main import app; open('openapi.json','w').write(json.dumps(app.openapi(),indent=2))"`
  - `api: start server` — `uv run uvicorn monocle.main:app --host 127.0.0.1 --port 8000 --reload` (non-debug, used as a preLaunchTask)
- [x] Extend `.vscode/launch.json`:
  - `API Server (debug)` — debugpy launch of uvicorn at `127.0.0.1:8000 --reload`

**Acceptance Criteria:**
- [x] `GET http://localhost:8000/api/health` returns 200 JSON
- [x] `GET http://localhost:8000/openapi.json` returns a valid OpenAPI 3.x document listing all 30 endpoints
- [x] Every non-health endpoint returns exactly 501 (not 404, not 500)
- [x] `uv run uvicorn monocle.main:app --host 127.0.0.1 --port 8000` starts without errors
- [x] `uv run python -m pytest monocle/tests/test_api.py -x --tb=short -q` passes (31 tests)

**Notes:**
- Commit `openapi.json` to the repo. The frontend uses it to generate `schema.d.ts`.
- After any route change, regenerate: `uv run python scripts/export_openapi.py`

---

### M3: Vault Layer

**Goal:** All filesystem operations for vault notes — CRUD, atomic writes, versioning, soft-delete, schema normalisation, template management, wikilink resolution.

**Deliverables:**
- [x] `monocle/vault/__init__.py` — `VaultLayer` class with methods:
  - `list_notes(folder, type, domain, sort, limit, offset) -> Page[NoteRef]` — paginated
  - `read_note(file_path) -> Note` — parse YAML frontmatter + body; raise `NoteNotFound` if missing; call `normalise_frontmatter`
  - `write_note(file_path, note, if_mtime=None)` — atomic write (system tempdir via `tempfile.mkstemp`); shadow version before overwrite; raise `409` on mtime mismatch
  - `patch_frontmatter(file_path, updates: dict)` — merge-update frontmatter only, preserve body
  - `delete_note(file_path)` — move to `<vault>/.trash/`; never delete from filesystem
  - `move_note(from_path, to_path)` — rename file, update index
  - `create_from_template(template_type, metadata, body) -> Note` — load template YAML, merge metadata, derive filename slug from title
  - `resolve_wikilink(name) -> str | None` — case-insensitive filename match, returns vault-relative path or None
  - `list_versions(file_path) -> list[str]` — list timestamps in `.versions/<path>/`
  - `restore_version(file_path, timestamp)` — overwrite current with historical version
- [x] `monocle/vault/normalise.py` — `normalise_frontmatter(fm: dict) -> dict` applying schema defaults
- [x] `monocle/vault/wikilinks.py` — `parse_wikilinks(body: str) -> list[str]`, `parse_links_field(links: list) -> list[LinkRef]`, `resolve_wikilink(name, vault_root) -> str | None`
- [x] `monocle/vault/templates/` — 10 YAML schemas: `person.yaml`, `decision.yaml`, `project.yaml`, `meeting.yaml`, `idea.yaml`, `observation.yaml`, `reference.yaml`, `action_item.yaml`, `blank.yaml`, `weekly_summary.yaml`. **These are machine-readable Pydantic schema definitions living in the Python package at `monocle/vault/templates/` — not in the vault directory. They are distinct from the user-facing Markdown templates in `vault/.templates/`.**
- [x] `monocle/tests/test_vault.py` — comprehensive tests using `tmp_vault` fixture
- [x] Extend `.vscode/tasks.json`:
  - `test: vault` — `python -m pytest monocle/tests/test_vault.py -x --tb=short -q`

**Acceptance Criteria:**
- [x] Atomic writes: temp file created in system tempdir (not vault); final file written via `os.replace`
- [x] Versioning: writing an existing note creates `.versions/{path}/{updated_at}.md`
- [x] Soft-delete: deleted note appears in `.trash/`; original path is absent
- [x] Path traversal: `read_note("../../.env")` raises `403` (not a file error)
- [x] Mtime conflict: `write_note(path, note, if_mtime=stale_ts)` raises `409`
- [x] Schema normalisation: note with no `type` field reads back with `type: "other"`
- [x] `parse_links_field` normalises plain strings `"Note Name"` and dicts `{target: "..."}` both into `LinkRef` objects
- [x] `uv run python -m pytest monocle/tests/test_vault.py -x --tb=short -q` passes (88 tests)

---

### M4: Index Layer — ChromaDB + MemoryIndex

**Goal:** IndexLayer abstraction with a ChromaDB production implementation and an in-memory test fake that requires no embeddings.

**Deliverables:**
- [x] `monocle/index/base.py` — `IndexLayer` ABC: `upsert_chunks`, `delete_file`, `search`, `get_stats`, `delete_all`
- [x] `monocle/index/memory.py` — `MemoryIndex(IndexLayer)` — in-memory dict, no embeddings, substring search. **Used only in tests.**
- [x] `monocle/index/chroma.py` — `ChromaIndex(IndexLayer)` wrapping `chromadb.PersistentClient`. Collection uses `cosine` space. Validates `embed_dimensions` against existing collection on startup; raises `DimensionMismatch` on mismatch.
- [x] `monocle/index/__init__.py` — `get_index(settings) -> IndexLayer` factory
- [x] `monocle/tests/test_index.py` — parametrized tests (`@pytest.mark.parametrize`) against both `MemoryIndex` and `ChromaIndex` (real ChromaIndex via fake in-memory ChromaDB client)
- [x] Extend `.vscode/tasks.json`:
  - `test: index` — `uv run python -m pytest monocle/tests/test_index.py -x --tb=short -q`

**Acceptance Criteria:**
- [x] `MemoryIndex` and `ChromaIndex` both pass identical parametrized test cases
- [x] `ChromaIndex` raises `DimensionMismatch` if `embed_dimensions` from config doesn't match existing collection
- [x] `delete_file(path)` removes all chunks for that file path
- [x] `search` respects `type`, `domain`, `source` metadata filters
- [x] `uv run python -m pytest monocle/tests/test_index.py -x --tb=short -q` passes

---

### M5: Inbox Watcher & Scheduled Re-Index

**Goal:** Inbox file watcher integration (Phase 1: async task in unified process), scheduled full-vault re-indexing, chunk utility, and foundation for optional standalone processes in Phase 3.

**Deliverables:**
- [x] `monocle/ingest/chunker.py` — `chunk_text(text, chunk_size=512, overlap=64) -> list[str]` using `tiktoken cl100k_base`
- [x] `monocle/watcher.py` — `InboxWatcher` class + `ReindexQueue`:
  - `watchdog.Observer` on `vault/inbox/` only (not recursive into subdirs)
  - 2-second debounce per file path *(inbox watcher context only — prevents double-trigger on multi-write saves to the inbox; distinct from the editor-save coalescing idle window, which is 10 seconds per file and is wired into PUT/PATCH routes in M8 per FR-WTCH-04a)*
  - On new file: calls `IngestPipeline.run(request)` directly (in-process for testability and dev mode)
  - Mode (Phase 1): integrated as async task in `main.py` lifespan; spins in an executor thread
  - Mode (Phase 3+ optional): can run as a standalone subprocess if `server.separate_processes: true` (future ProcessManager implementation)
  - On success: file relocated to vault by pipeline (pipeline writes processed note to main vault)
  - On failure: writes `.error.md` sidecar alongside the source file
  - `start()` / `stop()` / `status() -> dict` interface designed for future ProcessManager (currently unused in Phase 1)
  - `ReindexQueue` — asyncio-based per-file coalescing queue; `push(file_path)` schedules a background re-index with a 10-second idle window per file (multiple pushes for the same file within the window collapse into one re-index job); used by PUT/PATCH route handlers (M8) and the ingest pipeline (M7)
- [x] `monocle/agents/reindex.py` — `ReindexAgent`:
  - `run(vault, index, force=False)` — scans all `.md` files in vault; compares frontmatter `updated` to ChromaDB `updated_at` metadata; re-embeds only changed files (`force` clears all first)
  - `startup_check(vault, index)` — triggers full re-index if `index.get_stats().total_chunks == 0` and vault has notes; sets `health.status = "indexing"` during this
- [x] `monocle/agents/scheduler.py` — APScheduler setup for scheduled tasks (Phase 1: integrated in main process lifespan)
- [x] `monocle/tests/test_watcher.py` — mock filesystem events; verify:
  - New file in inbox triggers exactly one ingest call (with 2s debounce)
  - Failed ingest writes `.error.md` sidecar
  - Files outside inbox (e.g., `vault/people/`) do NOT trigger the watcher
- [x] `monocle/tests/test_reindex.py` — mock vault + `MemoryIndex`; assert stale-detection logic and `--force` full re-index
- [x] Extend `.vscode/tasks.json`:
  - `test: watcher` — `python -m pytest monocle/tests/test_watcher.py monocle/tests/test_reindex.py -x --tb=short -q`

**Acceptance Criteria:**
- [x] Creating a `.md` file in `vault/inbox/` triggers exactly one ingest call (two rapid saves = one call)
- [x] `ReindexQueue.push(path)` called multiple times for the same `file_path` within the 10-second idle window results in exactly one background re-index job (coalescing verified via mock)
- [x] A failed ingest leaves a `.error.md` sidecar adjacent to the source file
- [x] Files in `vault/people/`, `vault/work/` (outside inbox) produce no watcher events
- [x] Watcher integration in main process: log prefixed `[WATCHER]`; stops cleanly on app shutdown
- [x] `ReindexAgent.run()` only re-embeds notes where frontmatter `updated` > ChromaDB `updated_at`
- [x] `ReindexAgent.run(force=True)` re-embeds all notes regardless
- [x] `startup_check` triggers full re-index when index is empty; health reports `"indexing"`
- [x] APScheduler runs weekly_summary and re-index crons; scheduled tasks execution is logged
- [x] `uv run python -m pytest monocle/tests/test_watcher.py monocle/tests/test_reindex.py -x --tb=short -q` passes

---

### M6: AI Provider Abstraction

**Goal:** `AIProvider` ABC and `OllamaProvider`. Resolve SPIKE-1 (Whisper audio).

**Deliverables:**
- [x] `monocle/ai/base.py` — `AIProvider` ABC:
  - `embed(text: str) -> list[float]`
  - `embed_batch(texts: list[str]) -> list[list[float]]`
  - `chat(messages: list[dict], stream: bool) -> str | AsyncIterator[str]`
  - `transcribe(audio_bytes: bytes, mime_type: str) -> str`
  - `extract_note_metadata(text: str, template: str) -> NoteMetadata`
- [x] `monocle/ai/ollama_provider.py` — `OllamaProvider(AIProvider)` using `ollama.AsyncClient`. Auto-pulls model on first use if not found.
- [x] `monocle/ai/foundry_local_provider.py` — `FoundryLocalProvider(AIProvider)` using OpenAI-compatible HTTP API
- [x] `monocle/ai/azure_provider.py` — `AzureOpenAIProvider(AIProvider)` using `openai.AzureOpenAI`
- [x] `monocle/ai/__init__.py` — `get_provider(settings) -> AIProvider` factory
- [x] Instrument all `AIProvider` method implementations with OTel spans and metrics using `telemetry.span()` / `telemetry.timed()`: each of `embed`, `embed_batch`, `chat`, `transcribe`, `extract_note_metadata` creates a child span (attributes: `ai.provider`, `ai.model`) and records duration into the corresponding histogram (`ai.embed_duration`, `ai.chat_duration`, `ai.transcribe_duration`). `opentelemetry-instrumentation-httpx` auto-instruments the underlying HTTP calls to Ollama/Azure.
- [x] **SPIKE-1 resolution:** Run validation; record outcome in `## Technical Spikes` above
- [x] `monocle/tests/test_ai.py` — mock-based unit tests (mock `httpx`/`ollama` client). Integration tests behind `@pytest.mark.integration` (skipped by default).
- [x] Extend `.vscode/tasks.json`:
  - `test: ai` — `python -m pytest monocle/tests/test_ai.py -x --tb=short -q` (skips `@pytest.mark.integration`)

**Acceptance Criteria:**
- [x] Factory selects correct provider based on `settings.ai.provider`
- [x] `extract_note_metadata` returns complete `NoteMetadata` with all required fields
- [x] Mock-based unit tests pass; no live Ollama required
- [x] SPIKE-1 outcome recorded in `## Technical Spikes`
- [x] `uv run python -m pytest monocle/tests/test_ai.py -x --tb=short -q` passes (skips `@pytest.mark.integration`)

---

### M7: Ingest Pipeline & Plugin Registry

**Goal:** Full ingest pipeline with `IngestPlugin` ABC, plugin registry, and the three built-in plugins. Deterministic confidence scoring (no LLM call required).

**Deliverables:**
- [ ] `monocle/ingest/plugin.py` — `IngestPlugin` ABC with `source_id: ClassVar[str]`, `source_label: ClassVar[str]`, `can_handle(cls, request) -> bool`, `extract(request) -> str`; `IngestPluginRegistry` singleton
- [ ] `monocle/ingest/plugins/text_plugin.py` — `TextPlugin`
- [ ] `monocle/ingest/plugins/audio_plugin.py` — `AudioPlugin`
- [ ] `monocle/ingest/plugins/teams_plugin.py` — `TeamsPlugin`
- [ ] `monocle/agents/routing.py` — `RoutingAgent` class:
  - `route(text, template_hint) -> RoutingDecision`
  - Checks each template’s `sentence_starters` list first (synchronous, no LLM call)
  - Falls back to `AIProvider.chat` with `prompts/routing.md` system prompt for structured JSON response
  - Returns `RoutingDecision(template, confidence, reasoning, sentence_starter_matched)`
- [ ] `monocle/vault/templates/*.yaml` — add `sentence_starters: [...]` list to each of the 10 template schemas
- [ ] `monocle/ingest/__init__.py` — `IngestPipeline` class with `run(request) -> tuple[Note, IngestConfidence]` (steps per Architecture Quick Reference); integrates `RoutingAgent` in step 3
- [ ] Wrap each of the 8 ingest pipeline steps in `telemetry.span(f"ingest.step.{n}", ...)` child spans (parent span: `ingest.pipeline`); record `ingest.step_duration` histogram per step and `ingest.pipeline_duration` at the end. Emit `ingest.notes_total` counter on success; `ingest.failures_total` counter on failure (attribute: `step=N`).
- [ ] `monocle/ingest/confidence.py` — `score_confidence(note: Note, routing_confidence: float, body_embedding: list[float], vault: VaultLayer) -> IngestConfidence` implementing the deterministic formula below. **`body_embedding` is passed in from the re-index step (step 6) — no additional embed call is made.**
- [ ] **Deterministic Confidence Scoring (implemented in `monocle/ingest/confidence.py`):**
  - `score_confidence(note) -> IngestConfidence` computes confidence as: `0.35*template_match + 0.30*metadata_coverage + 0.20*tag_plausibility + 0.15*entity_match`
  - Four components: (1) `template_match` = routing agent confidence, (2) `metadata_coverage` = populated_fields / required_fields, (3) `tag_plausibility` = cosine similarity of tag embeddings to body embedding (or 1.0 if no tags), (4) `entity_match` = found_people_with_notes / max(found_people, 1)
  - Weights configurable via `config.yaml` `review.confidence_weights`; **no LLM call required** (halves ingest latency)
  - Compute `review_status` and approval metadata as follows:
    - If `review.auto_approve_threshold_pct == 0`, set `review_status: pending`
    - If `review.auto_approve_threshold_pct > 0` and `confidence * 100 >= review.auto_approve_threshold_pct`, set `review_status: approved`, `approval_mode: auto`, `approved_by: "system:auto"`, `approved_at: <now>`
    - Otherwise set `review_status: pending`
- [ ] Duplicate detection: compute semantic similarity (cosine) between note body embedding and last 7 days of note embeddings in index; return advisory `similar_note_detected` flag if similarity > 0.95; **no automatic dedup** (user confirms via `allow_duplicate=true`)
- [ ] Failed-ingest registry: persist enough metadata to drive a UI list and retry flow for `.error.md` sidecars. **Persistence mechanism: `data/failed_ingests.json`** — a JSON array written by the pipeline whenever a sidecar is created, updated on retry/dismiss. Uses Python stdlib `json` only (no new dependencies). Loaded into memory at startup; written atomically (write temp + rename) on each change.
- [ ] `monocle/prompts.py` — `load_prompt(name: str) -> str` helper: loads `prompts/local/<name>.md` if it exists, otherwise `prompts/<name>.md`; strips YAML frontmatter and returns prompt body
- [ ] Default prompt files (`prompts/routing.md`, `prompts/extract.md`) written with working content (not stubs); `prompts/confidence.md` **no longer needed** (replaced by deterministic scoring)
- [ ] `monocle/tests/test_ingest.py` — mock `AIProvider` and `VaultLayer`; assert correct frontmatter for sample inputs; assert sentence-starter fast path bypasses LLM routing call; assert deterministic confidence formula
- [ ] Extend `.vscode/tasks.json`:
  - `test: ingest` — `python -m pytest monocle/tests/test_ingest.py -x --tb=short -q`

**Acceptance Criteria:**
- [x] Text ingest produces a valid `.md` file with correct frontmatter, review metadata, and auto-approval behaviour based on `review.auto_approve_threshold_pct`
- [x] Audio ingest calls `AIProvider.transcribe`; resulting note has `source: "voice"`
- [x] Input beginning with a sentence starter (e.g., `"I decided to..."`) routes to the `decision` template WITHOUT making an LLM call
- [x] Falls back to `blank` template when routing confidence < 0.6
- [x] A new plugin can be registered without touching pipeline code: `registry.register(MyPlugin())`
- [x] Plugin `can_handle` is tested in registration order; first match wins
- [x] Ingest failure on step 3–5 writes a `.error.md` sidecar (verified with a mock that raises during routing)
- [x] Deterministic confidence score is computed and written to note frontmatter; **no LLM scoring agent call made**
- [x] Auto-approved notes include `approval_mode: auto`, `approved_by: "system:auto"`, and `approved_at`; manually approved notes later record `approval_mode: manual`
- [x] Re-ingesting a note with semantic similarity > 0.95 to existing note returns advisory flag; user can override with `allow_duplicate=true`
- [x] Failed-ingest registry entry is created alongside `.error.md` and cleared after a successful retry
- [x] `uv run python -m pytest monocle/tests/test_ingest.py -x --tb=short -q` passes

---

### M8: REST API Wiring — Core

**Goal:** Replace 501 stubs with real implementations for notes, search, ingest, transcribe, health, and stats. The API must be fully functional with an Ollama model running.

**Deliverables:**
- [ ] `monocle/main.py` lifespan: start `VaultWatcher`, initialise `AIProvider` + `IndexLayer` singletons, trigger startup re-index if needed; call `configure_telemetry(settings)` as the **first** lifespan action (before any subsystem starts)
- [ ] `routers/health.py` — wired to real `watcher.status`, `ai_reachable` (ping provider), `index.get_stats()`; add `telemetry_endpoint` field to the health response (the configured OTLP endpoint, or `null` when disabled) so operators can confirm where traces are going
- [ ] `routers/notes.py` — all CRUD routes wired to `VaultLayer`; `GET /api/notes` is paginated; `PUT` and `PATCH` handlers push `file_path` to `ReindexQueue` (defined in M5) after a successful write so editor saves enqueue coalesced background re-indexing without blocking the response (FR-WTCH-04a)
- [ ] `routers/search.py` — semantic search: `AIProvider.embed` + `IndexLayer.search`; keyword: `VaultLayer` text scan
- [ ] `routers/ingest.py` — `POST /api/ingest` wired to `IngestPipeline`; `POST /api/ingest/stream` emits `text/event-stream` SSE progress events during pipeline steps
- [ ] `routers/ingest_failures.py` — wire `GET /api/ingest/failures`, `POST /api/ingest/failures/retry`, and `DELETE /api/ingest/failures/{id}` (stubs registered in M2)
- [ ] `routers/transcribe.py` — wired to `AIProvider.transcribe`
- [ ] `routers/stats.py` — wired to `IndexLayer.get_stats` + `VaultLayer`; include `latency_p50_ms` and `latency_p95_ms` per operation type as fields directly on `BrainStats` (sourced from OTel histogram snapshots exposed via the metrics SDK). Keeping latency in `GET /api/stats` avoids a second HTTP round-trip for the stats screen; the payload overhead is negligible for a local personal tool.
- [ ] `monocle/tests/test_api.py` — integration tests via `TestClient` using `MemoryIndex` + mock `AIProvider`
- [ ] `monocle/tests/test_security.py` — path traversal, file size limits, 409 conflict detection, CORS headers, rate limiting
- [ ] Extend `.vscode/tasks.json`:
  - `test: api` — `python -m pytest monocle/tests/test_api.py -x --tb=short -q`
  - `test: security` — `python -m pytest monocle/tests/test_security.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] `POST /api/ingest {"content": "Met with Sarah today", "source": "web"}` → 201 with a `Note` object
- [ ] Ingesting content with > 0.95 cosine similarity to a note from the last 7 days returns 201 with `similar_note_detected: true` and `similar_note_path`; **no automatic deduplication** — user forces creation with `allow_duplicate: true` in the request body
- [ ] `GET /api/notes?sort=updated&limit=10&offset=0` → paginated response with `total` and `items`
- [ ] `GET /api/ingest/failures` returns `.error.md`-backed failures in newest-first order
- [ ] `DELETE /api/ingest/failures/{id}` removes the failed-ingest record from the list; the underlying `.error.md` file is NOT deleted
- [ ] `PUT /api/notes/test.md` with stale `if_mtime` → 409
- [ ] Rapid consecutive `PUT /api/notes/{path}` calls within 10 seconds result in exactly one background re-index job for that file (coalescing via `ReindexQueue`)
- [ ] `GET /api/notes/../../.env` → 403
- [ ] `POST /api/ingest` with `audio_bytes` > 25 MB → 422
- [ ] `GET /api/health` → `{"status": "ready", "ai_reachable": true, "telemetry_endpoint": "http://localhost:4317", ...}` when provider is live
- [ ] `uv run python -m pytest monocle/tests/test_api.py monocle/tests/test_security.py -x --tb=short -q` passes

---

### M9: Graph Layer

**Goal:** Ego-graph builder with all four edge sources, caching, and the fully wired `GET /api/graph` endpoint.

**Deliverables:**
- [ ] `monocle/graph.py` — `GraphBuilder` class:
  - `build(focus=None, max_degree=3, types=None, n=500) -> GraphData`
  - Reads all notes via `VaultLayer`; extracts edges from: (1) structured `links` frontmatter, (2) body `[[wikilinks]]`, (3) `people` co-mentions, (4) shared `tags`
  - Computes `degree` via BFS from `focus` node; `degree=null` in full-vault mode
  - In-memory cache keyed on `(focus, max_degree, types, n)`; invalidated by watcher events
- [ ] `routers/graph.py` — wired to `GraphBuilder`
- [ ] `routers/notes.py` — wire `GET /api/notes/{file_path:path}/backlinks` (stub registered in M2): scans all vault notes for incoming links to the target using the same edge-extraction logic as `GraphBuilder`; returns `source`, `relation`, and `context` fields per FR-API-12a
- [ ] `monocle/tests/test_graph.py` — use `tmp_vault` fixture; assert known node/edge structure
- [ ] Extend `.vscode/tasks.json`:
  - `test: graph` — `python -m pytest monocle/tests/test_graph.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] `GET /api/graph?focus=people/sarah.md&max_degree=2` returns Sarah at degree 0, co-mentioned notes at degree 1
- [ ] Structured `links` frontmatter edges carry `relation` and `metadata` in the response
- [ ] `types=person` excludes note and tag nodes from response
- [ ] Cache hit on second identical request; cache invalidated after a vault file is modified
- [ ] `GET /api/notes/people/sarah.md/backlinks` returns all notes that link to `sarah.md` via structured links, wikilinks, or `people` co-mention
- [ ] `uv run python -m pytest monocle/tests/test_graph.py -x --tb=short -q` passes

---

### M10: Agent Framework & Chat API

**Goal:** Microsoft Agent Framework integration for multi-step chat. SSE streaming chat endpoint. Resolve SPIKE-3.

**Deliverables:**
- [ ] `monocle/agents/tools.py` — 7 `@tool` decorated agent tools: `search_vault`, `read_note`, `write_note`, `create_note`, `get_stats`, `list_notes`, `get_person_graph`
- [ ] `monocle/agents/__init__.py` — `create_chat_agent(provider, vault, index) -> Agent`; agent uses all 7 tools; calls `agent_framework.observability.configure_otel_providers(vs_code_extension_port=4317, enable_sensitive_data=settings.telemetry.enable_sensitive_data)` once at construction time so agent spans and prompt/completion data flow into the same AI Toolkit trace as the surrounding FastAPI request span
- [ ] `routers/chat.py` — `POST /api/chat` streaming SSE; emits all event types from Architecture Quick Reference; handles `session_id` (echo back only — sessions stored client-side); records `chat.ttft` histogram at first `token` event and `chat.total_duration` histogram at `done` event
- [ ] Tool error handling: each tool wraps its body in `try/except`; failures emit `tool_error` event and return a structured error to the agent so it can continue
- [ ] **SPIKE-3 resolution:** Validate streaming latency. Record outcome in `## Technical Spikes`.
- [ ] `monocle/tests/test_agents.py` — mock agent; assert SSE event sequence
- [ ] Extend `.vscode/tasks.json`:
  - `test: agents` — `python -m pytest monocle/tests/test_agents.py -x --tb=short -q`

**Acceptance Criteria:**
- [ ] `POST /api/chat {"messages": [{"role": "user", "content": "What did I discuss with Sarah?"}], "session_id": "abc"}` returns `text/event-stream`
- [ ] Stream contains `token` events followed by `done` event
- [ ] Tool failure emits `tool_error` event; stream continues and agent provides a response
- [ ] `note_created` event emitted when agent creates a note during conversation
- [ ] SPIKE-3 outcome recorded
- [ ] `chat.ttft` histogram records time from POST to first `token` event; `chat.total_duration` records time to `done` event; both visible in AI Toolkit trace view
- [ ] `uv run python -m pytest monocle/tests/test_agents.py -x --tb=short -q` passes

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
