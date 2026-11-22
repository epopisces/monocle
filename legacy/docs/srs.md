# Software Requirements Specification — Monocle

**Version:** 2.6  
**Date:** 2026-04-27  
**Status:** Current  
**Supersedes:** v2.5
**Changes:** Reset the near-term mainline around trust-first capture, a unified capture workbench, lean chat, distinct omnisearch, and a single supported runtime topology; deferred Teams, OneNote, third-party MCP composition, and separate-process runtime support to a future phase.

---

## 1. System Overview

Monocle is a personal AI-powered knowledge system with a React web frontend, a FastAPI backend, an Obsidian-compatible vault as its document store, a ChromaDB vector index, a persisted ingest-session store, an immutable source archive, and a Microsoft Agent Framework orchestration layer. Browser/API/inbox/explicit-URL capture surfaces feed the ingest-session system, while the MCP server also exposes a synchronous `capture_thought` fast path for one-shot external ingestion. Chat is intentionally lean: it focuses on retrieval and authoring, and hands off capture work into explicit capture flows rather than hidden router-level automation. All Monocle-owned data operations are implemented once in a shared services layer (`monocle/services/`); both the MCP server tools and the chat agent tools are thin wrappers that delegate to those shared services. MCP is the canonical tool contract for Monocle-owned operations.

### 1.1 Architecture

```
Capture Surfaces            FastAPI Backend                              Consumers
──────────────────          ───────────────────────────────────────────   ─────────────────
React Web App   ──REST──►  ┌─ Ingest Router                             MCP Clients
Voice (browser) ──REST──►  │  ├─ Ingest Session Store (SQLite/file)     (Claude, Copilot,
Inbox Watcher   ──local──► │  ├─ Source Archive (immutable files)        Cursor…)
Explicit URL    ──REST──►  │  └─ AI Provider (extract/digest/linking)   │
MCP capture_tool──MCP───►  ├─ Vault Router (CRUD, search, history)      │
                           │  └─ File Watcher / Inbox poller            ▼
                           ├─ Agent Router                       GET /mcp (Streamable HTTP)
                           │  └─ Chat Agent (tool wrappers)     GET /search (REST)
                           └─ MCP Server (canonical tools)      GET /notes (REST)

                    ↓ both delegate to ↓
          monocle/services/  (single implementation of all data operations)
          ├─ search.py       ├─ notes.py      ├─ graph.py
          ├─ references.py   ├─ ingest.py     └─ history.py

Vault (filesystem .md files) ◄──► ChromaDB (embeddings + frontmatter metadata)
Source Archive (immutable raw files) ──manual review only; excluded from embedding/default search
```

### 1.2 Deployment (Phase 1)

A single unified process constitutes a full deployment:

| Process | Command |  Description |
|---|---|---|
| Main API + Services | `python -m monocle serve` | FastAPI + MCP server + APScheduler (scheduled re-index, weekly review) + integrated inbox file watcher (async task) + frontend static files; binds `127.0.0.1:8000` |

**Developer shortcut:** `python -m monocle dev` starts the unified process with prefixed stdout logging.

**Future optimization:** Near-term mainline supports only the unified process. Optional process separation may be revisited in a future phase if high-volume vaults justify it.

- **ChromaDB:** file-backed at the path in `config.yaml` (default: `./data/chroma`)
- **Vault:** Markdown files on local filesystem at the path in `config.yaml`
- **AI runtime:** Ollama or Foundry Local running separately on localhost; Azure AI Services for cloud option

### 1.3 Technology Stack

**Backend (Python 3.11+)**

| Concern | Technology | Notes |
|---|---|---|
| Web framework | FastAPI 0.115+ | ASGI, Pydantic v2 |
| ASGI server | uvicorn | Dev; Azure Functions ASGI for Phase 2 |
| Vector index | ChromaDB 0.6+ | `PersistentClient`, cosine distance |
| File watcher | watchdog 4+ | Vault change detection + re-index trigger |
| Agent framework | Microsoft Agent Framework (Python) | Multi-agent orchestration |
| AI backends | Ollama SDK, Foundry Local (OpenAI-compatible), OpenAI SDK (`AsyncOpenAI`, `AsyncAzureOpenAI`) | Runtime-selectable per model entry |
| MCP server | `mcp[cli]` FastMCP | Streamable HTTP transport |
| Task scheduler | APScheduler 3.x | Cron-style background agents (weekly review, scheduled re-index) |
| Topic modelling | scikit-learn KMeans/AgglomerativeClustering | Default weekly review clustering (fast, lightweight) |
| Config | PyYAML + python-dotenv | `config.yaml` + `.env` |

**Frontend (Node.js 20+)**

| Concern | Technology | Notes |
|---|---|---|
| Framework | React 18+ | Hooks, context, no class components |
| Build tool | Vite 5+ | Dev server + production build |
| Code editor | CodeMirror 6 | Markdown + YAML frontmatter mode |
| Graph view | React Force Graph | D3 + WebGL force-directed graph |
| Charts | Recharts | Stats screen charts |
| State | React Context + useReducer | No Redux |
| Styling | CSS custom properties | Design token system from UI Design doc |

---

## 2. Functional Requirements

Requirements are grouped by subsystem. Each requirement has a unique ID (`FR-<SUBSYSTEM>-<N>`) for traceability.

### 2.1 Configuration (FR-CFG)

**FR-CFG-01:** The system SHALL read configuration from a `config.yaml` file co-located with the entrypoint (or at the path specified by env var `MONOCLE_CONFIG`). **On first run, if `config.yaml` does not exist, the `Settings` loader SHALL automatically copy `config.yaml.example` to `config.yaml` and log a one-time notice, so a fresh clone works without manual setup.**

**FR-CFG-02:** The system SHALL read secrets from a `.env` file and from environment variables. Environment variables take precedence over `.env`.

**FR-CFG-03:** The `config.yaml` SHALL support the following top-level fields:

```yaml
ai:
  chat_model_key: llama3.2
  embed_model_key: nomic-embed
  stt_key: null
  embed_dimensions: null       # null = auto-detect from the first successful embedding call
  url_reference_timeout_s: 120
  transcribe_backend: subprocess   # "native" | "whisper_cpp" | "subprocess"
  transcribe_url: http://localhost:9000
  ollama_base_url: http://localhost:11434
  foundry_local_base_url: http://localhost:5272
  models:
    - key: llama3.2
      name: llama3.2
      role: chat
      provider: ollama
    - key: nomic-embed
      name: nomic-embed-text
      role: embed
      provider: ollama
    - key: gpt-4o-openai
      name: gpt-4o
      role: chat
      provider: openai

vault:
  path: ./vault                # Absolute or relative path to Markdown vault
  inbox_path: ./vault/inbox    # Dedicated inbox monitored by the watcher process
  templates_path: ./vault/.templates
  watch: true                  # Enable integrated inbox watcher (async task in main process)
  debounce_ms: 2000            # Watcher debounce per file path in milliseconds (2 s = FR-WTCH-03)

index:
  backend: chroma              # "chroma" (Phase 1) | "azure_search" (Phase 2)
  chroma_persist_path: ./data/chroma
  collection_name: notes
  chunk_size_tokens: 512       # Tokens per chunk for embedding
  chunk_overlap_tokens: 64

agents:
  weekly_summary:
    enabled: true
    cron: "0 17 * * 5"         # Friday at 17:00
    domains: ["work", "personal"]
  reindex:
    enabled: true
    cron: "0 3 * * 0"          # Sunday at 03:00 — catches Obsidian edits outside inbox

review:
  queue_threshold: 1.0         # Show pending notes with confidence <= threshold
  auto_approve_threshold_pct: 0 # 0 disables auto-approval; 90 auto-approves confidence >= 0.90
  confidence_weights:
    template_match: 0.35
    metadata_coverage: 0.30
    tag_plausibility: 0.20
    entity_match: 0.15

server:
  host: 127.0.0.1              # Loopback by default; set 0.0.0.0 only to expose to network
  port: 8000
  mcp_access_key_env: MCP_ACCESS_KEY
  frontend_dist: ./frontend/dist  # Path to Vite production build output (served as static files)
telemetry:
  enabled: true
  otlp_endpoint: http://localhost:4317  # AI Toolkit gRPC port; any OTLP-compatible backend
  otlp_transport: grpc          # grpc | http (http uses port 4318)
  log_level: INFO               # DEBUG | INFO | WARNING | ERROR
  log_format: text              # text (dev) | json (prod)
  enable_sensitive_data: true   # include prompts and completions in traces

ui:
  chat_session_history_limit: 10  # Number of chat sessions retained in browser localStorage

ingest:
  background_prepare_enabled: true
  prepare_poll_interval_s: 5.0
  max_idle_prepare_jobs: 1
  related_notes_limit: 5
  source_excerpt_chars: 4000

history:
  retention_versions: 50          # retain the most recent N stored versions per note

**FR-CFG-04:** Azure-backed model entries SHALL read credentials from environment variables: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_API_VERSION`. `AZURE_OPENAI_EMBED_DEPLOYMENT` and `AZURE_OPENAI_CHAT_DEPLOYMENT` MAY override the selected model names.

**FR-CFG-04a:** OpenAI-backed model entries SHALL read credentials from the `OPENAI_API_KEY` environment variable.

**FR-CFG-05:** Foundry Local backend configuration SHALL be read from env var `FOUNDRY_LOCAL_BASE_URL` (overrides config) and `FOUNDRY_LOCAL_API_KEY` (if required by the local server).

**FR-CFG-06:** The system SHALL validate configuration at startup and fail with a descriptive error if required fields are missing or inconsistent.

**FR-CFG-07:** Switching active chat/embed/STT models among `ollama`, `foundry_local`, `azure`, and `openai` entries SHALL require no code changes — only config/env var changes.

---

### 2.2 AI Provider Abstraction (FR-AI)

**FR-AI-01:** The system SHALL implement an `AIProvider` abstract base class:

```python
class AIProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str: ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str: ...
```

**FR-AI-02:** Four provider implementations SHALL be included:
- `OllamaProvider` — uses `ollama.AsyncClient`; models configured in `config.yaml`
- `FoundryLocalProvider` — uses OpenAI-compatible HTTP API at Foundry Local base URL
- `AzureOpenAIProvider` — uses `openai.AsyncAzureOpenAI` with credentials from env vars
- `OpenAIProvider` — uses `openai.AsyncOpenAI` with the public OpenAI API key from env vars

**FR-AI-03:** `get_provider(settings: Settings) -> AIProvider` SHALL resolve `ai.chat_model_key` and `ai.embed_model_key` against the model registry. When both roles share a provider/base URL, it SHALL return a single provider instance; when they differ, it SHALL return a composite provider that delegates chat and embed calls to the appropriate backends.

**FR-AI-04:** If the configured Ollama model is not found locally, the system SHALL automatically pull it and log progress.

**FR-AI-05:** Transcription SHALL be selected via the `TranscriptionProvider` abstraction. `transcribe_backend="native"` SHALL use the active provider's built-in transcription endpoint when available (Foundry Local, Azure OpenAI, or OpenAI); Ollama SHALL require `whisper_cpp` or `subprocess` transcription.

**FR-AI-06:** The provider SHALL expose `extract_note_metadata(content: str, template_hint: str | None) -> NoteMetadata` which returns the fields defined in the canonical model (§4.5). The fields populated by this method are:

```python
class NoteMetadata(BaseModel):
    type: str                    # note template type (e.g. "person_note")
    template: str = "other"      # template file name used to create the note (e.g. "person")
    title: str = ""              # extracted title; used to derive the filename slug
    domain: str = ""             # e.g. "work", "personal"
    people: list[str] = []
    tags: list[str] = []
    action_items: list[str] = []
    frontmatter_extras: dict = {}  # additional template-specific frontmatter fields
    # Note: `confidence`, `review_status`, `approved_by`, `approved_at`, `approval_mode`
    # are present in the canonical NoteMetadata model (§4.5) but are NOT populated by
    # extract_note_metadata(). They are set by the IngestConfidence scoring step (step 7)
    # after this method returns, then written to frontmatter via patch_frontmatter().
```

**FR-AI-07:** Embedding and metadata extraction SHALL run concurrently via `asyncio.gather` to minimize ingest latency.

---

### 2.3 Index Layer (FR-IDX)

**FR-IDX-01:** The system SHALL implement an `IndexLayer` abstract base class:

```python
class IndexLayer(ABC):
    @abstractmethod
    async def upsert_chunks(self, file_path: str, chunks: list[NoteChunk]) -> None: ...

    @abstractmethod
    async def delete_file(self, file_path: str) -> None: ...

    @abstractmethod
    async def search(self, query_embedding: list[float], n: int, threshold: float,
                     filters: dict | None) -> list[ScoredChunk]: ...

    @abstractmethod
    async def get_stats(self) -> IndexStats: ...
```

**FR-IDX-02:** The Phase 1 implementation SHALL use ChromaDB `PersistentClient` with `space="cosine"`. The `ChromaIndex` class SHALL implement `IndexLayer`. The active index backend is selected from `index.backend` in `config.yaml`.

**FR-IDX-03:** The collection SHALL be created at startup via `get_or_create_collection`. The `embed_dimensions` config SHALL be validated against the collection's actual dimension if it already exists.

**FR-IDX-04:** Index entries (ChromaDB documents) SHALL contain:

| Field | Type | Notes |
|---|---|---|
| `id` | string | `"{file_path}::{chunk_index}"` |
| `document` | string | Chunk text (passed as `documents=`) |
| `embedding` | list[float] | Pre-computed; passed as `embeddings=` |
| `file_path` | string | Relative path from vault root |
| `chunk_index` | int | 0-based position within file |
| `note_type` | string | Frontmatter `type` value |
| `tags` | JSON string | From frontmatter |
| `people` | JSON string | From frontmatter |
| `domain` | string | From frontmatter |
| `source` | string | `web` \| `mcp` \| `voice` \| `import` |
| `created_at` | ISO 8601 string | Frontmatter or file ctime |
| `updated_at` | ISO 8601 string | File mtime at index time |

**FR-IDX-05:** `search` SHALL convert ChromaDB cosine distance to similarity score: `similarity = 1 - distance`. Results with `similarity < threshold` SHALL be filtered out.

**FR-IDX-06:** A factory `get_index(settings: Settings) -> IndexLayer` SHALL select the implementation. The Phase 2 `AzureSearchIndex` implementation SHALL be added by implementing the same ABC without changes to callers.

---

### 2.4 Vault Layer (FR-VLT)

**FR-VLT-01:** The vault is the source of truth. All notes are stored as `.md` files in the vault directory configured in `config.yaml`. The database and index are derivatives.

**FR-VLT-01a (Vault Domain Structure — Flexible and Customizable):** The vault organizes notes into **domains** (top-level directories like `work/`, `technologies/`, `people/`, etc.) for user-facing browsing convenience. **Critical principle:** Folder structure is **not prescriptive**; it is purely a UX aid.
- Note *type* and *domain* are indexed via frontmatter metadata (YAML fields), not folder paths.
- All system queries (`search`, `graph`, `ingest routing`, CLI commands) use metadata, never folder structure.
- Users can freely add, remove, or rename top-level domain folders without code changes or data loss.
- Default domains are provided as a sensible starting point (`people/`, `work/`, `technologies/`, `theology/`, `entertainment/`, `projects/`, etc.), but users can customize.
- Multi-org/multi-context handling: use a `org` frontmatter field (e.g., `org: "Acme Corp"`) rather than nested folder hierarchies — keeps structure flat and flexible.
- Future (Phase 2+): Settings UI will allow users to customize, pin, and template domains without developer involvement.

**FR-VLT-02:** The system SHALL implement a `VaultLayer` class that provides filesystem CRUD for vault notes:

```python
async def list_notes(folder: str | None) -> list[NoteRef]
async def read_note(file_path: str) -> Note          # loads .md, parses frontmatter
async def write_note(file_path: str, note: Note) -> None  # atomically writes .md
async def delete_note(file_path: str) -> None
async def move_note(from_path: str, to_path: str) -> None
async def create_from_template(template_type: str, content: str) -> Note
def resolve_wikilink(name: str) -> str | None         # returns file_path or None
```

**FR-VLT-03:** All note files SHALL use YAML frontmatter (delimited by `---`) followed by a Markdown body. Frontmatter is parsed with `python-frontmatter`.

**FR-VLT-04:** The system SHALL include a unified set of note templates as YAML schemas in `monocle/vault/templates/` (one file per template type). Each schema consolidates extraction rules, frontmatter structure, required/optional fields, `sentence_starters` for routing, body outline, and metadata validation. Schemas include a `maps_to_types` field defining the `type` frontmatter value(s) that map to this template. Built-in templates (10 total):

| Template File | Required Frontmatter Keys |
|---|---|
| `person.yaml` | `type`, `name`, `tags`, `domain` |
| `decision.yaml` | `type`, `title`, `tags`, `domain`, `date`, `status` |
| `project.yaml` | `type`, `title`, `tags`, `domain`, `status` |
| `meeting.yaml` | `type`, `title`, `tags`, `people`, `date` |
| `weekly_summary.yaml` | `type`, `week`, `domain`, `date_range` |
| `action_item.yaml` | `type`, `title`, `status`, `due_date`, `people` |
| `idea.yaml` | `type`, `title`, `tags`, `domain` |
| `observation.yaml` | `type`, `title`, `tags`, `domain` |
| `reference.yaml` | `type`, `title`, `url`, `tags`, `domain` |
| `blank.yaml` | `type` (fallback when routing confidence < 0.6) |

**FR-VLT-04a:** The Document Browser editor SHALL include a **Template Editor UI** that allows non-developers to customize templates without editing YAML directly. The UI renders each YAML schema as form fields (text inputs for strings, multiselect for lists, toggles for booleans), with optional description text from the schema. Templates can be edited inline and saved back to their YAML files. This feature is optional for Phase 1 but enables user-driven template evolution.

**FR-VLT-05:** Two link mechanisms are supported and are complementary:

1. **Body wikilinks** (`[[Note Name]]`) — Plain Obsidian-compatible inline links written in the Markdown body. Parsed by `parse_wikilinks(body)`. These represent untyped connections.

2. **Structured `links` frontmatter field** — A YAML list that allows optional relation metadata per link. Each entry has a required `target` (resolved via `resolve_wikilink`) and optional additional key-value pairs:

```yaml
links:
  - target: "Sarah Chen"          # required; resolved via resolve_wikilink()
    relation: "manages"            # optional; free-text relation type
    since: "2024-01"               # optional; arbitrary additional metadata
  - target: "Consulting Project"  # minimal entry (target only)
    relation: "contributes-to"
```

`resolve_wikilink(name)` SHALL search for the first `.md` file whose filename (without extension) matches `name` case-insensitively, returning the vault-relative file path or `None`. Both link mechanisms feed the graph; structured links additionally carry `relation` and metadata onto graph edges.

`parse_links_field(links: list) -> list[LinkRef]` normalises the links frontmatter into a consistent `LinkRef` structure, accepting both plain strings (`"Note Name"`) and dicts with a `target` key.

**FR-VLT-06:** Note writes SHALL be atomic: new content SHALL be written to a temp file created via `tempfile.mkstemp` **in the system temp directory** (not inside the vault), then renamed into place via `os.replace`. Using a temp dir outside the vault ensures the file watcher never triggers on the temp file, and the final rename is atomic on POSIX filesystems (best-effort on Windows).

**FR-VLT-07:** Before overwriting an existing note, `write_note` SHALL save the previous version to `<vault_root>/.versions/<relative_path>/<updated_at_ms>.md` where `updated_at_ms` is the ISO 8601 timestamp with **millisecond precision** (e.g. `2026-03-13T09-12-34.567Z`) from the existing frontmatter `updated` field. Millisecond precision prevents silent collision when a note is written multiple times within the same second. Stored versions SHALL be subject to a configurable retention limit (`history.retention_versions`). The `.versions/` directory SHALL be excluded from the file watcher (FR-WTCH-01), the `reindex` command, and `GET /api/notes` listings. The CLI command `versions list <file_path>` SHALL enumerate stored versions; `versions restore <file_path> <timestamp>` SHALL overwrite the current file with a chosen version.

### 2.5 File Watcher & Re-Index (FR-WTCH)

**FR-WTCH-01:** The `InboxWatcher` SHALL run as an **async task integrated into the unified FastAPI process** (Phase 1). It monitors only `vault/inbox/` (configured via `vault.inbox_path`) and SHALL NOT watch the rest of the vault. Supported file types: `.md`, `.txt`, audio files (`.webm`, `.mp3`, `.wav`, `.m4a`). The integration point is `main.py`'s lifespan hook; the watcher runs in a thread-pool executor so file-system callbacks do not block the async event loop. No alternate runtime topology is in scope for the near-term mainline.

**FR-WTCH-02:** On new file detection in the inbox:
1. The watcher archives the source file into the immutable source store with provenance metadata
2. The watcher creates a persisted ingest session rather than writing a vault note directly
3. The new ingest session is queued for dormant background preparation and surfaced as a notification/review item for the user
4. On failure: the system records the ingest session or source as failed and preserves the raw source for manual inspection

**FR-WTCH-03:** A 2-second debounce per file path SHALL be applied to handle multi-write saves before triggering ingest.

**FR-WTCH-04 (API-mediated re-index):** The main API SHALL enqueue file-scoped re-index work whenever a note is written via `PUT /api/notes`, `PATCH /api/notes`, approved ingest-session execution output, or fast-capture execution output. The queue SHALL coalesce pending work by `file_path` so repeated saves of the same file result in at most one outstanding re-index job. New files created by approved ingest execution SHALL be prioritised ahead of background editor-save updates.

**FR-WTCH-04a (Editor save coalescing):** Repeated editor-driven saves for the same file within a configurable idle window (default: 10 seconds since the latest write) SHALL collapse into a single re-index. `PUT /api/notes` and `PATCH /api/notes` responses SHALL complete after the vault write succeeds; they SHALL NOT block on embedding work unless the caller explicitly requests synchronous indexing.

**FR-WTCH-05 (Scheduled re-index):** A `ReindexAgent` SHALL run on the schedule configured in `agents.reindex.cron` (default `"0 3 * * 0"` — weekly, Sunday 03:00). It SHALL:
1. Scan all `.md` files in the vault
2. Compare each file's frontmatter `updated` timestamp against the ChromaDB chunk `updated_at` metadata
3. Re-embed only files where `updated` > `updated_at` in ChromaDB (incremental re-index)

This process catches Obsidian edits and any changes made outside the API.

**FR-WTCH-06 (Startup check):** On first startup, if `index.get_stats().total_chunks == 0` and the vault contains notes, the system SHALL trigger a full vault re-index before accepting requests. `GET /api/health` SHALL return `status: "indexing"` during this process.

**FR-WTCH-07 (On-demand reindex):** `POST /api/agents/reindex` and `python -m monocle reindex [--force]` SHALL trigger an immediate full re-index. `--force` clears the existing index first.

**FR-WTCH-08:** The inbox watcher SHALL exclude from monitoring: `.versions/`, `.trash/`, `.templates/`, `prompts/`, `data/`.

### 2.6 Ingest Sessions & Review Flow (FR-ING)

**FR-ING-01:** The ingest subsystem handles unstructured input (text, voice, inbox file, explicit URL reference, or any future registered plugin source) by creating a persisted ingest session rather than immediately writing a structured vault note.

**FR-ING-02:** Ingest SHALL be a two-phase workflow:
1. Session preparation: extraction, digest, related-note linking, contradiction analysis, and proposal generation
2. Approved execution: canonical MCP-backed `create_note` / `update_note` operations, post-apply validation, and re-index

**FR-ING-03:** An ingest session SHALL be persisted independently of any active chat or browser session and SHALL support dormant background preparation during application idle windows.

**FR-ING-04:** The system SHALL accept an ingest request model that creates or updates an ingest session:

```python
class IngestRequest(BaseModel):
  content: str | None = None
  audio: bytes | None = None
  audio_mime: str | None = None
  source: Literal["web", "mcp", "voice", "import", "inbox", "chat"]
  template_hint: str | None = None
  allow_duplicate: bool = False
  fast_capture: bool = False
```

**FR-ING-05:** The canonical ingest-session schema SHALL include at least:

```python
class IngestSession(BaseModel):
  session_id: str
  origin: Literal["api", "chat", "inbox"]
  state: Literal[
    "captured", "queued", "preparing", "dormant_ready", "in_review",
    "awaiting_user", "proposal_ready", "approved_pending_execution",
    "executing", "completed", "failed", "dismissed"
  ]
  source_ids: list[str]
  title: str | None = None
  digest: str | None = None
  open_questions: list[dict] = []
  related_notes: list[dict] = []
  contradictions: list[dict] = []
  proposed_actions: list[dict] = []
  created_at: str
  updated_at: str
  prepared_at: str | None = None
  last_true_up_at: str | None = None
```

**FR-ING-06:** The canonical source-record schema SHALL include immutable provenance metadata and explicit lifecycle state:

```python
class SourceRecord(BaseModel):
  source_id: str
  session_id: str
  kind: Literal["file", "url", "chat_text", "chat_upload"]
  status: Literal[
    "captured", "archived", "queued", "processing", "ready",
    "consumed", "completed", "failed", "dismissed"
  ]
  source_name: str
  author: str | None = None
  mime_type: str | None = None
  archive_path: str
  checksum_sha256: str
  captured_at: str
  provenance: dict = {}
```

**FR-ING-07:** The canonical proposed-action schema SHALL support per-action approval with user edits and visible diffs before execution:

```python
class ProposedAction(BaseModel):
  action_id: str
  action_type: Literal["create_note", "update_note"]
  approval_state: Literal["draft", "edited", "approved", "rejected", "executed", "failed"]
  target_file_path: str | None = None
  target_note_type: str | None = None
  rationale: str
  diff_preview: dict | None = None
  proposed_content: dict = {}
```

**FR-ING-08 (Plugin Registry):** The ingest pipeline SHALL use a plugin registry to decouple content extraction from the classification/metadata steps. The `IngestPlugin` ABC:

```python
class IngestPlugin(ABC):
  source_id: ClassVar[str]    # e.g. "text", "audio", "url", "onenote"
    source_label: ClassVar[str] # e.g. "Plain Text", "Audio File"

    @classmethod
    @abstractmethod
    def can_handle(cls, request: IngestRequest) -> bool: ...

    @abstractmethod
    async def extract(self, request: IngestRequest) -> str:
        """Return plain text extracted from the source format."""
        ...
```

The `IngestPluginRegistry` singleton holds all registered plugins. On each ingest call, the registry calls `can_handle` in registration order and uses the first matching plugin. Built-in plugins focus on local-core capture: `TextPlugin` (passthrough) and `AudioPlugin` (calls `AIProvider.transcribe`). Future sources (e.g., explicit URL capture helpers, OneNote, or other integrations) are implemented by registering a new `IngestPlugin` subclass without modifying pipeline code.

**FR-ING-09:** Preparation steps (run in order unless marked optional/concurrent):
1. Content extraction — `IngestPluginRegistry.resolve(request)` selects plugin; `plugin.extract()` yields plain text
2. Source archival — immutable source record is created outside the vault
3. Digest preparation — summarize key takeaways and derive candidate entities/topics
4. Knowledge linking — propose links to related notes in the MCP knowledge base
5. Contradiction analysis — warnings with explanations and links to conflicting note(s)
6. Proposal generation — emit `create_note` / `update_note` actions with visible deltas
7. Dormant persistence — prepared session is stored for later review or queued for idle-time completion
8. Approved execution — once approved, actions execute through the canonical MCP tool plane
9. Validation / reindex — confirm expected changes exist and queue re-index for touched notes

**FR-ING-10:** The system SHALL support a user-triggered `true-up` operation that reruns session preparation on a dormant session before approval to account for drift in the source material or knowledge base since the session was first prepared.

**FR-ING-11:** Contradiction handling SHALL produce warnings with explanations and links to the contradicting document(s). Contradictions are advisory only: they do not block review completion or action approval.

**FR-ING-12:** Approval semantics SHALL be per-action with edits allowed before approval. The ingest-review workflow SHALL also provide an `approve all` operation that applies to all proposed actions in the current ingest session.

**FR-ING-13:** The source archive SHALL be outside the vault, immutable, excluded from embedding and default search, and linked back into resulting vault documents through a `Sources` section containing source name and author when known.

**FR-ING-14:** The system SHALL support a fast-capture mode for high-confidence users. Fast-capture SHALL reuse the ingest-session/source architecture while bypassing the full review workflow and still preserving provenance, post-write validation, and re-index behavior.

**FR-ING-15:** Each note template YAML schema SHALL include a `sentence_starters` list — opening phrases that strongly signal the template type. Examples:

| Template | Example starters |
|---|---|
| `decision` | `"I decided"`, `"We agreed to"`, `"The decision was"` |
| `observation` | `"I noticed that"`, `"It’s worth noting"`, `"Interesting that"` |
| `idea` | `"What if we"`, `"I had an idea"`, `"Could we"` |
| `action_item` | `"TODO:"`, `"Action item:"`, `"I need to"`, `"Follow up on"` |

The routing agent SHALL check the first sentence of the input against all templates' sentence starters before invoking the LLM. A sentence-starter match sets `RoutingDecision.sentence_starter_matched = True` and boosts routing confidence to at least `0.85`.

**FR-ING-16 (Failed Ingest Records):** When preparation or execution fails, the system SHALL write a lightweight failed-ingest record containing session identifier, source identifier, failure stage, failure timestamp, retryable flag, and diagnostic detail path if one exists. Failed ingest records power UI visibility and retry flows and SHALL be removed automatically when the failed step is retried successfully or the session is dismissed.

---

### Routing Agent (FR-RTNG)

**FR-RTNG-01:** A `RoutingAgent` class SHALL be implemented in `monocle/agents/routing.py`. It accepts extracted plain text (and optional `source` hint + `template_hint`) and returns a `RoutingDecision`:

```python
class RoutingDecision(BaseModel):
    template: str                     # selected template name
    confidence: float                 # 0.0–1.0 routing confidence
    reasoning: str                    # short explanation (logged, not shown to user)
    sentence_starter_matched: bool    # True if a sentence starter triggered the selection
```

**FR-RTNG-02:** The routing agent SHALL consult (in priority order):
1. `template_hint` in `IngestRequest` — immediately returns that template with `confidence: 1.0`
2. Sentence starter matching against all template `sentence_starters` lists (see FR-ING-09) — synchronous, no LLM call
3. LLM classification via `prompts/routing.md` system prompt and `AIProvider.chat` with structured JSON response

**FR-RTNG-03:** The routing agent is invoked by `IngestPipeline` after content extraction. Plugin resolution (which runs first) is responsible for format extraction (audio → text); routing is responsible for semantic dispatch.

**FR-RTNG-04:** Routing confidence below 0.6 causes session preparation to fall back to a `blank` template candidate for proposal generation, preserving the low-confidence fallback without forcing an immediate vault write.

---

### Prompt File Management (FR-PRMT)

**FR-PRMT-01:** Agent system prompts SHALL be stored as Markdown files in the `prompts/` directory at the project root. Default files:

| File | Agent / Phase |
|---|---|
| `prompts/routing.md` | `RoutingAgent` — template classification from raw text |
| `prompts/extract.md` | Metadata extraction (template-agnostic preamble) |
| `prompts/weekly_review.md` | Weekly summary agent |
| `prompts/confidence.md` | Documentation placeholder for the deterministic confidence model |

**FR-PRMT-02:** Each prompt file SHALL begin with YAML frontmatter:

```yaml
---
agent: routing
version: 1.0.0
description: Classifies raw input into a note template
---
```

The Markdown body is the full system prompt text.

**FR-PRMT-03:** Prompts SHALL be loaded at agent instantiation time. Changes take effect on the next agent invocation — no server restart required.

**FR-PRMT-04:** `prompts/local/` is gitignored and provides user-local prompt overrides. If `prompts/local/<name>.md` exists, it takes precedence over `prompts/<name>.md`.

**FR-PRMT-05:** Default prompt files SHALL be committed to version control. `prompts/local/` SHALL be listed in `.gitignore`.

---

### Process Management (FR-PROC)

**FR-PROC-01 (Phase 1 — Unified Process):** The full Phase 1 deployment is a **single unified OS process**:

| Process | Command | Description |
|---|---|---|
| Main API + Services | `python -m monocle serve` | FastAPI + APScheduler + MCP server + integrated `InboxWatcher` async task + frontend static files; binds `127.0.0.1:8000` |

All capture routes go through `POST /api/ingest`. There is no separate capture server or standalone watcher process in Phase 1.

**FR-PROC-02 (Dev shortcut):** `python -m monocle dev` SHALL start the unified process with prefixed stdout logging (`[API]`, `[WATCHER]`, `[SCHEDULER]`, `[INGEST]`, `[AGENT]`). The near-term mainline SHALL NOT expose capture-only or separate-process runtime modes.

**FR-PROC-03 (Test harness):** pytest SHALL provide a session-scoped `live_server` fixture in `monocle/tests/conftest.py` that:
- Starts the unified process on a random available port
- Polls `GET /api/health` until `status: ready` (timeout: 15 s)
- Yields the base URL for integration and E2E tests
- Sends `SIGINT` and waits up to 5 s for clean shutdown

Unit-level tests (using FastAPI `TestClient`) do NOT require the fixture.

**FR-PROC-04 (Health endpoint):** `GET /api/health` SHALL report the integrated watcher as part of the single process — no separate `processes` map. The `watcher_status` field (`"running"` | `"stopped"` | `"error"`) reflects whether the watcher async task is alive within the unified process.

---

### 2.7 REST API (FR-API)

All endpoints return `application/json`. Error responses conform to RFC 7807. The React frontend is the primary consumer; the MCP server also uses these endpoints internally. The near-term UX target is a unified capture workbench, so dedicated review/failure endpoints remain compatibility surfaces until the workbench aggregation milestones land.

#### 2.7.1 Ingest

**FR-API-01:** `POST /api/ingest`  
Accepts multipart form (`audio` file) or JSON body:
```json
{ "content": "string", "source": "web|mcp|voice|import|inbox|chat", "template_hint": "person", "fast_capture": false }
```
Response format depends on `Accept` header (content negotiation):
- `Accept: application/json` (default): Returns `202 Accepted` with the created `IngestSession` summary
- `Accept: text/event-stream`: Returns SSE stream with session-preparation progress events
```
event: archiving_source      data: {"source_id": "..."}
event: digest_ready          data: {"session_id": "..."}
event: proposals_ready       data: {"session_id": "...", "action_count": 2}
event: dormant_ready         data: {"session_id": "..."}
event: error                 data: {"message": "..."}
```

**FR-API-02:** Returns `422` if both `content` and `audio` are absent, if `content` exceeds 50,000 characters, if the `audio` file upload exceeds 25 MB, or if an unsupported audio format is provided.

**FR-API-02a:** `GET /api/ingest/sessions` — Lists ingest sessions with filters such as `state`, `origin`, `ready_only`, `limit`, and `offset`. This powers notifications and the dedicated ingest-review workspace.

**FR-API-02b:** `GET /api/ingest/sessions/{session_id}` — Returns the full ingest session, including digest, linked notes, contradiction warnings, proposed actions, and source records.

**FR-API-02c:** `POST /api/ingest/sessions/{session_id}/true-up` — Re-runs session preparation for a dormant or in-review session to account for drift since it was first prepared. Returns `202 Accepted` and updates `last_true_up_at` when complete.

**FR-API-02d:** `PATCH /api/ingest/sessions/{session_id}/actions/{action_id}` — Allows editing or updating approval state for a proposed action. Accepts revised content, rationale, and approval state.

**FR-API-02e:** `POST /api/ingest/sessions/{session_id}/approve-all` — Marks all draft or edited actions in the current ingest session as approved.

**FR-API-02f:** `POST /api/ingest/sessions/{session_id}/execute` — Executes approved actions via the canonical MCP-backed create/update path, validates the resulting writes, and queues re-index work.

**FR-API-03:** `POST /api/transcribe`  
Accepts multipart form with `audio` file field. Returns:
```json
{ "transcript": "...", "duration_ms": 12400 }
```
Used by the frontend voice capture modal for transcription-only (without ingest).

**FR-API-03a:** During proposal generation, the ingest subsystem performs an optional semantic similarity check against recent notes and related-note candidates. Similarity findings are advisory only and are surfaced as duplicate or overlap warnings in the ingest-review workspace. **No automatic deduplication occurs.**

#### 2.7.2 Vault (Notes CRUD)

**FR-API-04:** `GET /api/notes` — List all notes. Query params: `folder` (filter by subfolder), `type`, `domain`, `sort` (`name|updated|created`, default `updated`), `limit` (int, default 100, max 500), `offset` (int, default 0). Response includes `total` count for pagination: `{ "total": 1200, "offset": 0, "limit": 100, "notes": [...] }`.

**FR-API-05:** `GET /api/notes/{file_path:path}` — Read a single note by vault-relative path. Returns full `Note` object including frontmatter and body.

**FR-API-06:** `PUT /api/notes/{file_path:path}` — Write/overwrite a note. Body: `{ "frontmatter": {...}, "body": "...", "if_mtime": "<ISO 8601>" }`. Creates the file (and any parent directories) if not found. If `if_mtime` is present and the file's actual last-modified timestamp does not match, the server SHALL return `409 Conflict` with both the stored and provided mtime, enabling concurrent-edit detection for Obsidian compatibility.

**FR-API-07:** `PATCH /api/notes/{file_path:path}` — Partial update. Accepts `frontmatter` (merged with existing), `body` (replaces body), or `append` (appends text to body).

**FR-API-08:** `DELETE /api/notes/{file_path:path}` — Delete a note file. Returns `204`.

**FR-API-09:** `POST /api/notes/{file_path:path}/move` — Move/rename. Body: `{ "destination": "new/path.md" }`.

**FR-API-10:** `GET /api/templates` — List available note templates with their frontmatter schemas.

#### 2.7.3 Search

**FR-API-11:** `GET /api/search?q=<query>&n=10&threshold=0.5&type=<type>&domain=<domain>&source=<source>`  
Returns:
```json
{
  "query": "...",
  "results": [ { "note": { ...NoteRef }, "similarity": 0.87, "chunk": "..." } ]
}
```
`q` is required. `n` max 50. Search embeds the query, runs ChromaDB similarity search, then loads only the matched note files.

**FR-API-12:** `GET /api/search/keyword?q=<query>&n=20` — Keyword/substring search across frontmatter and body. No embedding required.

**FR-API-12a:** `GET /api/notes/{file_path:path}/backlinks` — Returns all notes linking to the target note (inbound links). Query params: `types` (filter by `relation` type if provided), `link_type` (filter by `"structured"`, `"wikilink"`, or `"comention"`), `limit`, `offset`. Response:
```json
{
  "file_path": "work/projects/q4-project.md",
  "backlink_count": 8,
  "backlinks": [
    { "source": "work/decisions/migrate.md", "link_type": "structured", "relation": "depends-on", "context": "..." },
    { "source": "work/meetings/kickoff.md",  "link_type": "wikilink",    "relation": null,         "context": "..." },
    { "source": "people/sarah-chen.md",       "link_type": "comention",  "relation": null,         "context": "shared tag: q4-project" }
  ]
}
```
Backlinks are computed from three tiers returned in priority order: (1) structured `links` frontmatter entries where `target` resolves to the requested file path; (2) body `[[wikilinks]]` parsed via `parse_wikilinks(body)`; (3) co-mentions — notes that share the same `people` or `tags` frontmatter values. Each backlink entry includes a `link_type` field (`"structured"` | `"wikilink"` | `"comention"`) so the UI can render each tier with appropriate visual treatment and grouping.

#### 2.7.4 Graph

**FR-API-13:** `GET /api/graph` — Returns an ego-graph (focus-centred) or full vault relationship graph. All node types are included by default. Query parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `focus` | str \| null | null | Vault-relative file path of the node to centre on. Omit for full-vault mode. |
| `max_degree` | int | 3 | Max BFS hops from focus node. Ignored in full-vault mode. |
| `types` | str | `"person,note,tag"` | Comma-separated node type filter. |
| `n` | int | 500 | Max nodes returned. In ego mode, closest-degree nodes returned first. |

Response:
```json
{
  "focus": "people/sarah-chen.md",
  "nodes": [
    { "id": "people/sarah-chen.md", "label": "Sarah Chen", "type": "person", "degree": 0, "weight": 5 }
  ],
  "edges": [
    { "source": "people/sarah-chen.md", "target": "work/decisions/migrate.md",
      "edge_type": "structured", "relation": "mentioned-in", "weight": 3, "metadata": {} }
  ]
}
```

`degree` is the BFS distance from the focus node (0 = focus itself). In full-vault mode, `degree` is `null`. Edge `relation` comes from structured `links` frontmatter if available; otherwise defaults to `"mentioned-in"` (people co-mention or tag co-mention) or `"links-to"` (plain wikilink). `edge_type` SHALL be one of `"structured"` (from `links` frontmatter), `"wikilink"` (from body `[[…]]`), or `"comention"` (from shared `people`/`tags` frontmatter). `metadata` carries any additional k/v pairs from the structured link entry. Graph results SHALL be cached per `(focus, max_degree, types)` key and invalidated on any file watcher event (see NFR-PERF-09). Graph edges are constructed from four sources in priority order: (1) structured `links` frontmatter, (2) body wikilinks, (3) `people` frontmatter co-mentions, (4) shared `tags`.

#### 2.7.5 Stats

**FR-API-14:** `GET /api/stats` — Returns `BrainStats` (see Data Model §4).

#### 2.7.6 Frontend Static Assets

**FR-API-15:** The FastAPI app SHALL mount the Vite build output at `/` and serve `index.html` for all non-API paths (SPA fallback).

#### 2.7.7 Capture Workbench & Review Actions

**FR-API-16:** `GET /api/capture-workbench` — Returns the unified app-shell capture summary. Query param: `limit_per_section` (default `10`, max `100`). The response includes one top-level `actionable_count`, the active `queue_threshold`, section counts, and sectioned items for `prepared`, `pending_review`, and `failures`. The near-term mainline SHALL NOT expose separate review-list, review-count, or failed-ingest list endpoints for app-shell aggregation.
```json
{
  "actionable_count": 4,
  "queue_threshold": 0.5,
  "counts": { "prepared": 1, "pending_review": 1, "failures": 2 },
  "sections": [
    { "section": "prepared", "count": 1, "items": [ { "item_type": "ingest_session", "session_id": "ing_123" } ] },
    { "section": "pending_review", "count": 1, "items": [ { "item_type": "pending_note", "file_path": "work/pending-note.md" } ] },
    { "section": "failures", "count": 2, "items": [ { "item_type": "failed_ingest", "failure_id": "fail_123" } ] }
  ]
}
```

**FR-API-17:** `PATCH /api/review/{file_path:path}/approve` — Sets `review_status: approved`, `approval_mode: manual`, `approved_by`, and `approved_at` in the note's YAML frontmatter and mirrors the new status into index metadata. Returns a lightweight approval result containing `file_path`, `review_status`, `approval_mode`, `approved_by`, and `approved_at`.

**FR-API-18:** `PATCH /api/review/{file_path:path}/reject` — Sets `review_status: rejected`, `approval_mode: manual`, `approved_by`, and `approved_at` in the note's YAML frontmatter and mirrors the new status into index metadata. Returns the same lightweight approval result shape as approval.

**FR-API-19:** `POST /api/ingest/failures/retry` — Retries a failed-ingest registry record by failure id using the stored preview/source context. Returns an ingest response payload for the retried capture and marks the original registry entry as retried.

**FR-API-19a:** `DELETE /api/ingest/failures/{id}` — Deletes a single failed-ingest registry record. It removes the record from actionable workbench failures but does not delete the associated `.error.md` sidecar file. Returns `204 No Content`.

#### 2.7.8 Chat

**FR-API-20:** `POST /api/chat` — Accepts a messages array (OpenAI-style) and streams agent responses as Server-Sent Events (SSE). Request body:
```json
{
  "messages": [ { "role": "user", "content": "..." } ],
  "session_id": "optional-uuid",
  "context_items": []
}
```
SSE event types:

| Event type | Payload | Notes |
|---|---|---|
| `token` | `{ "delta": "..." }` | Incremental response token |
| `tool_call` | `{ "name": "search_vault", "result_count": 4 }` | Collapsed disclosure for UI |
| `tool_error` | `{ "name": "...", "error": "..." }` | Tool call that failed |
| `note_created` | `{ "file_path": "...", "type": "..." }` | Triggers inline note card in UI |
| `done` | `{ "total_tokens": 420 }` | Stream complete |
| `error` | `{ "message": "..." }` | Fatal agent error |

The endpoint returns `Content-Type: text/event-stream`. The connection is closed by the server after the `done` event.

`context_items` are explicit user-added document or snippet references supplied from the Document Browser or Docs explorer. They are distinct from implicit vault retrieval and SHALL be preserved in chat session history as user-provided grounding.

#### 2.7.9 Ingest Progress (SSE)

**FR-API-21:** `POST /api/ingest/stream` — Same parameters as `POST /api/ingest` but returns an SSE stream of session-preparation progress events instead of a single `202` response. Progress event types:

| Event type | Payload |
|---|---|
| `archiving_source` | `{ "source_id": "..." }` |
| `extracting` | `{}` |
| `digesting` | `{}` |
| `linking` | `{ "candidate_count": 4 }` |
| `proposing` | `{}` |
| `done` | `{ "session_id": "...", "state": "dormant_ready" }` |
| `error` | `{ "message": "..." }` |

The original `POST /api/ingest` endpoint remains the ingest entry point, but it now creates ingest sessions instead of directly creating notes.

#### 2.7.10 Settings

**FR-API-22:** `GET /api/settings` — Returns current server settings. Secret values are **never** returned in full: the MCP access key is returned as a masked string (`"••••••••<last4chars>"`). Response example:
```json
{
  "ai": {
    "chat_model_key": "llama3.2",
    "embed_model_key": "nomic-embed",
    "stt_key": null,
    "url_reference_timeout_s": 120,
    "transcribe_backend": "subprocess",
    "models": []
  },
  "ingest": { "background_prepare_enabled": true, "prepare_poll_interval_s": 5.0 },
  "history": { "retention_versions": 50 },
  "review": { "queue_threshold": 0.75, "auto_approve_threshold_pct": 90 },
  "agents": {
    "weekly_summary": { "enabled": true, "cron": "0 17 * * 5", "domains": [] },
    "reindex": { "enabled": true, "cron": "0 3 * * 0" }
  },
  "ui": { "chat_session_history_limit": 10, "voice_input_backend": "whisper" },
  "mcp_key_last4": "****a3f9"
}
```

**FR-API-23:** `PATCH /api/settings` — Updates mutable server-side settings at runtime. Accepted fields include `ai.chat_model_key`, `ai.embed_model_key`, `ai.stt_key`, `ai.url_reference_timeout_s`, `ai.transcribe_backend`, `ai.transcribe_url`, `ai.ollama_base_url`, full replacement of `ai.models`, `history.retention_versions`, `review.queue_threshold`, `review.auto_approve_threshold_pct`, `ui.voice_input_backend`, and `telemetry.trace_filters`. Changing active model selections or the model registry SHALL hot-reload the `AIProvider` singleton. **Updated values SHALL be written back to `config.yaml` atomically (write temp + rename) so that changes survive a server restart.** This endpoint SHALL **not** accept new secret values (rotate the MCP key via `POST /api/settings/rotate-mcp-key`).

**FR-API-24:** `POST /api/settings/rotate-mcp-key` — Generates a new cryptographically random 64-hex-character MCP access key, writes it to the `.env` file (replacing the old value), and reloads it in memory. Returns `{ "mcp_key_last4": "****<last4chars>" }`. Old key is immediately invalidated.

#### 2.7.11 Health

**FR-API-25:** `GET /api/health` — Returns server operational status. Response:
```json
{
  "status": "ready",          // "starting" | "indexing" | "ready" | "degraded"
  "index_status": "ready",    // "empty" | "indexing" | "ready"
  "index_progress": null,     // { "indexed": 412, "total": 1200 } during startup re-index
  "watcher_status": "running", // "running" | "stopped" | "error"
  "ai_backend": "ollama",
  "ai_reachable": true,
  "telemetry_endpoint": "http://localhost:4317",  // configured OTLP endpoint, or null if disabled
  "version": "0.1.0"
}
```
During a startup re-index (FR-WTCH-05), `status` SHALL be `"indexing"` and other endpoints MAY return `503 Service Unavailable` with a `Retry-After: 5` header. Read-only endpoints (`GET /api/notes`, `GET /api/search`) SHOULD remain available and return stale/partial results.

---

### 2.8 MCP Server (FR-MCP)

**FR-MCP-01:** The MCP server SHALL be implemented using `FastMCP` with `stateless_http=True` and `json_response=True`, mounted at `/mcp` on the FastAPI app.

**FR-MCP-02:** All requests to `/mcp` SHALL be authenticated via an access key provided in the `x-monocle-key` request header. The `?key=` query parameter MAY also be accepted for compatibility with MCP clients that do not support custom headers, but its use is discouraged — query parameters appear in server access logs and browser history. Requests without a valid key via either mechanism SHALL return `401 Unauthorized`.

**FR-MCP-03:** The MCP server SHALL expose the following tools. Each tool is a thin schema/transport wrapper over the corresponding `monocle/services/` function. No business logic lives in the tool handler itself.

| Tool | Description | Parameters | Service function |
|---|---|---|---|
| `search_vault` | Semantic search; returns matching notes with similarity scores | `query: str`, `n_results: int = 5`, `note_type: str = None`, `domain: str = None` | `search_service.search_vault()` |
| `read_note` | Load full note content by file path | `file_path: str` | `notes_service.read_note()` |
| `capture_thought` | Synchronous one-shot ingestion of unstructured text for external MCP clients | `content: str`, `source: str = "mcp"` | `ingest_service.capture_thought()` |
| `create_note` | Create a new note using a template | `title: str`, `body: str`, `note_type: str = "observation"`, `domain: str = "personal"`, `tags: list[str] = None` | `notes_service.create_note()` |
| `create_reference_from_url` | Fetch a web page, summarise it with AI, and create a reference note | `url: str`, `extra_context: str = None` | `reference_service.create_reference_from_url()` |
| `update_note` | Update the body of an existing note | `file_path: str`, `body: str` | `notes_service.update_note()` |
| `get_graph` | Get relationship graph data centred on a focus entity | `focus: str = None`, `max_degree: int = 2` | `graph_service.get_graph()` |

**FR-MCP-03a (Canonical surface):** The MCP tool layer SHALL be the authoritative external contract for Monocle-owned data operations. The chat agent's internal tool names SHALL match the canonical MCP tool names for all Monocle-owned operations. Both converge on the same `monocle/services/` implementations.

**FR-MCP-04:** Tool return values SHALL be `str` (JSON-serialized) or `dict` serializable via `model_dump_json()`.

**FR-MCP-05:** `search_vault` SHALL embed the query, run ChromaDB similarity search, and return note metadata + matching chunk text. It SHALL NOT return full note bodies — the AI client uses `read_note` for that.

**FR-MCP-06:** The MCP server name SHALL be `"monocle"` and the version SHALL be read from the package version.

---

### 2.9 CLI (FR-CLI)

A Typer application invocable as `python -m monocle <command>`, primarily for server operations and debugging.

**FR-CLI-01:** `serve [--host STR] [--port INT]` — Starts the FastAPI + file watcher server.

**FR-CLI-02:** `reindex [--force]` — Triggers a full vault re-index (delete all ChromaDB entries, re-embed all notes).

**FR-CLI-03:** `pull-models` — Pulls the configured Ollama embed and chat models if not already present.

**FR-CLI-04:** `stats` — Prints aggregate index stats to stdout.

**FR-CLI-05:** `search "<query>" [--n INT] [--threshold FLOAT]` — Runs semantic search, prints results as a formatted table (for debugging).

**FR-CLI-06:** `export [--output PATH]` — Copies the vault directory and ChromaDB data to a zip archive at `PATH` (default: `./monocle-backup-<timestamp>.zip`). This is the primary backup/migration procedure.

**FR-CLI-07:** `versions list <file_path>` — Lists all stored versions for a vault note from `.versions/`. `versions restore <file_path> <timestamp>` — Overwrites the current note with the specified historical version (making a new version entry of the current state first).

---

### 2.10 Web Frontend (FR-WEB)

**FR-WEB-01:** The frontend SHALL be built with React 18 + Vite 5. The Vite production build output SHALL be served as static files by FastAPI.

**FR-WEB-02:** The app SHALL implement the five screens defined in the UI Design doc: Chat, Document Browser, Search, Graph, and Stats.

**FR-WEB-03 (Chat):** The chat screen SHALL:
- Display chat starters when the conversation is empty
- Stream AI responses token-by-token via `EventSource` or `ReadableStream` from a `POST /api/chat` streaming endpoint
- Collapse agent tool calls into a disclosure element (e.g., "Used `search_vault` — 4 results")
- Render agent response Markdown (headings, lists, bold/italic, code blocks)
- Show explicit user-added context items when a document, section, sentence, or selection has been added from the Docs explorer or Document Viewer

**FR-WEB-03a (Ingest Review Workspace):** The app SHALL provide a dedicated ingest-review workflow separate from the general chat screen. It SHALL:
- List dormant and active ingest sessions with notification counts
- Open a prepared ingest session with digest, linked-note candidates, contradiction warnings, open questions, and proposed actions
- Support per-action edits, approval toggles, and an `approve all` action for the current ingest session
- Allow the user to trigger a true-up / validation rerun before approving changes

**FR-WEB-04 (Voice):** The voice capture modal SHALL:
- First attempt transcription using the browser Web Speech API
- Fall back to server-side Whisper by posting audio to `POST /api/transcribe` if Web Speech API is unavailable or returns an empty result
- Show real-time transcript as it is produced
- Allow the user to save the note, send the transcript to chat, or discard

**FR-WEB-05 (Document Browser):** The document browser SHALL:
- Render the vault file tree via `GET /api/notes`
- Show note content rendered from Markdown in read mode
- Switch to a CodeMirror 6 editor in Markdown source edit mode, with Markdown + YAML frontmatter syntax highlighting
- Provide a mode toggle between Markdown source mode, a lightweight rich preview editing mode for common formatting operations, and the frontmatter form editor
- Auto-save on 2-second debounce via `PUT /api/notes/{path}`, while relying on the coalesced re-index queue from FR-WTCH-04/04a so active typing does not trigger a full embed pass on every save
- Provide an AI Assist slide-over panel that sends instructions about the current note to the chat agent
- Include a collapsed `Sources` section in each document, expanded on demand, showing linked archived sources labeled with source name and author when known
- Open text-based source files in the Document Browser and non-text files with the operating system's default application
- Provide access to file-history diffs and revert actions in the Document Viewer
- Provide right-click context-menu actions that add the current document, section, sentence, or current selection into a new or existing chat session as explicit context

**FR-WEB-05a (Docs Explorer):** The Docs/File Explorer SHALL:
- Display archived sources under a collapsed dropdown separate from the normal vault tree
- Allow drag-and-drop of a document into a new or existing chat session as explicit context
- Keep archived sources out of the default semantic knowledge-base browsing surface unless the user explicitly expands the sources area

**FR-WEB-06 (Search):** The search screen SHALL support both semantic (`GET /api/search`) and keyword (`GET /api/search/keyword`) modes, with a threshold slider for semantic mode.

**FR-WEB-07 (Graph):** The graph view SHALL render a force-directed ego-graph using React Force Graph. The graph API is `GET /api/graph` (see FR-API-13). Behaviour:
- **Default (no focus):** Full vault graph is displayed. Node size and opacity are proportional to connectivity `weight`.
- **Ego mode (focus selected):** The focused node is at the centre. Degree-based visual decay: degree 0 → 100% opacity / max size; each additional degree reduces opacity by 25% and size by 15%. Nodes at `max_degree` are the smallest/most faded.
- **Controls:** Focus input with autocomplete (person/note/tag name); depth toggle [1][2][3]; type filter chips [Person \u2713][Note \u2713][Tag \u2713]; Reset View button to clear focus.
- **Edge labels:** Edges with a `relation` value display the relation as a label; unlabeled edges (plain wikilinks, co-mentions) show no label.
- **Node interaction:** Click → side panel with top 5 related notes; double-click → navigate to note in Document Browser; drag → position persisted to localStorage.
- **Type filters** call `GET /api/graph` with updated `types=` parameter; graph redraws with filtered node set.

**FR-WEB-08 (Stats):** The stats screen SHALL render ingestion-by-source, notes-by-type, and weekly activity charts using Recharts (bundled in the React build).

**FR-WEB-09 (Settings):** A settings modal SHALL allow the user to:
- Select the active AI backend (Ollama / Foundry Local / Azure AI Services) and configure per-backend model names
- Set the **review queue threshold** (slider, 0.00–1.00, default `1.00`) — pending notes with `confidence ≤ threshold` appear in the capture workbench attention count; setting to `0.00` hides low-confidence pending-note alerts entirely
- Set the **auto-approve threshold** (integer 0–100, default `0`) — `0` disables auto-approval; `90` auto-approves notes whose confidence is at least 90%
- Rotate the MCP access key (calls `POST /api/settings/rotate-mcp-key`; displays only the masked hint after rotation)
- Toggle dark/light/system theme

On page load, the frontend SHALL call `GET /api/settings` to initialise all settings fields from the server. `localStorage` is used as a cache for instant render before the first API response returns. `PATCH /api/settings` is called on save. The review settings in `GET /api/settings` are the authoritative source of truth; `localStorage` only caches them for UI performance.

**FR-WEB-10:** Theme (dark/light/system) and backend selection SHALL be persisted across page loads via `localStorage`.

**FR-WEB-10a (Capture Workbench Visibility):** The app shell SHALL display a unified capture-workbench indicator whenever prepared ingest sessions, pending-review notes, or failed ingests require user attention. The initial implementation MAY aggregate this from existing session, review, and failure endpoints until the dedicated workbench contract lands.

**FR-WEB-11 (Chat History):** Chat sessions SHALL be persisted to `localStorage`. Each session is identified by a UUID, holds an ordered list of messages (`role`, `content`, optional `tool_calls`), and records a `created_at` timestamp. The frontend SHALL retain up to **`ui.chat_session_history_limit` sessions** (default 10; configurable via `config.yaml` and settable at runtime via `PATCH /api/settings`). A session picker dropdown in the chat topbar allows the user to load a previous session. Chat history is client-side only — it is not sent to the server or stored in the vault.

Chat session history SHALL also preserve any explicit user-added `context_items` so that document/snippet grounding remains visible and auditable when a session is reloaded.

**FR-WEB-11a (Add To Chat Context):** Users SHALL be able to add a document or snippet to a new or existing chat session from either the Docs explorer or the Document Viewer. When no text is selected, the context menu SHALL offer `add document`, `add section`, and `add sentence` actions. When text is selected, the context menu SHALL offer `add selection` actions.

**FR-WEB-12 (Keyboard Shortcuts):** The following keyboard shortcuts SHALL be supported application-wide:

| Shortcut | Action |
|---|---|
| `Ctrl+K` / `Cmd+K` | Open semantic search |
| `Ctrl+Shift+K` / `Cmd+Shift+K` | Open keyword search |
| `Ctrl+N` / `Cmd+N` | Open new note template picker |
| `Ctrl+S` / `Cmd+S` | Save current note (in editor mode) |
| `Ctrl+/` / `Cmd+/` | Open command palette (list of all available actions) |
| `Ctrl+\` / `Cmd+\` | Toggle sidebar |
| `Escape` | Close active modal or slide-over |
| `Enter` (in chat) | Send message |
| `Shift+Enter` (in chat) | Insert newline |

### 2.11 Agent Framework (FR-AGT)

**FR-AGT-01:** The system SHALL use the Microsoft Agent Framework (Python) for all multi-step agent orchestration.

**FR-AGT-02:** Two agent interaction modes SHALL be supported:
- **Interactive:** User triggers agent via chat; agent streams response to the frontend via `POST /api/chat` (SSE streaming)
- **Background:** APScheduler triggers agent task on a cron schedule; agent writes results to vault; completion event sent to connected frontend clients via SSE

**FR-AGT-03:** The chat agent's tool library SHALL be thin adapters over the shared service layer (`monocle/services/`). All Monocle-owned business logic lives in the service layer; tools only validate input format, call the corresponding service function, and serialize results. Canonical Monocle-owned tools:

| Tool | Canonical name | Service function |
|---|---|---|
| Semantic search | `search_vault(query, n, threshold)` | `search_service.search_vault()` |
| Load note | `read_note(file_path)` | `notes_service.read_note()` |
| Create note from template | `create_note(title, body, note_type, domain, tags)` | `notes_service.create_note()` |
| Update note | `update_note(file_path, body)` | `notes_service.update_note()` |
| Relationship graph | `get_graph(focus, max_degree)` | `graph_service.get_graph()` |
| URL reference | `create_reference_from_url(url, extra_context)` | `reference_service.create_reference_from_url()` |

Additional chat-only tools (no MCP equivalent; not Monocle data operations):

| Tool | Description |
|---|---|
| `get_stats()` | Return `BrainStats` directly via `IndexLayer` |
| `list_notes(folder, type)` | Browse vault note listing via `VaultLayer` |

Raw-text capture is intentionally not exposed as a direct chat agent tool. Chat and browser capture flows use the persisted ingest-session APIs instead.

**FR-AGT-04:** The Weekly Summary agent SHALL:
1. Retrieve all notes modified in the past 7 days via `VaultLayer`
2. Fetch their pre-computed 1536-dim embeddings from ChromaDB (avoid re-embedding)
3. Run lightweight clustering on the embedding matrix using scikit-learn (`KMeans` or `AgglomerativeClustering`)
4. For each cluster: invoke `AIProvider.chat` with `prompts/weekly_review.md` to generate a paragraph summary of the cluster’s theme
5. Optionally further segment by `domain` frontmatter field if `agents.weekly_summary.domains` is configured
6. Write a summary note to `vault/summaries/YYYY-WW.md` using the `weekly_summary` template with `confidence: 1.0`, `review_status: approved`, `approval_mode: auto`, `approved_by: "system:weekly-summary"`, and `approved_at: <now>`
7. Return a completion event to the frontend

If model-based clustering yields poor separation or the batch is too small, the fallback is LLM-based grouping via a structured prompt (`"Group these notes into 3–5 themes"`).

**FR-AGT-05:** The `POST /api/chat` endpoint SHALL accept a messages array (OpenAI-style) and stream back SSE events. The agent MAY make multiple tool calls before streaming its final response.

**FR-AGT-06:** `POST /api/agents/weekly-summary` — Manually trigger the weekly summary agent outside the schedule. Returns `202 Accepted`; completion is delivered via SSE.

**FR-AGT-07:** When an agent tool call returns an error (e.g., `read_note` on a deleted file, `search_vault` when ChromaDB is unavailable), the framework SHALL deliver a structured error result to the agent — not raise an unhandled exception. The agent SHALL include the failure reason in its reasoning and either retry the call once with corrected parameters or surface a user-readable error message. The SSE stream SHALL emit a `tool_error` event (see FR-API-20).

---

### 2.12 Shared Service Layer (FR-SVC)

The shared service layer (`monocle/services/`) is the single authoritative implementation of all Monocle-owned data operations. It eliminates business-logic duplication between the MCP server tools and the chat agent tools.

**FR-SVC-01:** A `monocle/services/` package SHALL be present with the following modules:

| Module | Exported functions |
|---|---|
| `search.py` | `search_vault(vault, index, ai, query, n, threshold, filters) -> list[ScoredNote]` |
| `notes.py` | `read_note(vault, file_path) -> Note`, `create_note(vault, index, ai, ...) -> Note`, `update_note(vault, index, ai, file_path, body) -> Note` |
| `graph.py` | `get_graph(vault, focus, max_degree, types, n) -> GraphResult` |
| `references.py` | `create_reference_from_url(vault, index, ai, url, extra_context) -> Note` |
| `ingest.py` | `capture_thought(pipeline, content, source) -> tuple[Note, IngestConfidence \| None]` |
| `ingest_sessions.py` | `IngestSessionStore(...)` persistence, source archival, notifications, and session mutation helpers |
| `ingest_prepare.py` | background preparation, digest/linking/contradiction/proposal orchestration |
| `ingest_review.py` | review loading, question answering, proposal edits, approval transitions |
| `ingest_execute.py` | approve-all execution, fast-capture execution, validation, and reindex handoff |
| `activity.py` | interactive-idle activity monitoring for background prepare gating |
| `tags.py` | shared tag normalization helpers used by wrappers and services |

**FR-SVC-02:** Service functions SHALL own all business logic: vault file I/O, embedding calls, reindex queue dispatch, review-status assignment, path-boundary validation, and result shaping. Tool wrappers SHALL NOT duplicate this logic.

**FR-SVC-03:** Service functions SHALL be independently testable without requiring MCP transport or agent framework context. They accept injected dependencies (vault, index, ai provider, pipeline) and return well-typed Pydantic models.

**FR-SVC-04:** All vault path validation (absolute path resolution, rejection of paths outside `vault.path` with `403`) SHALL be performed inside service functions, not in tool wrappers.

**FR-SVC-05:** Reindex queue triggers (`ReindexQueue.push(file_path)`) SHALL be called by service functions after any write operation, not by tool wrappers.

**FR-SVC-06:** Review-status semantics (setting `review_status: pending` on agent-created notes, `review_status: approved` on user-direct notes) SHALL be enforced by service functions.

**FR-SVC-07:** MCP tool handlers and chat agent tool handlers SHALL each have corresponding service-level tests that assert shared behavior and result-field stability. Contract parity tests SHALL assert that both wrappers resolve to identical output for identical inputs.

---

### 2.13 Deferred Channel Integrations (FR-INT)

**FR-INT-01:** Broad channel integrations such as Microsoft Teams and OneNote import are explicitly deferred beyond the near-term local core.

**FR-INT-02:** Existing stubs, seams, or plugin extension points for deferred channels MAY remain in the codebase temporarily, but they are not required deliverables for the current simplification track.

### 2.14 Capture Review Semantics (FR-REV)

The user-facing destination for these semantics is the unified capture workbench. Separate review-list, review-count, and failed-ingest list endpoints are no longer part of the supported mainline contract.

**FR-REV-01:** Every note created by the ingest pipeline SHALL have two additional frontmatter fields written at creation time:

```yaml
confidence: 0.72          # float 0.0–1.0, agent-assessed composite quality score
review_status: pending    # "pending" | "approved"
approved_by: null         # "system:auto" or the approving user identity
approved_at: null         # ISO 8601 timestamp when approval happened
approval_mode: null       # "auto" | "manual"
```

**FR-REV-02:** `confidence` is computed deterministically without an LLM call using a weighted combination of four components:
- **template_match (0.35 weight)** — routing confidence from `RoutingAgent.route()`; range 0.0–1.0
- **metadata_coverage (0.30 weight)** — fraction of required frontmatter fields that are non-empty; range 0.0–1.0
- **tag_plausibility (0.20 weight)** — if tags are present, the cosine similarity of tag embeddings (averaged) against the note body embedding; if no tags, score = 1.0; range 0.0–1.0
- **entity_match (0.15 weight)** — ratio of detected people entities that already exist as person notes in the vault; range 0.0–1.0

Composite score formula: `confidence = 0.35 * template_match + 0.30 * metadata_coverage + 0.20 * tag_plausibility + 0.15 * entity_match`. Weights are adjustable via `review.confidence_weights` in `config.yaml`.

**FR-REV-03:** Notes written directly by the user (not via ingest, e.g., created in the Document Browser editor) SHALL have `confidence: 1.0`, `review_status: approved`, `approval_mode: manual`, `approved_by: "user"`, and `approved_at: <now>` written at creation time and SHALL NOT appear as actionable items in the capture workbench.

**FR-REV-04:** Pending-review notes contribute to the capture-workbench actionable count when `review_status == "pending" AND confidence <= queue_threshold`; prepared sessions and failures contribute through their own workbench sections. **Source of truth for review behaviour (in priority order):** (1) the values persisted server-side via `PATCH /api/settings` (stored in process memory and written back to `config.yaml`), (2) the values from `config.yaml` on startup. `review.queue_threshold` governs workbench visibility for pending notes. `review.auto_approve_threshold_pct` governs whether a newly ingested note is auto-approved. The Settings modal reads the current values from `GET /api/settings` on open, and writes back via `PATCH /api/settings` on save. `localStorage` caches them only for instant UI render before the first API response arrives; the server is authoritative.

**FR-REV-05:** Approving a note (`PATCH /api/review/{path}/approve`) SHALL:
1. Set `review_status: approved`, `approval_mode: manual`, `approved_by`, and `approved_at: <now>` in the frontmatter via `VaultLayer.patch_frontmatter()`
2. Patch the index metadata for the affected note so the new `review_status` is reflected in search/query consumers
3. Return the lightweight approval-result object documented in `FR-API-17`

**FR-REV-06:** Rejecting a note (`PATCH /api/review/{path}/reject`) SHALL set `review_status: rejected`, remove it from actionable workbench sections, and preserve the note for later inspection. If the user clicks **Edit** instead, the note opens in the Document Browser editor so it can be corrected and then approved from the editor toolbar.

**FR-REV-07:** The Document Browser editor toolbar SHALL show an **Approve** button when a note has `review_status: pending`.

**FR-REV-08:** `BrainStats` SHALL include `pending_review: int` (total notes with `review_status: pending`).

---

### 2.15 Observability (FR-TEL)

**FR-TEL-01:** Monocle SHALL use **OpenTelemetry (OTel)** as the single, cross-cutting observability layer covering distributed tracing, metrics, and log correlation. All three signals SHALL be exported via OTLP. The default local sink is VS Code AI Toolkit (gRPC port 4317); any OTLP-compatible backend (Jaeger, Grafana, Honeycomb, Azure Monitor) can be substituted via `config.yaml` `telemetry.otlp_endpoint` and `telemetry.otlp_transport`.

**FR-TEL-02:** `monocle/telemetry.py` SHALL expose:
- `configure_telemetry(settings)` — called once in the FastAPI app lifespan **before** any other subsystem starts; wires up `TracerProvider`, `MeterProvider`, and root-logger handler; no-ops gracefully if `telemetry.enabled: false`.
- `get_tracer(name) -> Tracer` — thin wrapper; modules import this instead of OTel directly.
- `get_meter(name) -> Meter` — same pattern for metrics.
- `span(name, **attrs)` — async context manager that wraps a coroutine in a child span.
- `timed(histogram, **attrs)` — async context manager that records wall-clock duration into an OTel `Histogram` on exit.

**FR-TEL-03:** The following FastAPI auto-instrumentation packages SHALL be active: `opentelemetry-instrumentation-fastapi` (per-route HTTP spans), `opentelemetry-instrumentation-logging` (injects `trace_id` and `span_id` into every log record), `opentelemetry-instrumentation-httpx` (outbound HTTP to Ollama/Azure).

**FR-TEL-04:** The following OTel metric instruments SHALL be created per milestone:

| Instrument | Type | Unit | Milestone | Description |
|---|---|---|---|---|
| `http.server.request_duration` | Histogram | ms | M2 | User-facing route latency (auto from FastAPI instrumentation) |
| `ai.embed_duration` | Histogram | ms | M6 | Per-call embed latency |
| `ai.chat_duration` | Histogram | ms | M6 | Per-call chat/completion latency |
| `ai.transcribe_duration` | Histogram | ms | M6 | Per-call transcription latency |
| `ingest.pipeline_duration` | Histogram | ms | M7 | End-to-end ingest pipeline per note |
| `ingest.step_duration` | Histogram | ms | M7 | Per-step ingest latency (`step` attribute = 1–8) |
| `ingest.notes_total` | Counter | notes | M7 | Notes ingested, by `source` and `template` |
| `ingest.failures_total` | Counter | errors | M7 | Failed ingests, by `step` |
| `chat.ttft` | Histogram | ms | M10 | Time from `POST /api/chat` to first `token` SSE event |
| `chat.total_duration` | Histogram | ms | M10 | Time from `POST /api/chat` to `done` SSE event |
| `index.search_duration` | Histogram | ms | M4 | Vector search latency per query |
| `index.upsert_duration` | Histogram | ms | M4 | Chunk upsert latency per file |

**FR-TEL-05:** Observability code SHALL add zero blocking work to hot paths. All spans are created async-safely; sampling is `AlwaysOn` locally. The `telemetry.enable_sensitive_data` config flag controls whether prompt / completion content is included in spans (opt-in; default `true` for local personal use).

**FR-TEL-06:** Log format is `text` in dev mode and `json` in production (configurable via `telemetry.log_format`). In `json` mode, every log record SHALL include `timestamp`, `level`, `logger`, `message`, `trace_id`, and `span_id` as structured fields.

---

## Long-Term Roadmap (LTR)

These items are committed design directions deferred beyond Phase 2. Architectural decisions made in Phase 1 SHALL NOT foreclose them.

### LTR-1: Logseq Compatibility

- Support Logseq-format daily notes, journal pages, and `((block-ref))` block references as an alternative to Obsidian.
- Vault format (standard `.md`) is already partially compatible. Phase 3 adds: Logseq import plugin, block-reference resolution in `parse_wikilinks`, and a `LogseqPlugin` in the ingest registry.
- **Architectural constraint (Phase 1):** `parse_wikilinks` and `resolve_wikilink` must remain abstracted and not hard-code Obsidian-only link syntax. The plugin registry pattern makes adding `LogseqPlugin` purely additive.

### LTR-2: Migration Documentation

- Publish a step-by-step guide covering: ChromaDB → Azure AI Search collection export/import, Ollama → Azure AI Services provider swap, local vault → cloud storage mount.
- **Architectural constraint (Phase 1, enforced now):**
  - `IndexLayer` ABC is the single swap point for the index backend; `get_index(settings)` factory must remain the only place that constructs an index implementation.
  - `AIProvider` ABC is the single swap point for the AI backend; `get_provider(settings)` factory is the only construction site.
  - Fixed 1536-dim embeddings mean local ChromaDB vectors are directly compatible with Azure AI Search collection dimensions — no re-embedding needed when migrating.
  - `config.yaml` provider/backend switches must remain zero-code-change operations (NFR-EXT-01, NFR-EXT-02).

### LTR-3: Server-Side Agent Memory (Chat Sessions)

- Phase 1 chat sessions are stored in browser `localStorage` only (last 10 sessions, client-side only). The agent has no cross-session memory; it starts fresh after a page reload. This is a deliberate Phase 1 simplification — document this constraint clearly in the README.
- Phase 3+ adds: server-side session store (SQLite or vault-backed `chat_sessions/` directory), session continuity across devices and reloads, and an opt-in mode where the agent can retrieve past sessions via `read_note`.
- **Architectural constraint (Phase 1):** `POST /api/chat` already accepts a `session_id` field (echoed back without server-side storage). The wiring point exists; no payload changes are needed to implement LTR-3.

---

## 3. Non-Functional Requirements

### 3.1 Performance

| Requirement | Target |
|---|---|
| NFR-PERF-01: Ingest latency (p95) | < 5 seconds (transcribe → template → metadata → file write → re-index) |
| NFR-PERF-02: Search latency (p95) | < 1 second on vault with up to 10,000 notes |
| NFR-PERF-03: Chat first-token latency (p95) | < 2 seconds (Ollama local) |
| NFR-PERF-04: Voice transcription via Whisper | < 15 seconds for 2-minute audio clip |
| NFR-PERF-05: MCP tool response time (p95) | < 3 seconds (includes embed for search queries) |
| NFR-PERF-06: Graph data (`GET /api/graph`) | < 2 seconds for vault with up to 2,000 notes |
| NFR-PERF-07: Frontend initial load (SPA + assets, localhost) | < 2 seconds (Vite optimized build) |
| NFR-PERF-08: File watcher debounce | 2 seconds per file path (inbox watcher) to handle multi-write saves before triggering ingest; editor-save re-index coalescing uses a 10-second idle window per file via `ReindexQueue` (FR-WTCH-04a) |
| NFR-PERF-09: Graph data caching | `GET /api/graph` results SHALL be cached in memory and invalidated on any file watcher event. On cache miss, graph is rebuilt asynchronously; a stale cache result (up to 30 seconds old) is acceptable to serve while the rebuild is in progress. Cold-build time shall meet NFR-PERF-06. |

### 3.2 Security

| Requirement | Detail |
|---|---|
| NFR-SEC-01 | All `/mcp` endpoints require a valid access key (header preferred; query param discouraged — see FR-MCP-02) |
| NFR-SEC-02 | REST API endpoints are unauthenticated in Phase 1. The server SHALL bind to `127.0.0.1` by default to limit exposure to loopback only. Binding to `0.0.0.0` is opt-in via `server.host` config and requires explicit user intent. |
| NFR-SEC-03 | Secrets (`MCP_ACCESS_KEY`, API keys) SHALL never be logged or included in API responses. `GET /api/settings` SHALL return the MCP key as a masked string showing only the last 4 characters (e.g., `"••••••••a3f9"`). |
| NFR-SEC-04 | ChromaDB and vault directories SHALL be local-only; no automatic cloud sync |
| NFR-SEC-05 | The `.env` file SHALL be listed in `.gitignore`. `config.yaml` SHALL also be listed in `.gitignore`; a `config.yaml.example` with placeholder values SHALL be version-controlled instead. |
| NFR-SEC-06 | Credentials for any deferred future channel integrations SHALL be read from `.env` exclusively (never `config.yaml`). |
| NFR-SEC-07 | Vault paths in API requests (`file_path` params) SHALL be validated server-side: the resolved absolute path SHALL be confirmed to start with the configured vault root using `os.path.realpath`. Symlinks that resolve outside the vault root SHALL be rejected with `403 Forbidden`. |
| NFR-SEC-08 | The near-term mainline exposes no Teams webhook endpoint. Any future channel webhook SHALL enforce equivalent request authentication and reject unauthenticated requests with `401 Unauthorized`. |
| NFR-SEC-09 | The CORS policy SHALL be explicit. Allowed origins: `http://localhost:{server.port}` and `http://127.0.0.1:{server.port}` (API consumers); and in dev mode only, `http://localhost:5173` and `http://127.0.0.1:5173` (Vite dev server). Wide-open `*` CORS SHALL NOT be used. |
| NFR-SEC-10 | The `/api/ingest`, `/api/transcribe`, and `/api/chat` endpoints SHALL have per-IP rate limiting applied (e.g., 30 requests/minute for ingest/transcribe, 60/minute for chat) to prevent runaway MCP clients or scripts from exhausting the AI backend. |

### 3.3 Extensibility

| Requirement | Detail |
|---|---|
| NFR-EXT-01 | Switching active models across `ollama`, `foundry_local`, `azure`, and `openai` providers SHALL require no code changes — only config/env changes |
| NFR-EXT-02 | Replacing ChromaDB with Azure AI Search SHALL only require implementing `IndexLayer` ABC and updating the factory in `index/__init__.py` |
| NFR-EXT-03 | Adding a new capture source SHALL only require a new route posting to the ingest pipeline — no pipeline changes |
| NFR-EXT-04 | Adding a new MCP tool SHALL only require adding a `@mcp.tool()` decorated function |
| NFR-EXT-05 | Adding a new note template SHALL only require adding a YAML template file to `monocle/vault/templates/` |

### 3.4 Testing

| Requirement | Detail |
|---|---|
| NFR-TST-01 | Backend: `pytest` 8+. All tests in `monocle/tests/`. Run via `python -m pytest monocle/tests/ -x --tb=short -q`. |
| NFR-TST-02 | Frontend: Vitest 2+. All tests in `frontend/tests/`. Run via `cd frontend && npm run test -- --run`. |
| NFR-TST-03 | E2E: Playwright. Tests in `tests/e2e/`. Run via `playwright test`. Requires server running at `http://localhost:8000`. |
| NFR-TST-04 | Backend unit test coverage target: 80% for `VaultLayer`, `IndexLayer`, `IngestPipeline`, and all routers. |
| NFR-TST-05 | `IndexLayer` SHALL have a `MemoryIndex` in-memory implementation in `monocle/index/memory.py` used exclusively in tests (no embeddings, substring match only). All `IndexLayer` tests MUST be parametrized to run against both `MemoryIndex` and `ChromaIndex`. |
| NFR-TST-06 | All path traversal rejection, auth, and input validation tests SHALL live in `monocle/tests/test_security.py`. |
| NFR-TST-07 | `monocle/tests/conftest.py` SHALL provide a `tmp_vault` pytest fixture (a temporary directory pre-populated with 5+ fixture notes covering all template types) and a `memory_index` fixture. |
| NFR-TST-08 | Integration tests that require a live Ollama instance SHALL be marked `@pytest.mark.integration` and skipped by default. Run with `pytest -m integration`. |
| NFR-TST-09 | GitHub Copilot MUST run `python -m pytest monocle/tests/ -x --tb=short -q` after every backend change and `cd frontend && npm run test -- --run` after every frontend change before marking any task complete. |

---

### 3.5 Reliability

| Requirement | Detail |
|---|---|
| NFR-REL-01 | If metadata extraction fails, the note SHALL still be written with empty metadata rather than dropped |
| NFR-REL-02 | If Ollama / Foundry Local is temporarily unreachable, `POST /api/ingest` SHALL return `503 Service Unavailable` with a descriptive message |
| NFR-REL-03 | VaultLayer SHALL use atomic writes (write to temp file, then rename) to prevent partial writes |
| NFR-REL-04 | If the inbox watcher async task exits unexpectedly (Phase 1 unified process), the lifespan exception handler SHALL log an error and potentially trigger server shutdown or auto-restart (depending on deployment environment). Phase 3+ (separate OS subprocess) allows independent watcher restart without server restart. |
| NFR-REL-05 | The ChromaDB index MAY be rebuilt from scratch at any time by running `reindex --force`; this is the recovery procedure for index corruption |

---

## 4. Data Model

### 4.1 Note (vault file)

The canonical on-disk representation of every piece of knowledge in the vault. Stored as `<name>.md` with YAML frontmatter.

```python
class Note(BaseModel):
    file_path: str                       # Vault-relative path, e.g. "people/sarah.md"
    frontmatter: dict[str, Any]          # All YAML frontmatter fields (see 4.2)
    body: str                            # Markdown body below frontmatter
    created_at: datetime                 # From frontmatter `created` or file ctime
    updated_at: datetime                 # From frontmatter `updated` or file mtime
    word_count: int
    wikilinks: list[str]                 # Parsed [[link]] targets from body
```

### 4.2 Standard Frontmatter Fields

| Field | Type | Description |
|---|---|---|
| `type` | `str` | Note type (see 4.3) |
| `domain` | `str` | Business domain (`hr`, `engineering`, `personal`, ...) |
| `people` | `list[str]` | Names mentioned |
| `tags` | `list[str]` | Topic tags |
| `source` | `str` | Originating capture channel (`web`, `voice`, `mcp`, `import`) |
| `action_items` | `list[str]` | Follow-up tasks |
| `created` | `datetime` | ISO 8601 creation timestamp (set by ingest pipeline) |
| `updated` | `datetime` | ISO 8601 last-modified timestamp (updated on every save) |
| `links` | `list[LinkRef]` | Structured link metadata entries. Each entry: `{ target: str, relation?: str, ...extras }`. `target` resolves via `resolve_wikilink`. Plain string entries (`"Note Name"`) are also accepted and normalised. In addition to structured links, inline `[[wikilinks]]` in the body are parsed separately. |
| `confidence` | `float` | Agent-assessed quality score 0.0–1.0 (set by ingest, 1.0 for user-created notes) |
| `confidence_rationale` | `str \| null` | Human-audit explanation of the confidence score breakdown written at ingest time (e.g. `"Low metadata_coverage: missing required fields [status, date]"`) and shown in the capture workbench. Null for user-created notes and weekly summaries. |
| `review_status` | `str` | `"pending"` (awaiting review) or `"approved"` |
| `approved_by` | `str \| null` | `"system:auto"`, `"system:weekly-summary"`, or the user identity responsible for approval |
| `approved_at` | `datetime \| null` | Approval timestamp; null while pending |
| `approval_mode` | `str \| null` | `"auto"` or `"manual"`; null while pending |

### 4.3 Note Types

| Value | Template | Description |
|---|---|---|
| `person_note` | `person` | Observation about a specific person |
| `decision` | `decision` | A decision made, with context and rationale |
| `idea` | `idea` | Speculative or creative thought |
| `observation` | `observation` | Factual observation about a project or situation |
| `reference` | `reference` | Pointer to a URL, document, or external resource |
| `meeting_note` | `meeting` | Notes from a meeting |
| `project` | `project` | Project overview and status |
| `action_item` | `action_item` | A specific follow-up task |
| `weekly_summary` | `weekly_summary` | Auto-generated weekly summary |
| `other` | `blank` | Catch-all for unclassified / low-confidence content |

### 4.4 NoteChunk (ChromaDB index entry)

Each note is split into chunks before embedding. These are stored in ChromaDB — not in the vault.

```python
class NoteChunk(BaseModel):
    id: str                              # "{file_path}::{chunk_index}"
    file_path: str                       # Vault-relative path of the parent note
    chunk_index: int                     # Chunk number (0-based)
    text: str                            # Chunk text (~512 tokens)
    embedding: list[float]               # Pre-computed embedding
    metadata: dict                       # Mirrors key frontmatter fields for filtering
```

ChromaDB `metadata` fields per chunk:

```python
{
    "file_path": str,
    "type": str,
    "domain": str,
    "source": str,
    "people": str,       # JSON-encoded list (ChromaDB only supports str metadata values)
    "tags": str,         # JSON-encoded list
    "updated_at": str,   # ISO 8601
    "chunk_index": int,
}
```

### 4.5 NoteMetadata (extracted by AIProvider)

The `type` field is the frontmatter note type value (e.g., `"person_note"`). The `template` field is the template name used to create the file (e.g., `"person"`). They are related but distinct: multiple `type` values may map to the same template. The mapping is defined in the template YAML schema under `maps_to_types`.

```python
class NoteMetadata(BaseModel):
    type: str                        # Note type value written to frontmatter (e.g. "person_note")
    template: str = "other"          # Template file name used for file creation (e.g. "person")
    title: str = ""                  # Extracted note title; used to derive the filename slug in create_from_template()
    domain: str = ""
    people: list[str] = []
    tags: list[str] = []
    action_items: list[str] = []
    frontmatter_extras: dict = {}    # Additional template-specific frontmatter fields
    confidence: float = 1.0          # Set after confidence scoring step in pipeline
    confidence_rationale: str | None = None  # Human-audit explanation; NOT set by extract_note_metadata(); set by IngestConfidence scoring (step 7) then written to frontmatter via patch_frontmatter()
    review_status: str = "pending"
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_mode: str | None = None
```

### 4.6 NoteRef (search result reference)

Lightweight reference returned in search results and browse listings.

```python
class NoteRef(BaseModel):
    file_path: str
    type: str
    domain: str
    people: list[str]
    tags: list[str]
    updated_at: datetime
    word_count: int
```

### 4.7 Page (generic paginated response)

Returned by list endpoints that support `limit`/`offset` pagination (e.g., `GET /api/notes`).

```python
from typing import Generic, TypeVar
T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    total: int          # Total items matching the filter (before limit/offset)
    offset: int         # Zero-based start offset of this page
    limit: int          # Items per page requested
    items: list[T]      # Slice of results
```

The `GET /api/notes` response is `Page[NoteRef]` with `total`, `offset`, `limit`, and `items` fields. Import as needed — `Page[NoteRef]`, `Page[Note]`, etc.

### 4.8 BrainStats

```python
class BrainStats(BaseModel):
    total_notes: int
    total_chunks: int
    total_people: int
    total_tags: int
    by_source: dict[str, int]
    by_type: dict[str, int]
    by_domain: dict[str, int]
    last_30_days: int
    pending_review: int               # Notes with review_status == "pending"
    vault_size_mb: float
    index_size_mb: float
    latency_p50_ms: dict[str, float]  # p50 latency per operation (keys: "search", "ingest", "chat")
    latency_p95_ms: dict[str, float]  # p95 latency per operation; sourced from OTel histogram snapshots
```

---

## 5. Project Structure

```
monocle/
├── config.yaml.example                # Config template (committed); config.yaml is gitignored
├── .env.example                       # Secrets template (committed); .env is gitignored
├── openapi.json                       # Auto-generated OpenAPI spec (committed; regenerate after route changes)
├── pyproject.toml                     # Package metadata + all backend deps
├── pytest.ini                         # testpaths = monocle/tests
├── docs/
│   ├── prd.md
│   ├── srs.md
│   ├── ui-design.md
│   └── build-plan.md                  # Copilot-maintained build sequencing document
├── vault/                             # Obsidian-compatible markdown vault (gitignored or user-tracked)
│   ├── .obsidianignore                # Excludes .versions/, .trash/ from Obsidian index
│   ├── .templates/                    # User-facing Markdown templates (visible in Obsidian)
│   ├── .versions/                     # Shadow copies of previous note versions (excluded from index)
│   ├── .trash/                        # Soft-deleted notes (excluded from index)
│   ├── people/                        # Entity hub: individuals, contacts
│   ├── organizations/                 # Entity hub: companies, teams, orgs (optional)
│   ├── work/                          # Domain: all work-related notes (org/role metadata in frontmatter)
│   ├── technologies/                  # Domain: languages, tools, frameworks, how-tos, architecture
│   ├── theology/                      # Domain: beliefs, philosophy, spiritual exploration
│   ├── entertainment/                 # Domain: games, books, shows, music (each as subfolders)
│   ├── projects/                      # Cross-domain hub: active learning, side, or hobby projects (optional)
│   ├── summaries/                     # Auto-generated weekly summaries (flat or by domain)
│   └── inbox/                         # Unclassified captures land here
├── data/
│   ├── chroma/                        # ChromaDB persistence (gitignored)
│   └── failed_ingests.json            # Failed-ingest registry (gitignored); JSON array, persisted across restarts,
│                                      # written atomically (write temp + rename); stdlib json only (no new deps).
├── frontend/                          # React + Vite SPA
│   ├── index.html
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── package.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   ├── schema.d.ts            # Auto-generated from openapi.json via openapi-typescript
│   │   │   ├── client.ts              # Typed fetch wrapper (handles SSE, errors)
│   │   │   └── *.ts                   # Per-endpoint typed API functions
│   │   ├── components/
│   │   │   ├── Chat/
│   │   │   ├── DocumentBrowser/
│   │   │   ├── Search/
│   │   │   ├── Graph/
│   │   │   ├── Stats/
│   │   │   ├── VoiceModal/
│   │   │   ├── CaptureWorkbench/
│   │   │   ├── CommandPalette/
│   │   │   ├── SettingsModal/
│   │   │   └── shared/
│   │   ├── hooks/
│   │   └── styles/
│   ├── tests/                         # Vitest component tests
│   └── dist/                          # Vite build output (served by FastAPI; gitignored)
├── tests/
│   └── e2e/                           # Playwright E2E tests (require running server)
└── monocle/                        # Python package (importable as `import monocle`)
    ├── __init__.py
    ├── __main__.py                    # Entry: `python -m monocle <command>`
    ├── main.py                        # FastAPI app + router registration + lifespan
    ├── config.py                      # Settings model (Pydantic v2) + loader
    ├── models.py                      # All shared Pydantic models
    ├── watcher.py                     # VaultWatcher: watchdog observer + asyncio re-index queue
    ├── graph.py                       # GraphBuilder: ego-graph construction + in-memory cache
    ├── mcp_server.py                  # FastMCP tool definitions + auth middleware
    ├── cli.py                         # Typer CLI (serve, reindex, pull-models, stats, search, export, versions)
    ├── ai/
    │   ├── __init__.py                # get_provider() factory
    │   ├── base.py                    # AIProvider ABC
    │   ├── ollama_provider.py
    │   ├── foundry_local_provider.py
    │   └── azure_provider.py
    ├── index/
    │   ├── __init__.py                # get_index() factory
    │   ├── base.py                    # IndexLayer ABC
    │   ├── chroma.py                  # ChromaDB implementation
    │   └── memory.py                  # In-memory implementation (tests only; no embeddings required)
    ├── vault/
    │   ├── __init__.py                # VaultLayer class
    │   ├── normalise.py               # normalise_frontmatter() — applies schema defaults to existing notes
    │   ├── wikilinks.py               # parse_wikilinks(), parse_links_field(), resolve_wikilink()
    │   └── templates/                 # Machine-readable YAML note template schemas
    │       ├── person.yaml
    │       ├── decision.yaml
    │       ├── project.yaml
    │       ├── meeting.yaml
    │       ├── idea.yaml
    │       ├── observation.yaml
    │       ├── reference.yaml
    │       ├── action_item.yaml
    │       ├── blank.yaml
    │       └── weekly_summary.yaml
    ├── ingest/
    │   ├── __init__.py                # IngestPipeline class + IngestPluginRegistry singleton
    │   ├── plugin.py                  # IngestPlugin ABC
    │   ├── classify.py                # REMOVED — routing is handled by agents/routing.py (RoutingAgent); this file is not created
    │   ├── chunker.py                 # Text chunking (512 tokens / 64 overlap; tiktoken cl100k_base)
    │   ├── confidence.py              # IngestConfidence scoring
    │   └── plugins/
    │       ├── text_plugin.py         # TextPlugin — passthrough for plain text
    │       ├── audio_plugin.py        # AudioPlugin — delegates to AIProvider.transcribe()
    │       └── ...                    # Additional deferred plugins may be added later behind the registry seam
    ├── agents/
    │   ├── __init__.py
    │   ├── tools.py                   # Shared agent tool library (@tool decorated)
    │   ├── weekly_summary.py          # Weekly Summary agent
    │   ├── routing.py                 # RoutingAgent — sentence-starter + LLM template dispatch (replaces ingest_agent.py)
    │   └── scheduler.py               # APScheduler setup
    ├── routers/
    │   ├── health.py                  # GET /api/health
    │   ├── capture_workbench.py       # GET /api/capture-workbench
    │   ├── ingest.py                  # POST /api/ingest, POST /api/ingest/stream
    │   ├── ingest_failures.py         # POST /api/ingest/failures/retry, DELETE /api/ingest/failures/{id}
    │   ├── notes.py                   # GET/PUT/PATCH/DELETE /api/notes/*
    │   ├── search.py                  # GET /api/search, /api/search/keyword
    │   ├── graph.py                   # GET /api/graph
    │   ├── stats.py                   # GET /api/stats
    │   ├── transcribe.py              # POST /api/transcribe
    │   ├── chat.py                    # POST /api/chat (SSE streaming)
    │   ├── agents.py                  # POST /api/agents/*
    │   ├── review.py                  # PATCH /api/review/{path}/approve, PATCH /api/review/{path}/reject
    │   └── settings.py                # GET/PATCH /api/settings, POST /api/settings/rotate-mcp-key
    └── tests/
        ├── conftest.py                # tmp_vault fixture + memory_index fixture
        ├── test_vault.py
        ├── test_index.py              # Parametrized: MemoryIndex + ChromaIndex
        ├── test_ingest.py
        ├── test_api.py
        ├── test_security.py           # Path traversal, auth, input validation
        ├── test_graph.py
        ├── test_mcp.py
        ├── test_agents.py
        ├── test_settings.py
        ├── test_review.py
        ├── test_cli.py
        └── test_scheduler.py
```

---

## 6. Configuration Reference

### config.yaml (template)

```yaml
ai:
  provider: ollama                  # "ollama" | "foundry_local" | "azure"
  embed_model: nomic-embed-text     # Ollama embed model name
  embed_dimensions: 1536            # Fixed across providers for migration compatibility
  chat_model: llama3.2              # Ollama chat model for metadata extraction + agent chat
  ollama_base_url: http://localhost:11434

foundry_local:
  base_url: http://localhost:5272   # Foundry Local OpenAI-compat API
  embed_model: nomic-embed-text-v1.5
  chat_model: phi-4

vault:
  path: ./vault                     # Path to the Obsidian-compatible markdown vault
  default_folder: inbox             # Unclassified notes land here
  watch: true                       # Enable watchdog file watcher
  debounce_ms: 2000         # Inbox watcher debounce: 2 seconds per file path (FR-WTCH-03)

index:
  backend: chroma                   # "chroma" (Phase 1) | "azure_search" (Phase 2)
  chroma_persist_path: ./data/chroma
  collection_name: notes
  chunk_size_tokens: 512            # Tokens per chunk; measured by tiktoken cl100k_base tokenizer
  chunk_overlap_tokens: 64

server:
  host: 127.0.0.1              # Loopback by default; set 0.0.0.0 only to expose to network
  port: 8000
  mcp_access_key_env: MCP_ACCESS_KEY
  frontend_dist: ./frontend/dist    # Path to Vite build output

agents:
  weekly_summary:
    enabled: true
    cron: "0 17 * * 5"              # Friday at 17:00 (per PRD default)
    domains: []                     # Filter to specific domains; empty = all
  reindex:
    enabled: true
    cron: "0 3 * * 0"               # Sunday at 03:00 — catches Obsidian edits outside inbox

review:
  queue_threshold: 1.0              # Show pending notes with confidence <= threshold
  auto_approve_threshold_pct: 0     # 0 disables auto-approval; 90 auto-approves confidence >= 0.90
  confidence_weights:
    template_match: 0.35            # Weight for template correctness sub-score
    metadata_coverage: 0.30         # Weight for required frontmatter field coverage
    tag_plausibility: 0.20          # Weight for tag semantic consistency
    entity_match: 0.15              # Weight for entity cross-reference match

telemetry:
  enabled: true
  otlp_endpoint: http://localhost:4317  # AI Toolkit gRPC (or any OTLP backend)
  otlp_transport: grpc
  log_level: INFO
  log_format: text                  # text (dev) | json (prod)
  enable_sensitive_data: true       # include prompts/completions in traces

ui:
  chat_session_history_limit: 10    # Sessions retained in browser localStorage
```

### .env.example

```dotenv
# Required for MCP authentication
MCP_ACCESS_KEY=change-me-to-a-random-64-char-hex-string

# Required only if ai.provider = azure
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-05-01-preview
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini

# Required only if any ai.models entry uses provider = openai
OPENAI_API_KEY=

# Required for Azure AI Search (Phase 2)
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=monocle

# Reserved for deferred future channel integrations
# TEAMS_APP_ID=
# TEAMS_APP_PASSWORD=
```

---

## 7. MCP Client Connection Reference

> **Authentication note:** The `x-monocle-key` header is preferred. The `?key=` query parameter is supported for client compatibility but is discouraged (appears in server logs).

### Claude Desktop

Settings → Connectors → Add custom connector  
URL: `http://localhost:8000/mcp`  
Headers: `x-monocle-key: <MCP_ACCESS_KEY>`

### VS Code Copilot / Cursor (mcp.json or settings.json)

```json
{
  "mcpServers": {
    "monocle": {
      "url": "http://localhost:8000/mcp?key=${env:MCP_ACCESS_KEY}"
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add --transport http monocle \
  http://localhost:8000/mcp \
  --header "x-monocle-key: <MCP_ACCESS_KEY>"
```

---

## 8. Phase 2 Outline (Azure Migration)

The following changes constitute a complete Phase 1 → Phase 2 migration. No Phase 1 code is deleted; only config values and new implementations are swapped in.

| Area | Phase 1 | Phase 2 |
|---|---|---|
| AI provider | Ollama / Foundry Local (local) | Azure OpenAI (`ai.provider: azure`) |
| Embed model | Provider-specific 1536-dim local model | `text-embedding-3-small` (1536-dim) — no re-embedding required when dimensions remain unchanged |
| Index backend | ChromaDB (`index.backend: chroma`) | Azure AI Search (`index.backend: azure_search`) — `AzureSearchIndex(IndexLayer)` implemented, factory updated |
| Storage for notes | Local vault filesystem | Azure Blob Storage or OneDrive (optional), vault path still works locally |
| Compute | FastAPI + uvicorn (local) | Azure Container App or Azure Functions (ASGI transport) |
| Teams integration | Webhook ingest only (`POST /api/teams/messages`) | Full proactive Teams bot with adaptive cards, Azure Bot Service channel |
| Auth | None (localhost assumed) | Azure Entra ID (MSAL) — user identity scopes vault and index |
| Multi-user | Single user | User ID field on `Note` frontmatter; all index queries scoped by user |
| Scheduled agents | APScheduler in-process | Azure Functions Timer Trigger or Logic Apps |
| Secrets management | `.env` file | Azure Key Vault references via Managed Identity |
