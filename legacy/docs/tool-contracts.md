---
type: reference
project: monocle
milestone: M31
last-updated: 2026-04-27
status: versioned-amendment-in-progress
---

# Monocle Canonical Tool Contracts

This document is the **single source of truth** for Monocle-owned data operations.
It is the primary deliverable of **M29 — MCP-First: Contract Freeze & Canonical Tool Schema**,
and is declared **FROZEN** as of **M31 — MCP Canonicalization** (2026-04-09).

> **VERSIONED AMENDMENT (M41):** `capture_thought` is being migrated from the direct note-write
> contract to a persisted ingest-session contract. All other tool schemas remain frozen.
> The accepted M41 change is documented in §2.3 before implementation.

MCP tools and chat agent tools MUST converge on the schemas and behaviors
defined here. Divergences from this document are bugs to be resolved in M32.

---

## 1. Canonical Operation Set

Seven operations are designated canonical Monocle-owned data operations. These are implemented
in `monocle/services/` (M30) and exposed via both the MCP tool layer and the chat agent tool
layer as thin wrappers.

| # | Canonical name | Purpose |
|---|---|---|
| 1 | `search_vault` | Semantic search across the vault using embeddings |
| 2 | `read_note` | Load a full note by vault-relative file path |
| 3 | `capture_thought` | Ingest unstructured text through the full ingest pipeline |
| 4 | `create_note` | Create a new note from a template with frontmatter |
| 5 | `update_note` | Update the body of an existing note |
| 6 | `get_graph` | Retrieve relationship graph data for a focus entity or the full vault |
| 7 | `create_reference_from_url` | Fetch a URL, AI-summarise it, and create a reference note |

Two additional tools are **chat-only** (no MCP equivalent required; they do not own Monocle data
operations and will not be exposed through the canonical MCP tool layer):

| Tool | Scope | Reason |
|---|---|---|
| `get_stats` | Chat-only | Thin read from `IndexLayer` + `VaultLayer`; no side effects; not worth MCP exposure |
| `list_notes` | Chat-only | Convenience browsing; covered by `search_vault` + `read_note` for external clients |

---

## 2. Canonical Tool Contracts

### 2.1 `search_vault`

**Purpose:** Embed a natural-language query and return semantically similar vault note excerpts.

**Input schema:**

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `query` | `str` | yes | — | Non-empty |
| `n_results` | `int` | no | `5` | 1–10 (capped internally) |
| `note_type` | `str \| null` | no | `null` | ChromaDB `type` metadata filter |
| `domain` | `str \| null` | no | `null` | ChromaDB `domain` metadata filter |

**Output schema (JSON array):**

```json
[
  {
    "file_path": "people/alice.md",
    "similarity": 0.874,
    "chunk": "First 500 characters of matching chunk…"
  }
]
```

**Side effects:** None (read-only).

**Required app state:** `AIProvider` (for embedding), `IndexLayer` (for search).

**Review/reindex semantics:** N/A.

**Chat-only decorations:** None. The agent tool and MCP tool are identical.

**Current divergence:** None. ✅

---

### 2.2 `read_note`

**Purpose:** Load the full content and frontmatter of a vault note by its vault-relative file path.

**Input schema:**

| Parameter | Type | Required | Constraints |
|---|---|---|---|
| `file_path` | `str` | yes | Vault-relative path, e.g. `people/alice.md` |

**Output schema (JSON object):**

```json
{
  "file_path": "people/alice.md",
  "title": "Alice Example",
  "type": "person_note",
  "domain": "work",
  "tags": ["onboarding"],
  "people": [],
  "body": "Full Markdown body…"
}
```

**Side effects:** None (read-only).

**Required app state:** `VaultLayer`.

**Review/reindex semantics:** N/A.

**Chat-only decorations:** None. The agent tool and MCP tool are identical.

**Current divergence:** None. ✅

---

### 2.3 `capture_thought`

**Purpose:** Accept raw unstructured text, persist it as an ingest session first, then run the
existing fast-capture prepare/approve/execute flow synchronously when possible.

**Input schema:**

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `content` | `str` | yes | — | Max 50,000 characters |
| `source` | `str` | no | `"mcp"` | `"web" \| "mcp" \| "voice" \| "teams" \| "import"` |

**Output schema (JSON object):**

```json
{
  "session_id": "sess_123",
  "state": "completed",
  "source_ids": ["src_123"],
  "affected_file_paths": ["work/decisions/2026-04-08-migrate-db.md"],
  "created_at": "2026-04-27T10:00:00Z",
  "updated_at": "2026-04-27T10:00:01Z"
}
```

**Side effects:**
- Creates a persisted ingest session and archives the raw source immediately.
- Attempts synchronous fast capture via the existing prepare/review/execute pipeline.
- May complete with affected note paths, or return a persisted fallback state when review blockers remain.

**Required app state:** `IngestSessionStore`, `IngestPreparationWorker`, `VaultLayer`, `ReindexQueue`.

**Review/reindex semantics:** The persisted ingest-session lifecycle owns preparation, blocker fallback,
execution, validation, and reindex behavior. `state` communicates whether the request completed
synchronously (`completed`) or needs further review (`in_review`, `awaiting_user`, `proposal_ready`, etc.).

**Chat-only decorations:** The chat agent does not expose `capture_thought` directly.
Unstructured capture in chat is handled by the `/api/ingest` endpoint via the UI ingest flow,
not by a chat agent tool. This is an MCP-only tool for external clients that send raw text
intended for persisted ingest-session processing.

**Current divergence:** No agent tool equivalent. MCP-only. ✅

---

### 2.4 `create_note`

**Purpose:** Create a new vault note from a named template, populating frontmatter fields and
writing a Markdown body. Notes created by agents or MCP clients are always placed in the
review queue (`review_status: pending`).

**Input schema:**

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `title` | `str` | yes | — | Non-empty |
| `body` | `str` | yes | — | Max 50,000 characters |
| `note_type` | `str` | no | `"observation"` | Any key in `monocle/vault/templates/` |
| `domain` | `str` | no | `"personal"` | Free-text domain label |
| `tags` | `list[str] \| null` | no | `null` | Normalised from any LLM tag format |

**Output schema (JSON object):**

```json
{
  "file_path": "work/ideas/2026-04-08-new-idea.md",
  "title": "New Idea",
  "status": "created"
}
```

**Side effects:**
- Creates a new `.md` file in the vault.
- Triggers reindex for the new file via `ReindexQueue`.
- Sets `review_status: pending` in frontmatter.

**Required app state:** `VaultLayer`, `ReindexQueue`.

**Review/reindex semantics:** Always `review_status: pending`. Does not run the confidence scoring
pipeline (that is `capture_thought`'s responsibility). Confidence is not written to frontmatter
by this tool — the review queue will show the note with `confidence: null` until the user approves.

**Chat-only decorations:** None. Agent tool and MCP tool are functionally identical.
The agent tool accepts tags as `str | list[str]` (with LLM normalisation) and MCP tool
accepts `list[str]` with `BeforeValidator(_normalize_tags)` — same result.

**Current divergence:** None (modulo tag normalisation entry point). ✅

---

### 2.5 `update_note`

**Purpose:** Update the body of an existing vault note. Preserves existing frontmatter.
Updates `updated` timestamp. Triggers reindex.

**Canonical input schema:**

| Parameter | Type | Required | Constraints |
|---|---|---|---|
| `file_path` | `str` | yes | Vault-relative path to EXISTING note |
| `body` | `str` | yes | Max 50,000 characters |

**Output schema (JSON object):**

```json
{
  "file_path": "people/alice.md",
  "status": "updated"
}
```

**Side effects:**
- Overwrites note body at `file_path`. Preserves all frontmatter fields.
- Updates `updated` timestamp in frontmatter.
- Triggers reindex via `ReindexQueue`.
- Writes to `.versions/` shadow before overwriting (via `VaultLayer.write_note`).

**Required app state:** `VaultLayer`, `ReindexQueue`.

**Review/reindex semantics:** Does not change `review_status`. Does not run confidence scoring.

**Chat-only decorations:**
- **Query-based discovery** (chat-only): If `file_path` is not known, the chat agent tool
  accepts an optional `query` parameter and runs a three-step resolution: wikilink → title scan
  → semantic search (0.6 threshold). This resolution lives in the agent tool adapter, not in
  the canonical service.
- **AI content merge** (chat-only): When an `AIProvider` is available, the chat agent tool
  calls `_merge_body()` to produce an LLM-merged body instead of a hard overwrite. This
  is a chat UX enhancement that lives in the agent tool adapter. The canonical service
  always does a hard overwrite; the adapter applies merge before calling the service.

**Current divergence:** ⚠️ **SIGNIFICANT** — resolving in M32.
- Agent tool: optional `query` parameter for discovery; body is AI-merged.
- MCP tool: `file_path` only (required); body is hard overwrite.
- Resolution: canonical service does hard overwrite with `file_path` required. Chat adapter
  does query resolution + AI merge as pre-processing before delegating to service. MCP tool
  stays as-is (hard overwrite, file_path required). Chat agent keeps merge as a chat-only
  orchestration enhancement.

---

### 2.6 `get_graph`

**Purpose:** Return a relationship graph centred on a focus entity (ego-graph) or the full
vault graph.

**Canonical input schema:**

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `focus` | `str \| null` | no | `null` | Vault-relative file path; `null` = full-vault mode |
| `max_degree` | `int` | no | `2` | BFS depth from focus (ignored in full-vault mode) |

**Output schema (JSON object, serialised `GraphResult`):**

```json
{
  "focus": "people/alice.md",
  "nodes": [
    { "id": "people/alice.md", "label": "Alice", "type": "person", "degree": 0, "weight": 5 }
  ],
  "edges": [
    { "source": "people/alice.md", "target": "work/project.md",
      "edge_type": "structured", "relation": "works-on", "weight": 1 }
  ]
}
```

**Side effects:** None (read-only). Result is cached per `(focus, max_degree, types)` key
in `GraphBuilder`; cache is invalidated by `ReindexQueue` events.

**Required app state:** `VaultLayer`, `GraphBuilder`.

**Review/reindex semantics:** N/A.

**Chat-only decorations:** None. The canonical contract covers the full graph API.

**Current divergence:** ⚠️ **NAMING DIVERGENCE** — resolving in M32.
- Agent tool: `get_person_graph(name_or_path)` — restricted to degree-1 people ego-graph only.
- MCP tool: `get_graph(focus, max_degree)` — full API, canonical.
- Resolution: `get_person_graph` in the chat agent adapter is deprecated. In M32, replace
  with a call to the canonical `get_graph` service with `max_degree=1`. The `name_or_path`
  wikilink resolution logic moves to the adapter layer.

---

### 2.7 `create_reference_from_url`

**Purpose:** Fetch a web page, strip boilerplate HTML, ask the AI provider to produce a structured
Markdown summary, and create a `reference`-type vault note tagged `web-reference`.

**Input schema:**

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `url` | `str` | yes | — | Must be `http://` or `https://` scheme |
| `extra_context` | `str \| null` | no | `null` | Optional focus instructions for the summariser |

**Output schema (JSON object):**

```json
{
  "file_path": "technologies/2026-04-08-some-library.md",
  "title": "Short Descriptive Title",
  "url": "https://example.com/article",
  "status": "created"
}
```

**Side effects:**
- Makes an outbound HTTP GET to `url` (network call).
- Calls `AIProvider.chat` once for summarisation.
- Creates a new `reference` `.md` file in the vault.
- Triggers reindex via `ReindexQueue`.
- Sets `review_status: pending`, `source: "web"`, tags prefixed with `["web-reference", ...]`.

**Required app state:** `VaultLayer`, `AIProvider`, `ReindexQueue`. Network access required.

**Review/reindex semantics:** Always `review_status: pending`.

**Chat-only decorations:**
- **URL pill opt-in flow**: The chat router (`routers/chat.py`) owns the URL detection heuristic,
  user confirmation prompt, and parallel prefetch batching. These are chat orchestration concerns
  and do NOT belong in the canonical tool or service.

**Current divergence:** ⚠️ **NAMING DIVERGENCE** — resolving in M32.
- Agent tool: `fetch_and_summarize_url` (non-canonical name, inline HTML-strip implementation).
- MCP tool: `create_reference_from_url` (canonical name, cleaner `_fetch_url_text` helper,
  shared `_URL_SUMMARISE_PROMPT` template).
- Resolution (D3 decision — see §3): `create_reference_from_url` is the canonical name.
  The agent tool `fetch_and_summarize_url` is renamed to `create_reference_from_url` in M32.
  HTML stripping and the prompt template move to the shared service in M30.

---

## 3. D3 Decision: `fetch_and_summarize_url` Disposition

**Decision:** `fetch_and_summarize_url` is **replaced** by `create_reference_from_url`.

**Rationale:**

1. Both tools do the same thing: fetch a URL, strip HTML, call AI to summarise, create a `reference` note.
2. `create_reference_from_url` is the canonical MCP name and the cleaner implementation
   (shared `_fetch_url_text` helper, `_URL_SUMMARISE_PROMPT` constant, proper boilerplate
   section removal including `<nav>`, `<aside>`, `<footer>`).
3. The agent tool `fetch_and_summarize_url` has duplicate HTML-strip logic that differs slightly
   from the MCP implementation — this is the exact drift the refactor aims to eliminate.
4. After M30 extracts `reference_service.create_reference_from_url()`, both the MCP tool and
   the (renamed) agent tool become thin wrappers calling the shared service.

**Implementation in M32:**
- Remove `fetch_and_summarize_url` from `VaultTools.tools`.
- Add `create_reference_from_url` to `VaultTools.tools` (delegates to service).
- Update `_ALLOWED_TOOL_HINTS` in `agents/__init__.py`.
- Update agent system prompt tool name reference.

**Chat-only orchestration that stays separate:**
- URL detection heuristic in `routers/chat.py`.
- User opt-in confirmation flow.
- Parallel prefetch batching.
- `context_injection` with URL content previews.

These are NOT part of `create_reference_from_url` or the underlying service.

---

## 4. Agent Tool → Canonical Name Mapping (D2)

Complete mapping of every current agent VaultTools method to its canonical status.

| Agent tool name | MCP tool name | Canonical name | Status |
|---|---|---|---|
| `search_vault` | `search_vault` | `search_vault` | ✅ Aligned |
| `read_note` | `read_note` | `read_note` | ✅ Aligned |
| `create_note` | `create_note` | `create_note` | ✅ Aligned |
| `update_note` | `update_note` | `update_note` | ⚠️ Different behavior — documented in §2.5 |
| `fetch_and_summarize_url` | `create_reference_from_url` | `create_reference_from_url` | ⚠️ Rename in M32 — see §3 |
| `get_person_graph` | `get_graph` | `get_graph` | ⚠️ Rename + generalize in M32 — see §2.6 |
| *(none)* | `capture_thought` | `capture_thought` | MCP-only; chat uses `/api/ingest` directly |

**Summary:** 3 tools are already aligned. 3 need resolution in M32. 1 is MCP-only by design.

---

## 5. MCP Tool → Canonical Name Mapping

Complete mapping of every current MCP tool to its canonical status.

| MCP tool name | Agent tool name | Canonical name | Status |
|---|---|---|---|
| `search_vault` | `search_vault` | `search_vault` | ✅ Aligned |
| `read_note` | `read_note` | `read_note` | ✅ Aligned |
| `create_note` | `create_note` | `create_note` | ✅ Aligned |
| `update_note` | `update_note` | `update_note` | ⚠️ Different behavior — documented in §2.5 |
| `create_reference_from_url` | `fetch_and_summarize_url` | `create_reference_from_url` | ⚠️ Agent rename in M32 |
| `get_graph` | `get_person_graph` | `get_graph` | ⚠️ Agent rename in M32 |
| `capture_thought` | *(none)* | `capture_thought` | ✅ MCP-only by design |

---

## 6. Services Layer (M30 — COMPLETE)

The following `monocle/services/` modules are implemented and operational (M30 complete 2026-04-09).
Function signatures shown here are the canonical interface; implementations are extracted from
current MCP/agent tool logic.

| Module | Function | Source implementation |
|---|---|---|
| `monocle/services/search.py` | `search_vault(vault, index, ai, query, n, threshold, filters) -> list[ScoredNote]` | `mcp_server.search_vault`, `tools.VaultTools.search_vault` |
| `monocle/services/notes.py` | `read_note(vault, file_path) -> Note` | `mcp_server.read_note`, `tools.VaultTools.read_note` |
| `monocle/services/notes.py` | `create_note(vault, reindex_queue, title, body, note_type, domain, tags) -> Note` | `mcp_server.create_note`, `tools.VaultTools.create_note` |
| `monocle/services/notes.py` | `update_note(vault, reindex_queue, file_path, body) -> Note` | `mcp_server.update_note` (canonical: hard overwrite) |
| `monocle/services/graph.py` | `get_graph(graph_builder, focus, max_degree, types, n) -> GraphResult` | `mcp_server.get_graph` |
| `monocle/services/references.py` | `create_reference_from_url(vault, ai, reindex_queue, url, extra_context) -> Note` | `mcp_server.create_reference_from_url` (preferred implementation) |
| `monocle/services/ingest.py` | `capture_thought(pipeline, content, source) -> IngestResponse` | `mcp_server.capture_thought` |

**Adapter responsibilities that remain in tool wrappers (not in services):**
- Agent `update_note`: query-based note discovery (wikilink → title scan → semantic search) before calling `update_note(file_path, body)`.
- Agent `update_note`: AI content merge before calling service with merged body.
- Agent `get_graph` (from deprecated `get_person_graph`): wikilink name resolution before calling `get_graph(focus, ...)`.
- Both wrappers: tag normalisation from LLM-produced formats.
- MCP wrappers: input validation, auth context, JSON serialisation.
- Agent wrappers: `@ai_function` decorator binding, tool schema generation.

---

## 7. Behavioral Divergences to Resolve

All divergences must be resolved no later than M32.

| # | Operation | Agent behavior | MCP behavior | Resolution |
|---|---|---|---|---|
| 1 | `update_note` inputs | Accepts `file_path` OR `query` | `file_path` required | `file_path` required in service; query resolution stays in adapter |
| 2 | `update_note` body | AI content-aware merge | Hard overwrite | Hard overwrite in service; merge stays in adapter as pre-processing |
| 3 | `create_reference_from_url` name | `fetch_and_summarize_url` | `create_reference_from_url` | Rename agent tool in M32 |
| 4 | `create_reference_from_url` HTML stripping | Inline (heavier; strips `<nav>`,`<header>` etc.) | `_fetch_url_text()` helper (cleaner) | Adopt MCP helper in shared service |
| 5 | `get_graph` vs `get_person_graph` | `get_person_graph(name_or_path)`, degree=1 fixed | `get_graph(focus, max_degree)`, full API | Rename agent tool; name resolution in adapter |
| 6 | `read_note` output | No `url` field in output | No `url` field in output | ✅ Already identical |

---

## 8. Contract Parity Test Targets (M31)

Tests to add in M31 asserting that MCP tool handlers and chat agent tools resolve to the same
service behavior and result fields for identical inputs.

For each canonical operation:

1. Call the operation via a mock MCP tool handler.
2. Call the same operation via the corresponding VaultTools method.
3. Assert that both return JSON with identical top-level keys.
4. Assert that both trigger `ReindexQueue.push` (for write operations).
5. Assert that both set `review_status: "pending"` on created notes.

Special cases:
- `update_note`: assert both call `write_note` with the same `file_path` and a non-empty body.
  Assert that MCP does NOT apply AI merge; assert that the service `update_note` function is
  the same reference in both call paths (via M30 services).
- `get_graph`: assert agent adapter resolves name-or-path before calling service, and that the
  returned graph structure is identical.
