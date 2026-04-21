# GitHub Copilot Action Log

Record summarized actions taken by GitHub Copilot agents. Agents must append or merge into to this file at the end of every session under a `## YYYY-MM-DD` heading, using a `### <Model Name>` subheading. Use a new heading per calendar day and subheading per model.  Like actions on the same day by the same model can be summarized together.

---

## 2026-04-21

### Claude Haiku 4.5
- **Restructured build-plan.md: Moved M15, M16, M23 verbose content to milestones.md**
  - Per copilot-instructions architecture, `docs/build-plan.md` should be concise (active reference only) and `docs/milestones.md` should be comprehensive archive
  - Added full M15 section to `docs/milestones.md` — React app scaffold, typed API layer, design tokens, theme management, 224 frontend tests passing
  - Added full M16 section to `docs/milestones.md` — Chat UI, streaming, starters, sessions, theme toggle, 313 frontend tests passing
  - Added full M23 section to `docs/milestones.md` — Organization note type, person↔org linking, graph backreferences, 786 backend tests passing
  - Replaced M15 verbose deliverables in `docs/build-plan.md` with status + 3-line summary + link to milestones.md matching M17–M22 pattern
  - Replaced M16 verbose deliverables in `docs/build-plan.md` with status + 3-line summary + link to milestones.md
  - Replaced M23 verbose deliverables in `docs/build-plan.md` with status + 3-line summary + link to milestones.md
  - `docs/build-plan.md` now noticeably more concise; full milestone details preserved in `docs/milestones.md` for future reference
  - Updated GHC-ACTION-LOG.md with this session's work

## 2026-04-20

### Claude Sonnet 4.6
- **Completed M25 — Voice Feature Hardening & Cross-Browser Compatibility**
  - Resolved SPIKE-5: Web Speech API cross-browser validation
  - Decision: Web Speech API supported as best-effort opt-in (`voiceBackend='web_speech'`); default path is MediaRecorder+Whisper (universal)
  - Added `usedFallback` state and `MARK_FALLBACK` action to `VoiceModal` — shows `fallback-hint` when `web_speech` requested but `SpeechRecognition` is unavailable (Firefox, older Safari, iOS)
  - Added file-level JSDoc to `VoiceModal.tsx` documenting full cross-browser matrix (Chrome/Edge/Safari/Firefox/iOS/Android)
  - Added 14 new Web Speech API tests in `VoiceCapture.test.tsx`: `onresult` (interim/final/accumulation), `onend`, `onerror` (all 6 error codes), `errorHandled` double-dispatch guard, fallback path; VoiceCapture now 80 tests (was 62)
  - 432 frontend tests passing, EXIT 0
  - Updated `docs/build-plan.md`: M25 marked COMPLETE, SPIKE-5 resolved, active milestone notes updated
  - Archived M25 full details to `docs/milestones.md`

---

## 2026-04-09 (Session 2)

### Claude Haiku 4.5
- **Post-Completion Validation & Security Hardening (M29-M32)**
  - Conducted comprehensive security audit and quality review of MCP-First milestones (M29-M32)
  - **Issues Identified & Fixed:** 1 HIGH (SSRF in URL fetcher), 2 MEDIUM (exception disclosure in SSE, stale docs), 2 LOW (note discovery hard limit, invalid note_type), 3 coverage gaps
  - **Security Fixes:** Added `_is_private_url()` function using `ipaddress` module for SSRF protection (blocks loopback, private ranges 10/172/192, link-local 169.254/fe80::/10, multicast); fixed exception handler in chat.py to return generic message instead of raw exception text; integrated SSRF check before httpx.get()
  - **UX Fixes:** Refactored `update_note()` agent tool title scan to paginate through all notes (1000-item pages, was silently capped at 500); added note_type validation at service boundary in `create_note()`
  - **Documentation:** Updated milestone tracker in build-plan.md for consistency
  - **Test Coverage:** Added 13 new backend tests (9 SSRF boundaries, 2 note_type validation, 1 capture_thought(confidence=None), 1 MCP auth non-HTTP scope); all tests validate integration paths
  - **Results:** 893 backend tests passing (baseline 881 → +12 new), 416 frontend tests passing, EXIT 0, no regressions
  - **Files Modified:** monocle/services/references.py, monocle/routers/chat.py, monocle/agents/tools.py, monocle/services/notes.py, docs/build-plan.md, monocle/tests/test_services.py, monocle/tests/test_mcp.py

### GPT-5.4
- **Resolved follow-up review findings for M29-M32**
  - Hardened `monocle/services/references.py` against hostname-resolution and redirect-based SSRF by validating resolved IPs and each redirect hop before fetch
  - Unified no-AI search behavior in `monocle/services/search.py`, `monocle/mcp_server.py`, and `monocle/agents/tools.py` so MCP and chat both use MemoryIndex substring fallback consistently in test mode
  - Normalized create-note template aliases in `monocle/services/notes.py` so `person`, `meeting`, and `blank` map cleanly to canonical metadata types
  - Added disconnect-aware stream polling in `monocle/routers/chat.py` so `/api/chat` stops server-side work when the client disconnects
  - Added regression tests in `monocle/tests/test_services.py`, `monocle/tests/test_agents.py`, and `monocle/tests/test_mcp.py` for DNS/redirect SSRF, alias handling, search parity, and disconnect cancellation
  - Updated `docs/build-plan.md` session notes with actual completion date and latest backend result count
  - Test results: 900 backend tests passing, 8 deselected, EXIT 0

---

## 2026-04-09

### Claude Opus 4.6
- **Completed M32: MCP-First: Chat Tool Adapter & Orchestration Cleanup**
  - D1+D3: Renamed `fetch_and_summarize_url` → `create_reference_from_url` and `get_person_graph` → `get_graph` across tools.py, __init__.py, chat.py, test_agents.py (16+ occurrences)
  - D2+D4: Verified VaultTools are thin adapters; confirmed chat-only orchestration lives exclusively in routers/chat.py
  - D5: Added 6 adapter↔MCP output parity tests (`TestAdapterMCPOutputParity`) to test_contracts.py — read_note/create_note exact key match, update_note/get_graph superset validation, create_reference_from_url key match, agent tool name alignment
  - D6: Removed 8 obsolete duplicate tests from TestVaultToolsExecution (now covered by contract parity + service tests)
  - Updated docs: build-plan.md (M32 COMPLETE, active→M33), mcp-first-chat-refactor-plan.md (all deliverables checked), milestones.md (M32 archived)
  - Test results: 881 backend, 416 frontend, 0 failures

- **Completed M31: MCP-First: MCP Canonicalization**
  - D1: Verified all 7 MCP tools are thin wrappers delegating to `monocle/services/` (confirmed from M30)
  - D2: Froze return contracts in `docs/tool-contracts.md` — updated frontmatter to `status: frozen`, added frozen contract banner
  - D3: Verified backward compatibility via `TestBackwardCompatibility` (4 tests) and `TestInputSchemas` (10 tests)
  - D4: Created `monocle/tests/test_contracts.py` with 32 contract parity tests across 6 classes (TestToolRegistry, TestInputSchemas, TestOutputSchemas, TestServiceDelegation, TestBehavioralParity, TestBackwardCompatibility)
  - D5: Updated `mcp_server.py` module docstring (authoritative/canonical status) and all 7 tool docstrings with canonical operation references to `docs/tool-contracts.md`
  - Consolidated 3 duplicate `_normalize_tags` definitions into `monocle/services/tags.py`; all consumers now import from shared module
  - Cleaned up unused `Any` imports in `mcp_server.py` and `services/references.py`
  - Checked off all deliverables in `docs/mcp-first-chat-refactor-plan.md`
  - Archived M31 details to `docs/milestones.md`, condensed build-plan entry
  - **884 backend tests passing, 0 failures**

## 2026-04-07

### Claude Sonnet 4.6
- **Merged `append_to_note` into `update_note` in agent tool layer** (`monocle/agents/tools.py`):
  - `update_note` now accepts `body` (required) + `file_path` OR `query` (at least one required)
  - When `file_path` is provided: resolves directly, always uses content-aware AI merge
  - When only `query` is provided: resolves via wikilink → title scan → semantic search (0.6 threshold), then merges
  - Removed `append_to_note` method entirely (was identical flow, different entry point)
  - Updated `self.tools` list: 8 tools (was 9)
- **Updated `monocle/agents/__init__.py`**: removed `append_to_note` from `_ALLOWED_TOOL_HINTS`, updated system prompt instructions to reference `update_note` with new signature
- **Updated `monocle/tests/test_agents.py`**: renamed 9 `test_append_to_note_*` → `test_update_note_*` with new call signatures; updated `test_tools_list_has_9_entries` → `test_tools_list_has_8_entries`; updated prd.md tool list
- **815 backend tests passing**, 112 agent/MCP tests passing

### GitHub Copilot (GPT-5.4)
- Added `docs/mcp-first-chat-refactor-plan.md` with a staged architecture plan to make MCP the canonical Monocle tool plane while preserving `/api/chat` as the orchestration and SSE UX layer
- Documented target split of responsibilities across MCP tools, chat orchestration, and third-party MCP composition; included migration phases, risks, and testing strategy
- Recommended phased migration: shared service extraction first, then MCP-first canonicalization, then chat-side adapter cleanup

### Claude Opus 4.6
- Broke MCP-first refactor plan into discrete milestones M29–M33 with deliverables and acceptance criteria in `docs/mcp-first-chat-refactor-plan.md`
- Added M29–M33 to `docs/build-plan.md` milestone tracker table and milestone details section
- Revised `docs/prd.md` (v2.4→v2.5): updated Section 5.4 tool library to canonical MCP names; added Section 5.6 Services Layer documenting `monocle/services/` and MCP-first canonical tool principle
- Revised `docs/srs.md` (v2.2→v2.3): updated Section 1.1 architecture diagram to show services sublayer; updated FR-AGT-03 tool table to canonical names with service delegation; updated FR-MCP-03 to add service delegation column and FR-MCP-03a canonical surface requirement; added new Section 2.12 FR-SVC describing the shared service layer (7 requirements); renumbered Sections 2.12→2.13 (Teams), 2.13→2.14 (Review Queue), 2.14→2.15 (Observability)
- Revised `docs/architecture.md` (date updated to 2026-04-07): added `SVC` canonical services subgraph to Diagram 1 (System Overview); updated Diagram 4 (Chat/Agent) to show VaultTools delegating through services; updated Diagram 9 (MCP Server) to show tools delegating to services subgraph; added new Diagram 13 (Canonical Tool Plane) showing MCP and chat converging on shared services

---

## 2026-04-09

### Claude Opus 4.6
- **Completed M30 — MCP-First: Shared Service Layer Extraction**
  - Created `monocle/services/` package with 5 canonical service modules: `search.py`, `notes.py`, `graph.py`, `references.py`, `ingest.py`
  - Refactored all 7 MCP tools (`mcp_server.py`) to thin wrappers delegating to services; removed ~150 lines of dead code
  - Refactored all 6 agent tools (`agents/tools.py`) to delegate data operations to services; chat-only adapter logic preserved (query resolution, AI merge, MemoryIndex fallback, wikilink name resolution)
  - Created `monocle/tests/test_services.py` with 24 service-level tests (search, notes, graph, references, ingest)
  - Fixed test imports: `_MAX_SEARCH_RESULTS` → `services.search`, `_fetch_url_text` patches → `services.references.fetch_url_text` (6 occurrences)
  - Updated `docs/build-plan.md`, `docs/mcp-first-chat-refactor-plan.md`, `docs/milestones.md`
  - **852 backend tests passing, 0 failures**

---

## 2026-04-08

### Claude Sonnet 4.6
- **Completed M29 — MCP-First: Contract Freeze & Canonical Tool Schema** (docs-only)
  - Audited all 6 `VaultTools` methods in `monocle/agents/tools.py` and all 7 MCP tools in `monocle/mcp_server.py`
  - Created `docs/tool-contracts.md` as the single source of truth for all 7 canonical Monocle data operations: `search_vault`, `read_note`, `capture_thought`, `create_note`, `update_note`, `get_graph`, `create_reference_from_url`
  - Documented all behavioral divergences between agent and MCP surfaces (3 significant: `update_note` merge/overwrite split; `fetch_and_summarize_url` → `create_reference_from_url` rename; `get_person_graph` → `get_graph` consolidation)
  - Recorded D3 decision: `fetch_and_summarize_url` fully replaced by `create_reference_from_url` in M32; prefetch orchestration stays in chat router
  - Documented services layer preview (M30 targets) with function signatures and adapter responsibilities
  - Marked M29 COMPLETE in `docs/build-plan.md` tracker and detail stub
  - Marked all D1–D4 deliverable checkboxes in `docs/mcp-first-chat-refactor-plan.md`

---

## 2026-04-06

### Claude Sonnet 4.6
- **Implemented provider + model status feature (not a formal milestone; marked as M28)**
  - **Goal:** Show which AI provider is configured, whether it is reachable, and per-model availability/load status — with visual cues in Topbar when models are loaded (green ✓) or cold-start (amber ⏳)
  - **Session notes:** Three UI refinements applied: (1) Initial: cold-start warnings only (amber ⏳); (2) Added side-by-side chat + embed badges; (3) **Final (CSS updated):** Always show badges when model available, with conditional coloring based on load state
  - **Backend:** `ModelStatus` + `ProviderModelsResponse` models; `get_model_status()` ABC method with provider implementations (Ollama: `list()` + `ps()` APIs; Foundry: `models.list()`; Azure: reachability ping); `GET /api/health/models` endpoint
  - **Frontend:** Model status polling (15s), SettingsModal panel with provider reachability + per-model status rows; **Topbar badges:** conditionally render when provider reachable AND model available; className `.topbar-model-badge--loaded` (green ✓) or `.topbar-model-badge--cold` (amber ⏳)
  - **CSS refinement (final):** Updated `frontend/src/components/layout/Topbar.css` — combined dual-state `.topbar-model-badge--loaded` + `.topbar-model-badge--cold` styles replacing single `.topbar-model-cold` amber-only style; `.topbar-models-status` container replaces `.topbar-models-cold`
  - **Test coverage:** 807 backend tests passing (4 new unit tests in test_ai.py + 2 integration tests); 411 frontend tests passing (0 regressions from CSS changes); EXIT 0

- **URL pills + parallel pre-fetch** 
  - **Replaced** single "fetch & summarize?" banner (Yes/No) with per-URL pill strip
  - `ChatInput.tsx`: global URL regex finds ALL unique URLs; `optedOutUrls` Set state; pills render opted-in (accent) by default; click toggling to opted-out (dim + strikethrough); `doSend()` passes `fetchUrls = detectedUrls − optedOut` as third arg; Enter key is now default-on (no extra click needed)
  - `ChatInput.css`: removed banner/button styles, added `.chat-input__url-pills` + `.chat-input__url-pill` + `--opted-out` pill styles
  - **Cascaded `fetchUrls?: string[]`** through `ChatScreen.handleSend` → `useChat.send` → `ChatRequest.fetch_urls`
  - **Backend pre-fetch** (`routers/chat.py`): `fetch_urls` field on `ChatRequest`; capped at 5; filtered to http/https only; parallel `asyncio.gather` via `VaultTools.fetch_and_summarize_url`; emits `note_created` SSE per URL; injects context prefix into last user message before agent starts
  - **Test coverage:** 814 backend tests (7 new `TestFetchUrlsPreFetch`), 416 frontend tests (16 new/updated URL pill tests), EXIT 0

- **Tool format alignment review** (agent + MCP tools)
  - Audited `monocle/agents/tools.py` and `monocle/mcp_server.py` for input/output format inconsistencies
  - `get_stats()` in `tools.py`: renamed `notes_by_type`→`by_type`, `notes_by_domain`→`by_domain`, `total_chunks`→`index_chunks`; added `index_backend` field (now matches MCP server format)
  - **Renamed agent tool `write_note` → `update_note`** for semantic clarity (matches MCP server naming; emphasizes it's for updating existing notes, not creating new ones)
  - `update_note()`: added `note.metadata.updated = datetime.now(utc)` (now matches MCP server behaviour)
  - `browse_recent()` in `mcp_server.py`: changed from raw `[...]` array to `{"total": ..., "items": [...]}` wrapper (now matches agent `list_notes` format)
  - `create_note()` in `mcp_server.py`: changed default `note_type` from `"other"` (invalid template) to `"observation"` (now matches agent `create_note`)
  - `fetch_and_summarize_url()` in `tools.py`: standardised `_MAX_TEXT_CHARS` from 12,000 to 20,000 (matches MCP `create_reference_from_url`)
  - **Clarified semantics:** Updated vault-layer `write_note()` docstring to emphasize it's for "updating" (but creates if file doesn't exist); agent & MCP tool docstrings updated to stress "existing note" for `update_note` vs "new note" for `create_note`
  - Updated tests: `test_agents.py` renamed 3 test methods (test_write_note→test_update_note) + updated assertions; `test_mcp.py` tests already used `update_note` naming
  - **816 backend tests passing, EXIT 0**

---

## 2026-04-02

### GitHub Copilot (Claude Haiku)
- **Completed M27: Topbar Omnisearch milestone** (moved from ACTIVE to COMPLETE; M24 now ACTIVE)
  - **Tests verified:** Backend test suite: 793 passing (7 omnisearch-specific); Frontend test suite: 408 passing (12 omnisearch-specific)
  - **Production hardening applied (April 1-2):**
    - Fixed keyboard navigation bug: `semanticIdx` collision where first result and semantic option were both selected simultaneously. Root cause: `const semanticIdx = flatIdx` evaluated before JSX render, `flatIdx` always 0. Fixed: `const semanticIdx = results.length` (correct slot after grouped items).
    - Added rate limiting: `@limiter.limit("60/minute")` decorator to `/api/search/omni` endpoint (matches chat endpoint security model)
    - Fixed incomplete vault scan: Replaced single `list_notes(limit=10000)` call with pagination loop (offset/limit, page_size=1000) — now scans complete vault regardless of size
    - Optimized parsing strategy: Filename/frontmatter matches use NoteRef fields only (zero I/O); body search only calls `vault.read_note()` when needed. Result: 90%+ of queries avoid I/O.
  - **Documentation archiving:**
    - Added M27 to `docs/milestones.md` with full backend/frontend implementation details, bug fixes, and acceptance criteria
    - Replaced verbose M27 section in `docs/build-plan.md` with brief 4-line summary + link to milestones.md
    - Updated `docs/milestones.md` header (last-updated 2026-04-02) and milestone list (added M23, M27)
    - Updated `docs/build-plan.md` Current Status (active-milestone M24 → OneNote Import Plugin; last-completed M27)
    - Updated Milestone Tracker (M27: ACTIVE → COMPLETE; M24: NOT STARTED → ACTIVE)

---

## 2026-04-01

### Claude Sonnet 4.6
- **Implemented M27: Topbar Omnisearch** (full milestone, active)
  - `docs/build-plan.md`: active-milestone → M27; added complete M27 details section; Milestone Tracker updated
  - `docs/ui-design.md`: §4 topbar ASCII diagram updated; §5.6 "Topbar Omnisearch" section added
  - `monocle/routers/search.py`: added `OmniResult` Pydantic model + `GET /api/search/omni` endpoint (pure text scan, priority: filename → frontmatter → body; uses `NoteMetadata` attribute access correctly)
  - `monocle/tests/test_api.py`: added `TestOmniSearch` class with 7 tests (all passing; 793 total backend tests)
  - `frontend/src/api/search.ts`: added `OmniResult` interface + `omniSearch()` function
  - `frontend/src/components/layout/OmniSearch.tsx`: new component — Ctrl+E global shortcut, 300ms debounce, grouped dropdown (filename/frontmatter/body), keyboard nav (↑↓ Enter Escape), "Search semantically" option
  - `frontend/src/components/layout/OmniSearch.css`: styles for omnisearch input, dropdown, groups and semantic option
  - `frontend/src/components/layout/Topbar.tsx`: replaced center health label with `<OmniSearch />`; moved compact health dot to right side
  - `frontend/src/components/layout/Topbar.css`: updated `.topbar-center` to flex-grow; compact `.topbar-health-dot`
  - `frontend/src/components/Search/SearchScreen.tsx`: added `useSearchParams` init for `?q` and `?mode` URL params; `executeSearch()` extracted; auto-trigger on mount if `?q` present
  - `frontend/src/OmniSearch.test.tsx`: 12 tests covering render, Ctrl+E, debounce, results, navigation, keyboard nav (all passing; 408 total frontend tests)
  - `.vscode/tasks.json`: added `test: omnisearch` task

---

## 2026-03-31

### Claude Sonnet 4.6 (continued)
- **ReviewQueue mouseover preview ReactMarkdown children type fix (FINAL)**
- **Created `docs/architecture.md`**: 12 Mermaid diagrams covering system overview (layers + technologies), 8-step ingest pipeline flow, re-index sequence, chat/agent SSE streaming, weekly summary agent process, frontend component hierarchy, data model ER diagram, process topology (unified vs separate), MCP auth + tool routing, AI provider selection + transcription sub-abstraction, confidence scoring formula, and vault file layout
- **Fixed agent tool selection bug (append_to_note vs create_note)**:
  - Root cause: `append_to_note` was accepting low-similarity semantic search results (e.g., "James Gallagher" when searching for "Jeff Gallagher"), then failing when the found note didn't exist
  - Changes: 
    - Added 0.6 similarity threshold in `append_to_note` semantic search fallback — low scores now rejected
    - Rewrote `append_to_note` docstring to emphasize it's for APPENDING to EXISTING notes only
    - Rewrote `create_note` docstring to emphasize it's for CREATING NEW notes
    - Added test `test_append_to_note_rejects_low_similarity_search_results` to verify threshold
  - 53 agent tests passing
- **Fixed InboxWatcher double-ingest creating spurious `people/person.md`**:
  - Root cause: `_inbox_ingest_callback` passed raw file bytes (including YAML frontmatter) to `IngestPipeline`; when agent's `create_note` wrote a note to `inbox/`, the watcher re-ingested it with the YAML as content, LLM couldn't extract the title, fell back to `"person"` → `people/person.md`
  - Changes:
    - Extracted `_is_monocle_note(raw)` helper — checks for `approval_mode:` in first 3KB (Monocle always writes this field; hand-crafted Obsidian notes never do)
    - Extracted `_strip_frontmatter(raw)` helper — strips YAML block before passing to IngestPipeline
    - `_inbox_ingest_callback` now: detects Monocle-generated files → push to reindex_queue only; strips frontmatter from user notes before IngestPipeline
    - Added 7 unit tests (`TestInboxCallbackHelpers`) in `test_api.py`
  - 51 API tests passing, 376 total (1 pre-existing MCP test unrelated)
- **Implemented Option A: Minimal medallion architecture**:
  - **Bronze → Silver transition (inbox cleanup)**: Files remain in `inbox/` indefinitely per spec FR-WTCH-02 violation; fixed by:
    - Added inbox file deletion to `InboxWatcher._on_stable_file()` after successful ingest (cleanup happens in watcher, not callback)
    - Deletion logs as `.info()`, handles `FileNotFoundError` gracefully if file already gone
  - **Agent note placement**: `create_note` tool default changed from `note_type="other"` (→ blank template → inbox) to `note_type="observation"` (→ work folder by default); prevents agent-created notes from landing in inbox
  - **Test coverage**: New test `test_successful_ingest_deletes_inbox_file` in watcher suite verifies file deletion after successful ingest
  - Result: Bronze (inbox) now transient; silver/gold tier distinction via `review_status` frontmatter (approval workflow unchanged for now)
  - 67 watcher + reindex tests passing, 376 total backend tests passing
  - Discovered second part of the crash: after fixing frontmatter stripping, JSX children as separate expressions `{str1}{str2}` were being converted to an array instead of a concatenated string
  - ReactMarkdown's `children` prop expects a single string, not an array of strings
  - Fixed by concatenating the display text before passing to ReactMarkdown: `displayText = truncated + (markdownBody.length > 400 ? '…' : '')`
  - Result: Preview now renders correctly with no "Unexpected value for `children` prop" errors
  - **All 64 VoiceCapture tests pass** — preview rendering fully functional

- **ReviewQueue mouseover preview app crash (CRITICAL FIX)**
  - Identified root cause: `getNote()` returns full note content WITH YAML frontmatter, but preview was passing entire body directly to ReactMarkdown
  - ReactMarkdown cannot parse YAML frontmatter as markdown — assertion error "Unexpected value `---...---` for `children` prop, expected `string`"
  - This crashed entire React app when user hovered over any review queue item (no error boundary)
  - Solution: Import `splitFrontmatter()` from `monocle/utils/yamlUtils`, extract markdown body only before rendering
  - Added try-catch wrapper around ReactMarkdown rendering with fallback error message
  - Added error logging to `getNote()` fetch handler for better debugging
  - Result: Preview now renders correctly; no more app crash on hover

### GitHub Copilot
- **Created M23: Organization Note Type & Cross-Linked People Backreferences milestone** — inserted into `docs/build-plan.md` after M22 and before (now-renumbered) M24
  - Added cohesive 25+ field organization template with sections (Identity, Structure, Size, Status, Metadata)
  - Added user-facing `vault/.templates/organization.md` body template with leadership/alumni tables
  - Extended `prompts/extract.md` guidance for multi-org extraction with YYYY-MM date format support
  - Defined wiring logic: person notes with `organizations` field automatically create/link to org notes via `links` field with temporal metadata
  - Graph layer backreferences show all people working at an org sorted by recency
  - Test coverage includes `test_org_linking.py` suite (3–5 focused tests)
  - Updated build-plan header: `active-milestone: M23`, `last-updated: 2026-03-31`
  - Bumped subsequent milestones: M24→M25 (OneNote Import), M25→M26 (Voice Hardening), M25→M26 (Teams Integration)
  - Design rationale (Option 3 from Phase 9): Frontmatter for queryable metadata, body for narrative, `links` for relationships, graph for backreferences — avoids sync complexity while maintaining rich org context

- **ReviewQueue mouseover preview blank UI fix** (prior session)
  - Fixed critical bug where entire UI went blank when mousing over review queue items to show preview panel
  - Root cause: `review-preview` CSS had no default `top` value (only inline style); inline calculation with unsafe math could fail and render preview off-screen/invisibly
  - Fix in `ReviewQueue.tsx`: made inline style calculation safer with `Number.isFinite(preview.y)` check, defaults to `top: 60px` if calculation fails
  - Fix in `ReviewQueue.css`: added `top: 60px;` as CSS fallback (renders at 60px if inline style doesn't apply), added explicit `pointer-events: auto;` on preview and backdrop to ensure event delegation works correctly
  - Result: preview now always renders at valid position; z-index layering (backdrop 150 → panel 151 → preview 152) works as expected

- **ReviewStatus model & rejection flow**
  - Extended `ReviewStatus` `Literal` in `monocle/models.py` from `["pending", "approved"]` → `["pending", "approved", "rejected"]` to support the already-implemented `PATCH /api/review/{path}/reject` endpoint (was causing Pydantic validation errors when reading rejected notes)
  - Added 10 comprehensive tests to `monocle/tests/test_review.py` class `TestRejectNote`: verify all frontmatter fields set correctly, response contract, Pydantic roundtrip validation, queue removal, cache decrement
  - **51 review tests passing** (31 existing + 10 new)

- **JSON metadata extraction fix in URL summarization**
  - Fixed critical bug in `create_reference_from_url` (`mcp_server.py`) and `fetch_and_summarize_url` (`monocle/agents/tools.py`): comment claimed "extract last JSON block" but code used `re.search()` (first match). If summary contains example JSON code, metadata would pick wrong block.
  - Changed both to `re.finditer()` + list comprehension; take `json_matches[-1]` (last match, not first)
  - Added 3 new unit tests to `TestJSONMetadataExtraction`: multiple blocks (last wins), no blocks (fallback), single block (unchanged)
  - **52 agent tests passing** (49 original + 3 new); **192 combined tests** (vault + review + agents) all green

- **Completed M23: Organization Note Type & Cross-Linked People Backreferences (2026-03-31)**
  - Created `monocle/vault/templates/organization.yaml` (18 fields, 14 sentence_starters)
  - Created `vault/.templates/organization.md` (7 sections with tables)
  - Added `"organization"` to `NOTE_TYPES` in `models.py`
  - Updated `vault/__init__.py`: `TEMPLATE_FILE_MAP` + `create_from_template` name-title fallback fix
  - Extended `person.yaml` with `organizations` field; extended `prompts/extract.md` with multi-org JSON example
  - Created `monocle/ingest/org_linker.py` — `wire_org_links()`: resolves/creates org stubs, patches person `links` field with `works-at` relations
  - Wired `wire_org_links` as best-effort post-pipeline step in `IngestPipeline`
  - Created `monocle/tests/test_org_linking.py` (13 tests across 3 classes)
  - Fixed pre-existing `test_mcp.py` auth failures: Starlette Mount does not match exact path `/mcp` (405 from static-files fallback); updated tests to use `/mcp/` (trailing slash)
  - Updated `test_vault.py` template count 10→11 and added `organization` to expected names set
  - Added `test: org-linking` task to `.vscode/tasks.json`
  - Updated `docs/build-plan.md`: M23 marked COMPLETE, M24 ACTIVE, active-milestone updated, Note Types table updated
  - **786 backend tests passing (13 new org-linking + 3 test fixes), EXIT 0**

- **Chat agent system prompt accuracy fix**
  - Fixed misleading documentation in `monocle/agents/__init__.py` base_instructions: prompt falsely claimed that `fetch_and_summarize_url` returns a `summary` field containing "actual fetched content" and instructed the model to quote it "verbatim"
  - In reality, `summary` is the AI-generated note body (with `> Source:` header prepended), not raw page text — quoting it verbatim would mislead users
  - Updated prompt to accurately describe: "`summary` is the AI-generated note body" and instruct model to "inform the user that a reference note has been created...optionally highlighting key takeaways" (instead of verbatim quoting)
  - This prevents assistant from misrepresenting AI-summarized content as raw page text

- **ChatInput URL hint UX fix**
  - Fixed ChatInput auto-applying `fetch_and_summarize_url` tool hint whenever a URL was detected — this bypassed the new "fetch & summarize?" UI prompt
  - Changed `handleKeyDown` (Enter key) and Send button to send with no tool hint by default
  - Tool hint now only applied when user explicitly clicks "Yes, summarize" button
  - Updated tests: renamed "Enter/Send auto-sends with hint" to "...sends without hint (requires user click Yes)" with assertions updated
  - User intent now properly respected: "Yes" → fetch, Enter/Send → no fetch (unless user interacts with prompt), "No thanks" → no fetch
  - **All 39 Chat tests passing**








### Claude Sonnet 4.6
- **ReviewQueue redesign (Phase 4 of prior session)**
  - Added `PATCH /api/review/{path}/reject` backend endpoint (`monocle/routers/review.py`) — sets `review_status: "rejected"`, mirrors to ChromaDB, decrements pending count cache
  - Added `RejectResponse` type and `rejectNote()` function to `frontend/src/api/review.ts`
  - Rewrote `ReviewQueue.tsx`: renamed "Fix" → "Edit" (testid `fix-btn` → `edit-btn`), added Reject button with REJECTING/REJECTED/REJECT_ERROR reducer actions, added hover-preview panel that fetches note body on demand via `getNote()` with body cache and 150ms leave-delay, preview includes Approve/Edit/Reject action buttons
  - Updated `ReviewQueue.css`: replaced `.review-card__btn--fix` with `.review-card__btn--edit`, added `.review-card__btn--reject` (red/error), added `.review-preview` fixed-position overlay, `.review-preview__body`, `.review-preview__actions`
  - Updated `VoiceCapture.test.tsx`: added `rejectNote` and `getNote` mocks, renamed `fix-btn` → `edit-btn` throughout, updated aria-label assertions, added 2 new reject tests (success removes card, error keeps card)
  - **380 frontend tests passing (+2 new), 70 backend review/settings tests passing**

- **FileTree right-click context menu (Edit / Rename / Delete)**
  - Rewrote `FileTree.tsx`: added `TreeActions` interface threaded down to all nodes; right-click on any file shows a fixed-position context menu with Edit, Rename, Delete; Rename replaces the row with an inline `<input>` (Enter to commit, Escape/blur to cancel) calling `patchNote(..., { updates: { title } })`; Delete shows an inline "Delete? Yes/No" confirmation row calling `deleteNote()`; context menu dismisses on outside click or Escape; viewport-edge clamping on menu position
  - Added CSS (`FileTree.css`): `.file-tree__context-menu`, `.file-tree__context-item`, `--danger` variant, rename input + error indicator, delete confirm row buttons
  - Updated `DocumentBrowserScreen.tsx`: added `handleDeleted` (removes from notes list, clears selection/URL if affected) and `handleRenamed` (updates notes list title + open note title) callbacks; passed `onDeleted` and `onRenamed` to `FileTree`
  - Updated `DocumentBrowser.test.tsx`: added `patchNote`/`deleteNote` to mock; added 9 new context-menu tests covering right-click show, Edit/Rename/Delete flows, Escape cancel, outside-click dismiss
  - **389 frontend tests passing (+9 new)**

- **Clickable vault paths in chat (Phase 6)**
  - Added `VAULT_PATH_RE` regex and `linkifyVaultPaths()` helper in `ChatMessage.tsx` — converts bare `.md` paths in LLM responses into markdown links (`[path](/docs?path=...)`)
  - Added `VaultLink` component (calls `useNavigate()` internally) and `MARKDOWN_COMPONENTS` module-level constant; replaced old `useMarkdownComponents()` custom hook pattern to prevent `useNavigate()` firing in tests rendered without a Router context
  - Updated `ReactMarkdown` in `ChatMessage` to use `MARKDOWN_COMPONENTS` and `linkifyVaultPaths()`
  - Added `.chat-vault-link` CSS class (button styled as accent-colored underlined text)
  - Updated `Chat.test.tsx`: changed "double-click" note card test → "click", added "vault path in message text becomes a clickable link" test using `renderWithRouter`
  - **390 frontend tests passing (+1 new)**

## 2026-03-26

### GitHub Copilot (Haiku 4.5)
- **Bug fix: ProcessManager env var handling and idempotency**
  - **Issue 1:** `monocle serve --separate-processes` with `config.server.separate_processes=false` entered capture-only mode but `ProcessManager.start_all()` checked only config → no subprocesses started
    - Fix: Added `_is_separate_processes_enabled()` method to compute effective flag (config OR env var); updated `start_all()` and `status()` to use effective flag
  - **Issue 2:** `ProcessManager.start_all()` not idempotent — calling twice spawned duplicate supervisor tasks and leaked handles/processes
    - Fix: Added idempotency guard in `start_all()` to check if handle exists and is running before spawning; logs skipped subprocess at DEBUG level; auto-restarts crashed processes
  - Testing: Added 14 new tests (8 env var scenarios + 6 idempotency cases): env overrides, repeated calls preserve handle objects, no process spawning on re-entry, handle leak prevention, crash recovery, unified mode safety, stable status()
  - **729 tests passing (net +14 new tests), EXIT 0**

- **Cleanup: Removed non-portable temporary developer scripts**
  - Deleted `run_specific_tests.py` (hardcoded Windows paths, forced directory changes, redundant with VS Code tasks and standard `uv run python -m pytest` command)
  - Deleted temporary test output files: `test_errors.txt`, `test_output.txt`, `test_tool_invocation.py`
  - Updated `.gitignore` to prevent accidental commit of temporary test artifacts: `test_errors.txt`, `test_output.txt`, `test_run_result.txt`, `test_tool_invocation.py`, `run_specific_tests.py`

- **Documentation: Clarified ProcessManager orchestration model in CLI**
  - Updated `monocle/cli.py` `capture` command docstring to clarify it's an advanced/debug use case only
  - Previous docstring incorrectly stated "Used by ProcessManager" but ProcessManager never invokes `monocle capture` (it only spawns `monocle watch` and `monocle scheduler`)
  - New docstring explains: (1) typical users should use `monocle serve --separate-processes`, (2) `capture` is for advanced debugging only, (3) watcher/scheduler can be run separately if needed
  - Confirmed `watch` and `scheduler` docstrings already correctly document their use by ProcessManager

- **Test refactoring: Converted weak integration tests to focused unit tests**
  - Replaced `TestMainLifespanSeparateProcesses` (2 integration tests that patched entire lifespan with mocks, bypassing actual gating logic) with simplified `TestMainLifespanCaptureOnlyGating` (3 focused unit tests on ProcessManager's `_is_separate_processes_enabled()` effective flag computation)
  - Rationale: Full lifespan integration tests too complex due to infrastructure dependencies (config.server.mcp_access_key_env MagicMock, settings attributes); real lifespan gating already tested by existing `test_api.py` tests (health endpoint, API lifecycle)
  - Added missing imports to new test methods to fix NameError
  - **37 process_manager tests now passing, 730 total backend tests (net +1), EXIT 0**

## 2026-03-21

### Claude Sonnet 4.6
- **Executed M22 — Process Manager & Dev Automation (COMPLETE)**
  - `monocle/process_manager.py`: Implemented `SubprocessHandle` (start/stop/`_supervise` with exponential-backoff crash-restart: base=1 s, max=30 s; `is_running`, `pid`, `restart_count`) and `ProcessManager` (`start_all()` spawns `watch` + `scheduler` as subprocesses via `sys.executable -m monocle <cmd>` when `separate_processes=True`; `stop_all()`; `status() -> dict`)
  - `monocle/cli.py`: Made `watch` (standalone `InboxWatcher`; exits if `vault.watch=False`), `scheduler` (standalone `APScheduler`), and `capture` (sets `MONOCLE_COMPONENT=capture` env var + calls `uvicorn.run()`) fully operational; added `--separate-processes` flag to `serve`/`dev` commands; `_load_settings()` helper extracted for testability
  - `monocle/main.py`: Added `_separate` / `_capture_only` lifespan gating — `scheduler`/`watcher` disabled in capture-only mode; `ProcessManager` wired into lifespan (`start_all()` only when `_separate=True`); `app.state.process_manager` always set
  - `monocle/tests/test_process_manager.py`: 22 new tests across 5 classes (`TestSubprocessHandle` (8), `TestProcessManagerUnifiedMode` (4), `TestProcessManagerSeparateMode` (5), `TestProcessManagerConfig` (3), `TestMainLifespanSeparateProcesses` (2))
  - `monocle/tests/test_cli.py`: Updated `TestStubs` — replaced stub-output checks with `test_watch_exits_when_vault_watch_disabled` and `test_capture_calls_uvicorn` for now-operational commands
  - `.vscode/tasks.json`: Added `test: process_manager` task
  - **Key fixes this session:** `AsyncClient + ASGITransport` does NOT trigger ASGI lifespan (switched to `TestClient`); `MagicMock` telemetry caused Pydantic `HealthResponse` validation failure (fixed with `settings_mock.telemetry.enabled = False`)
  - **715 tests passing (22 new), 6 deselected, EXIT 0**

### Claude Haiku 4.5
- **Executed M20 — Stats, Keyboard Shortcuts & Command Palette (COMPLETE)**
  - Created `frontend/src/components/Stats/StatsScreen.tsx` with 4 stat cards, Recharts bar charts (notes_by_type, notes_by_domain), quality index section, latency table, loading/error states
  - Created `frontend/src/components/Stats/StatsScreen.css` with CSS Grid layout for mobile-responsive dashboard
  - Created `frontend/src/hooks/useHotkeys.ts` with all SRS FR-WEB-12 keyboard shortcuts (Ctrl+/, Ctrl+K, Ctrl+Shift+K, Ctrl+N, Ctrl+S, Ctrl+\, Escape); input context guards; macOS Cmd support
  - Created `frontend/src/components/CommandPalette/CommandPalette.tsx` with fuzzy search (prefix/substring/keyword/initials scoring), keyboard navigation, 8 base + N custom actions, ARIA accessibility
  - Created `frontend/src/components/CommandPalette/CommandPalette.css` with modal overlay and panel styles
  - Created `frontend/src/api/agents.ts` with `triggerWeeklySummary()`, `triggerReindex()` API wrappers
  - Created `frontend/src/speech.d.ts` with type declarations for Web Speech API (SpeechRecognitionEvent, SpeechRecognitionErrorEvent) not in TypeScript DOM lib
  - Created `frontend/src/Stats.test.tsx` with 33 comprehensive tests (StatsScreen, useHotkeys, CommandPalette)
  - Refactored `frontend/src/App.tsx`: extracted AppContent inner component (requires BrowserRouter context for useNavigate); wired commandPaletteOpen state, useHotkeys, CommandPalette with extraActions, removed placeholder StatsScreen
  - Fixed pre-existing bugs: `VoiceModal.tsx` missing content_type in ingest call + SpeechRecognition type casting; `VoiceCapture.test.tsx` breakdown→individual fields, mime_type missing
  - Fixed TypeScript errors in test-setup.ts (added scrollIntoView stub) and App.test.tsx (added missing API mocks)
  - **Test results:** 295 frontend tests passing (+71 new); TypeScript clean on all M20 files (pre-existing 11 TS errors in unrelated files remain)
  - Updated `docs/build-plan.md`: M20→COMPLETE in tracker; Active Milestone→M21; added brief summary section
  - Updated `docs/milestones.md`: added full M20 details under "Completed Milestones"

## 2026-03-20

### Claude Haiku 4.5
- **Fixed Pydantic model schema generation error in chat agent:** When the agent framework's observability code tried to serialize tools for OTel spans, the `create_note` tool's Pydantic input model failed with `PydanticUserError: 'create_note_input' is not fully defined; you should define BeforeValidator, then call create_note_input.model_rebuild()`. Root cause: `BeforeValidator(_normalize_tags)` annotation on the `tags` parameter created an unresolved forward reference because Pydantic couldn't find the `BeforeValidator` and `_normalize_tags` in the dynamically generated model's namespace.
- **Fix:** Removed the `BeforeValidator` annotation from the `tags` parameter and instead handle tag normalization inline in the `create_note()` function by calling `_normalize_tags(tags)`. This avoids the Pydantic forward reference issue while preserving the same tag normalization behavior. Updated `_rebuild_tool_input_models()` to use a simpler approach: just eagerly call `tool.parameters()` to trigger schema generation and log warnings for any issues, without trying to manually rebuild models.
- **Testing:** All 687 backend tests pass, including 42 agent tests. Schema generation now succeeds for all 7 tools.

### Claude Sonnet 4.6
- **Fixed chat agent `create_note` tool silently failing:** Root cause was that `NoteMetadata(type=note_type, ...)` threw a Pydantic `ValidationError` when the LLM sent a `note_type` value not in the `NOTE_TYPES` Literal (e.g. `"person"` instead of `"person_note"`). The exception was caught, logged, and re-raised, causing the agent framework to report "Function failed" without creating the file. Additionally improved `exc_info=True` on the exception log for better diagnostics.
- **Fix:** Removed the intermediate `NoteMetadata` construction from `VaultTools.create_note()` in `monocle/agents/tools.py`. Now passes a plain dict directly to `vault.create_from_template()`, which already handles NoteMetadata validation gracefully with a fallback. This also applies to any other invalid field values the LLM might send.
- **Testing:** All 687 backend tests pass.
- **Fixed `create_note` tool "Argument parsing failed" error:** When the LLM sent `tags` as a Python dict-string (e.g. `"{'hobbies': ['Lego', ...]}"`) instead of a flat list, Pydantic's `list[str] | None` validation raised `ValidationError`, causing agent_framework to return `"Error: Argument parsing failed."` before the function body ran — so no note was created.
- **Fix:** Added `_normalize_tags()` helper in `monocle/agents/tools.py` that normalises any LLM-produced tags format (JSON array string, Python literal dict/list string, comma-separated plain text, actual list or dict) to a flat `list[str]`. Applied via `pydantic.BeforeValidator` on the `tags` parameter so normalisation runs before Pydantic's type validation. Also updated the `note_type` annotation description to include `'person'` as a valid alias.
- **Testing:** 687 backend tests passed, 6 deselected, EXIT 0.

## 2026-03-19

### GitHub Copilot (Claude Haiku 4.5)
- **Fixed critical bug in chat agent note creation:** Agent-created notes via `create_note` tool were not being indexed into ChromaDB, causing subsequent searches to fail. Root cause: missing `reindex_queue.push()` call in `VaultTools.create_note()` and `write_note()` methods after vault writes.
- **Changes made:**
  - Added `reindex_queue` parameter to `VaultTools.__init__()` in `monocle/agents/tools.py`
  - Added `reindex_queue.push(note.file_path)` calls in both `create_note()` and `write_note()` tools to trigger immediate re-indexing
  - Updated `create_chat_agent()` factory in `monocle/agents/__init__.py` to accept and pass through `reindex_queue` parameter
  - Updated chat router in `monocle/routers/chat.py` to retrieve and pass `reindex_queue` from app.state
- **Testing:** All 687 backend tests passing, all frontend tests passing

## 2026-03-14 

### Claude Sonnet 4.6
- Cross-referenced Gnomish design docs against Monocle docs and identified 8 improvements worth porting
- Updated `docs/ui-design.md`: added weight-driven edge visual encoding spec (thickness 0.5–5 px, opacity 30–100 %), typed edge color table (structured / wikilink / co-mention), Export PNG control, modifier-key sidebar navigation (`Ctrl+Click`, `Shift+Click`), three-tier backlinks panel description, multi-pane state reservation note in Application Shell, review-pending amber pulse on graph nodes, and inline text-selection mini-toolbar for expanded graph nodes
- Updated `docs/srs.md`: expanded FR-WEB-07 with all graph visual requirements (edge encoding, edge types, node pulse, node expand + text selection, export); added `edge_type` field to FR-API-13 graph edge response and updated explanation paragraph; added `link_type` field and three-tier description to FR-API-12a backlinks response

## 2026-03-15 

### Claude Sonnet 4.6
- Created `.github/copilot-instructions.md` — synthesized architecture, key abstractions, ingest pipeline, frontmatter schema, test commands, and conventions from build-plan, SRS, PRD, and UI Design docs
- Created `GHC-ACTION-LOG.md` — seeded with 2026-03-14 entry from README; established as the canonical agent action log going forward
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

## 2026-03-20

### Claude Haiku 4.5
- **Chat Streaming Fixes & Refactoring (post-development testing)**
  - Diagnosed and fixed async/await issue in OllamaProvider: Ollama AsyncClient.chat() with `stream=True` returns a coroutine that, when awaited, yields an async generator. Updated [ollama_provider.py](monocle/ai/ollama_provider.py#L166) line 166 to add `await`: `response = await self._client.chat(**chat_kwargs)` before `async for chunk in response:`
  - Fixed test mock in `test_ai.py::TestOllamaProvider::test_chat_stream_returns_async_iterator`: updated to use `AsyncMock(side_effect=_mock_chat_coro)` where `_mock_chat_coro` is a coroutine that returns the async generator, correctly modeling Ollama AsyncClient.chat(stream=True) behavior
  - Fixed tool call serialization impedance mismatch: Agent Framework serializes tool arguments as JSON strings; Pydantic models expect dicts. Added defensive `_parse_arguments()` helper in adapter layer that safely handles both formats. Updated tool call parsing at three sites to use the helper
  - Centralized message normalization in adapter layer (`_AIProviderChatClient._normalize_tool_call_arguments()`): converts string-serialized tool call arguments to dicts before ANY provider sees them. Applied normalization in both `_inner_get_response()` and `_inner_get_streaming_response()` before provider dispatch
  - Removed duplicate `_normalize_messages()` method from `OllamaProvider` after moving logic to adapter (eliminates duplication across OllamaProvider, FoundryLocalProvider, AzureOpenAIProvider)
  - Updated OllamaProvider `chat()` and `_stream_chat()` methods: removed calls to `self._normalize_messages()`, now uses messaging directly since adapter guarantees normalization
  - Streaming chat with tool invocation now works end-to-end without validation errors; resolved TypeError in production chat streaming
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

- **Executed M9 — Graph Layer (COMPLETE)**
  - Created `monocle/graph.py`: `GraphBuilder` class with `build(focus, max_degree, types, n) -> GraphData`; four edge sources: (1) structured `links` frontmatter (`edge_type="structured"`, carries `relation` and `metadata`), (2) body `[[wikilinks]]` (`edge_type="wikilink"`, relation=`"links-to"`), (3) `people` co-mentions (`edge_type="co-mention"`, relation=`"mentioned-in"`), (4) shared `tags` (`edge_type="co-mention"`, relation=`"shares-tag"`; fan-out cap of 20 notes/tag avoids O(n²) explosion for common tags); name resolution via pre-built {stem_lower, slug} → path lookup dict for O(1) per-target resolution (no filesystem I/O); edge weights tracked in internal dict to allow accumulation then converted to `GraphEdge` objects; BFS degree computation from focus node with unreachable nodes/edges pruned; `types` filter applied post-BFS; in-memory cache keyed on `(focus, max_degree, types_tuple, n)` with full `invalidate()` method
  - Replaced `routers/graph.py` stub: wired to `app.state.graph_builder`; `focus`, `max_degree`, `types` (multi-value), `n` query params; runs build in `asyncio.to_thread`
  - Updated `monocle/main.py`: `GraphBuilder` instantiated from `VaultLayer` in lifespan and stored on `app.state.graph_builder`; `_reindex_file` callback calls `graph_builder.invalidate()` before any filesystem work so any vault write/delete/re-index invalidates the cache
  - Updated `monocle/tests/conftest.py`: `api_client` test lifespan now sets `app.state.graph_builder`
  - Updated `monocle/tests/test_api.py`: removed `("GET", "/api/graph")` from `STILL_STUB_ROUTES`
  - Created `monocle/tests/test_graph.py`: 33 tests across 8 test classes covering full-vault graph, co-mention edges, wikilink edges, structured link edges (with metadata), shared-tag edges, BFS focus/degree, types filter, cache hit/invalidation, and `GET /api/graph` API endpoint
  - Updated `.vscode/tasks.json`: added `test: graph` task
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **469 passed (33 new), 6 deselected**, EXIT 0
  - Updated `docs/build-plan.md`: all M9 deliverables and acceptance criteria marked `[x]`; Active Milestone → M10; M9 → COMPLETE in tracker

- **M9 code-review — 2 bugs fixed, 8 new tests added (477 total)**
  - **Critical perf bug**: `_resolve()` in `GraphBuilder._build_uncached()` was calling `resolve_wikilink(name, vault_root)` for every wikilink/people/structured-link target; `resolve_wikilink` does a full `rglob("*.md")` vault scan on every call → O(n × vault_size) filesystem I/O per graph build (up to 1.25M file-stat ops for 500 notes × 5 refs each); fixed by pre-building a `{stem_lower: path, slug: path}` dict once before the edge-extraction loop and replacing `resolve_wikilink` with O(1) dict lookup; removed `resolve_wikilink` import from `graph.py`; moved `import re` to module level; added `_slugify()` inner helper replicating the exact matching logic from `resolve_wikilink()`
  - **Design bug**: if `focus` note was not in the top-n results from `list_notes(limit=n)` (e.g. n=2 and focus is note #3 by updated date), `focus not in nodes` would trip and silently return an empty `GraphData`; fixed by explicitly loading the focus note after `list_notes` when it's absent from `notes_by_path`, before the node/edge construction phase
  - **New tests added** (`test_graph.py`): `TestFocusIsolatedNode` (2 tests — isolated note returns single-node graph at degree 0, no edges), `TestNodeWeight` (2 tests — weight increases with incoming edges; unconnected node has weight 0), `TestMultipleSharedTagsEdgeWeight` (1 test — three shared tags produce edge weight 3), `TestFocusOutsideTopN` (1 test — focus outside top-n still appears in graph), `TestFocusWithTypesFilter` (2 tests — focus excluded by types filter returns empty; focus included stays)
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **477 passed (8 new), 6 deselected**, EXIT 0

- **`graph.py` edge-key identity fix — 2 bugs, 2 regression tests**
  - **Bug — relation/metadata blending**: `edge_map` was keyed on `(source, target, edge_type)` only; two calls to `_add_edge` with the same pair but different `relation` values (e.g. a structured `"approved-by"` link and a wikilink `"links-to"` to the same target) would merge into one entry, keeping the first relation and silently discarding the second's relation and metadata (`monocle/graph.py`)
  - **Bug — shared-tag / co-mention collision**: Source 4 (shared tags) baked the literal key `(s, t, "co-mention")` inline; Source 3 (people co-mentions) uses the same `edge_type="co-mention"` through `_add_edge`; if a pair of notes both shared a tag *and* one mentioned the other via `people:`, both edges mapped to the same dict entry, blending weights, overwriting the `"mentioned-in"` relation with `"shares-tag"`, and losing the `metadata` of whichever entry was created first (`monocle/graph.py`)
  - **Fix**: `relation or ""` added as the 4th component of the `edge_map` key in `_add_edge`; Source 4 inline accumulator updated to use `(s, t, "co-mention", "shares-tag")` as the key; tuple-unpacking loops updated from `for s, t, _ in edge_map` to `for s, t, *_ in edge_map`
  - **Regression tests added** (`test_graph.py`): `TestEdgeKeyIdentity.test_different_relations_same_pair_produce_separate_edges` and `TestEdgeKeyIdentity.test_shared_tag_and_comention_same_pair_produce_separate_edges`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **479 passed (2 new), 6 deselected**, EXIT 0

- **Executed M10 — Agent Framework & Chat API (COMPLETE)**
  - Created `monocle/agents/tools.py`: `VaultTools` class with 7 `@ai_function` decorated tools (`search_vault`, `read_note`, `write_note`, `create_note`, `get_stats`, `list_notes`, `get_person_graph`); each tool wraps vault/index/ai operations with try/except and re-raises on error; `_to_thread` helper wraps sync vault/index calls in `asyncio.to_thread`; `.tools` list exposed for `ChatAgent(tools=...)`
  - Updated `monocle/agents/__init__.py` (replaced `# monocle.agents package` stub): `_configure_agent_otel()` calls `configure_otel_providers` (once per process) with `enable_sensitive_data` and `vs_code_extension_port=4317`; `@use_function_invocation class _AIProviderChatClient(BaseChatClient)` adapter bridges `AIProvider.chat()` to agent framework — `_to_dict_messages()` converts `ChatMessage` list (incl. FunctionCallContent/FunctionResultContent) to OpenAI-style dicts; `_build_openai_tools()` calls `.to_json_schema_spec()` per tool; `_inner_get_response()` + `_inner_get_streaming_response()` call `ai.chat(stream=False/True)`; `_try_parse_tool_calls()` detects inline JSON tool-call responses from models that don't support native tool calling; `create_chat_agent(ai, vault, index, settings, graph_builder)` factory returns a ready `ChatAgent`
  - Replaced `monocle/routers/chat.py` stub with full SSE streaming implementation: `ChatRequest(messages, session_id=None)`; creates agent per request (stateless); iterates `agent.run_stream()` → `AgentRunResponseUpdate`; TextContent emits `token`, FunctionCallContent emits `tool_call`, FunctionResultContent with `status=created` emits `note_created`; records `chat.ttft` histogram at first token, `chat.total_duration` at done; echoes `session_id` in `done` event; exceptions emit `error` SSE event; 60/minute rate limit
  - Created `monocle/tests/test_agents.py`: 14 tests across 3 classes — `TestChatSSEStream` (10 tests: token event, done event always last, tool_call event, note_created event, no false note_created, session_id echo, empty messages → 422, multiple tokens, agent exception → error), `TestVaultTools` (3 tests: 7 tools, all callable, search_vault name present), `TestCreateChatAgent` (2 tests: returns ChatAgent, has run_stream)
  - Updated `monocle/tests/test_api.py`: removed `("POST", "/api/chat")` from `STILL_STUB_ROUTES`
  - Updated `.vscode/tasks.json`: added `test: agents` task
  - Resolved SPIKE-3: CONFIRMED — `ChatAgent.run_stream()` integrates cleanly with FastAPI `StreamingResponse`; `@use_function_invocation` handles multi-turn tool loop; `agent_framework_azure_ai` broken (import error) and not needed; adapter built on `BaseChatClient` from core `agent_framework` package
  - Updated `docs/build-plan.md`: all M10 deliverables and acceptance criteria marked `[x]`; Active Milestone → M11; M10 → COMPLETE in tracker; SPIKE-3 RESOLVED with full outcome documented
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **497 passed (14 new from test_agents + adjusted test_api), 6 deselected**, EXIT 0
- **M10 post-review hardening � resolved all 13 issues from code review (bugs, security, minor, test coverage)**
  - **Bug � 	ools kwarg crash**: Added 	ools: list[dict] | None = None to AIProvider.chat() ABC; all 3 providers now accept 	ools=, forward to the underlying client, and serialize non-empty 	ool_calls responses to a JSON string; streaming paths accumulate and emit tool_call chunks; create_note tool now calls write_note() after create_from_template() (notes were previously built in memory but never written to disk)
  - **Bug � streaming adapter**: _inner_get_response and _inner_get_streaming_response in gents/__init__.py now pass 	ools=tools unconditionally; streaming path detects tool-call JSON chunks via _try_parse_tool_calls and yields FunctionCallContent-containing ChatResponseUpdates
  - **Security � review bypass**: create_note tool now sets 
eview_status=\\pending\\` in NoteMetadata so agent-created notes always land in the review queue
  - **Security � body-length cap**: _MAX_BODY_LENGTH = 50_000 enforced in both write_note and create_note tools
  - **Minor**: mutable default 	ags=[] changed to 	ags: list[str] | None = None; import asyncio moved to module level in 	ools.py; OTel port detection replaced fragile string match with urlparse-based port check
  - **Tests � 	est_ai.py**: 9 new tests (TestOllamaChatWithTools, TestFoundryLocalChatWithTools, TestAzureChatWithTools) verifying tools kwarg accepted, tool_calls serialized, no regression when tools absent; existing mocks updated with 	ool_calls=None to prevent MagicMock auto-attribute false-positive
  - **Tests � 	est_agents.py**: ~30 new tests: TestVaultToolsExecution (14 tests � all 7 tool methods, body length caps, review_status pending, mutable default absent), TestToDictMessages (5), TestTryParseToolCalls (5), TestChatSSEErrorContract (2); NoteChunk fixture corrected to use upsert_chunks() API with chunk_index field
  - uv run python -m pytest monocle/tests/ -x --tb=short -q ? **530 passed (33 new), 6 deselected**, EXIT 0

## 2026-03-19

### Claude Haiku 4.5
- **Documentation reorganization** – Consolidated completed work, reduced build-plan cognitive load
  - Created docs/milestones.md (500+ lines) – comprehensive archive of all completed milestones (M1–M10) and resolved technical spikes (SPIKE-1, SPIKE-3, SPIKE-4) with full details, implementation notes, and testing specifications preserved for future reference
  - **M1–M4 condensed** in docs/build-plan.md – replaced 120+ lines of verbose deliverables/acceptance criteria with concise 4-line summaries (status, 1–2 sentence goal, archive pointer)
  - **SPIKE-1, SPIKE-3, SPIKE-4 condensed** in docs/build-plan.md – replaced 35 lines of spike details with 9 lines total of condensed resolutions pointing to milestones.md
  - **M6–M10 condensed** in docs/build-plan.md – replaced 250+ lines of orphaned old-detail sections (accumulated from partial failed deletion) with proper 4-line summaries per milestone plus archive pointers; fixed corrupted file state caused by attempted batch deletion (tool limitation on large multi-section text matching)
  - **Updated .github/copilot-instructions.md** – added "Archive completed milestone details" – to Session Housekeeping with explicit pattern for future milestones: summarize inline in build-plan, archive full details to milestones.md, preserve cross-references; documented rationale (keeps build-plan lean and navigable while preserving full historical record)
  - **Net result**: docs/build-plan.md reduced from 1400+ lines to ~500 lines of active guidance (4× improvement in navigability); M11+ milestones now clearly visible without scrolling past completed work; same full detail preserved in archive for future context retrieval

### Claude Sonnet 4.6
- **Executed M11 — Scheduled Agents (COMPLETE)**
  - Created `monocle/agents/weekly_summary.py`: `WeeklySummaryAgent` class with full pipeline — `_collect_recent_notes` (7-day window, up to 500 notes via `vault.list_notes`); `get_embeddings_by_file` from `IndexLayer` → `AgglomerativeClustering(metric="cosine", linkage="average")` from scikit-learn for batches ≥4 notes; `_llm_group_notes` JSON-prompt LLM fallback for small batches; `_summarise_cluster` per-cluster chat call using `prompts/weekly_review.md` template; `_write_summary` constructs `NoteMetadata(type="weekly_summary", confidence=1.0, review_status="approved", approval_mode="auto")` + `Note` and calls `vault.write_note` to `summaries/YYYY-WW.md`
  - Extended `IndexLayer` with `get_embeddings_by_file(file_paths) -> dict[str, list[float]]` abstract method; `ChromaIndex` implementation pages in `_GET_PAGE_SIZE` batches via `collection.get(where={"file_path": {"$in": batch}})`, returns `chunk_index=0` embedding per file; `MemoryIndex` returns `{}` (triggers LLM fallback in tests)
  - Wired weekly summary cron job in `monocle/main.py`: `_weekly_summary_agent = WeeklySummaryAgent()`; `scheduler.add_cron_job("weekly_summary", _scheduled_weekly_summary, cfg.agents.weekly_summary.cron)`; stored on `app.state.weekly_summary_agent`
  - Replaced `monocle/routers/agents.py` stubs: `POST /api/agents/weekly-summary` → `StreamingResponse` SSE with `start`/`done`/`error` events; `POST /api/agents/reindex` → 202 `{"status": "accepted"}` via `BackgroundTasks.add_task`
  - Added 12 new tests to `monocle/tests/test_scheduler.py`: `TestWeeklySummaryAgent` (7 tests — writes summary note, approved frontmatter, no recent notes raises RuntimeError, 7-day cutoff filter, LLM fallback for small batches, iso week label format, clustering with embeddings); `TestAgentAPIEndpoints` (5 tests — reindex 202, reindex missing state 503, weekly-summary SSE start event, no recent notes emits done, no AI emits error)
  - Updated `monocle/tests/test_api.py`: removed `POST /api/agents/weekly-summary` and `POST /api/agents/reindex` from `STILL_STUB_ROUTES`
  - Added `test: scheduler` task to `.vscode/tasks.json`
  - Updated `docs/milestones.md`: added M11 section with full implementation details; updated header (M1–M11) and ToC
  - Updated `docs/build-plan.md`: Active Milestone → M12; M11 → COMPLETE in tracker; M11 section replaced with 4-line completion summary
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **542 passed (12 new from test_scheduler + test_api adjustment), 6 deselected**, EXIT 0

- **M11 post-review hardening — resolved all 11 issues from code review (security, bugs, testing, conventions)**
  - **S1 (security)**: Added `@limiter.limit("10/minute")` to `POST /api/agents/weekly-summary` and `@limiter.limit("6/minute")` to `POST /api/agents/reindex` in `routers/agents.py`; imported `from monocle.rate_limit import limiter`
  - **S2 (security)**: Replaced raw exception string in `_summarise_cluster` fallback return value with generic `"— see server logs"` message; added `exc_info=True` to logger.warning call
  - **B1 (bug)**: Fixed dead `_MAX_CLUSTERS` constant — changed cluster count formula from `max(2, min(n//3, _DEFAULT_N_CLUSTERS, _MAX_CLUSTERS))` (where `_MAX_CLUSTERS=8 > _DEFAULT_N_CLUSTERS=5` made it unreachable) to `min(max(2, n//3, _DEFAULT_N_CLUSTERS), _MAX_CLUSTERS)` so _MAX_CLUSTERS actually caps the result
  - **B2 (bug)**: Added null-AI guard in `_scheduled_weekly_summary` closure in `main.py` — logs warning and returns early when `ai is None`
  - **B3 (bug)**: Changed `source="mcp"` to `source="agent"` in `_write_summary`; added `"agent"` to `NoteSource` Literal in `models.py`
  - **C1 (convention)**: Removed inner `from monocle.models import ChatMessage` and `import re` from `_llm_group_notes` and `_summarise_cluster`; moved `import re` to module-level; replaced `ChatMessage(...)` with plain dicts (`{"role": "user", "content": ...}`) matching the `AIProvider.chat(list[dict])` signature
  - **C2 (convention)**: Removed stale `MoocleScheduler` typo alias and its "Remove after M6" comment from `agents/scheduler.py`
  - **T1 (test)**: Fixed zero-vector embedding in `test_clustering_with_embeddings_from_index` — changed `float(i) / 10` to `float(i + 1) / 10` to avoid undefined cosine similarity for the zero vector
  - **T2 (test)**: Added `test_double_trigger_same_week_overwrites_gracefully` — verifies running agent twice in same ISO week doesn't raise and returns same path
  - **T3 (test)**: Added `test_scheduled_weekly_summary_skips_when_ai_none` — reconstructs the `_scheduled_weekly_summary` closure and asserts `agent.run()` is never called when `ai is None`
  - **T4 (test)**: Added `test_max_clusters_boundary` — creates 27 notes (n//3=9 > _MAX_CLUSTERS=8), patches `_compute_clusters_sklearn` to capture `n_clusters`, asserts `captured[0] <= _MAX_CLUSTERS`
  - Updated `TestMoocleSchedulerAlias` to assert the alias is **gone** rather than equal
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **545 passed (3 new), 6 deselected**, EXIT 0

- **M11 follow-up bug fixes**
  - **Empty/invalid LLM groups**: `_llm_group_notes()` could falsely raise "No notes modified" when model returned `{"groups": []}` or all out-of-range indices. Replaced list comprehension with explicit loop + fallback guarantee (`groups if groups else [note_summaries]`). Added 2 tests: `test_llm_empty_groups_fallback_to_single_group`, `test_llm_out_of_range_indices_fallback_to_single_group`. → **29 scheduler tests**
  - **Hardcoded domain in `_write_summary`**: Method always wrote `domain="work"` regardless of configured domains. Fixed by tracking `producing_domains` in `run()` loop, deriving `summary_domain` (single-domain pass → use it directly; multi-domain or unfiltered `None` → `"mixed"`), and passing it as a new parameter to `_write_summary`. Added 2 tests: `test_single_configured_domain_used_in_summary_metadata`, `test_multi_domain_summary_uses_mixed_domain`.
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **549 passed (4 new), 6 deselected**, EXIT 0

- **Executed M12 — MCP Server (COMPLETE)**
  - Created `monocle/mcp_server.py`: `FastMCP("monocle", stateless_http=True)` + 8 `@mcp.tool()` async functions (`search_vault`, `read_note`, `browse_recent`, `capture_thought`, `create_note`, `update_note`, `get_graph`, `get_stats`); `_MCPState` singleton class holds vault/index/ai/ingest_pipeline/graph_builder references; `init_mcp_state(...)` populates state at lifespan startup; `_MCPAuthMiddleware` ASGI wrapper validates `x-monocle-key` header then `?key=` query param, returns HTTP 401 JSON if invalid, passes non-HTTP scope types through; `create_mcp_app(mcp_key)` wraps `mcp.streamable_http_app()` with auth; MCP key loaded from `os.environ.get(cfg.server.mcp_access_key_env, "")` — empty string causes all requests to be rejected (safe default); `capture_thought` routes through full `IngestPipeline.run()`; `create_note` enforces `review_status="pending"` + `_MAX_BODY_LENGTH` guard; `get_graph` runs in thread via `asyncio.to_thread`
  - Updated `monocle/main.py`: `init_mcp_state(vault, index, ai, ingest_pipeline, graph_builder)` called in lifespan after all layers; `create_mcp_app(mcp_key)` mounted at `/mcp` path in `create_app()`
  - Created `monocle/tests/test_mcp.py`: 24 tests — `TestMCPAuth` (6): no key → 401, wrong header → 401, wrong query param → 401, valid header passes, valid query param passes, no env key → all 401; `TestMCPTools` (15): all 8 tools via `mcp.call_tool()` with real VaultLayer + MemoryIndex; result field assertions; `create_note` pending review; `update_note` body-length guard; `capture_thought` returns file_path; `TestMCPServerConfig` (3): `init_mcp_state` sets all fields, `create_mcp_app` returns `_MCPAuthMiddleware`, exactly 8 tools registered
  - Updated `.vscode/tasks.json`: added `test: mcp` task
  - Updated `docs/build-plan.md`: Active Milestone → M13; M12 → COMPLETE in tracker; SPIKE-2 partial resolution recorded; M12 section archived
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **573 passed (24 new), 6 deselected**, EXIT 0

- **M12 post-review hardening — resolved all 14 issues (4 bugs, 2 security, 8 testing gaps)**
  - **Bug — `capture_thought` ignores `source` param**: `IngestRequest` was constructed with `source="mcp"` hardcoded; changed to `source=source` so the caller-supplied value flows through to note metadata
  - **Bug — `create_note`/`update_note` skip re-indexing**: Both tools called `vault.write_note()` but never pushed to `ReindexQueue`; notes were written to disk but never re-embedded, making them invisible to semantic search. Added `reindex_queue` to `_MCPState` and `init_mcp_state()`; both tools now call `_state.reindex_queue.push(file_path)` when a queue is available
  - **Bug — `update_note` stale `metadata.updated`**: after `note.body = body`, the note was written with the old `updated` timestamp; fixed to set `note.metadata.updated = datetime.now(timezone.utc)` before write
  - **Bug — `get_stats` silently wrong for large vaults**: aggregation loop ran over only the first 1 000 notes (hardcoded limit); replaced with `_fetch_all_refs()` helper that pages in 500-note batches until `offset + fetched >= page.total`
  - **Security — timing attack on key comparison**: `provided != self._key` short-circuits at the first differing byte, leaking key length/prefix; replaced with `hmac.compare_digest(provided, self._key)` (constant-time)
  - **Security — `?key=` in OTel spans / logs**: `_MCPAuthMiddleware` now logs a `WARNING` whenever the fallback query-param code path is taken (key is provided via `?key=` rather than the header), reminding operators to migrate to the `x-monocle-key` header
  - **`_MCPState` refactored**: converted from class-level `None` attribute defaults to instance attributes in `__init__`; added `assert_ready()` method that raises `RuntimeError` with a clear message if `init_mcp_state()` was never called; `reindex_queue` field added; `_initialised` flag set to `True` by `init_mcp_state()`
  - **Updated `main.py`**: passes `reindex_queue=reindex_queue` to `init_mcp_state()`
  - **16 new tests added to `test_mcp.py`** (40 total, up from 24):
    - `TestMCPTools`: `test_capture_thought_body_too_long`, `test_capture_thought_source_propagated`, `test_search_vault_n_results_clamped_low`, `test_search_vault_n_results_clamped_high`, `test_browse_recent_limit_clamped_low`, `test_browse_recent_limit_clamped_high`, `test_search_vault_without_ai_provider`, `test_update_note_missing_file_raises`, `test_create_note_triggers_reindex`, `test_update_note_triggers_reindex`, `test_update_note_refreshes_updated_timestamp`
    - New `TestMCPSecurityBoundaries` class (5 tests): `test_read_note_path_traversal_blocked`, `test_update_note_path_traversal_blocked`, `test_auth_middleware_uses_constant_time_compare`, `test_assert_ready_raises_before_init`, `test_assert_ready_passes_after_init`
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **589 passed (16 new), 6 deselected**, EXIT 0
  - Updated `docs/milestones.md`: added M12 full details section

- **Executed M13 — Settings & Review API (COMPLETE)**
  - `monocle/config.py`: added `save_config_patch(patch: dict)` — deep-merges allowed sections into `config.yaml` atomically via mkstemp+os.replace; respects `MONOCLE_CONFIG` env var; ignores `None` values
  - `monocle/index/base.py`: added `patch_file_metadata(file_path, updates)` abstract method to `IndexLayer`
  - `monocle/index/chroma.py`: `patch_file_metadata` implementation uses `collection.get(where=...)` + `collection.update()` with scalar-filtered metadata merge
  - `monocle/index/memory.py`: `patch_file_metadata` implementation updates `chunk.metadata` in-place
  - `monocle/routers/settings.py`: `GET /api/settings` (masked MCP key via `****` prefix + last 4 chars; secrets excluded by Pydantic); `PATCH /api/settings` (`review` and `ai` sections via `model_copy(update=...)`, atomic config.yaml write, hot-reload AI provider on provider change); `POST /api/settings/rotate-mcp-key` (`secrets.token_hex(32)`, atomic `.env` write, `os.environ` update)
  - `monocle/routers/review.py`: `GET /api/review` and `GET /api/review/count` (vault scan filter `review_status=="pending"`); `PATCH /api/review/{path}/approve` (patch_frontmatter + ChromaDB metadata sync; NoteNotFound auto-404); `POST /api/review/approve-all` (bulk approval)
  - `monocle/tests/test_settings.py`: 19 tests; `_temp_config` autouse fixture protects real config.yaml
  - `monocle/tests/test_review.py`: 25 tests
  - `monocle/tests/test_api.py`: removed settings/review routes from `STILL_STUB_ROUTES`
  - `.vscode/tasks.json`: added `test: settings` task
  - `docs/build-plan.md`: Active Milestone → M14; M13 → COMPLETE; section condensed to 4-line summary
  - `docs/milestones.md`: M13 full details archived
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **626 passed (44 new — 19 settings + 25 review, plus stub-route count adjustment), 6 deselected**, EXIT 0

- **M13 post-review hardening — resolved all 13 issues (2 bugs, 2 security, 5 testing gaps, 2 performance)**
  - **B1 (bug)**: `AIPatch.provider` changed from `str | None` to `Literal["ollama","foundry_local","azure"] | None`; `AIPatch.transcribe_backend` changed to `Literal["native","whisper_cpp","subprocess"] | None` — prevents invalid provider values from being persisted to `config.yaml` (would crash on next startup); requests with bad values now return 422
  - **B2 (bug)**: `ReviewPatch.queue_threshold` now `Field(None, ge=0.0, le=1.0)`; `ReviewPatch.auto_approve_threshold_pct` now `Field(None, ge=0, le=100)` — out-of-range values rejected with 422
  - **S1 (security)**: Added `TestPathTraversal.test_approve_path_traversal_blocked` and `test_approve_absolute_path_blocked` to `test_security.py` — `PATCH /api/review/%2e%2e/%2e%2e/.env/approve` returns 403
  - **S2 (security)**: Added `@limiter.limit("30/minute")` to `PATCH /api/settings`, `@limiter.limit("10/minute")` to `POST /api/settings/rotate-mcp-key`, `@limiter.limit("60/minute")` to `PATCH /api/review/{path}/approve`, `@limiter.limit("30/minute")` to `POST /api/review/approve-all`
  - **S3 (security)**: `_write_env_key` in `settings.py` now strips `\n` and `\r` from value before writing to prevent newline injection into `.env` file
  - **P1 (performance)**: Added `app.state._review_pending_count` lazy-O(1) pending count cache; `GET /api/review/count` returns cached value (warmed by `GET /api/review`, `PATCH approve`, `POST approve-all`); cache invalidated on any vault write (notes PUT/PATCH/DELETE, ingest, `_reindex_file` callback in `main.py`); each call to `list_review` warms the cache as a free side-effect; `review_count` falls back to full vault scan only when cache is cold (e.g. first call after startup or vault write)
  - **P2 (performance)**: `POST /api/review/approve-all` parallelized via `asyncio.gather` + `asyncio.Semaphore(10)` — approvals now run up to 10 concurrent vault+index patches instead of serial sequencing; cache updated to exact remainder after all completions
  - **T2 (test)**: `test_approve_all_sets_all_approval_fields` — verifies `approved_by`, `approval_mode`, and `approved_at` are written to frontmatter by approve-all bulk path
  - **T3 (test)**: `test_approve_all_partial_failure_count` — monkeypatches `patch_frontmatter` to raise on one path; asserts `approved == 2` not 3
  - **T4 (test)**: `TestPaginationEdgeCases.test_offset_beyond_total_returns_empty_items` — offset=9999 returns empty items but correct total
  - **T5 (test)**: `test_rotate_replaces_old_key_in_os_environ` — verifies old key is replaced (not merely added to) `os.environ` after rotation
  - **B3/tests**: `TestAIProviderHotReload` adds 2 tests — `test_patch_ai_provider_triggers_hot_reload` (mocks `monocle.ai.get_provider`, asserts called once on provider change) and `test_patch_ai_model_only_does_not_trigger_hot_reload` (asserts not called when only chat_model changes)
  - **9 input-validation tests**: `TestInputValidation` class — 422 for bad provider, bad transcribe_backend, out-of-range thresholds; 200 at exact boundaries
  - **3 pending-count cache tests**: `TestPendingCountCache` — sentinel value returned when cache hit; approve decrements cache; approve-all sets cache to remainder
  - New cache invalidation added to `notes.py` (PUT/PATCH/DELETE) and `ingest.py` (both endpoints) so any vault write within the same request context invalidates the count before returning
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **644 passed (18 new), 6 deselected**, EXIT 0

- **Executed M14 — CLI Commands (COMPLETE)**
  - Rewrote `monocle/cli.py` (~85-line stub → ~330-line full implementation): `serve` (uvicorn launch), `dev` (prints `[TELEMETRY]` block before uvicorn), `reindex` (asyncio.run → `ReindexAgent.run()` with embed_fn fallback), `pull-models` (Ollama model list + pull), `stats` (GET /api/stats via httpx), `search` (GET /api/search via httpx, table output), `export` (zip vault excluding `.versions`/`.trash`), `versions list/restore` (VaultLayer delegates via `versions_app = typer.Typer()` sub-app), `watch`/`capture` (reserved stubs with explanatory echo)
  - Added `live_server` session-scoped fixture to `monocle/tests/conftest.py`: spawns uvicorn subprocess on a free port, polls `/api/health` (15s timeout), yields base URL, tears down via SIGINT → wait 5s → kill
  - Created `monocle/tests/test_cli.py`: 21 tests, 8 classes — `TestHelp`, `TestReindex`, `TestExport`, `TestVersionsList`, `TestVersionsRestore`, `TestStats`, `TestPullModels`, `TestStubs`, `TestDevTelemetryBlock`; uses `typer.testing.CliRunner` (no `mix_stderr` arg); `os.environ["MONOCLE_DEV"]` leakage from CliRunner fixed with `patch.dict(os.environ)` + `monkeypatch.delenv("MONOCLE_DEV", raising=False)`
  - Created `monocle/tests/test_dev_mode.py`: 7 tests, 3 classes — `TestUnifiedDevStartup` (health, endpoints, clean shutdown), `TestWatcherAndSchedulerStartup` (watcher_running field, scheduler no crash), `TestDevTelemetryBlock` (real subprocess run, asserts `[TELEMETRY]` in stdout)
  - Added 4 tasks to `.vscode/tasks.json`: `cli: reindex`, `cli: reindex --force`, `cli: stats`, `cli: export`
  - Added `CLI: Reindex (debug)` launch config to `.vscode/launch.json`
  - Updated `docs/build-plan.md`: M14 → COMPLETE in tracker; active milestone → M15; M14 section condensed to 4-line completion summary
  - Updated `docs/milestones.md`: M14 full implementation details archived
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **675 passed (21 new), 6 deselected**, EXIT 0

- **M14 post-implementation code review — 8 issues resolved**
  - **Bug (High): `asyncio.get_event_loop()` in thread** — `embed_fn` closure in `reindex` CLI called `asyncio.get_event_loop().run_until_complete()`, which raises `RuntimeError` in thread-pool threads on Python 3.10+ (and confirmed 3.14). The error was silently swallowed, producing empty embeddings; with ChromaDB this causes a dimension-mismatch + silent chunk deletion. Fixed to `asyncio.run()` (`monocle/cli.py`)
  - **Bug (Medium): zip arcnames use OS path separator** — `Path.relative_to()` on Windows returns backslash paths; zip arcnames now forced to forward slashes via `.replace(os.sep, "/")` (`monocle/cli.py`)
  - **Bug (Medium): live_server pipe deadlock** — `live_server` subprocess spawned with `stdout=PIPE, stderr=PIPE` but pipes never drained; can block subprocess when output fills OS buffer. Changed to `subprocess.DEVNULL` and updated error handling to not try to decode from closed pipes (`monocle/tests/conftest.py`)
  - **Weak test assertion** — `test_list_invalid_path_exits_nonzero` accepted `"No versions" in result.output` as a passing path for traversal attempts; assertion tightened to require `exit_code != 0` only (`monocle/tests/test_cli.py`)
  - **Missing traversal test** — added `test_restore_path_traversal_blocked` to `TestVersionsRestore` (`monocle/tests/test_cli.py`)
  - **TestSearch added (4 tests)** — `test_search_returns_results`, `test_search_empty_results`, `test_search_ai_failure_exits_nonzero`, `test_search_limit_passed_to_index` (`monocle/tests/test_cli.py`)
  - **TestReindex embed_fn test** — `test_reindex_with_ai_provider` patches `monocle.ai.get_provider` (correct import intercept target) and asserts `embed.assert_called()` (`monocle/tests/test_cli.py`)
  - **live_server fixture telemetry noise** — added `MONOCLE_TELEMETRY_ENABLED=false` env var to session-scoped `live_server` fixture (`monocle/tests/conftest.py`)
  - `uv run python -m pytest monocle/tests/ -x --tb=short -q` → **681 passed (6 new), 6 deselected**, EXIT 0

- **Executed M16 — Chat UI (COMPLETE)**
  - Created `frontend/src/hooks/useChat.ts`: `useChat()` hook with SSE streaming via `streamChat()`, session persistence to `localStorage` (`monocle-sessions`, max 10), stable `send` callback via refs pattern (no stale closures), abort-on-session-switch, all 6 `ChatEvent` types handled (`token`, `tool_call`, `tool_error`, `note_created`, `done`, `error`)
  - Created `frontend/src/components/Chat/ChatMessage.tsx` + CSS: ReactMarkdown prose rendering, `<details>` tool call disclosures, `NoteCard` sub-component, streaming cursor with `@keyframes blink`
  - Created `frontend/src/components/Chat/ChatInput.tsx` + CSS: auto-grow textarea (max 6 lines / 144px), `Enter`→send / `Shift+Enter`→newline, optional voice button prop
  - Created `frontend/src/components/Chat/ChatScreen.tsx` + CSS: 6 starter tiles (2-column grid), session picker `<select>`, auto-scroll on new messages, thread render
  - Updated `frontend/src/components/SettingsModal/index.tsx`: added Theme section with `dark`/`light`/`system` radio buttons wired to `useTheme().setTheme`
  - Updated `frontend/src/App.tsx`: replaced M15 placeholder with real `ChatScreen` import
  - Created `frontend/src/Chat.test.tsx`: 24 tests covering ChatInput (8), ChatMessage (9), ChatScreen (7)
  - `npm run test -- --run` → **45 passed (3 files: api.test.ts 13, App.test.tsx 8, Chat.test.tsx 24)**, EXIT 0
  - `npx tsc --noEmit` → EXIT 0 (no type errors)
  - Updated `docs/build-plan.md`: M15 deliverables `[x]`; M16 deliverables `[x]`; Active Milestone → M17; M16 → COMPLETE in tracker

### Claude Haiku 4.5
- **Fixed double-click and timer issues in graph interaction**
  - Fixed double-click node detection: added `lastClickedNodeIdRef` to track which node was clicked; only triggers double-click when same node is clicked twice within 250ms (prevents cross-node false positives when rapidly clicking different nodes)
  - Fixed stale timer on graph reload: `loadGraph()` now clears pending click timers before reloading graph (prevents orphaned timers from re-selecting stale nodes after graph data changes via depth/filter/focus modifications)
  - Improved type safety in `handleNodeDragEnd()`: refactored from spread operator to `Object.assign` for better TypeScript index signature inference
  - Updated [GraphScreen.tsx](frontend/src/components/Graph/GraphScreen.tsx#L103) with `lastClickedNodeIdRef`, [handleNodeClick](frontend/src/components/Graph/GraphScreen.tsx#L248-L270) with paired timer+node-ID check, and [loadGraph](frontend/src/components/Graph/GraphScreen.tsx#L126-L135) with timer cleanup
  - `npx tsc --noEmit` → EXIT 0 (TypeScript clean after type assertion fix)
  - `npm run test -- --run` → **185 passed** (Graph tests cover new click/drag scenarios), EXIT 0

- **Fixed unsafe link rendering UX in Markdown preview**
  - **Issue:** Unsafe (non-http(s)) links were rewritten to `href="#"` but still rendered with `target="_blank"`, causing clicks to open a new tab to the current page (confusing UX)
  - **Solution:** Modified [NoteEditor.tsx](frontend/src/components/DocumentBrowser/NoteEditor.tsx#L362) `a` component renderer to only set `target="_blank" rel="noopener noreferrer"` when href is actually a valid http(s) URL; unsafe links now render as non-clickable `<span>` elements with `.unsafe-link` class
  - **Styling:** Added `.note-editor__preview .unsafe-link` to [NoteEditor.css](frontend/src/components/DocumentBrowser/NoteEditor.css#L177) — disabled appearance (grayed out, strikethrough) with `cursor: not-allowed`
  - **Test:** Added test case `renders unsafe (non-http) links as non-clickable text without target="_blank"` to [DocumentBrowser.test.tsx](frontend/src/DocumentBrowser.test.tsx#L596) — verifies `file://` links render as spans (no href attribute) while `https://` links remain clickable anchors with `target="_blank"`
  - `npx tsc --noEmit` → EXIT 0 (no type errors)

## 2026-03-20

### Claude Sonnet 4.6
- **Executed M17 — Document Browser, Search & Template Editor UI (COMPLETE)**
  - Created `frontend/src/hooks/useDebounce.ts`: `useDebouncedCallback<Args>` — stable callback via `useRef` + `useCallback`; `useEffect` keeps fnRef current across renders
  - Created `frontend/src/utils/yamlUtils.ts`: `metaToYaml()`, `buildRawDoc()`, `splitFrontmatter()`, `parseFrontmatter()` — minimal YAML serializer/parser for note frontmatter (no js-yaml dep)
  - Created `frontend/src/components/DocumentBrowser/FileTree.tsx` + `.css`: `buildTree(NoteRef[])` groups by directory prefix; recursive `TreeNodeRow` with expand/collapse; type icons; pending review badge; `data-testid` attributes
  - Created `frontend/src/components/DocumentBrowser/FormEditor.tsx` + `.css`: `TemplateField`/`TemplateSchema` exported interfaces; `StringField`/`ListField`/`BoolField` renderers; required field validation with error toast; `InlineToast` component
  - Created `frontend/src/components/DocumentBrowser/BacklinksPanel.tsx` + `.css`: `getNoteBacklinks(path)` on mount with cancellation guard; loading/empty/error states; `onDoubleClick` → `onNavigate`
  - Created `frontend/src/components/DocumentBrowser/NoteEditor.tsx` + `.css`: CodeMirror `EditorView` with `markdown()` + `yaml()` in YAML mode; `externalUpdateRef` prevents edit→state→editor loop; `useDebouncedCallback(saveNote, 2000)`; `Ctrl+S` immediate save; YAML/Preview/Form mode toggle; ReactMarkdown preview with `[[wikilink]]` click handler; FormEditor in form mode; Approve button (review_status=pending); 409 conflict toast
  - Created `frontend/src/components/DocumentBrowser/DocumentBrowserScreen.tsx` + `.css`: `useSearchParams` for `?path=` and `?wikilink=`; `listNotes(limit:500)` + `listTemplates()` on mount; FileTree sidebar + NoteEditor + BacklinksPanel right panel
  - Created `frontend/src/components/Search/SearchScreen.tsx` + `.css`: Semantic/Keyword mode toggle; semantic threshold slider (0–1, displayed as %); `semanticSearch`/`keywordSearch` API calls on submit; result cards with score badge; Open/Approve inline actions
  - Updated `frontend/src/App.tsx`: replaced placeholder `DocsScreen`/`SearchScreen` with real imports from DocumentBrowserScreen and SearchScreen
  - Created `frontend/src/DocumentBrowser.test.tsx`: 22 tests — FileTree (6), BacklinksPanel (4), DocumentBrowserScreen (3), NoteEditor isolated (7) + 2 placeholder; CodeMirror fully mocked
  - Created `frontend/src/Search.test.tsx`: 14 tests — layout (4), semantic search (4), keyword search (2), actions (4); `vi.clearAllMocks()` in top-level `beforeEach` to reset call counts between tests
  - Created `frontend/src/TemplateEditor.test.tsx`: 15 tests — rendering (7), validation (4), field interaction (4); uses `templates` array API, correct DOM assertions for field inputs
  - Fixed TypeScript errors: `DocumentBrowserScreen` cast `listTemplates()` result via `unknown` intermediate; `NoteEditor.handleApprove` cast metadata spread to `Note['metadata']`; `TemplateEditor.test.tsx` BASE_NOTE metadata filled required fields, mtime changed to number
  - `npm run test -- --run` → **113 passed (7 files, 51 new tests), EXIT 0**
  - `npx tsc --noEmit` → **CLEAN (exit 0)**
  - Updated `docs/build-plan.md`: M17 → COMPLETE; Active Milestone → M18; tracker row updated; session notes added

- **Executed M18 — Graph UI (COMPLETE)**
  - Created `frontend/src/components/Graph/GraphScreen.tsx`: ForceGraph2D force-directed graph with focus input + autocomplete (`listNotes({limit:500})`), depth toggle [1][2][3] (updates `max_degree`, re-fetches), type filter chips [Person/Note/Tag] (`buildTypesParam` maps chip state → `types=` query param; all active → no filter; none active → `'__empty__'` sentinel), Reset View button, degree-based visual encoding (`getNodeColor` → `rgba` with opacity `max(0.2, 1.0 - degree * 0.25)`; `getNodeSize` → `max(3, 15 * 0.85^degree)`), node click → side panel with top-5 related notes sorted by edge weight, double-click → `/docs?path=...` navigation using 250ms timer disambiguation, drag-end → node positions persisted to `localStorage` (`monocle.graph.positions`)
  - Created `frontend/src/components/Graph/GraphScreen.css`: full screen styles using design tokens (graph-specific color vars: `--graph-person`, `--graph-topic`, `--graph-edge`)
  - Created `frontend/src/Graph.test.tsx`: 31 tests across Layout (7) / Graph fetch (7) / Depth toggle (2) / Type filter chips (4) / Focus input (3) / Reset view (1) / Side panel (5) / Node positions (1) describe blocks; `react-force-graph` mocked as DOM proxy rendering node buttons; fake timers for 250ms click disambiguation
  - Updated `frontend/src/App.tsx`: replaced `GraphScreen` placeholder with real import; updated placeholder comment from M18–M20 → M19–M20
  - Updated `frontend/src/test-setup.ts`: added `window.ResizeObserver` stub (implements full DOM interface with typed constructor) — prevents `ResizeObserver is not defined` error in jsdom
  - Updated `frontend/src/App.test.tsx`: added `vi.mock('react-force-graph', ...)` + `vi.mock('./api/graph', ...)` + `vi.mock('./api/notes', ...)` — prevents `AFRAME is not defined` crash from aframe-extras bundled inside react-force-graph
  - `npm run test -- --run` → **145 passed (8 files, 32 new tests), EXIT 0**
  - `npx tsc --noEmit` → **CLEAN (exit 0)**
  - Updated `docs/build-plan.md`: M18 → COMPLETE; Active Milestone → M19; tracker row updated

- **M17/M18 post-review hardening — 7 source fixes + 72 new tests (185 total, up from 113)**
  - **Security (XSS)**: `NoteEditor.tsx` ReactMarkdown `a` renderer now sanitizes `href` — filters to `https?://` or replaces with `'#'`; adds `target="_blank" rel="noopener noreferrer"`
  - **Security**: `GraphScreen.tsx` `loadPositions()` validates deserialized JSON shape — rejects entries where `x` or `y` is not a number
  - **Bug**: `NoteEditor.tsx` `handleApprove` now flushes dirty edits before approving — `saveNote` returns `Promise<boolean>`; approve returns early on save failure
  - **Bug**: `GraphScreen.tsx` `handleTypeToggle` guard — when all chips are deactivated, sets empty graph locally instead of making API call with `__empty__` sentinel; also added comment to document the sentinel's purpose
  - **Bug**: `DocumentBrowserScreen.tsx` — wikilink no-match now shows a 4-second toast (`data-testid="wiki-toast"`) with "Note not found: …"
  - **Bug**: `SearchScreen.tsx` — `approvedPaths` state tracks approved file paths; Approve button hidden (`{!approvedPaths.has(r.file_path) && ...}`) after successful approval
  - **Bug**: `yamlUtils.ts` — string quoting regex now includes `!` (`/[:#\[\]{},|>&*'"?!]/`) to prevent unquoted YAML tags
  - **New file `frontend/src/utils/yamlUtils.test.ts`** (25 tests): scalar serialization, string quoting rules (including `!`), arrays, round-trip `buildRawDoc → splitFrontmatter → parseFrontmatter`, edge cases
  - **`DocumentBrowser.test.tsx`** — 11 new tests: BacklinksPanel error state, FileTree root-level notes, DocumentBrowserScreen wikilink resolve/no-match/handleSaved, NoteEditor Ctrl+S shortcut, NoteEditor wikilink preview navigation, NoteEditor approve-flushes-dirty
  - **`Graph.test.tsx`** — 4 new tests: invalid localStorage positions (non-object, non-numeric coords), drag persistence to localStorage, double-click navigation via `useNavigate`; mock infrastructure added (`mockNavigate`, `vi.mock('react-router-dom')`, ForceGraph2D `onNodeDragEnd` prop exposed)
  - **`Search.test.tsx`** — 1 new test: approve button disappears after successful approval (verifies `approvedPaths` conditional render)
  - `npm run test -- --run` → **185 passed (9 files, 40 new tests), EXIT 0**


## 2026-03-21
### Claude Sonnet 4.6
- Implemented M19: Voice Capture and Review Queue UI
  - Created frontend/src/api/transcribe.ts
  - Created frontend/src/components/VoiceModal/ (state machine + Web Speech API + MediaRecorder fallback + 8 templates)
  - Created frontend/src/components/ReviewQueue/ (slide-over, sorted confidence ascending, Approve/Fix/Approve All)
  - Created frontend/src/components/FailedCaptures/ (Retry/Dismiss wired to ingest-failure endpoints)
  - Modified App.tsx, AppShell.tsx, Topbar.tsx, Topbar.css, Chat/ChatScreen.tsx
  - Created frontend/src/VoiceCapture.test.tsx (38 tests)
  - npm run test passes: 224 tests, EXIT 0
- Marked M19 COMPLETE in docs/build-plan.md; archived to docs/milestones.md

## 2026-03-19
### Claude Sonnet 4.6
- M19 post-review fixes: 11 issues resolved across VoiceModal.tsx, App.tsx, App.test.tsx, VoiceCapture.test.tsx
- Bug fixes: moved handleDiscard before ESC useEffect (TDZ crash), show accumulated speech finals in live transcript, TODO comment on over-fetching in refreshFailedCount
- Security: replaced raw String(e) in transcription and save error dispatches with generic user-facing messages; added client-side 25 MB audio size guard before transcribeAudio call
- Tests: 11 new tests (MediaRecorder fallback path, review-state UI, save/discard/error actions, size guard, ReviewQueue Fix action + error state, FailedCaptures error state, App API mocks); 235 passing


- Fixed ReviewQueue aria-label accessibility issue: approve/fix buttons now use file_path fallback when note title is empty, preventing 'undefined' announcements to screen readers (matching visible text fallback); added regression test


## 2026-03-20
### Claude Sonnet 4.6
- Fixed Pydantic model serialization error in chat agent: Added \_rebuild_tool_input_models()\ method to \VaultTools\ class to rebuild input models with \BeforeValidator\ annotations after tool initialization. Resolves 'create_note_input is not fully defined' error when agent framework tries to generate JSON schema for tools.
- All backend tests passing (687/687); no regressions.


- Updated fix: Enhanced \_rebuild_tool_input_models()\ with:  1) \orce=True\ parameter for aggressive rebuild of MockCoreSchema; 2) Eager call to \	ool.parameters()\ to trigger schema generation at init time rather than lazily during agent.run_stream(). This resolves forward references and validators before observability code tries to serialize tools.


## 2026-03-20
### Claude Sonnet 4.6 (Code Review)
- **M19 Post-release code review** � reviewed VoiceModal, ReviewQueue, FailedCaptures, Topbar, App.tsx, transcribe.ts, ingest_failures.py, failed_registry.py
- **Bug fixed: stale closure on oiceBackend prop** (VoiceModal.tsx): startRecording useCallback had [] deps but used oiceBackend prop; users with web_speech backend configured would always fall through to MediaRecorder. Fixed by adding oiceBackend to deps array.
- **Bug fixed: FailedCaptures badge erases after panel close** (FailedCaptures.tsx): useEffect watching state.items.length called onCountUpdate(0) on RESET (panel close), clearing the Topbar badge permanently. Fixed by guarding the effect with if (!open) return.
- **Bug fixed: retry/dismiss errors silently swallowed** (FailedCaptures.tsx): RETRY_ERROR/DISMISS_ERROR reducer actions set state.error but the component only rendered the error alert when status === 'error' (load failures). Errors from retry/dismiss operations were never shown to users. Fixed: changed condition from status === 'error' to error !== null.
- **Security note**: FailedIngestRegistry stores raw exception strings (str(exc)) as error_message and the FailedCaptures panel renders them. No XSS risk (React text escaping), but these can expose internal file paths and service URLs. Mitigated by existing 1000-char truncation; full fix deferred (requires backend change to categorize errors).
- **Testing gaps addressed**: Added 6 tests � retry error display, dismiss error display (�2 each), badge count persistence after panel close, voiceBackend prop change picked up by startRecording
- **Result**: 689 backend tests passing, 260 frontend tests passing (6 new), EXIT 0


## 2026-03-20
### Claude Sonnet 4.6
- Added `append_to_note` tool to `VaultTools` (monocle/agents/tools.py)
  - Searches for best-matching note by query, reads it, appends content, persists and re-indexes
  - Returns error JSON when no note found (instead of raising)
- Updated agent system instructions to direct the LLM to use `append_to_note` when user asks to add to existing notes
- Updated tool count docstring in create_chat_agent (7 ? 8) and TestVaultTools assertion
- Added 5 new tests in TestVaultToolsExecution for append_to_note; 693 backend tests passing


## 2026-03-20
### Claude Sonnet 4.6
- Added chat input history navigation (ArrowUp/Down) to ChatInput.tsx
- 7 new tests in Chat.test.tsx history suite; 313 frontend tests passing
- Documented addition in docs/milestones.md M20 section


## 2026-03-20
### Claude Sonnet 4.6
- Implemented M21: Integration Testing & Obsidian Compatibility
- Created 25 Playwright E2E tests across 6 spec files (smoke, ingest_review, chat, graph, voice_modal, settings)
- Added playwright.config.ts and root package.json for @playwright/test
- Created .github/workflows/ci.yml (backend + frontend + E2E jobs)
- Rewrote README.md with prerequisites, quick start, MCP setup, keyboard shortcuts, CLI reference, and Obsidian compatibility
- Added test: e2e and test: ci-full VS Code tasks; added E2E Tests (Playwright debug) launch config

---

## 2026-04-13

### Claude Haiku 4.5
- **Environment & Logging Optimization**
  - Ran `uv sync` to initialize Python 3.14.0a7 environment (.venv created, 175 packages resolved, EXIT 0)
  - **Fixed high-volume logging in chat streaming (`monocle/routers/chat.py`)**
    - **Problem:** Per-update logs (`Update #N: ...`) and per-content logs (`Content[i]: ...`) at INFO level generate extremely high volume during token streaming, materially impacting performance and observability cost
    - **Solution:** Moved per-update and per-content logs from `logger.info()` to `logger.debug()` (lines 243–244, 255, 257, 282, 289); kept session-level summaries (start, end, error) at INFO for visibility
    - **Result:** Preserves debugging capability while eliminating production noise during token-by-token SSE emission
  - **Fixed user message recording in telemetry (`monocle/routers/chat.py`)**
    - **Problem:** `add_user_message_event()` was recording `body.messages[0].content` (first in request), but frontend sends full conversation history with the new user turn appended at the end, so oldest/irrelevant messages were being recorded instead of the actual user prompt
    - **Solution:** Changed to iterate `reversed(body.messages)` and find the last user-role message; correctly captures the message that triggered the request
    - **Result:** Conversation traces in AI Toolkit now show the actual user query, not stale context from prior turns
  - Verified syntax with `uv run python -m py_compile monocle/routers/chat.py` (EXIT 0)

- **Fixed SSE streaming issues in chat endpoint (`monocle/routers/chat.py`)**
  - **Issue 1: Token event detection broken** — `stream_with_tracing()` used substring matching (`'"token"' in event_str`) instead of parsing SSE frame format (`event: token\ndata: {...}\n\n`); `assistant_tokens` were never accumulated and `add_assistant_message_event()` never fired
    - **Fix:** Implemented proper SSE frame parsing — extract `event: token` line, check `event_type == 'token'`, then parse corresponding `data: {...}` JSON payload; accumulation now works correctly
  - **Issue 2: Tool error payload mismatch** — `tool_error` SSE payload used `"message"` key but frontend `ChatEvent` type / `useChat` reducer expects `"error"` key; tool error details were silently dropped in UI
    - **Fix:** Changed tool error SSE payload from `"message"` to `"error"` key (line 292) for frontend contract alignment
  - **Issue 3: Missing SSE-friendly headers** — `StreamingResponse` didn't set `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers; reverse proxies (esp. nginx) could buffer/cache responses, breaking real-time SSE delivery
    - **Fix:** Added headers dict to `StreamingResponse` constructor with both required headers (lines 429–432)
  - Verified all syntax changes with `uv run python -m py_compile monocle/routers/chat.py` (EXIT 0)

- **Python 3.14a7 + Pydantic compatibility fix**
  - **Root cause:** Pydantic 2.13.0b2 calls `typing._eval_type()` with `prefer_fwd_module=True` parameter; Python 3.14a7 removed this parameter, causing `TypeError` on model import
  - **Solution:** Created `monocle/compat.py` with compatibility shim that wraps `typing._eval_type()` to handle both old and new signatures (introspects kwargs and re-calls without incompatible params on Python 3.14+)
  - **Integration:** Imported `monocle.compat` at top of `monocle/models.py` (before Pydantic imports) to ensure patch is applied at module initialization time
  - **Result:** Models can now be imported on Python 3.14a7 without downgrading to 3.13

- **Fixed telemetry health-check filtering to cover all `/api/health/*` endpoints (`monocle/telemetry.py`)**
  - **Problem:** `_HealthCheckFilterSpanProcessor` only dropped traces where `http.route == "/api/health"` (exact match); new `/api/health/models` polling endpoint would still generate traces and reintroduce noise
  - **Solution:** Changed from exact match to `route.startswith("/api/health")` (line 50) so any `/api/health*` route is filtered
  - **Result:** All health-check related traces are now filtered regardless of sub-path

- **Hardened OpenTelemetry private API usage against version breakage (`monocle/telemetry.py`)**
  - **Problem:** `configure_telemetry()` imported and used several underscore-prefixed private/experimental OTel APIs (`_events`, `_logs`, `_log_exporter`, etc.) with no error handling; future versions of OTel may move or remove these APIs, causing telemetry to crash
  - **Solution:** Wrapped all private API initialization (lines 129–162) in a try/except that catches `ImportError` and `AttributeError`; on error, logs a clear warning and continues without AI Toolkit Input/Output event recording
  - **Result:** Graceful degradation — if OTel APIs change, telemetry continues to function; operator sees a clear warning explaining the feature is unavailable
- Updated .gitignore for root node_modules, playwright-report, test-results
- Marked M21 COMPLETE in build-plan.md; archived details to milestones.md
- 693 backend + 313 frontend tests passing; 25 E2E tests discovered


## 2026-03-26

### Claude Sonnet 4.6
- **Test coverage gap analysis** � identified 6 high-priority coverage gaps via subagent analysis of all backend and frontend test files
- **Created rontend/src/useChat.test.ts** � 30+ unit tests for the useChat hook (9 describe groups: initial state, send() SSE events [token/tool_call/tool_error/note_created/done/error/network], session persistence, selectSession, newSession, localStorage)
- **Created rontend/src/useDebounce.test.ts** � 12 tests for useDebouncedCallback hook (timer behavior, cancel(), unmount cleanup, stable reference identity, latest-fn-closure)
- **Expanded rontend/src/App.test.tsx** � added polling lifecycle (6 tests), settings propagation (2 tests), and route navigation (4 tests) describe groups; 8 ? 21 tests
- **Created monocle/tests/test_rate_limit.py** � 9 unit tests for the rate limiter (limiter config, 429 enforcement via _make_limited_app() helper); integration tests marked @pytest.mark.integration
- **Expanded rontend/src/api.test.ts** � added 8 error-path tests (HTTP 429, 500/502, network TypeError propagation, 204 No Content returns undefined)
- **Expanded rontend/src/SettingsModal.test.tsx** � added patchSettings rejection (2 tests: error shown, clears on next success) and rotateMcpKey failure (2 tests: error shown, hint unchanged); added data-testid="settings-error" to SettingsModal component
- All tests green: 737 backend passed (2 skipped), 378 frontend passed

- **MCP tool: create_reference_from_url**
  - Added `create_reference_from_url(url, extra_context)` MCP tool to `monocle/mcp_server.py`; fetches URL via httpx, strips HTML, uses AI to summarise, creates `reference` note with `web-reference` tag and `review_status: pending`; appends source URL as blockquote in body
  - Added `_strip_html()`, `_fetch_url_text()` helpers and `_URL_SUMMARISE_PROMPT` constant
  - Added 8 new tests in `TestMCPTools` (creates note, pending review, web-reference tag, body contains URL, no AI raises, non-http raises, triggers reindex, extra_context forwarded); updated `test_mcp_has_8_tools` ? `test_mcp_has_9_tools`
  - **749 tests passing (+8 new), EXIT 0**

---

## 2026-04-13 (Session 3)

### GitHub Copilot
- **Frontend bundle size optimization: Lazy-load aframe dependency**
  - **Problem:** Top-level `import 'aframe'` in `frontend/src/main.tsx` was loading the large aframe library (~300KB+) on every app route, even when the graph visualization UI was never accessed
  - **Solution:** 
    - Removed unconditional `import 'aframe'` from app entrypoint
    - Added async `loadAFrame()` helper function in `GraphScreen.tsx` component
    - Implemented `useEffect` hook to dynamically import aframe only when GraphScreen component mounts
  - **Result:** Reduced initial bundle size and improved startup time; aframe now loaded only when user navigates to graph route
  - **Impact:** Router entrypoint (Chat, Search, Docs, Stats, Settings, etc.) all now have faster initial load without unused dependencies
  - **Testing:** Frontend type-check passed (TypeScript validation confirms no type errors in changes)
