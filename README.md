# Monocle

> A personal agentic knowledge system — a single pane of glass over your notes.

Monocle is an Obsidian-compatible Markdown vault with a FastAPI backend, semantic search, multi-agent orchestration via Microsoft Agent Framework, and a React web frontend for chat, document browsing, graph visualisation, and a confidence-based review queue. It captures knowledge from web, voice, Teams, and MCP clients; extracts structured metadata via LLM; and surfaces connections in a force-directed graph.

**Stack:** Python 3.11+ · FastAPI · ChromaDB · APScheduler · React 18 · Vite 5 · playwright

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | 3.14 tested and working |
| [uv](https://docs.astral.sh/uv/) | latest | package manager — `pip install uv` |
| Node.js | ≥ 20 | for frontend dev server and tests |
| [Ollama](https://ollama.com/) | latest | local LLM backend (default; Azure/Foundry also supported) |
| Git | any | |

---

## Quick Start

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd monocle
```

### 2. Install backend dependencies

```bash
uv sync
```

All Python dependencies are installed into `.venv/` automatically. Never call `pip` directly — always use `uv run` or `uv sync`.

### 3. Pull Ollama models

```bash
# Embedding model (required for semantic search)
ollama pull nomic-embed-text

# Chat / reasoning model
ollama pull llama3.2
```

> **Azure OpenAI / Foundry Local:** Skip this step and configure the `ai.provider` in `config.yaml` (see step 5).

### 4. Create your config files

```bash
# Main configuration (gitignored — safe to customise freely)
cp config.yaml.example config.yaml

# Secrets (gitignored — never commit this file)
cp .env.example .env
```

Edit `config.yaml`:
- Set `vault.path` to where you want notes stored (default: `./vault`).
- Set `ai.provider` if not using Ollama (`ollama` | `foundry_local` | `azure`).

Edit `.env`:
- Set `MCP_ACCESS_KEY` to a random secret (used by MCP clients to authenticate).
- Fill in Azure/Foundry credentials if using a cloud provider.

### 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 6. Start the application

```bash
# Development mode — unified process with prefixed logs and crash-restart
uv run python -m monocle dev
```

The API server starts on `http://127.0.0.1:8000`.

In a second terminal, start the frontend dev server:

```bash
cd frontend
npm run dev
```

The UI is available at `http://localhost:5173`.

### 7. First run checklist

- Open `http://localhost:5173` — the health indicator (top-right) should turn green within ~10 seconds.
- Click the ⚙️ icon to open Settings and verify the AI provider is reachable.
- Type a message in the chat box and press `Enter` to test end-to-end ingestion and retrieval.
- Drop a `.md` file into your vault's `inbox/` directory to test the file watcher.

---

## MCP Client Setup

Monocle exposes an MCP server at `http://127.0.0.1:8000/mcp` using the 2025-03-26 Streamable HTTP transport.

**Authentication:** Set the `x-monocle-key` header (or `?key=` query param) to the value of `MCP_ACCESS_KEY` from your `.env` file.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "monocle": {
      "url": "http://127.0.0.1:8000/mcp",
      "headers": { "x-monocle-key": "<your MCP_ACCESS_KEY>" }
    }
  }
}
```

### VS Code GitHub Copilot (MCP extension)

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "monocle": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": { "x-monocle-key": "<your MCP_ACCESS_KEY>" }
    }
  }
}
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+/` | Open command palette |
| `Ctrl+K` | Focus semantic search |
| `Ctrl+Shift+K` | Focus keyword search |
| `Ctrl+N` | New note (navigate to Docs) |
| `Ctrl+,` | Open Settings |
| `Ctrl+\` | Toggle sidebar |
| `Escape` | Close the active modal/panel |

---

## CLI Reference

```bash
uv run python -m monocle serve          # Start production server
uv run python -m monocle dev            # Start development server (debug logging + crash-restart)
uv run python -m monocle reindex        # Re-index stale vault notes
uv run python -m monocle reindex --force  # Force re-index of all vault notes
uv run python -m monocle stats          # Print vault statistics to stdout
uv run python -m monocle search "query"  # Semantic search from the CLI
uv run python -m monocle export --output ./export.zip  # Export vault as ZIP
uv run python -m monocle versions list <path>     # List note versions
uv run python -m monocle versions restore <path> --version <ts>  # Restore a version
```

---

## Running Tests

```bash
# Backend unit tests (always run after backend changes)
uv run python -m pytest monocle/tests/ -x --tb=short -q

# Frontend unit tests
cd frontend && npm run test -- --run

# E2E tests (requires API server at :8000 AND frontend dev server at :5173)
# From the repo root:
npx playwright test

# TypeScript type-check
cd frontend && npx tsc --noEmit
```

Integration tests (require a live Ollama instance) are deselected by default. To include them:

```bash
uv run python -m pytest monocle/tests/ -m integration --tb=short -q
```

---

## Obsidian Compatibility

The `vault/` directory is a fully Obsidian-compatible Markdown vault:

- `vault/.obsidianignore` hides `.versions/` (note history) and `.trash/` (soft-deleted notes) from Obsidian's file list.
- All frontmatter fields (`confidence`, `review_status`, `approval_mode`, etc.) are standard YAML — Obsidian renders them without errors.
- `[[wikilinks]]` written by agents resolve correctly in Obsidian's link graph.
- `vault/.templates/` contains user-facing Markdown templates visible in Obsidian.

Simply open the `vault/` directory as an Obsidian vault to use it alongside Monocle.

---

## Architecture Overview

```
Capture (web/voice/Teams/MCP) → POST /api/ingest → IngestPipeline → VaultLayer (.md files)
                                                                    ↕ re-index trigger
                                                              ChromaDB (embeddings)
GET /api/* (search/graph/notes) ← VaultLayer + IndexLayer
GET /mcp   (FastMCP, Streamable HTTP) ← AIProvider + VaultLayer
```

- Single unified process: `python -m monocle serve` starts FastAPI + MCP server + APScheduler + integrated inbox file watcher.
- `python -m monocle dev` adds prefixed logging (`[API]`, `[WATCHER]`, `[SCHEDULER]`, `[INGEST]`, `[AGENT]`) and crash-restart.
- Backend port: `127.0.0.1:8000` · Frontend dev: `localhost:5173` · OTLP: `localhost:4317` (AI Toolkit).

---

## Observability

Monocle exports OpenTelemetry traces, metrics, and logs via OTLP. The default sink is [VS Code AI Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio) (gRPC port 4317). Any OTLP-compatible backend works — set `telemetry.otlp_endpoint` in `config.yaml`.

```yaml
telemetry:
  enabled: true
  otlp_endpoint: "http://localhost:4317"
  otlp_transport: grpc
```

---

# Developing this Application

I have created varous iterations of this app as a hobby project for some time.  After finishing an iteration that produced a working (but slow) application using Microsoft Agent Framework + Ollama, I encountered Nate B Jones [Open Brain concept](https://www.youtube.com/watch?v=2JiMmye2ez), which took the knowledge layer and placed it behind an MCP server for speed, modularity, and to avoid vendor lock-in.  This led me to start from scratch once more.

This application was developed in large part through GitHub Copilot.  I spent a decent amount of time in the planning stage, defining the architecture, milestones, and technical spikes to validate assumptions before writing code.  At the conclusion of that stage multiple models were used to evaluate my design and identify potential gaps, issues or improvements to the plan and design.

# Preparing this repository for GitHub Copilot

Process:
1. Create folder, open in VSCode
2. Initialize git: `git init`
3. Create a VSCode workspace: `Ctrl+Shift_P > Workspaces: Save Workspace As...`
4. Using GitHub Copilot Custom Agents (instructing the agent to emulate specialists such as Product Manager, UX Designer, Cybsersecurity Expert, Development Architect) draft PRD, UI Design, and SRS documentation, as well as a build plan.  Some things that were important to me:
   1. Debugging in VSCode.  I included the creation and maintenance of 
   2. Tracing using AI Toolkit
5. Create a GitHub Copilot workspace instructions file
6. Create a local index `Ctrl+Shift+P → Chat: Build Local Workspace Index` (since this was not an AzDO or GitHub project which support remote index)

# References
- Nate B Jones [Build Your Open Brain](https://promptkit.natebjones.com/20260224_uq1_guide_main)
- Nate B Jones [Open Brain Companion Prompts](https://promptkit.natebjones.com/20260224_uq1_promptkit_1)

---

# GitHub Copilot Action Log Summary

## 2026-03-14 – Claude Sonnet 4.6
- Cross-referenced Gnomish design docs against Monocle docs and identified 8 improvements worth porting
- Updated `docs/ui-design.md`: added weight-driven edge visual encoding spec (thickness 0.5–5 px, opacity 30–100 %), typed edge color table (structured / wikilink / co-mention), Export PNG control, modifier-key sidebar navigation (`Ctrl+Click`, `Shift+Click`), three-tier backlinks panel description, multi-pane state reservation note in Application Shell, review-pending amber pulse on graph nodes, and inline text-selection mini-toolbar for expanded graph nodes
- Updated `docs/srs.md`: expanded FR-WEB-07 with all graph visual requirements (edge encoding, edge types, node pulse, node expand + text selection, export); added `edge_type` field to FR-API-13 graph edge response and updated explanation paragraph; added `link_type` field and three-tier description to FR-API-12a backlinks response
