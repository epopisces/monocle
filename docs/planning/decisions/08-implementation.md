# D08 — Repository, stack, packaging and first milestone
**Status:** Decided (2026-11-21)

## Decision
- **New monorepo** with selective salvage from archived legacy Monocle app (UI, traces, model abstractions if useful); avoid reproducing Obsidian Markdown editing or general Copilot chat.
- **TypeScript / Node.js** throughout plugin, companion, Cravat and Monocle packages until Python is justified; installed skills may have Python scripts.
- **Developer-oriented installation** with Node/package-manager tooling, separately installing plugin and companion, documented reproduction on another host.
- Walking skeleton: **execution with active-note context and read-only Monocle vault access**, before mutation work.

## Implementation increments
M0 inspect assets/bootstrap → M1 read-only skeleton → M2 knowledge operations → M3 managed writes/review → M4 retrieval/indexing → M5 MVP verification. This is sequencing guidance, not tickets.

## Still requires inspection
Legacy source, skills/scripts, vault, platform/installation constraints, CI/test conventions. Do not assume specific package layout, schema or adapter compatibility before that inspection.
