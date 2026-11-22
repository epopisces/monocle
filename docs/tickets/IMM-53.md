# IMM-53 — [M3] Persist session-scoped portable change proposals

**Source:** [Linear IMM-53](https://linear.app/immoil/issue/IMM-53/monocle-m3-persist-session-scoped-portable-change-proposals)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-52](IMM-52.md)  
**Blocks:** [IMM-54](IMM-54.md), [IMM-55](IMM-55.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can retain review-worthy curation proposals across restarts without applying them.

## Scope

Define versioned portable proposal schema: proposal/change-set IDs, execution ID, note IDs, base hashes, patch, risk, status. Store locally; expose change set listing per execution; no authoritative index ingestion.

## Acceptance criteria

Multiple changes linked to one execution; restart preserves pending proposals; changes from other sessions isolated; serialization round-trip test.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No cross-device synchronization or comprehensive agent trace storage.

## Architecture references

Monocle MVP specification (D01–D08), M3. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 08 Create schema-valid notes via existing Curator skill.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed: `npm ci && npm run check` 255/255 (8 new proposal-store tests and 1 NotePlan→proposal test in core, 1 change-set route test in companion); `npm run smoke:obsidian` 60/60 (fake CLI; no plugin changes)
- [x] Acceptance criteria validated (temp data dirs and fixture vault only)
- [x] Summary and artifacts committed or handed back for synchronization (branch `epopisces-imm-53-change-proposals`)

**Implementation notes:**

- **Session = one Cravat execution.** Per the spec ("Approve All Pending for the current agent *execution* session") a change set holds the proposals of exactly one `executionId`; `conversationId` is recorded alongside so a conversation can list its executions' sets. A second execution in the same conversation gets its own set, and operations on one set never touch another.
- **Portable schema** (`@monocle/contracts` `proposals.ts`): `{format: "monocle.change-set", version: 1, changeSet}`. `ChangeSet {id, executionId, conversationId?, createdAt, updatedAt, changes[]}`; `ChangeProposal {id, changeSetId, executionId, operation: create|modify|delete, path (vault-relative `.md`), noteId?, base, patch, risk: low|high, status, summary?, predecessorId?, createdAt, updatedAt}`. `base` is `{hash: null}` (note must not exist) or `{hash: "sha256:<hex of UTF-8 content>", content}` — the base text is kept so review can diff and a stale proposal can be rebased (IMM-57) after the note changed. `patch` is `{format: "replace", content}` (full proposed content) or `{format: "delete"}`. Statuses `pending | applied | rejected | conflicted | failed | superseded`; only `pending` can change.
- **Storage** (`@monocle/core` `ProposalStore`): `<dataDir>/proposals/<changeSetId>.json` beside conversations (`--data-dir` / `MONOCLE_DATA_DIR`), never in the vault and never ingested into the note index. Atomic temp-file + rename writes, serialized per set; files that fail `parseChangeSet` (bad JSON, unknown version, base hash not matching base content, mismatched IDs, unsafe path) are skipped with a log line. No `dataDir` → in memory only.
- **APIs.** Core: `ProposalStore.open/propose/setStatus/get/getChange/changeSetForExecution/list({executionId?, conversationId?})/flush/close`, `serializeChangeSet`/`parseChangeSet`, `contentHash`, `noteCreationProposal(plan, {executionId, conversationId?, risk?})`. Companion: `RunningCompanion.proposals` (in-process), `GET /v1/change-sets[?executionId=&conversationId=]` → `{changeSets: ChangeSetSummary[]}` (status counts, newest first), `GET /v1/change-sets/{id}` → `ChangeSet` or 404. No write routes yet; `CONTRACT_VERSION` unchanged (additive).
- **`/new-note` stays direct apply** (decision). D06 makes approval risk-based and lets low-risk authorized operations run without review; `/new-note` is user-initiated, opt-in (`--note-template`), and only ever adds a file with an exclusive create. `planNote`'s `NotePlan` maps onto a `create` proposal via `noteCreationProposal` (default risk `low`) for agent-initiated creates once an agent write path exists (IMM-54).
- **TDD note.** The first two store slices were strict red→green; persistence/parse validation landed with the restart slice, so the isolation, immutability, invalid-shape and round-trip tests passed on first run.
