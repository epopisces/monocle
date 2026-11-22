# D04 — Agent invocation and execution contract
**Status:** Decided (2026-11-20/21)

## Decision
- Monocle and Cravat are **independent logical modules in one initial companion process**; extraction of Cravat into a separate service is possible later.
- **Cravat owns** agent execution sessions, provider adapters, streaming, cancellation, tool invocation and execution diagnostics.
- **Monocle UIs own presentation** of agent/model selection, context window and thinking effort; they pass settings as execution arguments; Cravat validates provider capabilities.
- Start with installed GitHub Copilot runtime/CLI or SDK behind an adapter. Additional providers are optional, enabling personal vs work deployment differences.
- Independent external agents may consume Monocle's deterministic tools via API/MCP without passing through Cravat.
- Existing **Obsidian Curator** and `create-obsidian-note` are reuse targets; Python script dependencies are allowed within skills, while application core is TypeScript.

## Verification needed
Inspect actual agent/skill code and provider APIs for read-only restrictions, streaming, session continuation, cancellation, skills and tool permissions.
