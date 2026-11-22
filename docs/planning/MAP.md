# Wayfinder Map — Monocle KMS MVP

**Status:** Architectural Wayfinder decisions D01–D08 resolved; `/to-spec` draft created 2026-11-21. Next: verify existing assets, review specification, then `/to-tickets`.

## Destination
Deliver the initial usable **Monocle** knowledge-management capability: Obsidian as the primary editor/interface, **Monocle for Obsidian** for agentic operations, locally deployed knowledge services and **Cravat** execution, authoritative synced Markdown, derived retrieval indexes, and an end-to-end create/curate/review/index workflow without switching to VS Code.

## Source of truth and constraints
- **Architecture decisions:** D01–D08 recorded during the 2026-11-20/21 Wayfinder discussion; this map has been reconciled with those later decisions.
- **Specification:** `../monocle-spec/MONOCLE-MVP-SPEC.md` (in the companion deliverable; not yet published to an issue tracker).
- **No vault or existing code inspection in this session.** Schema names, current script behavior, compatibility, existing diff components, and legacy application salvage must be verified before implementation.
- This map records **decisions**, not implementation tasks. Do not treat a technology selection as evidence that its integration works.

## Decision register
| Decision | Status | Resolution | Detail |
|---|---|---|---|
| D01 Deployment | Decided | Local-first, deployable across multiple hosts; no centralized service required | [01](tickets/01-execution-boundaries.md) |
| D02 Vault synchronization | Decided | Existing Obsidian sync external to Monocle; each client has its own authoritative vault copy and local derived indexes | [01](tickets/01-execution-boundaries.md) |
| D03 Runtime | Decided | Companion runs without Obsidian; portable non-secret settings may sync in vault, local settings/secrets do not | [01](tickets/01-execution-boundaries.md) |
| D04 Agent execution | Decided | Shared companion process, distinct Cravat module; Cravat invokes provider adapters; Monocle UI surfaces execution parameters | [02](tickets/02-agent-invocation.md) |
| D05 Retrieval/index | Decided | Persistent frontmatter note IDs; explicit relationships; SQLite/FTS5; optional ChromaDB and embedding adapter (local default); tiered indexing | [04](tickets/04-retrieval.md) |
| D06 Mutation/governance | Decided | Policy-based hybrid writes, risk-based approval, local portable proposals, progressive validation, minimal history, rebase into new proposal | [03](tickets/03-vault-access.md), [06](tickets/06-approval.md) |
| D07 Obsidian UX/MVP | Decided | Minimal native chat; hybrid commands/context; persistent local conversations; native diff review; compact index status; core workflow MVP | [05](tickets/05-clients.md), [07](tickets/07-acceptance.md) |
| D08 Implementation | Decided | New monorepo/selective salvage; TypeScript-first with Python skill dependencies; developer installs; read-only active-note walking skeleton | [08](tickets/08-implementation.md) |

## MVP success definition
1. Plugin + companion + Cravat + initial installed agent execute a **read-only** active-note request, stream progress, and support cancel/error handling.
2. Existing Curator and `create-obsidian-note` are integrated with conventions verified from an accessible test vault.
3. Managed changes use progressive validation, version guards, and session-associated diffs; user can navigate and individually accept/reject changes or **Approve All Pending in the current execution session**.
4. Stale changes are rebased to current note content and raised as **new** proposals, not implicitly approved.
5. Vault changes automatically update SQLite/FTS5; optional ChromaDB indexing is queued and independently configurable; plugin shows compact status with an expanded operations panel.
6. Conversations/proposals persist locally across restarts. Setup is reproducible on a second supported host; vault synchronization itself remains out of scope.
7. Search/retrieval APIs function; advanced search UI is deferred.

## Implementation milestones (not tickets)
- **M0 — Asset inspection & bootstrap:** inspect Curator/skill, old Monocle, vault and templates when available; initialize monorepo, tests, contracts.
- **M1 — Read-only walking skeleton:** Obsidian → companion → Cravat → Copilot adapter → streamed answer with active-note and read-only vault context.
- **M2 — Knowledge operations:** shared note-generation behavior, persistent IDs, validation, managed mutation API.
- **M3 — Governance/review:** local change sets, risk policy, native diff navigation, session-wide approval, rebase-as-new-proposal.
- **M4 — Indexing:** SQLite/FTS5, explicit relationship index, optional ChromaDB, tiered reconciliation and UI health indicator.
- **M5 — MVP validation:** representative vault, restart, conflict, offline/second-host deployability, end-to-end acceptance.

## Follow-on work deferred beyond MVP
- M365 ingestion and Top Hat integration; external remote service exposure; cross-device conversation/proposal sync; inferred relationship auto-promotion; advanced graph/search UI; broad provider support; comprehensive auditing; bespoke Markdown editor.

## Outstanding implementation research (not unresolved product decisions)
- Actual vault schema, note type conventions, ID migration, link parsing, and existing Obsidian sync behavior.
- Existing Curator/skill APIs, Copilot adapter SDK/CLI behavior, tool restrictions, streaming and cancellation.
- Best reusable legacy Monocle components, diff editor integration, TypeScript Chroma embedded/client support on target hosts.
- Git/versioning availability and backup/rollback behavior, operating system support, user/provider authentication details.

## Transition
`/to-spec` has produced `MONOCLE-MVP-SPEC.md`; inspect source assets and testing seams, publish to the chosen tracker when configured, and then use `/to-tickets` for vertically sliced implementation tasks. The draft spec and this map are aligned on D01–D08.
