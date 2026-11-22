# D07 — Client APIs, commands and Obsidian interface
**Status:** Decided (2026-11-21)

## Decision
- Minimal **Monocle for Obsidian** custom chat panel, reusing mature libraries and selectively salvaged legacy components; no competing Markdown editor.
- Hybrid routing: deterministic commands run directly in Monocle; free-form/agentic requests run in Cravat; expose commands through chat, Obsidian palette and contextual actions.
- Hybrid context: active note/selection and conversation state when relevant; user includes/excludes additional context; Cravat retrieves further knowledge via Monocle tools.
- Conversations are **persistent locally**, may include multiple execution IDs and session-scoped change sets, but do not sync in MVP.
- Native plugin diff review using established editor/diff libraries; inline/side-by-side, next/previous, accept/reject, **Approve All Pending in the current agent execution session**.
- Operational index panel hidden behind compact at-a-glance health/status indicator.
- Shared knowledge API supports read-only vault lookup/search and eventual external MCP clients; externally exposed remote service is not an MVP requirement.

## Verification needed
Obsidian API compatibility, native CodeMirror diff libraries, legacy UI reuse, actual context and tool contracts.
