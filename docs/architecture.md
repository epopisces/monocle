---
type: reference
project: monocle
last-updated: 2026-03-31
---

# Monocle — Architecture Diagrams

Reference diagrams for the Monocle knowledge system. All diagrams use [Mermaid](https://mermaid.js.org/) syntax and render natively in GitHub, VS Code, and Obsidian.

---

## 1. System Overview — Layers & Technologies

High-level view of the four major layers and the technologies used within each.

```mermaid
graph TB
    subgraph CAPTURE["Capture Layer"]
        direction LR
        WEB["React Web App<br/>(Vite 5 / React 18)"]
        VOICE["Voice Modal<br/>(Web Speech API +<br/>MediaRecorder)"]
        MCP_CLIENT["MCP Clients<br/>(Claude, Copilot,<br/>Cursor)"]
        TEAMS["Teams Bot<br/>(botbuilder-core)"]
    end

    subgraph API["API Layer  ·  FastAPI 0.115 · uvicorn · 127.0.0.1:8000"]
        direction TB
        INGEST_R["/api/ingest"]
        TRANSCRIBE_R["/api/transcribe"]
        NOTES_R["/api/notes"]
        SEARCH_R["/api/search"]
        GRAPH_R["/api/graph"]
        CHAT_R["/api/chat (SSE)"]
        AGENTS_R["/api/agents"]
        REVIEW_R["/api/review"]
        SETTINGS_R["/api/settings"]
        HEALTH_R["/api/health"]
        STATS_R["/api/stats"]
        MCP_R["/mcp  (Streamable HTTP)"]
    end

    subgraph SERVICES["Service Layer"]
        direction TB
        INGEST_P["IngestPipeline<br/>(8-step)"]
        WATCHER["InboxWatcher<br/>(watchdog)"]
        REINDEX_Q["ReindexQueue<br/>(asyncio coalescing)"]
        REINDEX_A["ReindexAgent<br/>(stale detection)"]
        SCHEDULER["MonocleScheduler<br/>(APScheduler 3.x)"]
        WEEKLY_A["WeeklySummaryAgent<br/>(scikit-learn clustering)"]
        ROUTING_A["RoutingAgent<br/>(sentence-starters fast-path)"]
        CHAT_A["ChatAgent<br/>(MS Agent Framework)"]
        GRAPH_B["GraphBuilder<br/>(BFS, in-memory cache)"]
        MCP_S["MCP Server<br/>(FastMCP)"]
        PROCESS_M["ProcessManager<br/>(crash-restart subprocesses)"]
    end

    subgraph AI["AI Layer"]
        direction LR
        AI_P["AIProvider ABC<br/>(runtime-selectable)"]
        OLLAMA["OllamaProvider<br/>localhost:11434"]
        FOUNDRY["FoundryLocalProvider<br/>localhost:5272"]
        AZURE["AzureOpenAIProvider<br/>Azure AI Services"]
        WHISPER["TranscriptionProvider<br/>(WhisperCpp / Subprocess<br/>/ NativeOpenAI)"]
    end

    subgraph DATA["Data Layer"]
        direction LR
        VAULT["Vault<br/>(Markdown .md files<br/>+ YAML frontmatter)"]
        CHROMA["ChromaDB<br/>(embeddings +<br/>frontmatter metadata)"]
        CONFIG["config.yaml<br/>+ .env"]
        FAILED["FailedIngestRegistry<br/>(data/failed_ingests.json)"]
    end

    %% Capture → API
    WEB -->|REST| INGEST_R
    WEB -->|REST| NOTES_R
    WEB -->|REST| SEARCH_R
    WEB -->|REST| GRAPH_R
    WEB -->|REST| CHAT_R
    WEB -->|REST| STATS_R
    WEB -->|REST| REVIEW_R
    WEB -->|REST| SETTINGS_R
    VOICE -->|multipart| TRANSCRIBE_R
    VOICE -->|REST| INGEST_R
    TEAMS -->|REST| INGEST_R
    MCP_CLIENT -->|Streamable HTTP| MCP_R

    %% API → Services
    INGEST_R --> INGEST_P
    TRANSCRIBE_R --> AI_P
    NOTES_R --> REINDEX_Q
    AGENTS_R --> WEEKLY_A
    CHAT_R --> CHAT_A
    GRAPH_R --> GRAPH_B
    MCP_R --> MCP_S

    %% Services → AI
    INGEST_P --> ROUTING_A
    INGEST_P --> AI_P
    CHAT_A --> AI_P
    WEEKLY_A --> AI_P
    REINDEX_A --> AI_P
    AI_P --> OLLAMA
    AI_P --> FOUNDRY
    AI_P --> AZURE
    AI_P --> WHISPER

    %% Services → Data
    INGEST_P --> VAULT
    INGEST_P --> FAILED
    VAULT <-->|read/write| NOTES_R
    VAULT <-->|read/write| REINDEX_Q
    WATCHER -->|push| REINDEX_Q
    REINDEX_Q -->|embed + upsert| CHROMA
    REINDEX_A --> VAULT
    REINDEX_A --> CHROMA
    GRAPH_B --> VAULT
    SEARCH_R --> CHROMA
    SEARCH_R --> VAULT
    MCP_S --> VAULT
    MCP_S --> CHROMA

    SCHEDULER --> WEEKLY_A
    SCHEDULER --> REINDEX_A
    PROCESS_M -. manages .-> WATCHER
    PROCESS_M -. manages .-> SCHEDULER

    %% Styling
    classDef layer fill:#1e2430,stroke:#3d4f6b,color:#cdd6f4
    classDef api fill:#1e3a2f,stroke:#2d6b4a,color:#a6e3a1
    classDef service fill:#2a1f3d,stroke:#5e3d8a,color:#cba6f7
    classDef ai fill:#3d2a1e,stroke:#8a5e3d,color:#fab387
    classDef data fill:#1e2d3d,stroke:#3d6b8a,color:#89dceb
    class CAPTURE layer
    class API api
    class SERVICES service
    class AI ai
    class DATA data
```

---

## 2. Ingest Pipeline — 8-Step Data Flow

The canonical path from a raw capture to a persisted, indexed note.

```mermaid
flowchart TD
    START(["POST /api/ingest<br/>IngestRequest"])

    S1["①  Plugin Resolution<br/>IngestPluginRegistry.resolve()<br/>(TextPlugin / AudioPlugin / TeamsPlugin)"]
    S2["②  Content Extraction<br/>plugin.extract()<br/>  ▸ text: pass-through<br/>  ▸ audio: ai.transcribe()<br/>  ▸ teams: parse webhook JSON"]
    S3["③  Routing<br/>RoutingAgent<br/>  ▸ template_hint → skip LLM (conf=1.0)<br/>  ▸ sentence_starters fast-path (conf=0.9)<br/>  ▸ LLM JSON fallback"]
    S4["④  Metadata Extraction<br/>ai.extract_note_metadata()<br/>via prompts/extract.md<br/>(concurrent with ③ when LLM needed)"]
    S5["⑤  Note Construction<br/>NoteMetadata assembled<br/>+ body composed"]
    S6["⑥  File Write + Re-index<br/>vault.write_note()<br/>ai.embed_batch()<br/>index.upsert_chunks()"]
    S7["⑦  Confidence Scoring<br/>score_confidence() — deterministic<br/>0.35×template_match + 0.30×metadata_coverage<br/>+ 0.20×tag_plausibility + 0.15×entity_match<br/>(reuses embedding from step ⑥)"]
    S8["⑧  Frontmatter Patch<br/>index.patch_file_metadata()<br/>confidence + review_status written back"]

    DUP{"Duplicate?<br/>similarity≥0.95<br/>AND ≤7 days"}
    ERR["❌  Error Path<br/>.error.md sidecar written<br/>FailedIngestRegistry.add()"]
    DONE(["IngestResponse<br/>{ note, confidence }"])

    START --> S1 --> S2
    S2 --> DUP
    DUP -->|"allow_duplicate=true<br/>or no match"| S3
    DUP -->|"DuplicateSuspected"| DONE

    S3 & S4 -.->|asyncio.gather| S3
    S3 --> S5
    S4 --> S5
    S5 --> S6 --> S7 --> S8 --> DONE

    S3 -->|exception| ERR
    S4 -->|exception| ERR
    S5 -->|exception| ERR

    style DUP fill:#3d3520,stroke:#a89060,color:#f9e2af
    style ERR fill:#3d2020,stroke:#a06060,color:#f38ba8
    style DONE fill:#203d2a,stroke:#60a080,color:#a6e3a1
    style START fill:#203d2a,stroke:#60a080,color:#a6e3a1
```

---

## 3. Re-index Flow — File Change to Updated Index

Shows how vault file changes (from any source) propagate to ChromaDB.

```mermaid
sequenceDiagram
    participant Source as Trigger Source
    participant WQ as ReindexQueue
    participant CB as _reindex_file callback
    participant VL as VaultLayer
    participant AI as AIProvider
    participant IX as ChromaDB
    participant GR as GraphBuilder

    note over Source: Any of:<br/>• InboxWatcher (watchdog)<br/>• PUT/PATCH /api/notes<br/>• POST /api/ingest (step ⑥)<br/>• MCP create_note / update_note

    Source->>WQ: push(file_path)
    note over WQ: 10-second idle coalesce window<br/>(same file path deduplicated)

    WQ->>CB: _reindex_file(file_path)
    CB->>GR: invalidate() [always first]
    CB->>CB: _review_pending_count = None

    CB->>VL: read_note(file_path)
    alt File gone
        VL-->>CB: exception
        CB-->>WQ: skip (file deleted)
    else File exists
        VL-->>CB: Note

        CB->>CB: chunk_text(note.body, 512 tokens, 64 overlap)
        alt No chunks (empty body)
            CB->>IX: delete_file(file_path)
        else Chunks exist
            CB->>AI: embed_batch(chunks_text)
            AI-->>CB: embeddings list[list[float]]
            CB->>IX: upsert_chunks(NoteChunk list)
        end
    end
```

---

## 4. Chat / Agent Interaction — SSE Streaming Flow

How a user chat message flows through the agent framework to the AI and back.

```mermaid
sequenceDiagram
    participant Browser as Browser (React)
    participant API as POST /api/chat
    participant CA as ChatAgent
    participant AI as AIProvider
    participant VT as VaultTools
    participant VL as VaultLayer
    participant IX as ChromaDB

    Browser->>API: { messages, session_id }
    API->>CA: create_chat_agent(ai, vault, index, ...)

    loop AgentRunResponseUpdate stream
        CA->>AI: chat(messages, tools=vault_tool_schemas)
        AI-->>CA: token | tool_call

        alt Text token
            CA-->>API: TextContent
            API-->>Browser: SSE: event=token, data=<text>
        end

        alt Tool call: search_vault
            CA->>VT: search_vault(query)
            VT->>AI: embed(query)
            AI-->>VT: embedding
            VT->>IX: search(embedding)
            IX-->>VT: NoteChunk list
            VT-->>CA: FunctionResultContent
            CA-->>API: FunctionCallContent
            API-->>Browser: SSE: event=tool_call, data=<name>
        end

        alt Tool call: create_note
            CA->>VT: create_note(...)
            VT->>VL: write_note() + review_status=pending
            VL-->>VT: file_path
            VT-->>CA: FunctionResultContent (status=created)
            CA-->>API: FunctionResultContent
            API-->>Browser: SSE: event=note_created, data=<path>
        end
    end

    API-->>Browser: SSE: event=done, data={ session_id }
```

---

## 5. Weekly Summary Agent — Process Flow

The scheduled background agent that clusters notes and writes weekly summaries.

```mermaid
flowchart TD
    CRON["APScheduler Cron Job<br/>Friday 17:00<br/>agents.reindex cron: Sunday 03:00"]
    COLLECT["Collect notes<br/>vault.list_notes(limit=500)<br/>updated within 7 days"]
    EMBED["Fetch embeddings<br/>index.get_embeddings_by_file()<br/>(chunk_index=0 per file)"]

    BRANCH{"≥4 notes?"}

    CLUSTER["AgglomerativeClustering<br/>(scikit-learn, cosine metric)<br/>metric=cosine, linkage=average"]
    LLM_GROUP["LLM grouping fallback<br/>_llm_group_notes()<br/>JSON prompt to AI"]

    SUMMARISE["_summarise_cluster()<br/>per-cluster chat call<br/>prompts/weekly_review.md"]
    WRITE["vault.write_note()<br/>summaries/YYYY-WW.md"]
    DONE(["Done"])

    CRON --> COLLECT --> EMBED --> BRANCH
    BRANCH -->|yes| CLUSTER --> SUMMARISE
    BRANCH -->|no| LLM_GROUP --> SUMMARISE
    SUMMARISE --> WRITE --> DONE
```

---

## 6. Frontend Component Hierarchy

React component tree and state ownership.

```mermaid
graph TD
    APP["App.tsx<br/>(AppContext + useReducer)<br/>global state: settings, activeView, notifications"]

    subgraph LAYOUT["Layout"]
        SB["Sidebar<br/>(navigation)"]
        CMD["CommandPalette<br/>(⌘K / Ctrl+K)"]
    end

    subgraph VIEWS["Route Views"]
        CHAT_V["Chat<br/>(useChat hook,<br/>SSE EventSource)"]
        DB_V["DocumentBrowser<br/>(list + CRUD)"]
        SEARCH_V["Search<br/>(debounced query)"]
        GRAPH_V["Graph<br/>(React Force Graph,<br/>D3 + WebGL)"]
        STATS_V["Stats<br/>(Recharts)"]
        REVIEW_V["ReviewQueue<br/>(approve / reject)"]
    end

    subgraph OVERLAYS["Overlays / Modals"]
        VOICE_M["VoiceModal<br/>(Web Speech API primary<br/>MediaRecorder fallback)"]
        SETTINGS_M["SettingsModal<br/>(PATCH /api/settings)"]
        FAILED_C["FailedCaptures<br/>(ingest failures)"]
    end

    APP --> LAYOUT
    APP --> VIEWS
    APP --> OVERLAYS

    CHAT_V -->|"useChat()"| SSE["SSE stream<br/>/api/chat"]
    VOICE_M -->|"multipart POST"| TRANS["POST /api/transcribe"]
    VOICE_M -->|"POST"| INGEST["POST /api/ingest"]
    SEARCH_V -->|"GET"| SRCH["GET /api/search"]
    GRAPH_V -->|"GET"| GRPH["GET /api/graph"]
    STATS_V -->|"GET"| STTS["GET /api/stats"]
    REVIEW_V -->|"PATCH"| RVIEW["PATCH /api/review/{path}/approve"]
    DB_V -->|"CRUD"| NOTES["GET/PUT/PATCH/DELETE<br/>/api/notes/{path}"]
    SETTINGS_M -->|"GET/PATCH"| STNGS["GET/PATCH /api/settings"]
```

---

## 7. Data Model Relationships

Core domain entities and how they relate to each other.

```mermaid
erDiagram
    NOTE {
        string file_path PK
        string title
        string body
        float mtime
    }
    NOTE_METADATA {
        string type
        string template
        string domain
        string source
        float confidence
        string review_status
        string approved_by
        datetime created
        datetime updated
    }
    NOTE_CHUNK {
        string chunk_id PK
        string file_path FK
        int chunk_index
        string text
        list_float embedding
    }
    LINK_REF {
        string target
        string relation
    }
    GRAPH_NODE {
        string id PK
        string label
        string type
        int degree
        int weight
    }
    GRAPH_EDGE {
        string source FK
        string target FK
        string edge_type
        string relation
        int weight
    }
    FAILED_INGEST {
        string id PK
        string original_request
        string error_message
        datetime failed_at
        bool retried
    }
    INGEST_CONFIDENCE {
        float score
        float template_match
        float metadata_coverage
        float tag_plausibility
        float entity_match
        bool similar_note_detected
        string similar_note_path
    }

    NOTE ||--|| NOTE_METADATA : "has"
    NOTE ||--o{ NOTE_CHUNK : "chunked into"
    NOTE ||--o{ LINK_REF : "links to"
    NOTE_METADATA }o--o{ LINK_REF : "structured links"
    GRAPH_NODE ||--o{ GRAPH_EDGE : "source of"
    GRAPH_NODE ||--o{ GRAPH_EDGE : "target of"
    NOTE ..|| GRAPH_NODE : "maps to"
    NOTE ||--o| INGEST_CONFIDENCE : "scored by"
```

---

## 8. Process Topology — Unified vs Separate Processes

How the single process forks when `--separate-processes` is used (M22 ProcessManager).

```mermaid
graph LR
    subgraph UNIFIED["Unified Mode (default)"]
        direction TB
        UP["monocle serve<br/>(single process, PID 1)"]
        UP_API["FastAPI + MCP Server<br/>:8000"]
        UP_WATCH["InboxWatcher<br/>(async task)"]
        UP_SCHED["APScheduler<br/>(async task)"]
        UP --> UP_API
        UP --> UP_WATCH
        UP --> UP_SCHED
    end

    subgraph SEPARATE["Separate-Processes Mode<br/>(--separate-processes or MONOCLE_SEPARATE_PROCESSES=1)"]
        direction TB
        PM["ProcessManager<br/>(main process)"]
        CAPTURE_P["monocle capture<br/>MONOCLE_COMPONENT=capture<br/>(API-only, no watcher/scheduler)"]
        WATCH_P["monocle watch<br/>(InboxWatcher only)"]
        SCHED_P["monocle scheduler<br/>(APScheduler only)"]
        PM -->|"spawn + crash-restart"| CAPTURE_P
        PM -->|"spawn + crash-restart"| WATCH_P
        PM -->|"spawn + crash-restart"| SCHED_P
    end

    note1["Crash-restart uses<br/>exponential back-off"]
    SEPARATE --- note1
```

---

## 9. MCP Server — Auth & Tool Routing

How MCP clients authenticate and which tools are available.

```mermaid
flowchart TD
    CLIENT["MCP Client<br/>(Claude / Copilot / Cursor)"]
    TRANSPORT["GET/POST /mcp<br/>Streamable HTTP Transport<br/>(MCP 2025-03-26)"]
    AUTH["_MCPAuthMiddleware<br/>(ASGI wrapper)<br/>x-monocle-key header<br/>OR ?key= query param<br/>hmac.compare_digest()"]
    AUTH_FAIL["HTTP 401<br/>{ error: Unauthorized }"]

    TOOLS["FastMCP Tool Router"]

    T1["search_vault<br/>embed query → ChromaDB"]
    T2["read_note<br/>vault.read_note()"]
    T3["browse_recent<br/>vault.list_notes()"]
    T4["capture_thought<br/>→ IngestPipeline"]
    T5["create_note<br/>vault.write_note()<br/>review_status=pending<br/>→ ReindexQueue"]
    T6["update_note<br/>vault.write_note()<br/>updated=now()<br/>→ ReindexQueue"]
    T7["get_graph<br/>GraphBuilder.build()"]
    T8["get_stats<br/>BrainStats (paged)"]

    CLIENT --> TRANSPORT --> AUTH
    AUTH -->|"invalid / missing key"| AUTH_FAIL
    AUTH -->|"valid key"| TOOLS
    TOOLS --> T1 & T2 & T3 & T4 & T5 & T6 & T7 & T8
```

---

## 10. AI Provider Selection & Transcription

Runtime provider selection and the transcription sub-abstraction.

```mermaid
flowchart TD
    CFG["config.yaml<br/>ai.provider: ollama|foundry_local|azure"]
    FACTORY["get_provider(settings)<br/>factory function"]

    subgraph PROVIDERS["AIProvider implementations"]
        OLLAMA_P["OllamaProvider<br/>• embed: nomic-embed-text<br/>• chat: llama3.2<br/>• auto-pull on first use"]
        FOUNDRY_P["FoundryLocalProvider<br/>• OpenAI-compatible HTTP API<br/>• embed_dimensions configurable"]
        AZURE_P["AzureOpenAIProvider<br/>• openai.AsyncAzureOpenAI<br/>• dims on embed<br/>• env var config only"]
    end

    subgraph TRANSCRIPTION["TranscriptionProvider (decoupled)"]
        TR_FACTORY["get_transcription_provider(settings)<br/>ai.transcribe_backend"]
        WHISPER_CPP["WhisperCppTranscriptionProvider<br/>httpx POST to whisper.cpp<br/>ai.transcribe_url"]
        SUBPROCESS["SubprocessTranscriptionProvider<br/>openai-whisper CLI<br/>(subprocess)"]
        NATIVE["NativeOpenAITranscriptionProvider<br/>OpenAI /audio/transcriptions<br/>(Foundry/Azure)"]
    end

    HOT_RELOAD["Hot-reload on PATCH /api/settings<br/>ai.provider change → new get_provider()"]

    CFG --> FACTORY
    FACTORY --> OLLAMA_P
    FACTORY --> FOUNDRY_P
    FACTORY --> AZURE_P
    FACTORY --> TR_FACTORY
    TR_FACTORY --> WHISPER_CPP
    TR_FACTORY --> SUBPROCESS
    TR_FACTORY --> NATIVE
    HOT_RELOAD --> FACTORY

    OLLAMA_P & FOUNDRY_P & AZURE_P --- TRANSCRIPTION
```

---

## 11. Confidence Scoring — Formula Breakdown

The deterministic confidence scoring algorithm (no LLM, step ⑦ of ingest).

```mermaid
flowchart LR
    NOTE_DATA["Note content<br/>+ NoteMetadata"]

    TM["template_match<br/>weight: 0.35<br/>──────────────<br/>Does routing template<br/>match expected type?<br/>(0.0, 0.5, or 1.0)"]
    MC["metadata_coverage<br/>weight: 0.30<br/>──────────────<br/>Fraction of expected<br/>fields populated<br/>(per template schema)"]
    TP["tag_plausibility<br/>weight: 0.20<br/>──────────────<br/>Tag text appears in<br/>note body? (substring<br/>match, no embedding)"]
    EM["entity_match<br/>weight: 0.15<br/>──────────────<br/>vault.resolve_wikilink()<br/>for each people/tag<br/>entity in note"]

    FORMULA["confidence =<br/>0.35 × template_match<br/>+ 0.30 × metadata_coverage<br/>+ 0.20 × tag_plausibility<br/>+ 0.15 × entity_match"]

    AUTO_APPROVE{"≥ auto_approve<br/>threshold_pct?"}
    PENDING["review_status: pending<br/>(manual review required)"]
    APPROVED["review_status: approved<br/>approved_by: system:auto<br/>approval_mode: auto"]

    NOTE_DATA --> TM & MC & TP & EM
    TM & MC & TP & EM --> FORMULA
    FORMULA --> AUTO_APPROVE
    AUTO_APPROVE -->|yes| APPROVED
    AUTO_APPROVE -->|no| PENDING
```

---

## 12. Vault File Layout

How the Markdown vault is structured on disk.

```
vault/
├── inbox/                    ← InboxWatcher monitors this directory
│   └── <captured notes>      ← Dropped here by AllCaptureSources → moved by IngestPipeline
├── people/                   ← type: person_note
├── projects/                 ← type: project
├── work/                     ← domain: work (decisions, observations, meeting_notes)
├── summaries/                ← type: weekly_summary  (YYYY-WW.md)
├── technologies/             ← reference notes
├── .templates/               ← User-facing Markdown templates (Obsidian)
├── .versions/                ← Shadow copy on each PUT (millisecond timestamp)
│   └── <path>/<ts_ms>.md
└── .trash/                   ← Soft-delete staging
    └── <path>.md
```

**Note frontmatter schema** (written by IngestPipeline, read by VaultLayer):

```yaml
---
title: "Example note"
type: person_note          # NOTE_TYPES enum
template: person           # vault/.templates/<template>.md
domain: work               # work | personal | ...
source: web                # web | voice | teams | mcp | import | agent
people: ["Alice", "Bob"]
tags: ["onboarding", "q1-2026"]
action_items: []
links:
  - target: "[[projects/ProjectX]]"
    relation: "works-on"
confidence: 0.87
confidence_rationale: "..."
review_status: pending     # pending | approved | rejected
approved_by: null          # "system:auto" or user identity
approved_at: null
approval_mode: null        # auto | manual
created: 2026-03-31T10:00:00Z
updated: 2026-03-31T10:00:00Z
---
```
