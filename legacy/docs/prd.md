# Product Requirements Document — Monocle

**Version:** 2.7  
**Date:** 2026-04-27  
**Status:** Draft  
**Supersedes:** v2.6  
**Changes:** Narrowed the near-term product around trust-first capture, a unified capture workbench, lean chat, and distinct omnisearch; deferred Teams, OneNote, third-party MCP composition, and separate-process runtime support to a future phase.

---

## 1. Problem Statement

Personal AI assistants have no shared memory and no access to a user's personal knowledge base. Notes live in siloed vault files, chat threads, voice memos, clipboard pastes, and ad-hoc captures. Structured thinking — decisions, relationship context, project history — is never available to AI when it's needed. Weekly reflection is skipped because synthesis is too slow. Unstructured inputs are captured but never cleaned up, reviewed, or connected before they matter.

**Monocle** is a personal AI-powered knowledge system centered on trusted capture: a vault-backed document store, a semantic search and retrieval index, a capture-and-review workflow, a multi-agent orchestration backend, and a React web application that ties them together. It makes your existing notes available to AI tools via MCP, provides a first-class editing and graph-browsing experience, and gives the user one place to prepare, review, approve, or retry captured knowledge before it becomes trusted context.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Provide a single, durable personal knowledge store that any AI tool can read from and write to via MCP |
| G2 | Ingest unstructured inputs (voice, raw text, inbox files, explicit URL captures) and convert them to structured, reviewable Markdown notes |
| G3 | Surface connected knowledge through semantic search, a relationship graph, and scheduled analysis |
| G4 | Run entirely locally with no mandatory cloud accounts; support migration to Azure with config changes only |
| G5 | Remain Obsidian-compatible — the vault directory is the source of truth and can be opened in Obsidian simultaneously |
| G6 | Provide a unified capture workbench for prepared sessions, pending review notes, and failed captures |
| G7 | Keep chat and MCP interactions lean and explicit, using deliberate capture actions instead of hidden background automation |

## 3. Non-Goals (Phase 1)

- Real-time collaboration or shared vaults
- Mobile application
- Binary file attachments (images, PDFs) beyond text extraction
- Custom plugin/extension system
- Billing or quota management UI
- Broad channel integrations such as Teams or OneNote in the near-term local core
- Separate-process deployment topologies in the near-term local core
- Multi-user support (planned for Phase 2)

---

## 4. Users

### Phase 1 — Single User (personal deployment)

**Primary persona: Lucas**  
A developer and knowledge worker who uses multiple AI tools, takes notes across Obsidian, browser text, voice memos, and AI chats, and wants captured knowledge available as trustworthy context in whatever tool they're currently working in. Key pain points: context loss between AI sessions, unprocessed raw notes, and no disciplined review path between capture and trusted knowledge.

### Phase 2 — Multi-User

Each user has an isolated vault and collection within a shared deployment. Authentication and user-scoped storage deferred to Phase 2 design.

---

## 5. System Components

### 5.1 Web Frontend (React + Vite)

| Feature | Description |
|---|---|
| Chat interface | Text + voice input, streaming AI responses, chat starters mapped to note templates and common query patterns, **session history** (last 10 sessions persisted to browser localStorage), and explicit URL capture handoff instead of automatic URL prefetch |
| Document browser | File-tree view of the vault; switches into full Markdown editor mode with frontmatter support |
| AI-assisted editing | Within the editor, invoke an agent to update, extend, or restructure the current note |
| Semantic search | Fast indexed full-text + vector search across the full vault |
| Node graph view | Visual map of entities and relationships; first mode: social graph (people nodes linked by shared topics, interactions, co-mentions) |
| Capture workbench | Unified workspace for prepared ingest sessions, pending-review notes, and failed captures, with true-up, approve/fix, retry, inspect-source, and dismiss actions |
| **Note versioning** | Every overwrite of an existing note saves a shadow copy to `.versions/`; CLI commands to list and restore versions |
| **Command palette** | `Ctrl+/` opens a searchable list of all application actions for keyboard-first navigation |

### 5.2 Document Store (Vault-First)

| Concern | Approach |
|---|---|
| Source of truth | Markdown files in a vault directory on the server filesystem |
| Format | Obsidian-compatible: YAML frontmatter + Markdown body; wikilinks (`[[Note Name]]`) supported |
| Note templates | Predefined templates with required/optional frontmatter keys (person, decision, project, meeting, weekly-summary, etc.) |
| Inbox watching | Integrated inbox watcher monitors `vault/inbox/`, archives raw sources, and creates persisted ingest sessions for later preparation/review or fast capture |
| Scheduled re-index | Full vault re-index runs on a configurable schedule (default: weekly, `0 3 * * 0`) to catch manual Obsidian edits made outside the inbox; also run on startup if the index is empty; triggered ad-hoc via `POST /api/agents/reindex` or `python -m monocle reindex` |
| Vector index | ChromaDB stores per-chunk embeddings + frontmatter metadata + file paths; full content not stored in DB |
| Query flow | Semantic search → matching paths + metadata → server loads only needed files on demand |
| Obsidian compatibility | Vault directory opens in Obsidian simultaneously; no exclusive lock; standard `.md` format |

### 5.3 API Layer (FastAPI)

| Concern | Approach |
|---|---|
| Frontend API | REST endpoints for all UI operations (notes CRUD, search, graph, ingest, stats) |
| MCP server | Streamable HTTP MCP server for AI client integration (Claude Desktop, VS Code Copilot, Cursor, Claude Code) |
| Process orchestration | Single unified FastAPI process with integrated inbox watcher and APScheduler; watchdog file monitoring runs as an async task; `python -m monocle serve` starts all components together with prefixed logging; pytest fixtures automatically manage startup/shutdown for integration and E2E tests. This is the only supported near-term topology; optional process separation is deferred to a future phase. |
| Content capture | UI/API capture flows go through `POST /api/ingest` (and session review/execute endpoints), creating persisted ingest sessions with immutable source archival; explicit URL capture feeds the same reviewable workflow; external MCP clients also retain a synchronous `capture_thought` tool for one-shot direct ingest |
| Agent scheduler | APScheduler for cron-style background tasks (weekly review, scheduled re-index) |

### 5.4 Agent Backend (Microsoft Agent Framework)

| Concern | Approach |
|---|---|
| Framework | Microsoft Agent Framework (Python) for multi-agent orchestration |
| Interaction modes | **Interactive** — user-triggered via chat, results stream to UI. **Background** — scheduled tasks run autonomously, results written to vault as new notes |
| Runtime selection | Settings select active chat/embed/STT models from a registry of **Ollama**, **Foundry Local**, **Azure AI Services**, and **OpenAI** entries; chat and embed may come from different providers via the composite provider path |
| Routing agent | Explicit routing agent examines raw content (and uses sentence starters as classification hints) to dispatch to the appropriate handler and template; decoupled from the extraction phase |
| Prompt files | Agent system prompts stored as editable `.md` files in `prompts/`; users can tune classification and extraction behaviour without code changes; local overrides in `prompts/local/` (gitignored) take precedence |
| Canonical tools | Chat agent tools are thin adapters over shared Monocle service functions. The MCP server exposes the same canonical tool contracts for external clients. Canonical Monocle-owned operations: `search_vault`, `read_note`, `capture_thought`, `create_note`, `update_note`, `get_graph`, `create_reference_from_url`. Additional chat-only tools: `list_notes`, `get_stats` |
| Tool canonicality | MCP is the authoritative tool contract for Monocle-owned data operations. Chat remains the orchestration layer for streaming UX, session handling, and tool-hint policy; capture actions such as URL intake are explicit handoffs rather than hidden router-level automation |

### 5.5 LLM Index

| Concern | Approach |
|---|---|
| Phase 1 | ChromaDB (file-backed `PersistentClient`, cosine distance, per-chunk embeddings) |
| Migration path | `IndexLayer` ABC isolates ChromaDB; `AzureSearchIndex` implementation targets Azure AI Search + Cosmos DB for Phase 2 |
| Index content | Embeddings per ~512-token chunk with 64-token overlap; frontmatter stored as metadata; file path stored for lazy load |

### 5.6 Services Layer (`monocle/services/`)

All Monocle-owned data operations are implemented once in a shared services layer. Both the MCP server tools and the chat agent tools are thin wrappers that delegate to these service functions.

| Service Module | Operations |
|---|---|
| `monocle/services/search.py` | `search_vault(query, n, threshold, filters)` — semantic search pipeline |
| `monocle/services/notes.py` | `read_note(file_path)`, `create_note(...)`, `update_note(...)` — vault CRUD with reindex |
| `monocle/services/graph.py` | `get_graph(focus, max_degree, types, n)` — graph build and cache |
| `monocle/services/references.py` | `create_reference_from_url(url, context)` — URL fetch, AI summarise, reference note creation |
| `monocle/services/ingest.py` | `capture_thought(content, source)` — synchronous MCP fast path through the full ingest pipeline |

**Architectural principle:** Service modules contain all business logic, side effects, reindex queue triggering, and review-status semantics. Tool wrappers (MCP and agent) validate input format, call services, and serialize output — they contain no business logic of their own.

**MCP as canonical schema:** The MCP tool layer defines the authoritative external contract for Monocle-owned operations. Chat agent tools expose the same canonical operations internally under the same names. Both converge on the same service implementations.

---

## 6. Common Workflow Automations

### 6.1 Weekly Knowledge Summary
- **Trigger:** Scheduled (configurable cron, default Friday 17:00) or user-invoked via chat or chat starter
- **Process:** Agent reads notes modified in past 7 days → retrieves their pre-computed 1536-dim embeddings from ChromaDB → applies lightweight clustering (simple k-means or agglomerative clustering) to discover latent themes → generates a descriptive label per cluster → LLM summarises each cluster → optionally further segmented by `domain` frontmatter field (e.g., "Work", "Personal")
- **Output:** New summary note written to vault at `summaries/YYYY-WW.md`; summary persists for multi-week trend analysis
- **Extensibility:** Topic clustering is pluggable; alternative clustering strategies can be added in the future via the plugin architecture without modifying the core pipeline

### 6.2 Unstructured Note Ingestion
- **Inputs:** Voice memo (browser microphone or uploaded audio file), raw text paste, inbox file, or explicit URL capture
- **Process:** Content is archived outside the vault and persisted as an ingest session → background preparation extracts a digest, related-note candidates, contradiction warnings, and proposed `create_note` / `update_note` actions → the user reviews, edits, true-ups, or fast-captures the session from the capture workbench → approved actions execute through the canonical MCP-backed note services with deterministic validation and re-index
- **Output:** The capture workbench and document browser reflect the prepared session and resulting note changes; fast capture can still complete the full flow immediately for clean sessions
- **On failure:** A failed-ingest record plus any diagnostic sidecar/artifact is preserved so the UI can inspect, retry, or dismiss the failed session without losing raw source provenance

### 6.3 Chat Starters / Quick Queries
- Clickable prompt buttons shown at the start of every new chat session
- Examples: "What are my notes on [person]?", "Summarize recent decisions about [project]", "What action items are open?", "Start weekly review", "Capture a voice note"
- Each starter maps to an agent invocation, a vault query, or opens a capture flow

### 6.4 Unified Capture Workbench
- **Trigger:** Automatically after every ingest operation (text, voice, inbox, explicit URL capture)
- **Process:** At the end of ingestion, a deterministic confidence score (0.0–1.0) is computed reflecting (a) template match certainty, (b) required frontmatter field coverage, (c) tag semantic consistency with body content, and (d) whether detected people already exist as person notes in the vault. The system then checks `review.auto_approve_threshold_pct`: `0` means no auto-approval; any value from `1` to `100` auto-approves notes whose confidence percentage meets or exceeds that threshold. Every note records `review_status`, `approved_by`, `approved_at`, and `approval_mode` so the approval path is auditable.
- **Workbench model:** The user sees one unified capture workbench containing prepared ingest sessions, pending-review notes, and failed captures. Prepared sessions can be true-upped, edited, approved, or fast-captured. Pending notes can be approved or fixed. Failed captures can be inspected, retried, or dismissed.
- **Review settings:** The user controls two values: a review queue threshold (default `1.0`) that determines which low-confidence pending notes require attention, and an auto-approve threshold percentage (default `0`) that determines whether high-confidence notes are approved immediately. Setting auto-approve to `90` means a confidence of 90% or above is approved automatically.
- **Output:** A single topbar badge increments for capture work requiring user attention. The workbench sorts lowest-confidence or most-actionable items first and routes detailed note editing into the Document Browser when needed.
- **Confidence computation:** Deterministic score = `0.35 * template_match + 0.30 * metadata_coverage + 0.20 * tag_plausibility + 0.15 * entity_match`. No LLM call required. Weights are adjustable.

### 6.5 Prompt Management
- Agent system prompts (routing/classification, metadata extraction, weekly review) are stored as editable `.md` files in the `prompts/` directory at the project root.
- Each file has YAML frontmatter (`agent`, `version`, `description`) followed by the full system prompt body.
- Changes take effect on the next agent invocation — no server restart required.
- `prompts/*.md` are committed to version control. `prompts/local/*.md` (gitignored) provide user-local overrides that take precedence over the defaults.

### 6.6 Note Templates
- A single unified YAML schema per template type (consolidating user-facing structure with extraction rules) is stored in `monocle/vault/templates/`.
- Each schema defines: required/optional frontmatter fields, `sentence_starters` for routing, body outline, and `maps_to_types` (the `type` frontmatter value written to notes).
- The Document Browser includes a user-friendly template editor UI that renders YAML frontmatter fields as form inputs, plus a note editor that lets users toggle between Markdown source editing and a lightweight rich preview editing mode for common formatting tasks.
- Templates can be customized or extended without code changes by editing the YAML (for developers) or via the editor UI (for all users).

---

## 7. Product Phases

### Phase 1 — Local Core (this document)

Full React web app, single user, local vault + ChromaDB, persisted ingest sessions/source archive, a unified capture workbench, lean chat focused on retrieval and authoring, distinct omnisearch, and runtime-selectable Ollama, Foundry Local, Azure AI Services, or OpenAI-backed models.

### Phase 2 — Cloud + Multi-User (named, not specified here)

- Azure AI Services as primary agent backend option (already in runtime dropdown)
- Azure AI Search + Cosmos DB as index/storage via `IndexLayer` swap
- Azure Functions as compute host
- Broad channel integrations such as Teams and OneNote, if still justified
- Optional process separation for high-volume vaults, if still justified
- Per-user vault isolation and authentication layer

### Phase 3 — Long-Term Roadmap (future, not specified)

- **Plugin Architecture Framework:** A formal plugin system for extending Monocle with custom features without modifying core code. Examples: custom clustering algorithms for weekly summaries, new capture sources, custom note types, themed UI skins. Plugins register via a registry pattern and follow a stable interface contract.
- **Optional Clustering Plugins:** Alternative topic-modelling strategies may be added later as optional plugins. Default remains lightweight k-means-style clustering.
- **Backlinks Navigation:** Cross-reference tracking and a "Linked Notes" sidebar in the Document Browser showing inbound and outbound connections with relation types and metadata.
- **Logseq Compatibility:** Support Logseq-format daily notes, journal pages, and `((block-ref))` block references as an alternative to Obsidian. A `LogseqPlugin` in the plugin registry handles import/export. Vault format (standard `.md`) remains compatible.
- **Migration Documentation:** Step-by-step guides for moving from local (ChromaDB + Ollama) to cloud (Azure AI Search + Cosmos DB + Azure AI Services). The `IndexLayer` ABC and fixed 1536-dim embeddings ensure this requires no code changes.

---

## 8. Success Metrics

| Metric | Target |
|---|---|
| Voice-to-structured-note latency | < 15 seconds end-to-end |
| Semantic search latency (p95) | < 1 second across vault up to 10,000 notes |
| Chat first-token latency | < 2 seconds |
| Weekly summary quality | Surfaces ≥ 3 non-obvious patterns per run (qualitative) |
| Confidence score calibration | Notes manually approved without edits have confidence ≥ 0.8 in ≥ 80% of cases |
| Obsidian compatibility | Vault opens and renders correctly in Obsidian with no manual intervention |
| Setup time (clean machine) | Automated setup via script where possible; Ollama model pull time is environment-dependent and is not a hard constraint |

---

## 9. Constraints

- Backend: Python 3.11+
- Frontend: Node.js 20+, React 18+, Vite 5+
- At least one configured AI backend must be reachable before first use (for example Ollama, Foundry Local, Azure AI Services, or OpenAI)
- Embedding vector dimensions fixed at **1536** across all providers; switching AI providers does not require a full re-index as long as the `embed_dimensions` config value remains 1536. A re-index is only required if the dimension value itself changes.
- MCP transport: Streamable HTTP (SSE deprecated per MCP spec 2025-03-26)
- Vault directory must be filesystem-accessible to the server process
- No secrets or credentials in source control; all via `.env`. `config.yaml` is also git-ignored; a `config.yaml.example` is committed instead.
- Server binds to `127.0.0.1` (loopback) by default; `0.0.0.0` is an explicit opt-in for network exposure
- MCP access key is authenticated via `x-monocle-key` header (preferred) or `?key=` query param (discouraged; logged by servers)

---

## 10. Open Questions

| # | Question | Owner | Due |
|---|---|---|---|
| OQ1 | ~~Should note links be directional or bidirectional-only?~~ **Resolved:** Links use a dual mechanism — plain `[[wikilinks]]` in the body (untyped, Obsidian-compatible) plus a structured `links` frontmatter field with a required `target` and optional `relation` + arbitrary k/v metadata. Both sources feed the graph; structured links additionally render `relation` labels on edges. See FR-VLT-05. | — | Resolved in SRS v2.2 |
| OQ2 | ~~Delete policy for vault notes: hard delete (remove `.md`), soft-delete (move to `.trash/`), or archive?~~ **Resolved:** Shadow versioning via `.versions/` on every overwrite; delete moves to `.trash/` (soft-delete). Both directories excluded from the index and Obsidian sync. | — | Resolved in SRS v2.1 |
| OQ3 | ~~Should the graph view show note nodes as well as person nodes in Phase 1, or people-only?~~ **Resolved:** Unified ego-graph — all node types (person, note, tag) shown by default. Focused on a selected node with degree-based opacity and size decay (each hop −25% opacity, −15% size). Full-vault mode (no focus) uses weight-proportional sizing. Type filter chips allow excluding node types. See FR-API-13, FR-WEB-07. | — | Resolved in SRS v2.2 |
| OQ4 | ~~OneNote import format: MHTML/HTML files, or Microsoft Graph API?~~ **Resolved:** Ingest pipeline uses an extensible `IngestPlugin` architecture. OneNote support is **deferred to a future phase**. A `OneNotePlugin` can be added without modifying pipeline code. Near-term built-in plugins focus on text and audio capture. See FR-ING-08. | — | Resolved in SRS v2.2 |
