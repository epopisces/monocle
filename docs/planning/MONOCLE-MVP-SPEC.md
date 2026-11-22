# Monocle KMS — MVP Product and Engineering Specification

**Status:** Draft for implementation handoff; synthesized from Wayfinder decisions D01–D08  
**Date:** 2026-11-21  
**Next workflow:** `/to-tickets` after reviewing testing seam and checking existing repositories/vault  
**Sources:** Conversation decisions through D08.4 and the local Wayfinder map. The Wayfinder map and tickets have been reconciled with the D01–D08 decisions recorded in conversation.

## Problem Statement

The author has an established Obsidian knowledge vault and existing Obsidian Curator agent plus `create-obsidian-note` skill. Today, creating and curating notes often requires switching from Obsidian to VS Code/GitHub Copilot, duplicating context and interrupting knowledge work. The legacy Monocle web application attempts to recreate both Obsidian editing and Copilot chat and does neither as effectively as the existing tools. The desired system must make agent-assisted knowledge operations accessible within Obsidian, preserve Markdown as authoritative knowledge, keep human review limited and efficient, and support independent installations on multiple synchronized-vault clients. The same architecture should be reusable across personal/homelab and work environments with different allowed providers.

## Solution

Implement **Monocle**, the overall KMS, with **Monocle for Obsidian** as its first interface and an independently launchable **local companion process**. Within the companion, **Monocle knowledge services** own read/search/index/validation/change operations; **Cravat**, a logically independent module, owns agent execution and runtime/provider adapters. Top Hat remains a separate, future orchestration layer.

Each client has a locally synchronized Markdown vault, a local SQLite/FTS5 derived index, and optionally a ChromaDB derived semantic index. Existing Obsidian sync handles file replication; Monocle never implements vault sync or requires a central service. A compact plugin chat supports commands, natural-language requests, editor context, execution settings, persistent local conversations, and diff-based review. Agent-mediated managed mutations use progressive validation, risk-based approval, guarded writes and proposal rebasing. The MVP demonstrates a full note-creation/curation loop plus automatic indexing; advanced search UI and broad integrations are deferred.

## User Stories

### Core user experience
1. As an Obsidian user, I want to open Monocle within Obsidian so that I do not switch to VS Code for knowledge tasks.
2. As an Obsidian user, I want streamed agent responses so that I can follow active work.
3. As an Obsidian user, I want to select an available agent and model so that I can choose the execution capability appropriate to a task.
4. As an Obsidian user, I want to see and set context-window and thinking-effort options so that I can control execution within a provider's supported limits.
5. As an Obsidian user, I want unsupported execution settings clearly reported so that I do not assume they were applied.
6. As an Obsidian user, I want to cancel a running execution so that unwanted work stops.
7. As an Obsidian user, I want clear progress and failure reporting so that I can diagnose invocation problems.
8. As an Obsidian user, I want conversations preserved locally across restarts so that I can resume multi-step work.
9. As an Obsidian user, I want a conversation to contain multiple executions so that iterations retain their relevant context.
10. As an Obsidian user, I want to see which execution produced which proposed changes so that review is intelligible.

### Commands, context, and existing assets
11. As an Obsidian user, I want deterministic operations exposed as commands so that routine actions do not require an agent.
12. As an Obsidian user, I want agentic commands and free-form requests routed through Cravat so that reasoning is available when needed.
13. As an Obsidian user, I want commands accessible from chat, the Obsidian command palette, and relevant context menus so that I can use the most convenient entry point.
14. As an Obsidian user, I want the active note and selection available as context so that I do not manually copy source text.
15. As an Obsidian user, I want to add or exclude notes and context so that I can control the scope and disclosure of a request.
16. As an Obsidian user, I want Cravat agents to retrieve additional knowledge through Monocle tools so that only relevant context needs to be supplied initially.
17. As a curator, I want to reuse the existing Obsidian Curator agent and `create-obsidian-note` skill so that mature instructions and scripts are not rewritten unnecessarily.
18. As a curator, I want notes created by Obsidian and agent-driven tools to comply with the same note conventions so that entry point does not change document quality.
19. As a user, I want to look up people, decisions, or projects through natural language so that Monocle can synthesize existing knowledge with references.

### Safe mutations and review
20. As a user, I want routine low-risk approved operations to complete without review so that maintaining the vault does not become another inbox.
21. As a user, I want risky, ambiguous, sensitive, and high-impact changes flagged for approval so that important knowledge is protected.
22. As a user, I want inline and side-by-side diffs in Obsidian's document area so that I can evaluate a proposed edit in context.
23. As a user, I want Previous/Next change controls so that I can review a session efficiently.
24. As a user, I want to accept or reject an individual change so that decisions can be granular.
25. As a user, I want **Approve All Pending** for the current agent execution session so that I can quickly apply eligible changes without affecting other sessions.
26. As a user, I want the bulk action to report applied, skipped, conflicted, and failed changes so that partial success is transparent.
27. As a user, I want pending changes to survive restarts locally so that review can be deferred.
28. As a user, I want stale proposals rebased against current content and raised as *new* proposals so that no changed proposal is silently approved.
29. As a user, I want legacy schema violations to be tolerated when unrelated so that gradual vault migration does not block useful edits.
30. As a user, I want new notes and newly introduced violations rejected when they fail applicable rules so that the vault converges toward consistency.
31. As a user, I want every managed note to maintain a stable frontmatter ID so that moves and renames do not break identity.
32. As a user, I want duplicate note IDs and unsafe overwrites blocked so that identity and content integrity are preserved.
33. As a user, I want minimal mutation metadata linking changes to sessions and content hashes so that history can be inspected without building a full audit subsystem.

### Search, indexing, deployment
34. As a user, I want exact/full-text retrieval so that identifiers, names, and technical terms can be found precisely.
35. As a user, I want metadata and explicit relationship queries so that I can traverse links among notes, people, projects and decisions.
36. As a user, I want optionally enabled semantic retrieval so that conceptual matches can be found when my installation supports embeddings.
37. As a user, I want query results to identify sources at document or passage level so that answers can be checked.
38. As a user, I want newly created, changed, moved and deleted notes automatically reconciled into the local index so that retrieval remains useful after syncing.
39. As a user, I want fast foundational indexing while embedding jobs run separately so that normal editing is responsive.
40. As a user, I want a compact index health indicator that expands into operational controls so that diagnostics do not dominate the UI.
41. As a user, I want to inspect indexing errors and selectively reindex or reconcile so that failures can be repaired without rebuilding everything.
42. As an operator, I want to rebuild all derived indexes from synchronized Markdown so that indexes need not sync between machines.
43. As an operator, I want companion and plugin setup documented for a second machine so that multiple independent client installs are reproducible.
44. As an operator, I want the companion to run with Obsidian closed so that local indexing and agent/MCP operations are not UI-dependent.
45. As an operator, I want portable non-secret KMS settings optionally housed in the synced vault so that common settings follow my vault.
46. As an operator, I want local paths, installed providers and secrets to remain host-local so that work and homelab configurations do not leak across machines.
47. As an agent-tool user, I want Monocle's read/search interfaces accessible without using the Obsidian UI so that future MCP clients can consume the same knowledge services.
48. As an engineer, I want Cravat's provider adapter independent of Monocle so that different permitted agent runtimes can be swapped in later.

## Implementation Decisions

### Product and capability boundaries
- Monocle means the **entire KMS**, not the retired standalone web app. Obsidian is the primary initial editor and human UI; Monocle for Obsidian adds KMS-specific capabilities.
- Top Hat is the separate productivity and workflow orchestration platform, not part of the MVP.
- Cravat is the agent-execution capability. Monocle interfaces *surface* model, context-window and thinking-effort controls and pass settings to Cravat; Cravat *validates and executes* them. Model capability differences must be surfaced honestly.
- New implementation in a monorepo with independent module boundaries; salvage legacy Monocle UI, trace display, and adapter code only after inspection. Do not rebuild its Markdown editor, file browser, or a full Copilot interface.
- TypeScript/Node.js for plugin, companion and core packages; Python is permitted within skills or as a future specialized dependency where necessary.
- MVP installation is developer-oriented: package manager/Node.js, separately installed plugin and companion, documented reproducible setup.

### Deployment, authority and configuration
- Local-first, deployable on multiple machines. A single local companion **process** hosts Monocle and Cravat as independent modules, and can run with Obsidian closed. Process separation later must not change the logical contract.
- Existing Obsidian synchronization replicates the *authoritative Markdown vault* across clients. Monocle does not implement synchronization; each client has its own derived index.
- Non-secret portable configuration may be stored within synchronized vault files. Host-specific paths, bindings, provider availability and secrets remain in local configuration/credential storage.
- The MVP does not require an externally reachable centralized service; bind local interfaces securely, with remote exposure deferred pending security design.

### Agent execution and knowledge interfaces
- Known deterministic commands should bypass Cravat; free-form requests and agentic skills invoke Cravat. Commands are registered once and exposed through chat, palette and contextual UI.
- The first walking skeleton is **read-only**: Obsidian plugin → companion → Cravat adapter → installed Copilot agent/runtime → streamed response. It includes active-note context and read-only vault tools, cancellation, execution identifiers, error handling, and no vault writes.
- Existing Obsidian Curator and `create-obsidian-note` behavior are integration inputs, not assumptions about implementation. Skills may invoke Python scripts; avoid duplicating deterministic behavior where one shared operation is possible.
- Both execution modes are architectural goals: Monocle may invoke Cravat; independent external agents may use Monocle's deterministic tools via an MCP/API surface without necessarily invoking Cravat.
- Conversations persist locally, can contain multiple Cravat executions, and reference session-specific change sets. Cross-client conversation and proposal sync are deferred.
- Provide context intentionally: immediate editor/session context, explicit include/exclude controls, and on-demand Monocle retrieval. Context exclusions must be applied before provider execution.

### Knowledge index
- Markdown/frontmatter is authoritative; indexes are derived and rebuildable per installation.
- Every note is assigned a stable unique frontmatter ID; titles and paths are mutable. Exact field name/format and legacy migration procedures require vault inspection before coding.
- Index explicit relationships from frontmatter and Obsidian links. Inferred relationships remain proposals until accepted, not authoritative graph edges.
- SQLite/FTS5 supplies full-text, metadata, identity, relationship and index-state operations; ChromaDB is the first optional semantic/vector backend. A shared retrieval results interface handles filtering, fusion, ranking and source references.
- Configurable embedding providers with **local default**, independent of Cravat. Individual installations may enable permitted remote providers. Semantic retrieval absence must not break lexical/metadata/relationship queries.
- Tiered automatic indexing: debounced foundational updates, separately queued semantic updates with configurable resource limits, startup reconciliation and rebuild operations; show freshness/degraded state when relevant.

### Mutations, review and history
- Policy-based hybrid write authority: managed writes preferred/required for designated operations, trusted deterministic scripts or explicitly authorized agents may write directly under defined policies. Filesystem access restrictions are necessary where a hard enforcement guarantee is claimed.
- Risk-based human approval. Low-risk authorized changes may apply automatically; risky, ambiguous, sensitive or high-impact changes require review.
- Native Obsidian diff review implemented minimally using established editor/diff libraries (not a required third-party community plugin). Supports inline/side-by-side, next/previous, individual accept/reject, and **Approve All Pending for the current execution session**.
- Pending proposals live locally for MVP in a versioned portable format. Cravat owns execution sessions; Monocle owns proposals and guarded mutations. Proposal state must survive restarts.
- Progressive validation: strict integrity and new-note schema; unrelated pre-existing legacy violations grandfathered; new violations rejected. Use a representative real vault to settle exact schema rules.
- On a stale proposal, **rebase against current content and raise a new proposal** linked to its predecessor. Do not treat an approval of the old proposal as approval of the new one. Failed/ambiguous rebases require review.
- Minimal mutation history only (time, operation, note ID, session, before/after hash, disposition, optional commit reference). Rely primarily on Git or existing history for rollback; the actual version-history mechanism is to be confirmed, as sync is not itself versioning.

### Interface and MVP acceptance scope
- Minimal custom Monocle chat panel built from established libraries and suitable salvageable legacy components.
- Compact, legible index-status indicator, expandable to freshness, queue depth, errors, reindex and reconciliation controls.
- MVP must demonstrate agent interaction, context, note creation and curation, managed mutation/review, safe rebasing, automatic foundational indexing, optional semantic indexing when enabled, index controls, local persistence and second-machine deployability.
- Functional read/search APIs are required. Advanced search presentation, graph exploration and full Top Hat integration are not.

### Open implementation details / inspect-before-commit constraints
- Existing vault frontmatter schemas, ID field conventions, templates, link resolution rules, excluded folders and sensitivity classifications are **uninspected**.
- Existing agent/skill entry points, legacy Monocle UI extraction feasibility, Copilot adapter/SDK version compatibility and existing tests are **uninspected**.
- Exact API transport, authentication, MCP server MVP exposure, embedding model, vector schema, chunking strategy, ranking weights, dependency versions, host support matrix, and Git/backup recovery mechanism remain technical design details to validate. They are not silently decided by this spec.
- Clarify what a session-scoped bulk action means when one conversation contains multiple executions: the accepted rule is **the current agent execution session**, not every conversation or vault proposal.

## Testing Decisions

### Preferred seams
- **Primary high-level seam:** exercise the Obsidian plugin through the companion to Cravat and Monocle tools using a small synthetic vault and controlled agent adapter. Assert observed outcomes (context passed, streamed answer, proposals, applied files and index freshness) rather than internal call ordering.
- **Additional integrity seam where unavoidable:** exercise Monocle guarded mutation API directly with real temporary Markdown files to verify stale proposals, rebases, validation and approval behavior. This seam is justified because direct agent writes and filesystem sync bypass UI.
- Reuse existing integration/test harnesses if discovered during repository inspection. Do not fabricate prior art from unseen code.

### Required behavior-level tests
- Plugin connects to running companion; companion can run without Obsidian; clear disconnected/error states.
- Streamed agent output, model-option validation, cancellation, session IDs and failure handling.
- Active note and selection supplied when relevant; explicitly excluded notes never reach adapter calls.
- Read-only skeleton agent cannot mutate test vault; tool permissions enforce this, not just prompt instructions.
- Deterministic commands work without invoking agent; agentic commands invoke Cravat.
- Conversation reopening restores messages, execution associations and pending proposals.
- Existing Curator and note-creation skill produce notes conforming to inspected templates and persistent-ID invariants.
- Individual diff accept/reject and current-execution **Approve All Pending** cannot affect other executions' proposals.
- Auto-approval applies allowed low-risk changes and holds high-risk changes; conflicts and validation failures are surfaced.
- Stale proposal rebase creates a **new pending proposal** with predecessor link, leaving old approval insufficient.
- Progressive validation allows unrelated legacy defects but blocks new defects and duplicate IDs.
- SQLite full-text, metadata and explicit-link queries return stable note identities and citations.
- Optional Chroma indexing can be disabled without baseline retrieval failing.
- Tiered indexing reconciles create/update/delete/move, sync-originated changes and missed watch events; reports stale data.
- Restart rebuilds/reconciles derived state; no index is required to be synchronized.
- Install on a second supported host/test environment against an independently synced or copied test vault and rebuild indexes.

## Out of Scope

- New bespoke Markdown editor or general-purpose vault navigator.
- Full GitHub Copilot interface recreation; rich agent IDE features beyond the core loop.
- Full Top Hat application or Microsoft 365 Copilot/Graph ingestion.
- Cross-client synchronization of chat, execution traces, or pending change sets in MVP.
- A central always-on hosted Monocle service, multi-tenant platform, or distributed index management.
- Building a generalized multi-agent orchestration system; Cravat starts with one proved provider adapter.
- Automatically storing machine-inferred relationships as authoritative facts.
- Detailed enterprise audit/provenance subsystem, comprehensive trace archive, or a new VCS.
- Advanced graph explorer, embedding inspector, and polished advanced search UI.
- Bulk migration/rewrite of the production vault as a prerequisite without inspection and explicit migration plan.

## Further Notes

### Ordered implementation increments
1. **Discovery/bootstrap:** inspect repositories, Curator, skill, legacy Monocle, vault (when available), and prior test seams; establish monorepo and contracts.
2. **Read-only walking skeleton:** agent invocation from Obsidian through companion/Cravat, vault context, streaming, errors and cancellation.
3. **Note creation and curation:** existing skills, deterministic utilities, ID/schema validation, proposal format.
4. **Review and guarded writes:** local persistence, approval policies, editor diff navigation, session-wide approve, rebase into new proposals.
5. **Indexing and retrieval:** SQLite/FTS5, explicit relationships, optional Chroma/embeddings, reconciliation and status UI.
6. **MVP acceptance:** end-to-end tests on representative test vault and reproducible installation on another host.

### Publication and setup
The official `to-spec` flow calls for publishing this specification in the project issue tracker with the `ready-for-agent` label. The tracker and triage-label configuration have not been established in this project session. This file is a **local specification artifact**, not a published issue. Configure the tracker through `/setup-matt-pocock-skills`, then publish the spec and proceed to `/to-tickets`.

### Testing seam review
The preferred high-level test boundary is the **plugin → companion → Cravat/Monocle → observable result** path, with a narrow mutation-focused test boundary for guarded writes. Confirm or adjust these seams before producing detailed implementation tickets.
