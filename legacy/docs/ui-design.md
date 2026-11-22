# UI Design Document — Monocle

**Version:** 2.0  
**Date:** 2026-03-10  
**Status:** Draft  
**Supersedes:** v1.0

---

## 1. Technology

The frontend is a **React 18 + Vite 5** single-page application served by the FastAPI backend as static assets. State management uses React context + `useReducer` (no Redux). API calls use `fetch` with a lightweight wrapper. No UI component library — a custom design system (see §2) is implemented directly.

---

## 2. Design Principles

| Principle | Rationale |
|---|---|
| **Chat as the primary surface** | The chat interface is where most interaction happens; everything else is one click away from it |
| **Vault transparency** | Users can see, edit, and navigate the actual Markdown files — the UI doesn't hide the data model |
| **Confirmation is essential** | Every ingest operation returns structured feedback so the user can trust and calibrate quality |
| **Dark mode by default** | Developers and knowledge workers frequently operate in low-light environments |
| **Progressively disclosed complexity** | Chat starters handle 80% of use cases; advanced features (graph, editor, stats) are one nav click deeper |
| **Agent-augmented, not agent-controlled** | AI assists within user-initiated actions; it does not restructure the UI or navigate autonomously |

---

## 3. Color System

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--bg-base` | `#f8f9fa` | `#111318` | Page background |
| `--bg-surface` | `#ffffff` | `#1c1f26` | Cards, panels, sidebar |
| `--bg-elevated` | `#f0f2f5` | `#252830` | Input fields, hover states, code blocks |
| `--border` | `#e2e5ea` | `#2e3240` | Card borders, dividers |
| `--text-primary` | `#111318` | `#ebedf2` | Body text, headings |
| `--text-secondary` | `#5a6072` | `#8891a8` | Labels, metadata, captions |
| `--accent` | `#5865f2` | `#7c8af7` | Primary action buttons, active nav items, links |
| `--accent-hover` | `#4752c4` | `#9099fb` | Button hover |
| `--success` | `#2d9e6b` | `#3dbf84` | Confirmation banners, success badges |
| `--error` | `#d9534f` | `#e96b67` | Error banners |
| `--warning` | `#e08a00` | `#f5a623` | Warnings, pending states |
| `--tag-bg` | `#e8eaff` | `#2a2e4a` | Pill/tag backgrounds |
| `--tag-text` | `#3a45c4` | `#a0aaff` | Pill/tag text |
| `--graph-person` | `#5865f2` | `#7c8af7` | Person nodes in graph |
| `--graph-topic` | `#2d9e6b` | `#3dbf84` | Topic/tag nodes in graph |
| `--graph-edge` | `#8891a8` | `#5a6072` | Graph edges |
| `--review-pending` | `#e08a00` | `#f5a623` | Notification badge, low-confidence confidence pill |

**Fonts:**  
- UI: `Inter`, fallback `system-ui`  
- Editor / code: `JetBrains Mono`, fallback `monospace`  
- Size scale: 12 / 13 / 14 / 16 / 20 / 24 / 32px

**Border radius:** 8px (card), 6px (button/input), 20px (pill/tag), 12px (modal)  
**Shadows:** `0 1px 3px rgba(0,0,0,0.12)` (card), `0 4px 12px rgba(0,0,0,0.2)` (elevated/modal)

---

## 4. Application Shell

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ◉ Monocle   [🔍 Search vault…              Ctrl+E]  ● [🎤] [🔔] [⚙] │  ← Topbar (52px)
├───────────┬─────────────────────────────────────────────────────────────┤
│           │                                                             │
│  💬 Chat  │                                                             │
│  📄 Docs  │              Main Content Area                             │
│  🔍 Search│                                                             │
│  ◉ Graph  │                                                             │
│  📊 Stats │                                                             │
│           │                                                             │
└───────────┴─────────────────────────────────────────────────────────────┘
   220px              flex-grow
```

**Left nav** (220px fixed): icon + label nav items; active item has accent-colored left border + `--bg-elevated` background. Collapses to icon-only rail at ≤ 1200px viewport width.

**Main content area** (`flex-grow`): Phase 1 renders a single content panel. The internal React state tracks an ordered `tabs` array (each entry: `{ tabId, type: "note"|"graph", noteId? }`) so the UI is architecturally ready for multi-pane expansion in Phase 2 without a state model redesign. The tab bar is not surfaced in the Phase 1 UI but the state is wired.

**Topbar**: app name/logo on the left; **omnisearch bar** (§5.6) centered and taking the majority of horizontal space; compact health dot (colored, no label), voice capture button, one capture-workbench button/badge for actionable ingest work, and settings cog on the right. Backend dot color is driven by `GET /api/health`: green = `ai_reachable: true`, amber = server reachable but `status: indexing` or AI check in-progress, red = `ai_reachable: false`. The workbench badge uses `--review-pending` color and is hidden when the actionable count is 0.

**Settings modal** (overlay): backend selection dropdown (Ollama / Foundry Local / Azure AI Services), model configuration fields for the selected backend, vault path display, MCP access key management, confidence review threshold slider.

---

## 5. Screens

### 5.1 Chat (Default / Home)

The primary working surface. A chat thread with the agent, with chat starters shown when the thread is empty.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│           ┌──────────────────────────────────┐             │
│           │  Chat Starters                   │             │
│           │  ┌──────────────┐ ┌────────────┐ │             │
│           │  │ 👤 Notes on  │ │ 📋 Open    │ │             │
│           │  │  a person    │ │  action    │ │             │
│           │  │              │ │  items     │ │             │
│           │  └──────────────┘ └────────────┘ │             │
│           │  ┌──────────────┐ ┌────────────┐ │             │
│           │  │ 📅 Weekly    │ │ 🎤 Capture │ │             │
│           │  │  review      │ │  voice note│ │             │
│           │  └──────────────┘ └────────────┘ │             │
│           └──────────────────────────────────┘             │
│                                                             │
│ ─────────────────────────────────────────────────────────  │
│ ┌────────────────────────────────────────────── [🎤] [→] ┐ │
│ │  Message the assistant…                                 │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Chat starters** are 2×3 grid (or fewer) of cards. Each card has an icon, short label, and an optional chevron if it opens a sub-flow. Clicking a starter pre-fills the input or immediately invokes the agent.

**Predefined starters:**

| Label | Action |
|---|---|
| Notes on a person | Fills input: "What are my notes on [person name]?" with entity autocomplete |
| Open action items | Agent invokes `search_vault` filtered to `type: action_item`, `status: open` |
| Weekly review | Agent invokes the weekly summary workflow |
| Capture voice note | Opens voice capture modal |
| Recent decisions | Agent queries recent notes with `type: decision` |
| Summarize project | Fills input: "Summarize my notes about [project]" |

**Message input:**
- Multiline, auto-grows to 6 lines maximum
- `Enter` sends; `Shift+Enter` inserts newline
- `🎤` button opens voice capture (replaces text input contents with transcription)
- `→` send button
- **Session picker** (dropdown top-right of chat panel): shows the last 10 sessions by timestamp; selecting one restores its message history from `localStorage`. A `+ New` option clears the current thread and starts a fresh session.

**Chat thread:**
- User messages: right-aligned, `--bg-elevated` background
- Agent messages: left-aligned, `--bg-surface`; Markdown rendered (headings, lists, code blocks, bold/italic)
- Streaming: agent response streams token-by-token; a blinking cursor indicates pending output
- Agent tool calls shown as collapsed disclosure: "Used `search_vault` — 4 results" (expandable)
- Note creation/edit confirmations render as an inline note preview card (see §8.1)

---

### 5.2 Document Browser

Two-panel layout: file tree (left) + document preview/editor (right). Vault is organized by domain (users browse this way); note types are indexed via frontmatter metadata.

```
┌──────────────────┬──────────────────────────────────────────┐
│  📁 Vault  [+ New]│  people/sarah-chen.md          [✏ Edit] │
│  ──────────────  │  ────────────────────────────────────── │
│  📂 people/      │  ---                                     │
│    sarah-chen.md │  type: person                           │
│    john-doe.md   │  domain: social                         │
│  📂 work/        │  tags: [career, consulting]             │
│    📂 projects/  │  ---                                     │
│    📂 decisions/ │                                          │
│    📂 meetings/  │  # Sarah Chen                            │
│  📂 entertainment/│                                          │
│    📂 games/     │  Sarah mentioned she's thinking about   │
│  📂 summaries/   │  leaving her job to start a consulting  │
│  📂 inbox/       │  business…                              │
│                  │                                          │
│  [🔍 Filter...]  │  ## Action Items                         │
│                  │  - [ ] Check in re consulting plans     │
│                  │                                          │
│                  │  ## Related                              │
│                  │  [[Consulting Project]]                  │
└──────────────────┴──────────────────────────────────────────┘
   260px                    flex-grow
```

**File tree:**
- Folder expand/collapse; files sorted alphabetically within folders
- File type icon based on frontmatter `type` field
- Right-click context menu: Rename, Move, Delete, Open in Graph
- `Ctrl/Cmd+Click` — opens the note in a new browser tab (Phase 2: opens in a new pane)
- `Shift+Click` — opens the Graph view with the clicked note set as the focus node
- "New" button opens a template picker modal before creating the note

**Template picker modal:**

```
┌─ New Note ──────────────────────────────────┐
│  Choose a template:                          │
│                                              │
│  ○ Person note        ○ Decision            │
│  ○ Project note       ○ Meeting notes       │
│  ○ Weekly summary     ○ Blank               │
│                                              │
│  [Cancel]                          [Create] │
└──────────────────────────────────────────────┘
```

**Document view (read mode):**
- Frontmatter rendered as a structured metadata panel above the body
- Markdown body rendered with syntax highlighting
- Wikilinks (`[[Note Name]]`) are clickable; opens the linked note
- `✏ Edit` button switches to editor mode

**Document editor mode:**
- **Triple editing modes:**
  - **YAML mode (default):** Full-width CodeMirror 6 instance with Markdown syntax highlighting + YAML frontmatter block at the top
  - **Preview mode:** Lightweight rich preview editing for common formatting actions while preserving Markdown as the underlying source of truth. This is not a separate heavyweight WYSIWYG document model; it is a Markdown-first editing surface.
  - **Form mode (new):** Template Editor UI — frontmatter fields rendered as interactive form inputs based on the note's type-specific template schema
    - Text fields for string values (e.g., `name`, `title`)
    - Toggles for boolean values (e.g., `reviewed`)
    - Multiselect dropdowns for array values (e.g., `tags`, `people`)
    - Date/time pickers for timestamp fields (e.g., `created`, `updated`)
    - Enum dropdowns for constrained string values (read from template YAML `enum` key)
    - Required fields marked with a red `*` label; form prevents save if any required field is empty
    - Description text below each field pulled from template schema's `description` key (optional)
  - Mode toggle in editor toolbar: "YAML" / "Preview" / "Form" radio buttons; switching modes preserves unsaved changes (user is prompted if switching with pending changes)
  
- Toolbar: Bold, Italic, Heading, Link, Wikilink, Checkbox (visible in YAML and Preview modes); in Form mode, toolbar is simplified to just a Save button
- Auto-saves on 2s debounce; editor saves update the file immediately but re-indexing is coalesced in the background so active typing does not retrigger embeddings on every save
- `AI Assist` panel (slide-in from right, 360px): text input to instruct the agent on the current note (e.g., "Extract action items and add them as checkboxes", "Summarize this note in 2 sentences and add as a tldr frontmatter field")
- `Ctrl+S` saves immediately
- **Backlinks side panel** (toggle in toolbar or via right margin): slides in from the right (300px wide) showing notes that link to the current note
  - Displays: source note title, link relation type (if structured), context snippet (1-2 line extract around the link)
  - Each backlink is clickable to navigate to that source note
  - Grouped by relation type if multiple structured links exist from the same source
  - Backlinks are grouped into three tiers, displayed in this order:
    1. **Structured links** — sources where the target note appears in a `links` frontmatter entry; shows the `relation` type (if present) as a small badge and a 1–2 line context snippet
    2. **Wikilinks** — sources containing `[[Note Name]]` in the body; shows a 1–2 line context snippet around the link text
    3. **Co-mentions** — sources that share the same `people` or `tags` frontmatter values as the current note; rendered in a visually muted style (`--text-secondary` color, smaller font) to distinguish them from direct references; each entry is prefixed with a label such as "Also mentions Sarah Chen" or "Also tagged: consulting"
  - An empty-state message per tier (e.g., "No direct links") is shown when a tier has no items; the panel is hidden entirely only when all three tiers are empty
  - Empty state: "No backlinks" if the note is not referenced anywhere

---

### 5.3 Search

```
┌──────────────────────────────────────────────────────────────┐
│  [ 🔍  Search your vault...            ]  [⚙ Filters ▾]    │
│  Mode: ● Semantic  ○ Keyword   Threshold: [──●────] 0.5     │
│  Type: [All ▾]   Source: [All ▾]   Domain: [All ▾]          │
│  ────────────────────────────────────────────────────────── │
│  [Note card — 92% match]                                    │
│  [Note card — 87% match]                                    │
│  [Note card — 74% match]                                    │
└──────────────────────────────────────────────────────────────┘
```

- Semantic mode: vector similarity search; query is embedded at search time
- Keyword mode: frontmatter metadata freetext search + body substring match (fast, no embedding)
- Results rendered as note cards (§8 Note Card Component)
- Each result card has: `[Open]` `[Edit]` `[Add to Graph]` `[Delete]` inline actions
- Empty state: "No results above this threshold. Try lowering the similarity threshold or switching to keyword mode."

---

### 5.4 Node Graph View

A unified ego-graph rendered with **React Force Graph** (D3-backed, WebGL for performance). There are no separate "modes" — all node types (people, notes, tags) are displayed together by default. The user can focus on a specific node or browse the full vault graph.

```
┌──────────────────────────────────────────────────────────────┐
│  Focus: [________ Sarah Chen ____________________ ▾]         │
│  Depth: [1] [●2] [3]   Types: [●Person] [●Note] [●Tag]      │
│                                        [Reset View]          │
│  ──────────────────────────────────────────────────────────  │
│                                                              │
│                    ◉ Sarah (deg 0, 100%)                     │
│                   /  \                                       │
│          ●Migrate   ●Alex  (deg 1, 100% opacity)             │
│         /                \                                   │
│       ●Azure             ●Q4 tag  (deg 2, 75% opacity)      │
│                    ↑                                         │
│       edges with relation label ("manages", "involves")      │
│                                                              │
│  ◉ Person  ● Note  · Tag  — wikilink  ─→ structured link    │
│  [Zoom +/-]  [Export PNG]                                    │
└──────────────────────────────────────────────────────────────┘
```

**Ego mode (focus selected):** The focused node is centred and rendered at maximum size and 100% opacity. Each additional hop from the focus node reduces node opacity by 25% and node size by 15%:

| Degree | Opacity | Relative Size |
|---|---|---|
| 0 (focus) | 100% | 100% |
| 1 | 100% | 85% |
| 2 | 75% | 72% |
| 3 | 50% | 61% |

Nodes beyond `max_degree` are not rendered. The API call is `GET /api/graph?focus=<file_path>&max_degree=<n>&types=<csv>`.

**Full vault mode (no focus):** All nodes are shown. Node size and opacity are proportional to connectivity `weight` (number of edges). Useful for discovering hubs and orphaned notes at a glance.

**Controls:**
- **Focus input** — autocomplete across person, note, and tag names; selecting an item enters ego mode; clearing the field returns to full vault mode
- **Depth toggle** — [1] [2] [3] buttons set `max_degree` in ego mode
- **Type filter chips** — [Person ✓][Note ✓][Tag ✓]; toggling a chip excludes that node type from `types=` param and redraws
- **Reset View** — clears focus, resets depth to 2, resets type filters; returns to full vault mode
- **Export PNG** — captures the visible canvas via `canvas.toBlob()` and triggers a browser download; filename defaults to `graph-<focus-or-vault>-<date>.png`; SVG and PDF export are Phase 2 stretch goals

**Edge rendering:**

Edges are visually differentiated by type and — for wikilink and structured edges — by weight:

| Edge type | Source | Style | Color |
|---|---|---|---|
| Structured link | `links` frontmatter | Solid; `relation` label at midpoint | `--accent` tinted by relation |
| Wikilink | `[[…]]` body | Thin, undecorated | `--graph-edge` neutral grey |
| Co-mention | Shared `people`/`tags` | Dotted, no label | `--text-secondary` muted |

**Weight-driven visual encoding** (wikilink and structured edges only):
- Thickness: `0.5 + (weight / 10) × 4.5` px — 0.5 px at weight 0, 5 px at weight 10
- Opacity: `30 + (weight / 10) × 70` % — 30 % at weight 0, 100 % at weight 10
- Edges with `weight < 2` are rendered below all other edges so they recede without being hidden entirely

**Node interaction:**
- **Hover:** tooltip with node name and edge count
- **Click:** side panel slides in with top 5 related notes and the node's `relation` to the current focus
- **Double-click:** navigates to the note in Document Browser; drag to reposition (persisted to `localStorage`)
- **Expand:** click the expand icon on a node to open its full note content inline; while expanded, text within the note body is selectable — selecting text reveals a floating mini-toolbar with *Link to note*, *Link to tag*, *Bold*, *Italic* actions, enabling inline enrichment without leaving the graph
- **Review-pending pulse:** nodes whose note has `review_status: pending` display a subtle repeating amber pulse (`--review-pending` color); clicking a pulsing node opens the Capture Workbench (§7) pre-filtered to that note, providing a spatial shortcut to the review workflow from within the graph

---

### 5.5 Stats

```
┌──────────────────────────────────────────────────────────────┐
│  Knowledge Base Overview                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐      │
│  │  2,847   │ │   63     │ │  142     │ │    89     │      │
│  │  notes   │ │  people  │ │  tags    │ │  open AIs │      │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘      │
│                                                              │
│  Ingestion by Source (last 30 days)                         │
│  ████████████  web / chat    614                            │
│  ██████         MCP           289                           │
│  ████           import         91                           │
│  ██             voice          48                           │
│                                                              │
│  Notes by Type                    Activity (last 8 weeks)  │
│  [Horizontal bar chart]           [Sparkline bar chart]    │
│                                                              │
│  Source Quality Index ⓘ                                    │
│  MCP: ★★★★☆  Voice: ★★★★★  Web: ★★★☆☆  Import: ★★★☆☆      │
└──────────────────────────────────────────────────────────────┘
```

**Source Quality Index:** Computed from metadata completeness (tags populated, people identified, action items extracted) per source. Shown as a star rating. Provides feedback to iteratively improve capture quality per channel.

Charts: **Recharts** bundled in the React bundle (no CDN). All chart data fetched from `GET /stats`.

---

### 5.6 Topbar Omnisearch

A full-width search bar centered in the topbar, accessible from anywhere in the app via `Ctrl+E`.

```
┌────────────────────────────────────────────────────────────┐
│  [🔍  Search vault…                             Ctrl+E   ] │
└────────────────────────────────────────────────────────────┘
                        ↓ dropdown (≥3 chars typed):
┌────────────────────────────────────────────────────────────┐
│  In filename                                               │
│  ● people/sarah-chen.md         Sarah Chen                │
│  ─────────────────────────────────────────────────────    │
│  In title / tags                                           │
│  ● work/q4-planning.md          Q4 Planning               │
│  ─────────────────────────────────────────────────────    │
│  In body                                                   │
│  ● ideas/consulting.md          Consulting Ideas          │
│  ─────────────────────────────────────────────────────    │
│  🤖  Search semantically for "sarah"                       │
└────────────────────────────────────────────────────────────┘
```

**Behavior:**
- **Keyboard shortcut `Ctrl+E`** focuses the input from anywhere in the app (global `keydown` listener; no-op when focus is already in a form/input)
- Search fires automatically after a **300 ms debounce** when the query is **≥ 3 characters** — no Enter required
- Results come from `GET /api/search/omni` — a pure text scan requiring **no AI or embeddings**
- Result ordering (strict priority): filename matches → frontmatter matches (title, tags, people, type, domain) → body matches
- A note appears in only one bucket (highest priority match wins)
- Selecting a result navigates to `/docs?path=<encoded_path>` (opens the note in Document Browser)
- "Search semantically" option (always visible when query ≥ 3 chars) navigates to the **Search screen** (`/search?q=<query>&mode=semantic`) — the Search screen reads `?q` and `?mode` URL params to pre-populate and auto-trigger the search

**Keyboard navigation:**
- `↑` / `↓` — move selection through results and the semantic option
- `Enter` — navigate to selected item; if nothing selected, open first result (or semantic option if no results)
- `Escape` — close the dropdown and blur the input

**Visual design:**
- Input: `--bg-elevated` background, 8px border-radius, full-width up to 500px max
- Dropdown: `--bg-surface` with `--shadow-elevated`, positioned below the input, max 400px wide matching input, max-height 360px with scroll
- Group labels (e.g. "In filename"): `--text-secondary`, 11px, uppercase
- Selected result: `--accent` left border, `--bg-elevated` background
- Semantic option: separated by a divider, italic accent text

---

## 6. Voice Capture Modal

Triggered from the chat `🎤` button or the "Capture voice note" chat starter.

```
┌─ Voice Capture ─────────────────────────────────────────┐
│                                                          │
│              🎤   Recording... 0:14                      │
│           ●────────────────────●                         │
│                 [■ Stop]                                 │
│                                                          │
│  ─ Transcription ──────────────────────────────────────  │
│  "Sarah mentioned she's thinking about starting a       │
│  consulting business focused on healthcare data…"       │
│                                                          │
│  ─ Detected template ──────────────────────────────────  │
│  person_note   [Change ▾]                               │
│                                                          │
│  [✕ Discard]           [← Edit in Chat]  [✓ Save Note] │
└──────────────────────────────────────────────────────────┘
```

**Flow:**
1. Browser Web Speech API attempts transcription in real time
2. If Web Speech API is unavailable (non-Chrome/Edge), audio is recorded as a blob and sent to `POST /transcribe` (Whisper via Ollama)
3. Transcription appears in modal as it completes
4. Agent classifies content and suggests a template
5. User can: save directly, edit in chat (sends transcription as chat message for further refinement), or discard

---

## 7. Capture Workbench

A right-anchored slide-over panel or dedicated route triggered by clicking the topbar capture-workbench button.

```
                              ┌─ Capture Workbench (3 items) ──────┐
                              │  [Prepared] [Pending] [Failures]   │
                              │  ─────────────────────────────────  │
                              │  ┌──────────────────────────────┐ │
                              │  │ prepared  voice   2 actions    │ │
                              │  │ Sarah mentioned she’s thinking │ │
                              │  │ about leaving her job…         │ │
                              │  │ [True-up] [Review] [Capture]  │ │
                              │  └──────────────────────────────┘ │
                              │  ┌──────────────────────────────┐ │
                              │  │ pending   mcp    71%          │ │
                              │  │ Decided to migrate to Azure…   │ │
                              │  │ [Fix ✏]           [Approve ✓] │ │
                              │  └──────────────────────────────┘ │
                              │  ┌──────────────────────────────┐ │
                              │  │ failed    web    retryable    │ │
                              │  │ URL capture could not be       │ │
                              │  │ summarized in time…            │ │
                              │  │ [Inspect] [Retry] [Dismiss]   │ │
                              │  └──────────────────────────────┘ │
                              │                                   │
                              │  [Bulk Approve ✓] [Close ×]      │
                              └───────────────────────────────────┘
```

**Workbench behavior:**
- Opens as a right-anchored slide-over (400px wide) or dedicated route; `Escape` closes the slide-over variant
- Presents three sections or tabs: `Prepared`, `Pending Review`, and `Failures`
- `Prepared` items surface dormant-ready sessions with digest, related-note context, and actions such as `True-up`, `Review`, and `Fast Capture` when allowed
- `Pending Review` items retain confidence-first ordering and approval/fix actions for pending notes
- `Failures` surface retryable failed ingests with `Inspect`, `Retry`, and `Dismiss`
- The topbar badge reflects one actionable workbench count rather than separate review and failure counts
- Detailed note editing still routes into the Document Browser when the user chooses `Fix`

---

## 7.1 Workbench Sections

- **Prepared:** ingest sessions waiting for review, true-up, or fast capture
- **Pending Review:** notes or proposed actions that still require explicit human approval
- **Failures:** failed ingests, failed preparation, or failed execution records that require inspection or retry
- Each section can share the same shell, filtering, and keyboard behavior so the workbench feels like one surface instead of three separate drawers

---

## 8. Note Card Component

Reused in Search results, Browse lists, Chat confirmations, and Graph side panel.

```
┌────────────────────────────────────────────────────────────┐
│  person_note  ·  voice  ·  people/sarah-chen.md           │  ← meta row
│  ────────────────────────────────────────────────────────  │
│  Sarah mentioned she's thinking about leaving her job      │  ← content
│  to start a consulting business…                           │  (2-line clamp)
│  ────────────────────────────────────────────────────────  │
│  career  consulting  Sarah Chen                  87% match │  ← tags + score
└────────────────────────────────────────────────────────────┘
```

- Clicking the card body opens full note in Document Browser
- The similarity score (%) is only shown in Search results
- Source badge uses the Source Badge system (§9)
- When a note has `review_status: pending`, a small amber dot appears in the top-right corner of the card

---

## 9. Source Badge

Every note carries a `source` frontmatter value. Rendered as a small monospaced badge in note cards and the Stats screen.

| Source | Badge | Meaning |
|---|---|---|
| `web` | `web` | Chat capture or direct web form |
| `mcp` | `mcp` | Captured via MCP tool from an AI client |
| `voice` | `voice` | Transcribed from audio (browser or Whisper) |
| `import` | `import` | Imported or explicitly handed off from a non-chat capture flow |

---

## 10. Settings Modal

Accessible from the topbar `⚙` icon.

```
┌─ Settings ────────────────────────────────────────────────┐
│  Agent Backend                                            │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  ● Ollama (local)                                   │ │
│  │  ○ Foundry Local (Microsoft)                        │ │
│  │  ○ Azure AI Services                                │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Embed model:   [nomic-embed-text ▾]                     │
│  Chat model:    [llama3.2 ▾]                             │
│  Base URL:      [http://localhost:11434]                  │
│                                                           │
│  Vault Path:    /Users/lucas/vault  (read-only)           │
│                                                           │
│  MCP Access Key: [••••••••••a3f9]  [↺ Rotate]          │
│                                                           │
│  ─ Capture Workbench ─────────────────────────────────── │
│  Queue threshold                                          │
│  Show pending notes below: [────────●──────────────] 1.00│
│  (1.00 = show all pending   0.00 = hide badge)            │
│                                                           │
│  Auto-approve threshold                                   │
│  Approve at or above: [ 0 ]                               │
│  (0 = off   90 = auto-approve >= 90%)                     │
│                                                           │
│  Theme: [● Dark  ○ Light  ○ System]                      │
│                                                           │
│  ─ Scheduled Agents ──────────────────────────────────── │
│  Weekly summary                                           │
│  [✓] Enabled   Schedule: [0 17 * * 5         ]           │
│  Domains: [work] [personal]  [+ Add]                     │
│                                                           │
│  Scheduled re-index                                       │
│  [✓] Enabled   Schedule: [0 3 * * 0          ]           │
│                                                           │
│  ─ Chat History ──────────────────────────────────────── │
│  Sessions to retain: [ 10 ]                              │
│  (stored in browser localStorage only)                    │
│                                                           │
│  [Cancel]                                     [Save]     │
└───────────────────────────────────────────────────────────┘
```

Backend-specific fields show/hide dynamically based on selection. Azure fields require `AZURE_OPENAI_*` env vars set in `.env`.

On open, all fields are populated from `GET /api/settings`. Saving calls `PATCH /api/settings` — the server is the authoritative source. `localStorage` holds a cache for instant UI render only.

The **Queue threshold** slider controls which pending notes appear in the capture workbench. Range 0.00–1.00, step 0.05. Default `1.00` (all pending notes visible). Setting to `0.00` hides low-confidence pending-note alerts entirely.

The **Auto-approve threshold** input controls whether high-confidence ingests are approved immediately. Range 0–100. Default `0` disables auto-approval. Setting it to `90` means notes scoring 90% or higher are auto-approved and stamped with approval metadata (`approved_by: system:auto`, `approved_at`, `approval_mode: auto`).

The **Scheduled Agents** section controls agent automation:
- **Weekly summary**: enable/disable toggle + cron expression (displayed as a text input with humanised preview, e.g. "Every Friday at 17:00"). Domains multiselect filters the summary to specific vault domains; empty = all domains.
- **Scheduled re-index**: enable/disable toggle + cron expression. Runs a full incremental re-index to catch Obsidian edits made outside the API.

Cron changes take effect on the next APScheduler reschedule (no restart required). Invalid cron expressions show an inline error before save is allowed.

The **Chat History** input controls how many chat sessions are retained in browser `localStorage`. Reducing the limit trims oldest sessions immediately on save. Range 1–50, default 10.

Changes take effect immediately on save — the topbar badge count re-evaluates without a page reload.

The **MCP Access Key** field shows only the last 4 characters masked (`••••••••a3f9`). The full key is never displayed — it is only shown in the `.env` file. **Rotate** generates a new key server-side and displays the new hint.

---

## 11. Responsive Behavior

Phase 1 targets desktop browsers only (≥ 1024px width). 

| Viewport | Behavior |
|---|---|
| ≥ 1200px | Full layout: nav labels visible, two-panel doc browser |
| 768–1199px | Nav collapses to icon-only rail; doc browser becomes single panel |
| < 768px | Nav becomes hamburger menu; not a supported primary use case in Phase 1 |

---

## 12. Accessibility

- All interactive elements have visible focus rings (2px `--accent` outline)
- Color is never the sole state indicator — icons and text used alongside color
- ARIA labels on all icon-only buttons
- The capture-workbench button announces its badge count via `aria-label="{n} capture items need attention"`; when count is 0 the label reads `"No capture items need attention"`
- Tab order follows visual reading order; `Escape` closes modals and slide-over panels
- Graph view provides a table-format fallback accessible via keyboard navigation

---

## 13. Keyboard Shortcuts

All shortcuts use `Ctrl` on Windows/Linux and `Cmd` on macOS.

| Shortcut | Action | Context |
|---|---|---|
| `Ctrl+K` | Open semantic search | Global |
| `Ctrl+Shift+K` | Open keyword search | Global |
| `Ctrl+N` | New note (opens template picker) | Global |
| `Ctrl+/` | Command palette | Global |
| `Ctrl+\` | Toggle sidebar | Global |
| `Escape` | Close modal / slide-over | Global |
| `Ctrl+S` | Save note immediately | Document editor |
| `Enter` | Send chat message | Chat input |
| `Shift+Enter` | Insert newline | Chat input |
| `Ctrl+B` | Bold | Document editor |
| `Ctrl+I` | Italic | Document editor |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / Redo | Document editor |
| `Tab` | Indent / next focusable element | Editor / navigation |

The **command palette** (`Ctrl+/`) is a searchable list of all available actions (navigate to screen, run chat starter, open the capture workbench, trigger weekly summary, etc.). It is the primary discoverability surface for keyboard-first users.

---

## 14. Phase 2: Teams Bot UX

The Teams bot adapts the chat starter pattern to a bot conversation model:

- User types in a dedicated private Teams channel
- Bot replies in thread with structured confirmation (type, tags, people, action items detected)
- Slash commands: `/search <query>`, `/notes <person name>`, `/weekly`, `/stats`
- Bot uses the same `POST /ingest` and `GET /search` REST endpoints as the web UI

No web UI changes are required for Teams bot support.
