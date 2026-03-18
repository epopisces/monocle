# GitHub Copilot Action Log

Record summarized actions taken by GitHub Copilot agents. Agents must append or merge into to this file at the end of every session under a `## YYYY-MM-DD` heading, using a `### <Model Name>` subheading. Use a new heading per calendar day and subheading per model.  Like actions on the same day by the same model can be summarized together.

---

## 2026-03-14 

### Claude Sonnet 4.6
- Cross-referenced Gnomish design docs against Monocle docs and identified 8 improvements worth porting
- Updated `docs/ui-design.md`: added weight-driven edge visual encoding spec (thickness 0.5–5 px, opacity 30–100 %), typed edge color table (structured / wikilink / co-mention), Export PNG control, modifier-key sidebar navigation (`Ctrl+Click`, `Shift+Click`), three-tier backlinks panel description, multi-pane state reservation note in Application Shell, review-pending amber pulse on graph nodes, and inline text-selection mini-toolbar for expanded graph nodes
- Updated `docs/srs.md`: expanded FR-WEB-07 with all graph visual requirements (edge encoding, edge types, node pulse, node expand + text selection, export); added `edge_type` field to FR-API-13 graph edge response and updated explanation paragraph; added `link_type` field and three-tier description to FR-API-12a backlinks response

## 2026-03-15 

### Claude Sonnet 4.6
- Created `.github/copilot-instructions.md` — synthesized architecture, key abstractions, ingest pipeline, frontmatter schema, test commands, and conventions from build-plan, SRS, PRD, and UI Design docs
- Created `GHI-ACTION-LOG.md` — seeded with 2026-03-14 entry from README; established as the canonical agent action log going forward
- Standardized all Python/tool invocations in `docs/build-plan.md` and `.github/copilot-instructions.md` to use `uv run` (e.g., `uv run python -m pytest`, `uv run uvicorn`); updated M1 tasks.json deliverable from `pip install -e .[dev]` to `uv sync`; updated `pyproject.toml` note to use `requires-python` (uv standard)
- **Executed M1 — Foundation & Project Skeleton (COMPLETE)**
  - Created `pyproject.toml` with 30+ backend dependencies, `[dependency-groups]` dev group, `[tool.uv] prerelease = "allow"` (required for agent-framework pre-release packages), `[tool.pytest.ini_options]`
  - Created all `monocle/` subdirectory `__init__.py` files: ai/, index/, vault/, ingest/, ingest/plugins/, agents/, routers/, tests/
  - Created `monocle/config.py` — Pydantic v2 Settings, YAML + .env loading, auto-copy config.yaml.example on first run
  - Created `monocle/models.py` — all 15+ shared Pydantic v2 models including `IngestRequest` with `allow_duplicate: bool = False`
  - Created `monocle/telemetry.py` — full OTel wiring with no-op fallbacks for all signals
  - Created `monocle/watcher.py`, `monocle/process_manager.py`, `monocle/agents/routing.py`, `monocle/agents/reindex.py` — stubs
  - Created `monocle/cli.py`, `monocle/__main__.py` — Typer app with serve/dev/reindex/pull-models/export/versions commands
  - Created `config.yaml.example`, `.env.example`
  - Created `vault/` skeleton: inbox/, people/, work/, technologies/, projects/, summaries/, .templates/, .obsidianignore
  - Created `prompts/routing.md`, `prompts/extract.md`, `prompts/weekly_review.md`, `prompts/confidence.md`, `prompts/local/README.md`
  - Created `monocle/tests/conftest.py` (tmp_vault + memory_index fixtures), `monocle/tests/test_imports.py` (9 smoke tests)
  - Created `frontend/` scaffold: package.json, vite.config.ts, tsconfig.json, vitest.config.ts, index.html, src/main.tsx, src/App.tsx, src/App.test.tsx, src/test-setup.ts
  - Created `.vscode/tasks.json`, `.vscode/launch.json`
  - Fixed `config.py`: removed stray `pydantic_settings` import (not in deps); fixed `pyproject.toml` to use `[dependency-groups]` (eliminates deprecation warning); added `[tool.uv] prerelease = "allow"` for agent-framework pre-release packages
  - `uv sync` → 148 packages resolved (EXIT 0); `uv run python -m pytest` → 9 passed (EXIT 0); `npm run test -- --run` → 1 passed (EXIT 0)
  - Updated `docs/build-plan.md`: all M1 deliverables and acceptance criteria marked `[x]`; Active Milestone → M2; M1 → COMPLETE in tracker
- **Executed M2 — API Skeleton (COMPLETE)**
  - Created `monocle/main.py`: FastAPI app with CORS (prod + dev_cors Vite origins), OTel FastAPI instrumentation, slowapi rate limiting, static file mount (noop if frontend/dist absent), lifespan hook, all 13 routers registered
  - Created `monocle/rate_limit.py`: shared `Limiter` instance to avoid circular imports between `main.py` and routers
  - Created 13 router files: `health.py` (200), `notes.py` (8 stubs), `search.py` (2 stubs), `ingest.py` (2 stubs, 30/min limit), `ingest_failures.py` (3 stubs), `transcribe.py` (1 stub, 30/min limit), `graph.py`, `stats.py`, `chat.py` (60/min limit), `agents.py`, `review.py`, `settings.py`, `teams.py`
  - Created `monocle/tests/test_api.py`: 31 TestClient tests — health returns 200, all 29 stubs return 501, none return 404/500
  - Exported `openapi.json`: 30 operations across 26 paths
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 40 passed (9 M1 + 31 M2), EXIT 0
  - Updated `docs/build-plan.md`: all M2 deliverables and acceptance criteria marked `[x]`; Active Milestone → M3; M2 → COMPLETE in tracker

## 2026-03-16

### Claude Sonnet 4.6
- **Executed M3 — Vault Layer (COMPLETE)**
  - Created `monocle/vault/normalise.py`: `normalise_frontmatter(fm)` applies all schema defaults (type→"other", lists→[], confidence→1.0, review_status→"approved", approval fields→null)
  - Created `monocle/vault/wikilinks.py`: `parse_wikilinks(body)` regex extraction of `[[...]]` targets; `parse_links_field(links)` normalises plain strings and dicts to `LinkRef` objects; `resolve_wikilink(name, vault_root)` case-insensitive file scan skipping hidden dirs
  - Created `monocle/vault/templates/__init__.py` + 10 YAML schemas: person, decision, project, meeting, idea, observation, reference, action_item, blank, weekly_summary — each with `sentence_starters`, `fields`, `default_folder`, `note_type`
  - Created `monocle/vault/__init__.py`: full `VaultLayer` implementation — `list_notes` (paginated, filtered), `read_note` (frontmatter parse + normalise), `write_note` (atomic via tempfile.mkstemp + os.replace, shadow versioning, mtime 409), `patch_frontmatter` (FM-only update preserving body), `delete_note` (soft-delete to .trash/), `move_note`, `create_from_template` (slug derivation, in-memory, no disk write), `resolve_wikilink`, `list_versions`, `restore_version`, `list_templates`; `NoteNotFound` (HTTP 404) and path traversal protection (HTTP 403) throughout
  - Created `monocle/tests/test_vault.py`: 88 tests covering all acceptance criteria — normalise_frontmatter defaults, parse_wikilinks, parse_links_field, resolve_wikilink, VaultLayer CRUD, atomic writes, versioning, soft-delete, path traversal 403, mtime conflict 409, create_from_template, list_notes pagination/filtering, version round-trip
  - Added `test: vault` task to `.vscode/tasks.json`
  - `uv run python -m pytest monocle/tests/test_vault.py -x --tb=short -q` → 88 passed, EXIT 0
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → 128 passed (all tests), EXIT 0
  - Updated `docs/build-plan.md`: all M3 deliverables and acceptance criteria marked `[x]`; Active Milestone → M4; M3 → COMPLETE in tracker

### Claude Haiku 4.5
- **Post-M3 Bug Fixes & Hardening (from PR review feedback)**
  - Fixed **Bug 1 (NoteRef missing created field + list_notes sort="created" copy-paste)**: Added `created: datetime | None = None` field to `NoteRef` model in `monocle/models.py`; fixed `_sort_value()` in `monocle/vault/__init__.py` to use `ref.created` when `sort_key == "created"`; `list_notes` now passes `created` from `note.metadata.created` to `NoteRef` constructor
  - Fixed **Bug 2 (list_versions unsafe path usage)**: Changed `list_versions(file_path)` to resolve and validate path before using in `_version_dir()` — now uses `self._safe_resolve(file_path)` + `self._to_relative()` to ensure safe, normalized vault-relative path (prevents directory escaping)
  - Fixed **Bug 3 (restore_version timestamp injection vulnerability)**: Added regex validation of timestamp format (`^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}Z$`); added `try/except version_file.relative_to(version_dir)` to catch path escape attempts with `..` or `/` sequences; raises HTTP 403 on invalid format or escape attempt
  - Fixed **Wikilink resolution asymmetry (from PR review)**: Made `resolve_wikilink()` bidirectional by slugifying both file stem and input name; now compares all 4 combinations (stem_lower, stem_slug, name_lower, name_slug); added tests `test_reverse_slug_match` and `test_reverse_slug_match_case_insensitive`
  - Fixed **Template field loss (from code review)**: `create_from_template()` now sets `"template": schema_name` in frontmatter dict; template choice persists through write/read cycle; added round-trip tests `test_template_preserved_on_roundtrip` and `test_decision_template_preserved`
  - Added security & correctness tests: `test_restore_version_invalid_timestamp_format_raises_403`, `test_restore_version_path_traversal_attempt_raises_403`, `test_restore_version_absolute_path_safe`, `test_sort_by_created_uses_created_not_updated`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **136 passed** (88 vault + 40 M1/M2 + 4 fix tests + 4 additional security tests), EXIT 0

- **Executed M4 — Index Layer (COMPLETE)**
  - Created `monocle/index/base.py`: `IndexLayer` ABC with five abstract methods (`upsert_chunks`, `delete_file`, `search`, `get_stats`, `delete_all`); `DimensionMismatch` exception class; `search()` includes `query_text: str = ""` optional param (used by `MemoryIndex` for substring matching; ignored by `ChromaIndex`)
  - Created `monocle/index/memory.py`: `MemoryIndex(IndexLayer)` — dict-backed in-memory index, substring search on `query_text`, metadata equality filters, stable sort; no embeddings computed; tests-only
  - Created `monocle/index/chroma.py`: `ChromaIndex(IndexLayer)` wrapping `chromadb.PersistentClient` with cosine HNSW collection; `_open_collection()` validates `embed_dimensions` from stored collection metadata on startup (raises `DimensionMismatch` on mismatch); OTel metric instruments `index.search_duration` and `index.upsert_duration` histograms; scalar metadata filtering via `_build_where()` (supports single-key and multi-key `$and` clauses); cosine distance → similarity conversion
  - Created `monocle/index/__init__.py`: `get_index(settings) -> IndexLayer` factory; re-exports `IndexLayer` and `DimensionMismatch`
  - Created `monocle/tests/test_index.py`: 43 tests including parametrized suite (memory + chroma), dimension mismatch, factory, and MemoryIndex-specific tests; ChromaDB `PersistentClient` replaced with `_FakeChromaClient`/`_FakeCollection` (pure-Python, cosine distance, where-clause evaluation) via `monkeypatch` to work around ChromaDB Rust-backend access-violation on this Windows + Python 3.14 environment
  - Added `test: index` task to `.vscode/tasks.json`
  - Created `.python-version` pinning to Python 3.14 to align local development and CI with the target runtime for this stack
  - `uv run python -m pytest monocle/tests/test_index.py -x --tb=short -q` → 43 passed, EXIT 0
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **179 passed** (all tests), EXIT 0
  - Updated `docs/build-plan.md`: all M4 deliverables and acceptance criteria marked `[x]`; Active Milestone → M5; M4 → COMPLETE in tracker
## 2026-03-17

### Claude Sonnet 4.6
- Added `packaging` to the `dev` dependency group in `pyproject.toml` so `scripts/check_requires_python.py` does not crash with `ModuleNotFoundError` in environments where `packaging` is not pulled in transitively
- Added per-chunk embedding dimension validation to `ChromaIndex.upsert_chunks()`: raises `ValueError` when a chunk's embedding length is empty or does not match `settings.ai.embed_dimensions`; added two covering tests → 181 passed, EXIT 0
- Added query embedding validation to `ChromaIndex.search()`: raises `ValueError` on wrong/empty vector length before ChromaDB call; added two covering tests → 183 passed, EXIT 0
- Audited M1–M4 test coverage for gaps; added 12 missing tests across `test_index.py`, `test_vault.py`, `test_imports.py`:
  - `TestChromaIndexStats` — `backend == "chroma"` and `collection_name` field values (3 tests)
  - `test_destination_path_traversal_raises_403` in `TestVaultLayerMoveNote` — destination path traversal was documented but untested
  - `test_sort_by_title_ascending` and `test_noteref_review_status_propagated` in `TestVaultLayerListNotes`
  - `test_server_config_invalid_host_raises` and `test_server_config_valid_hosts_accepted` (parametrized) for `ServerConfig.validate_host`
  - `test_inbox_watcher_stub_running_flag` and `test_reindex_queue_stub_does_not_raise` for M1 stubs
  - → 195 passed, EXIT 0
- Fixed `DeprecationWarning: datetime.datetime.utcnow()` in `test_vault.py` and `conftest.py`; replaced with `datetime.datetime.now(datetime.timezone.utc)` — warnings eliminated
- SPIKE-4 resolved: Re-validated ChromaDB 1.5.5 Rust `PersistentClient` on Python 3.14.3 — full smoke test (upsert, query, delete) passes without workaround; investigated [chroma-core/chroma#5937](https://github.com/chroma-core/chroma/issues/5937) `SegmentAPI` workaround (not needed); updated `.python-version` from `3.12` → `3.14`; 195 tests pass on Python 3.14.3; updated SPIKE-4 in `docs/build-plan.md` as RESOLVED
- **Executed M5 — File Watcher & Re-index Queue (COMPLETE)**
  - Created `monocle/ingest/chunker.py`: `chunk_text(text, chunk_size=512, overlap=64)` using tiktoken `cl100k_base`; handles empty text, overlap validation
  - Implemented `monocle/watcher.py` (replaced stub): `ReindexQueue` — asyncio per-file coalescing queue (10-second idle window), thread-safe `push()` via `loop.call_soon_threadsafe`; `InboxWatcher` — watchdog.Observer (non-recursive) on inbox dir, 2-second per-file debounce via `threading.Timer`, `_InboxEventHandler` with dynamic watchdog base-class inheritance, `.error.md` sidecar writing on failure; `_write_error_sidecar()` helper
  - Implemented `monocle/agents/reindex.py` (replaced stub): `ReindexAgent` with `run(vault, index, force=False)` (stale detection via `get_file_timestamps()`, force clears before re-index), `startup_check(vault, index)` (triggers full re-index when index empty), `health_status` attribute; `_collect_md_files()` helper (excludes hidden dirs)
  - Created `monocle/agents/scheduler.py`: `MoocleScheduler` wrapping APScheduler `AsyncIOScheduler`; `add_cron_job()` from 5-field cron string; start/stop/status interface
  - Extended `monocle/index/base.py` with `get_file_timestamps() -> dict[str, str]` abstract method; implemented in `MemoryIndex` and `ChromaIndex` (ChromaDB `collection.get()` metadata scan)
  - Updated `monocle/main.py` lifespan: wires VaultLayer, IndexLayer (via factory), ReindexQueue, ReindexAgent, MoocleScheduler (with reindex cron job), InboxWatcher (ingest callback wired in M7), and runs `startup_check` on startup
  - Created `monocle/tests/test_watcher.py`: 17 tests — ReindexQueue coalescing (6), InboxWatcher _on_stable_file logic (3), _InboxEventHandler dispatch+debounce (4), _write_error_sidecar (2), lifecycle (2)
  - Created `monocle/tests/test_reindex.py`: 21 tests — `chunk_text` (6), stale detection (4), force flag (1), startup_check (3), `_collect_md_files` (4), `MemoryIndex.get_file_timestamps` (3)
  - Updated `test_imports.py`: fixed `test_inbox_watcher_stub_running_flag` to use `tmp_path` for real `InboxWatcher` constructor
  - Added `test: watcher` task to `.vscode/tasks.json`
  - `uv run python -m pytest monocle/tests/test_watcher.py monocle/tests/test_reindex.py -x --tb=short -q` → **38 passed**, EXIT 0
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **233 passed** (all tests), EXIT 0
  - Updated `docs/build-plan.md`: all M5 deliverables and acceptance criteria marked `[x]`; Active Milestone → M6; M5 → COMPLETE in tracker
- **M5 post-completion code review — 14 issues resolved (bugs, testing gaps, security)**
  - **Bug fixes (5):**
    - `reindex.py`: added `_normalise_ts()` helper; normalised both sides of the `updated_at` comparison to `Z` format to prevent `+00:00` vs `Z` false-staleness (bug 1)
    - `reindex.py` / `_collect_md_files()`: added `.error.md` suffix exclusion to prevent sidecar files being fed to VaultLayer as regular notes (bug 2)
    - `watcher.py` / `InboxWatcher.status()`: now reads `_timers` under `_timer_lock` to prevent `RuntimeError: dict changed size during iteration` under concurrent timer callbacks (bug 3)
    - `watcher.py` / `ReindexQueue._debounced_reindex()`: added `except Exception` handler that logs callback errors at ERROR level instead of silently swallowing them (bug 4)
    - `agents/scheduler.py`: renamed `MoocleScheduler` → `MonocleScheduler`; added `MoocleScheduler = MonocleScheduler` backward-compat alias; updated `main.py` import/usage (bug 5)
  - **Testing gaps resolved (6):**
    - Created `monocle/tests/test_scheduler.py` (16 tests): lifecycle start/stop, double-stop safety, status() structure, add_cron_job happy path, replace_existing, RuntimeError before start, ValueError on invalid cron, backward-compat alias (gap 6)
    - Added `test_callback_exception_is_logged_not_silenced` to `TestReindexQueue` (gap 7)
    - Added `test_moved_event_uses_dest_path` to `TestInboxEventHandlerDispatch` (gap 8)
    - Added `test_error_sidecar_files_excluded` to `TestCollectMdFiles` (gap 9)
    - Added `TestTimestampNormalisation` class (6 tests): unit tests for `_normalise_ts()` and two integration tests proving Z/+00:00 cross-format equality prevents spurious re-indexes (gap 10)
    - `ingest/chunker.py`: added module-level `_cl100k_enc` cache; tiktoken encoder is now constructed once per process rather than on every `chunk_text()` call (gap 11)
  - **Security hardening (3):**
    - `reindex.py` / `_collect_md_files()`: added `os.path.realpath` + `Path.relative_to()` symlink-traversal guard; paths resolving outside the vault root are skipped with a WARNING log (sec 12)
    - `watcher.py` / `_write_error_sidecar()`: replaced raw string interpolation of the filename into YAML with `yaml.dump()` to prevent YAML injection via filenames containing colons or newlines (sec 13)
    - `watcher.py` / `ReindexQueue.push()`: added docstring trust-boundary note explaining that callers must validate paths against the vault root before enqueueing (sec 14)
  - **Dependency fix:** pinned `apscheduler>=3.10,<4` in `pyproject.toml`; APScheduler v4.0.0a6 (API-incompatible) was resolved; downgraded to v3.11.2
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **254 passed** (all tests), EXIT 0
- **M5 second-pass code review — 4 additional issues resolved**
  - **Bug A — `.error.md` cascade loop (already applied in prior edit pass):** `_InboxEventHandler.dispatch()` now rejects `src_path.endswith(".error.md")` with a combined short-circuit filter, preventing an ingest failure from writing a sidecar that re-triggers a new failing ingest indefinitely
  - **Bug B — vault under hidden parent dir silently empty:** `_collect_md_files()` hidden-dir guard now checks `f.relative_to(root).parts` (vault-relative) instead of `f.parts` (full absolute path), so a vault installed under `~/.config/...` or any `.`-prefixed ancestor is no longer silently treated as empty
  - **Bug C — embed failure aborts entire `run()` batch:** `ReindexAgent.run()` now wraps `await self._reindex_note(...)` in a per-note `try/except` that logs at ERROR and `continue`s; a single failing note no longer raises and aborts re-indexing of all subsequent notes
  - **Smell D — redundant `os.path.basename` (already applied in prior edit pass):** `_write_error_sidecar()` computes `basename` once before building the `fm` dict
  - Added 4 tests: `test_error_sidecar_not_dispatched` (cascade prevention), `test_vault_under_hidden_parent_dir_included` (Bug B), `test_embed_failure_leaves_empty_embedding_run_completes` (Bug C — per-chunk), `test_run_continues_after_per_note_exception` (Bug C — per-note)
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **258 passed** (all tests), EXIT 0- **`watcher.py` — `_fire()` shutdown-race and unobserved-Future fixes**
  - Added `import concurrent.futures`
  - Added `_log_future_exception(future)` module-level done-callback; logs at ERROR on unexpected exception, silently ignores `CancelledError` (clean shutdown)
  - Rewrote `_fire()`: added `loop.is_running()` pre-check (drops event with DEBUG log when loop already stopped); extracts coroutine into local variable before calling `run_coroutine_threadsafe` so it can be `close()`d on `RuntimeError` (avoids `ResourceWarning`); wraps call in `try/except RuntimeError` for TOCTOU gap; attaches `_log_future_exception` as done-callback
  - Added 5 tests in new `TestFireShutdownRaceAndFutureObservation` class: `test_fire_loop_not_running_drops_event`, `test_fire_runtime_error_is_swallowed`, `test_log_future_exception_logs_error`, `test_log_future_exception_ignores_cancelled`, `test_log_future_exception_ignores_success`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **263 passed** (all tests), EXIT 0
- **`watcher.py` — `ReindexQueue.stop()` pending-task fix**
  - Snapshot + clear `_tasks` before cancelling, then `await asyncio.gather(*tasks, return_exceptions=True)` so every `CancelledError` is fully raised and handled before `stop()` returns; eliminates `Task was destroyed but it is pending!` warnings on loop teardown
  - Added `test_stop_awaits_task_cleanup` test: enqueues 3 tasks, calls `stop()`, asserts all tasks are `done()` immediately after `stop()` returns
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **264 passed** (all tests), EXIT 0
- **`chroma.py` — `get_file_timestamps()` paginated load**
  - Added `_GET_PAGE_SIZE = 1_000` module constant
  - Rewrote `get_file_timestamps()` to loop with `collection.get(include=["metadatas"], limit=_GET_PAGE_SIZE, offset=offset)`; loop exits when a batch is smaller than the page size; peak memory is now O(_GET_PAGE_SIZE) instead of O(collection size)
  - Updated `_FakeCollection.get()` in `test_index.py` to accept and apply `limit` / `offset` parameters so the fake faithfully models ChromaDB pagination
  - Added `TestChromaIndexGetFileTimestampsPagination` with two tests: `test_all_files_returned_across_multiple_pages` (page_size=3, 5 files/10 chunks) and `test_exact_page_boundary_returns_all_files` (page_size=4, 4 files/4 chunks — edge case where first page is exactly full)
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **266 passed** (all tests), EXIT 0
- **`reindex.py` — `_reindex_note()` returns `bool`; `run()` count fix**
  - Changed `_reindex_note()` return type `None` → `bool`: returns `True` after upsert, `False` on empty/whitespace-only body (old chunks still deleted)
  - `run()` now gates `reindexed += 1` on the return value; empty-body notes no longer inflate the count or appear in the “N note(s) re-indexed” log line
  - Updated `debug` log in the empty-body path to say “removed existing chunks” (was “skipping”)
  - Fixed `patched_reindex` in `test_run_continues_after_per_note_exception` to `return await original_reindex(...)` so the mock forwards the bool correctly
  - Added `test_empty_body_note_not_counted_as_reindexed`: empty-body note counts as 0, its stale chunk is deleted
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **267 passed** (all tests), EXIT 0
- **`reindex.py` — `_collect_md_files()` dotfile/hidden-dir distinction**
  - Hidden-dir check changed from `rel_parts` to `rel_parts[:-1]` so only *directory* components are tested; dotfiles at any depth (e.g. `.frontmatter.md`, `work/.hidden.md`) are no longer silently excluded
  - Docstring updated to document the dir-only exclusion rule and explicitly note that dotfiles are **not** excluded
  - Added `test_dotfile_at_vault_root_included`: verifies `.hidden-note.md` and `work/.hidden-in-subdir.md` are collected while `.versions/note.md` is still excluded
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **268 passed** (all tests), EXIT 0
- **`reindex.py` — staleness comparison broken for notes without `updated` frontmatter**
  - Without the fix, `note_updated = ""` and `"2026-...Z" >= ""` is always `True`, so any previously-indexed note with no frontmatter timestamp was permanently frozen (never re-indexed on body changes)
  - Skip condition changed from `indexed_updated and indexed_updated >= note_updated` → `indexed_updated and note_updated and indexed_updated >= note_updated`; added DEBUG log for the no-timestamp path
  - Added `test_note_without_updated_frontmatter_always_reindexed`: pre-populates index with a non-empty `updated_at`, writes a note with no `updated` field, asserts `count == 1`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **269 passed** (all tests), EXIT 0
- **`watcher.py` / `main.py` — debounce wired from `settings.vault.debounce_ms`**
  - Added `debounce_s: float | None = None` to `InboxWatcher.__init__()`; when `None`, falls back to `DEBOUNCE_S` class constant (2.0 s) for backward compatibility
  - Instance stores `self._debounce_s`; `start()` passes `self._debounce_s` to `_InboxEventHandler` instead of the class constant
  - `main.py` now passes `debounce_s=cfg.vault.debounce_ms / 1000` at construction time; configuration drift between class constant and user config is impossible
  - `DEBOUNCE_S = 2.0` retained as explicit fallback default and for tests that instantiate `InboxWatcher` without settings
  - Added 2 tests: `test_debounce_s_from_constructor_overrides_class_default` (verifies storage and end-to-end timer firing at custom interval), `test_debounce_s_none_uses_class_default` (verifies `DEBOUNCE_S` fallback)
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **271 passed** (all tests), EXIT 0
- **`reindex.py` / `main.py` � embed_fn=None guard + prepare-then-swap reorder**
  - Root cause: `ReindexAgent()` in `main.py` is constructed without `embed_fn` (M6 not yet built). ChromaIndex rejects `len([]) != 1536` with `ValueError`. `_reindex_note()` previously called `delete_file()` first, then built chunks, then called `upsert_chunks()` � so when `upsert_chunks` raised (every note, on every startup_check or scheduled run), existing index data was silently wiped with nothing to replace it.
  - Fix 1 � Guard in `run()`: At the top of `run()`, before `if force:`, calls `index.get_stats()` to check backend. If `embed_fn is None` and `backend != "memory"`, logs a WARNING and returns 0 immediately. Prevents the delete-everything-fails-nothing cycle for all ChromaDB deployments until M6.
  - Fix 2 � Prepare-then-swap in `_reindex_note()`: All chunks are now fully built (including any embedding calls) before `delete_file()` is called, so chunk-preparation failures cannot corrupt the index.
  - `main.py` annotation: Added 4-line TODO comment above `ReindexAgent()` call noting that `embed_fn=ai_provider.embed` must be wired in M6.
  - Added `TestReindexAgentEmbedGuard` class (4 tests): guard fires for non-memory backend + no embed_fn (returns 0, no delete_file, WARNING emitted); guard fires for force=True too; guard does NOT fire for MemoryIndex + no embed_fn (count=1); guard does NOT fire when embed_fn is provided regardless of backend.
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` -> **275 passed** (all tests), EXIT 0- **`main.py` — respect `cfg.vault.watch` flag for InboxWatcher**
  - `InboxWatcher` was started unconditionally; `VaultConfig.watch: bool = True` was ignored by the lifespan hook
  - Wrapped InboxWatcher import, construction, and `start()` in `if cfg.vault.watch:`; added `else:` branch that logs `[WATCHER] vault.watch=false — inbox watcher disabled`
  - `watcher` local variable initialised to `None` before the conditional; shutdown guard changed from `await watcher.stop()` to `if watcher is not None: await watcher.stop()` to match
  - `app.state.watcher` is set in both branches (`InboxWatcher` instance or `None`) for consistent downstream access
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **275 passed** (all tests), EXIT 0
- **Executed M6 — AI Provider Abstraction (COMPLETE)**
  - Created `monocle/ai/base.py`: `AIProvider` ABC (`embed`, `embed_batch`, `chat`, `transcribe` abstract; `extract_note_metadata` concrete using `self.chat()` + `_load_extract_prompt()` + `_parse_json_response()`); `_open_span()` sync span helper (safe inside async generator functions where `@asynccontextmanager` is incompatible); `_AttrSpanContext` wrapper for attribute injection
  - Created `monocle/ai/ollama_provider.py`: `OllamaProvider` using `ollama.AsyncClient`; auto-pull via `_ensure_model()` (checks `show()`, pulls if 404); streaming via `_stream_chat()` async generator (iterate directly, no `await` on async generator); `_whisper_subprocess()` blocking helper for transcription (SPIKE-1 fallback)
  - Created `monocle/ai/foundry_local_provider.py`: `FoundryLocalProvider` using `openai.AsyncOpenAI` with custom `base_url`; `embed_dimensions` forwarded to API; OpenAI-compatible `/audio/transcriptions` for transcription
  - Created `monocle/ai/azure_provider.py`: `AzureOpenAIProvider` using `openai.AsyncAzureOpenAI`; `dimensions` parameter on embed; Azure Whisper deployment for transcription
  - Updated `monocle/ai/__init__.py`: `get_provider(settings) -> AIProvider` factory for all three providers
  - Updated `monocle/config.py`: added `ai.transcribe_model: str = "whisper"` field to `AIConfig`
  - OTel instrumentation: `span()` + `timed()` on all non-streaming methods; `_open_span()` sync wrapper on streaming methods; histograms `ai.embed_duration`, `ai.chat_duration`, `ai.transcribe_duration` created per-provider in `__init__`
  - Fixed `monocle/telemetry.py` `span()` Python 3.14 double-yield bug: added `_yielded` flag to prevent `yield None` after `athrow()` (context manager exception propagation was violated)
  - **SPIKE-1 RESOLVED (FAILED)**: `ollama` Python client has no transcription API; fallback is `openai-whisper` subprocess; documented in build-plan under Technical Spikes
  - Created `monocle/tests/test_ai.py`: 27 mock-based unit tests; 3 live integration tests behind `@pytest.mark.integration` (skipped by default)
  - Updated `pyproject.toml`: added `addopts = "-m 'not integration'"` and registered `integration` marker
  - Updated `.vscode/tasks.json`: added `test: ai` task
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **302 passed, 3 deselected** (all tests), EXIT 0

---

## 2026-03-18

### Claude Sonnet 4.6
- **Implemented pluggable `TranscriptionProvider` architecture** (follow-up to SPIKE-1 resolution; user chose Option 3 — whisper.cpp HTTP server with future-swap interface)
  - Created `monocle/ai/transcription.py`: `TranscriptionProvider` ABC; `WhisperCppTranscriptionProvider` (httpx `POST /inference` to whisper.cpp HTTP server); `SubprocessTranscriptionProvider` (openai-whisper CLI subprocess, dev fallback); `NativeOpenAITranscriptionProvider` (OpenAI client adapter for Foundry/Azure native endpoints); `get_transcription_provider(settings)` factory returning `None` for `"native"` backend
  - Updated `monocle/ai/base.py`: `AIProvider.transcribe()` made concrete — delegates to `self._transcription_provider`; adds `_transcription_provider: object = None` class attribute; removed `@abstractmethod` decorator
  - Updated `monocle/ai/ollama_provider.py`: removed subprocess imports, `_EXT_MAP`, `_whisper_subprocess()` function and inline `transcribe()` override; accepts `transcription_provider=` constructor param; `TYPE_CHECKING` import for annotation
  - Updated `monocle/ai/foundry_local_provider.py`: accepts `transcription_provider=` param; defaults to `NativeOpenAITranscriptionProvider(self._client, self._transcribe_model)` when `None`; removed inline `transcribe()` and `import io`
  - Updated `monocle/ai/azure_provider.py`: same pattern as Foundry; defaults to `NativeOpenAITranscriptionProvider(self._client, self._transcribe_deployment)`; removed inline `transcribe()` and `import io`
  - Updated `monocle/ai/__init__.py`: calls `get_transcription_provider(settings)` once and passes result to all three provider constructors
  - Updated `monocle/config.py`: added `transcribe_backend: Literal["native","whisper_cpp","subprocess"] = "native"` and `transcribe_url: str = "http://localhost:9000"` to `AIConfig`
  - Updated `pyproject.toml`: added `httpx` to runtime `dependencies` (used directly by `WhisperCppTranscriptionProvider`)
  - Added 12 new tests to `monocle/tests/test_ai.py`: `TestWhisperCppTranscriptionProvider` (mock httpx, connect-error path, default URL), `TestSubprocessTranscriptionProvider` (mock subprocess, missing-whisper path), `TestNativeOpenAITranscriptionProvider` (mock OpenAI client), `TestGetTranscriptionProvider` (all 3 backends + unknown raises), `TestOllamaTranscription` (delegation + no-provider raises)
  - Updated SPIKE-1 outcome in `docs/build-plan.md` with final architecture description
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **314 passed, 3 deselected**, EXIT 0
  - **Executed M7 — Ingest Pipeline & Plugin Registry (COMPLETE)**
  - Created `monocle/ingest/plugin.py`: `IngestPlugin` ABC (`source_id/source_label` ClassVars, `can_handle()`, `extract()`); `IngestPluginRegistry` singleton with first-match-wins `resolve()`, `.reset()` for test isolation
  - Created `monocle/ingest/plugins/text_plugin.py`, `audio_plugin.py`, `teams_plugin.py`: three built-in plugins; `register_default_plugins()` in `monocle/ingest/plugins/__init__.py` registers them in priority order (Audio → Teams → Text)
  - Created `monocle/prompts.py`: `load_prompt(name)` checks `prompts/local/<name>.md` first (user override), then `prompts/<name>.md`; strips YAML frontmatter; WARNING log if not found
  - Replaced `monocle/agents/routing.py` stub: `RoutingAgent` with sentence-starter fast path (no LLM, confidence=0.9), `template_hint` shortcut (confidence=1.0), LLM JSON fallback via `load_prompt("routing")`; all 10 template YAMLs already had `sentence_starters` — no changes needed
  - Created `monocle/ingest/confidence.py`: deterministic `score_confidence()` (0.35×template_match + 0.30×metadata_coverage + 0.20×tag_plausibility + 0.15×entity_match; tag plausibility = text substring match in body, NOT embedding; entity_match via `vault.resolve_wikilink`) + `compute_approval_metadata()`
  - Created `monocle/ingest/failed_registry.py`: `FailedIngestRegistry` with JSON array persistence (atomic write via mkstemp + os.replace); add/get/mark_retried/delete/count methods
  - Replaced `monocle/ingest/__init__.py` stub: full `IngestPipeline` 8-step `run()`; `DuplicateSuspected` exception; duplicate detection (cosine score ≥ 0.95 AND within 7 days); OTel histograms (`ingest.step_duration`, `ingest.pipeline_duration`) + counters (`ingest.notes_total`, `ingest.failures_total`); `.error.md` sidecar + failed_registry entry on steps 3–5 failure
  - Updated `monocle/models.py`: `IngestConfidence` gains `similar_note_detected: bool = False` and `similar_note_path: str | None = None`
  - Created `monocle/tests/test_ingest.py`: 66 tests across 14 test classes covering all plugins, registry, routing fast path, confidence formula, approval metadata, failed registry, pipeline text/audio/auto-approval/failure/duplicate/indexing flows
  - Updated `.vscode/tasks.json`: added `test: ingest` task
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **385 passed, 6 deselected**, EXIT 0
  - Updated `docs/build-plan.md`: all M7 deliverables and acceptance criteria marked `[x]`; Active Milestone → M8; M7 → COMPLETE in tracker
- **M7 post-implementation code review — 13 issues resolved (9 bugs/improvements, 4 security/test-quality)**
  - **Bug: greedy regex** — `_parse_routing_response` used non-greedy `{.*?}` which truncates nested JSON objects from LLM responses; changed to greedy `{.*}` with `re.DOTALL` (`monocle/agents/routing.py`)
  - **Bug: unvalidated LLM template** — `_llm_route` accepted any string from the LLM as a template name; unknown names now normalised to `blank`/`confidence=0.0` before routing decision is returned (`monocle/agents/routing.py`)
  - **Bug: routing decision overwritten by metadata** — `_construct_note` included `"template"` in the `metadata_dict` passed to `create_from_template`; the vault's `fm.update(metadata)` was silently overwriting the routing-decision's schema-derived template name with NoteMetadata's `"blank"` default; `"template"` is now excluded from `metadata_dict` (`monocle/ingest/__init__.py`)
  - **Bug: Windows-illegal chars in sidecar filename** — `safe_preview` used only `/`/`\` replacement leaving `:`, `*`, `?`, `"` etc. intact, causing silent file-write failures on Windows; `_UNSAFE_FILENAME_RE` now strips all Windows-illegal characters (`monocle/ingest/__init__.py`)
  - **Bug: OTel duplicate-instrument warnings** — `create_histogram`/`create_counter` were called in `IngestPipeline.__init__` so each new pipeline instance re-created all 4 instruments; moved to module-level `_get_otel_instruments()` lazy singleton (`monocle/ingest/__init__.py`)
  - **Bug: RoutingAgent re-instantiated per run**: `_route_and_extract` called `RoutingAgent(ai=...)` on every pipeline invocation, scanning+parsing all 10 template YAMLs each time; now cached as `self._routing_agent` in `IngestPipeline.__init__` (`monocle/ingest/__init__.py`)
  - **Security: sidecar content** — error message written raw inline (potential `---` frontmatter injection); now wrapped in fenced code block; `---` sequences in error strings escaped as `- - -` (`monocle/ingest/__init__.py`)
  - **Security: `FailedIngestRegistry` thread-safety** — `_records` list mutations and `_save()` calls lacked a lock; added `threading.Lock` to all public mutation methods (`add`, `get`, `get_all`, `mark_retried`, `delete`, `count`, `count_failed`) (`monocle/ingest/failed_registry.py`)
  - **Idempotency: `register_default_plugins`** — calling twice duplicated all three plugins in the registry (first-match-wins made results correct but wasted memory/log noise); now checks `source_id` presence before registering each plugin (`monocle/ingest/plugins/__init__.py`)
  - **9 new tests added** to `monocle/tests/test_ingest.py`: 7-day cutoff (old note not flagged), `DuplicateSuspected` does not register in `FailedIngestRegistry`, step-8 failure propagates without sidecar, unparseable `created` date (conservative: still triggers dup), `register_default_plugins` idempotency, LLM-unknown-template falls back to blank, greedy-regex with nested JSON (2 variants); fixed no-op assertion in `test_sentence_starter_no_llm_routing_call`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **394 passed, 6 deselected**, EXIT 0

- **Executed M8 — REST API Wiring — Core (COMPLETE)**
  - Rewrote `monocle/main.py` lifespan: `AIProvider` init (non-fatal on error), `FailedIngestRegistry`, `IngestPipeline`, `ReindexQueue` callback `_reindex_file` (embed chunks → upsert), `InboxWatcher` callback `_inbox_ingest_callback` (reads file → `IngestRequest` → pipeline), `ReindexAgent(embed_fn=ai.embed if ai else None)`
  - Updated `monocle/models.py`: added `IngestResponse(note, confidence)`; added `latency_p50_ms`/`latency_p95_ms: dict[str, float]` to `BrainStats`; changed `audio_bytes` from `bytes | None` to custom `AudioBytesField` (`Annotated[bytes | None, BeforeValidator(_coerce_audio_bytes)]`) — decodes base64 JSON strings but passes raw `bytes` through unchanged (fixes Pydantic V2 `bytes` UTF-8 encoding vs base64 decode issue)
  - Implemented `routers/health.py`: pings AI via `embed("ping")`, reads watcher status, returns `telemetry_endpoint` and `watcher_running` fields
  - Implemented `routers/notes.py`: full CRUD wired to `VaultLayer`; `PUT`/`PATCH` push to `ReindexQueue`; backlinks endpoint scans structured links, wikilinks, and people co-mentions
  - Implemented `routers/search.py`: semantic (`embed` → `index.search`) and keyword (vault text scan)
  - Implemented `routers/ingest.py`: `POST /api/ingest` with `DuplicateSuspected → 409`; `POST /api/ingest/stream` SSE emitting step_start → done/duplicate/error
  - Implemented `routers/ingest_failures.py`: GET (newest-first), POST /retry (reconstruct + re-run + mark_retried), DELETE (record only, not the sidecar file)
  - Implemented `routers/transcribe.py`: multipart `UploadFile` + 25 MB guard
  - Implemented `routers/stats.py`: vault counts by type/domain/pending, index chunk count, failed count; latency fields return `{}` pending OTel histogram readback
  - Updated `monocle/tests/conftest.py`: added `mock_ai` (`AsyncMock` with embed/embed_batch/transcribe/chat/extract_note_metadata) and `api_client` (patches `monocle.main.lifespan` with `_test_lifespan` using temp VaultLayer + MemoryIndex + mock AI + FailedIngestRegistry)
  - Rewrote `monocle/tests/test_api.py`: complete M8 integration test suite — `TestHealth`, `TestNotes`, `TestSearch`, `TestIngest`, `TestIngestFailures`, `TestTranscribe`, `TestStats`, plus stub-guard parametrized test for graph/chat/agents/review/settings/teams still returning 501
  - Created `monocle/tests/test_security.py`: 17 tests across 5 classes — `TestPathTraversal` (5 tests using `%2e%2e` encoding), `TestAudioSizeLimits` (4 tests), `TestOptimisticConcurrency` (3 tests), `TestCORS` (3 tests), `TestDuplicateDetection` (2 tests)
  - Updated `.vscode/tasks.json`: added `test: api` and `test: security` tasks
  - Fixed path-traversal test: httpx normalises literal `../..` in URLs before routing; tests now use `%2e%2e` (percent-encoded dots) which httpx preserves; Starlette decodes to `..` in the path parameter so `_safe_resolve` still sees the traversal and returns 403
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **426 passed, 6 deselected**, EXIT 0
  - Updated `docs/build-plan.md`: all M8 deliverables and acceptance criteria marked `[x]`; Active Milestone → M9; M8 → COMPLETE in tracker

## 2026-03-17

### Claude Sonnet 4.6
- **M8 post-review hardening — resolved all high/medium issues and testing gaps (12 fixes, 10 new tests)**
  - **Security**: replaced `str(exc)` leak with generic messages in `routers/ingest.py` (500 + SSE error event), `routers/transcribe.py` (502), `routers/ingest_failures.py` (422); internal details still logged at ERROR level
  - **Bug — `_note_to_markdown` double-model-dump**: `vault/__init__.py` iterated over `raw["links"]` (already plain dicts from `model_dump()`) and called `.model_dump()` on them — raised `AttributeError` for any note with structured links; fixed to iterate over `note.metadata.links` (live `LinkRef` objects) then `raw.pop("links", None)` to prevent double-serialization
  - **Bug — SSE steps fired before pipeline**: `routers/ingest.py` emitted all 8 `step_start` events synchronously before `pipeline.run()` was called; added optional `on_step: Callable[[int], Awaitable[None]]` parameter to `IngestPipeline.run()` (called after each step); SSE endpoint now uses a `asyncio.Queue` + task pattern to stream events in real-time; `_run_pipeline` task uses `try/finally` to always put sentinel on queue even on exception
  - **Bug — health status not degraded**: `routers/health.py` returned `"ready"` even when `ai_reachable=False`; now returns `"degraded"` when AI is unreachable or enabled watcher is not running; also removed `__import__("asyncio")` in favour of top-level import
  - **Bug — retry truncation undisclosed**: `routers/ingest_failures.py` silently re-ingested 200-char preview with no warning; retry response now includes `content_truncated: bool`
  - **Bug — chunk `updated_at` drift**: `main.py` `_reindex_file` used re-index wall-clock time; now uses `note.metadata.updated` (falls back to `created`, then current time)
  - **Cleanup — `routers/notes.py`**: moved `import re` to top-level (was inside inner `for person in ...` loop); removed unused `parse_links_field` import from inner function
  - **Build-plan**: `stats.py` latency fields deferred explicitly to M11 with documented TODO
  - **Tests added** (`test_api.py`): `test_backlinks_returns_list` assertion fixed (now checks source path); `test_backlinks_structured_link`; `test_backlinks_people_co_mention`; `test_ingest_stream_emits_step_and_done_events`; `test_semantic_search_type_filter`; `test_semantic_search_domain_filter`; `test_semantic_search_source_filter`; `test_keyword_search_domain_filter`; `test_retry_success_creates_note`
  - **Tests added** (`test_security.py`): `test_cors_dev_origin_excluded_in_non_dev_mode`; `test_move_note_to_path_traversal_blocked`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **436 passed, 6 deselected**, EXIT 0

- **M8 post-review fix — `PUT /api/notes` returns 201 for resource creation**
  - `routers/notes.py`: `put_note` now calls `vault._safe_resolve(path)` pre-write to check existence (traversal 403 still raised); sets `response.status_code = 201` when file did not exist; updates return 200 per RFC 7231 §4.3.4
  - Updated test assertions: `test_put_creates_note`, `test_put_returns_note_with_mtime`, `test_put_conflict_stale_mtime` (initial create) → 201; `test_put_stale_mtime_returns_409` (security) → 201; `test_rapid_puts_coalesced_in_reindex_queue` → `in (200, 201)`
  - Added `test_put_update_returns_200` test
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **437 passed, 6 deselected**, EXIT 0