# D07.7 / D08.4 — MVP and walking skeleton acceptance
**Status:** Decided (2026-11-21)

## First walking skeleton (read-only)
- Launch companion without Obsidian; plugin sends active-note context to companion.
- Cravat invokes installed agent through adapter, streams response and execution status; cancellation and failure reporting work.
- Agent reads extra vault data through read-only Monocle tools; verify no vault mutation.

## MVP (core end-to-end, advanced UI deferred)
- Minimal chat, model/context-window/thinking controls, contextual and deterministic commands.
- Reuse Obsidian Curator and create-obsidian-note skill, generate valid frontmatter/IDs and update notes.
- Risk-based managed writes, progressive validation, local persistent change sets, native inline/side-by-side diff navigation, session-scoped bulk approval.
- Stale proposals rebase into new unapproved proposals; mutation outcomes are reported.
- SQLite/FTS5 indexing of notes/metadata/relationships with automatic reconciliation; optional tiered Chroma semantic indexing.
- Compact index health/status with expanded operational controls; functional search API, advanced search UI deferred.
- Conversations and proposals survive local restarts; developer installation reproducible on second host.

## Non-goals
M365 and Top Hat end-to-end, central hosting, cross-device conversation/proposal sync, advanced search UI, full graph explorer, comprehensive trace/audit stack.
