# Monocle — Copilot Instructions

## START HERE — Every Session

> **Action required:** Open and read [`docs/build-plan.md`](../docs/build-plan.md) before writing any code or making any decisions. It is the single working document for this project. Do not rely on memory from previous sessions.

`docs/build-plan.md` contains: active milestone, ordered deliverables, acceptance criteria, test commands, quick-reference table, and all design overrides. Everything else is reference material.

**Source-of-truth hierarchy:** `docs/build-plan.md` → `docs/srs.md` → `docs/prd.md` → `docs/ui-design.md`.  
**Override:** SRS §2.6 FR-PROC-01–05 describes an outdated multi-process architecture. The authoritative architecture is the single unified process in `docs/build-plan.md`.

## Session Housekeeping (required)

1. **Update `docs/build-plan.md`** — mark each deliverable `[x]` as completed; update `## Current Status` and `## Milestone Tracker` when a milestone finishes. Never mark a deliverable complete without running the appropriate test command first.
2. **Append to `GHI-ACTION-LOG.md`** (project root) — under a `## YYYY-MM-DD – <Model Name>` heading, summarize meaningful action taken (files created/modified, decisions made, milestones completed). Use a new heading per calendar day and subheading per model.  Like actions on the same day by the same model can be summarized together. Example:
   ```markdown
   ## 2026-03-15 
   ### Claude Sonnet 4.6
   - Created `.github/copilot-instructions.md` and `GHI-ACTION-LOG.md`
   - Updated `docs/build-plan.md` Current Status
   ```

---

## Architecture

Single unified process. `python -m monocle serve` starts FastAPI + MCP server + APScheduler + integrated inbox file watcher (async task). `python -m monocle dev` adds prefixed logging (`[API]`, `[WATCHER]`, `[SCHEDULER]`, `[INGEST]`, `[AGENT]`) and crash-restart.

```
Capture (web/voice/Teams/MCP) → POST /api/ingest → IngestPipeline → VaultLayer (.md files)
                                                                    ↕ re-index trigger
                                                              ChromaDB (embeddings)
GET /api/* (search/graph/notes) ← VaultLayer + IndexLayer
GET /mcp  (FastMCP, Streamable HTTP) ← AIProvider + VaultLayer
```

Key ports: backend `127.0.0.1:8000`, frontend dev server `localhost:5173` (Vite), OTLP `localhost:4317` (AI Toolkit).

---

## Key Abstractions

| Class | Location | Purpose |
|---|---|---|
| `AIProvider` | `monocle/ai/base.py` | `OllamaProvider` / `FoundryLocalProvider` / `AzureOpenAIProvider` — runtime-selectable via `ai.provider` config |
| `IndexLayer` | `monocle/index/base.py` | `ChromaIndex` (prod) / `MemoryIndex` (tests — no real embeddings) |
| `IngestPlugin` | `monocle/ingest/plugin.py` | `TextPlugin`, `AudioPlugin`, `TeamsPlugin` |
| `RoutingAgent` | `monocle/agents/routing.py` | Checks template `sentence_starters` first (no LLM); falls back to `prompts/routing.md` |

Factories: `get_provider(settings) -> AIProvider`, `get_index(settings) -> IndexLayer`.  
Plugin registry: `IngestPluginRegistry` singleton — `register(plugin)`, `resolve(request) -> IngestPlugin`.

---

## Ingest Pipeline (8 steps, in order)

1. Plugin resolution → 2. Content extraction (incl. `transcribe` for audio) → 3. Routing (sentence-starters fast path, then LLM) → 4. Metadata extraction via `prompts/extract.md` *(steps 3 & 4 run concurrently via `asyncio.gather` when LLM routing is needed)* → 5. Note construction → 6. File write + immediate re-index (no watcher dependency) → 7. Confidence scoring (deterministic — **no LLM call**; reuses embedding from step 6) → 8. Frontmatter patch.

Failure in steps 3–5 writes a `.error.md` sidecar alongside the source file.

---

## Note Frontmatter Schema

Every ingested note must have these fields (see `monocle/models.py` `NoteMetadata`):
```yaml
type: "person_note"         # see Note Types table in build-plan.md
domain: "work"
confidence: 0.85            # 0.35*template_match + 0.30*metadata_coverage + 0.20*tag_plausibility + 0.15*entity_match
review_status: "pending"    # pending | approved
approved_by: null           # "system:auto" or user identity
approval_mode: null         # auto | manual
```
`normalise_frontmatter()` (`monocle/vault/normalise.py`) fills defaults on read. Missing `review_status` defaults to `"approved"` (existing Obsidian notes are trusted).

---

## Test Commands

```bash
# Backend unit tests (run after every backend change)
python -m pytest monocle/tests/ -x --tb=short -q

# Frontend unit tests
cd frontend && npm run test -- --run

# E2E (requires server running at http://localhost:8000)
playwright test

# Type-check frontend
cd frontend && npx tsc --noEmit
```

**Copilot must run the appropriate command before marking any deliverable `[x]`.**

---

## Conventions

- **No `print()` in application code** — always use `logging.getLogger(__name__)`.
- **OpenTelemetry is cross-cutting**: `monocle/telemetry.py` exports `get_tracer()`, `get_meter()`, `span()` (async context manager), `timed()`. Import from there, not directly from OTel SDK.
- **Vault path validation everywhere**: resolve to absolute path with `os.path.realpath`; reject anything outside `vault.path` with `403`.
- **Server binds `127.0.0.1` by default**: `0.0.0.0` requires explicit opt-in in `config.yaml`.
- **`IngestRequest` must include `allow_duplicate: bool = False`** (FR-ING-11 duplicate-detection advisory flow).
- **Two template directories** (distinct purposes): `monocle/vault/templates/` = machine-readable YAML schemas (Python package); `vault/.templates/` = user-facing Markdown in the vault directory.
- **Prompt files** in `prompts/*.md` are committed; `prompts/local/*.md` are gitignored user overrides loaded first.
- **Settings are server-authoritative**: `localStorage` is a UI render cache only — never the source of truth.
- **Embedding dimensions fixed at 1536** across all providers. Re-index only required if `embed_dimensions` config value changes.
- **`GET /api/settings`** must mask the MCP key to last 4 characters only.
- **CORS**: allow `localhost:{port}` and `127.0.0.1:{port}`; in dev mode also `localhost:5173`. No wildcard origins.
- **Rate limits**: 30 req/min on `/api/ingest` and `/api/transcribe`; 60 req/min on `/api/chat`.

---

## Frontend Conventions

- React 18 + Vite 5, no class components, no Redux — React Context + `useReducer` only.
- No UI component library — custom design tokens in CSS custom properties (see `docs/ui-design.md` §3).
- Typed API wrappers generated from OpenAPI: `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts`
- Dark mode is the default theme.


