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