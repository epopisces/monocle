# IMM-48 — [M1] Supply active-note context and restricted read-only vault tools

**Source:** [Linear IMM-48](https://linear.app/immoil/issue/IMM-48/monocle-m1-supply-active-note-context-and-restricted-read-only-vault-tools)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-47](IMM-47.md)  
**Blocks:** [IMM-51](IMM-51.md), [IMM-52](IMM-52.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can ask the agent about the active note and let it read additional relevant vault notes without modifying them.

## Scope

Pass active note/selection and explicit context inclusions/exclusions; add read-only note/list/search-lite tools via Monocle contract; test containment on test vault and forbid write-capable filesystem tools in this execution mode.

## Acceptance criteria

Summarize active note succeeds; agent reads another allowed note; excluded context not transmitted; path traversal and write attempts fail; test vault hashes unchanged.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No note mutation or full index needed.

## Architecture references

Monocle MVP specification (D01–D08), M1. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 03 Stream and cancel a Cravat execution through Copilot adapter.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed: `npm ci && npm run check`: 176/176 after merging IMM-49/61 and 196/196 after merging IMM-50
- [x] Acceptance criteria validated
  - `npm run smoke:obsidian`: 21/21 before the merges, 32/32 after IMM-49/61 and 40/40 after IMM-50 (fake CLI). The fake CLI calls the tools through the real MCP server.
  - `MONOCLE_SMOKE_LIVE=1 npm run smoke:obsidian`: 15/15, 26/26 and then 35/35. The real Copilot CLI 1.0.104 summarised the active note and read another note through `monocle_vault-read_note`. The fixture vault's hashes were unchanged after the run (`.obsidian` excluded).
- [x] Summary and artifacts committed or handed back for synchronization (branch `epopisces-imm-48-active-note-context-tools`)

**Implementation notes:**

- **Contract (additive, still 0.2.x):** optional `ExecutionRequest.context = {activeNote?: {path, content?, selection?}, include?, exclude?}`.
  - Limits: `MAX_CONTEXT_LENGTH` (200,000 chars) and `MAX_CONTEXT_PATHS` (100).
  - Unknown fields are rejected.
- **Companion:**
  - `prepareExecution` puts the active note, the selection and the included notes ahead of the user prompt as fenced reference sections.
  - Exclusions always win: the companion's `--exclude` list is combined with the request's own exclusions.
  - If only the active note's path is sent, the note is read from the vault.
  - Include paths that escape the vault, or includes sent without a configured vault, fail with `invalid_request`.
  - Conversation records get `contextReferences` (kind/path/label only, never content).
- **Read-only tools:**
  - The tools are `read_note`, `list_notes` and `search_notes` in a `monocle_vault` MCP stdio server (`@monocle/core` `vault-tools/`).
  - They only read `.md` files.
  - The server checks the canonical realpath, so `..` segments, absolute paths and symlinks pointing outside the vault fail.
  - Excluded notes cannot be read.
  - There are no write tools.
- **Cravat:**
  - `start(req, {tools})` passes the toolset to the adapter as `ProviderRunOptions.tools`.
  - The Copilot adapter writes `--additional-mcp-config` and lists each allowed tool in its own `--available-tools` flag.
  - It also passes `--allow-tool monocle_vault`, `--deny-tool write` and `--deny-tool shell`, and never `--allow-all-tools`.
  - Without a toolset the adapter still passes `--available-tools none`.
- **Plugin:** a collapsible "Context" section in the panel offers the Active note and Selection checkboxes plus include/exclude path lists. Excluded items are dropped before anything is sent.
