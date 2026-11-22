# IMM-50 — [M2] Persist and resume local Monocle conversations

**Source:** [Linear IMM-50](https://linear.app/immoil/issue/IMM-50/monocle-m2-persist-and-resume-local-monocle-conversations)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-47](IMM-47.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can reopen a conversation after restarting Obsidian or companion.

## Scope

Store conversation IDs, messages, execution IDs and contextual references locally; allow multiple executions per conversation; distinguish UI resume from provider-session resume.

## Acceptance criteria

Restart preserves history; new execution attaches to same conversation; unavailable provider state is represented truthfully; no vault sync of conversations.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No cross-device conversation sync or indefinite raw tool trace retention.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 03 Stream and cancel a Cravat execution through Copilot adapter.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed: `npm ci && npm run check` (161/161 after merging origin/refactor with IMM-49/61); `npm run smoke:obsidian` passes with the fake CLI, and `MONOCLE_SMOKE_LIVE=1` passed 31/31 against Copilot CLI 1.0.104
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization (branch `epopisces-imm-50-conversation-persistence`)

**Implementation notes:**

- **Storage (no vault sync):** the companion owns conversations (`ConversationStore` in `@monocle/core`). They are stored as one JSON file per conversation (`{format:"monocle.conversation", version:1, conversation}`) in `<dataDir>/conversations/`. `dataDir` comes from `--data-dir`, then `MONOCLE_DATA_DIR`, then the machine-local default: `%LOCALAPPDATA%\Monocle`, `~/Library/Application Support/Monocle`, or `$XDG_STATE_HOME/monocle`. `startCompanion()` without `dataDir` keeps conversations in memory only. The plugin stores only the open conversation ID, in Obsidian localStorage (`monocle:conversation-id`), never in `data.json`.
- **Contract (additive, still 0.2.0):**
  - optional `ExecutionRequest.conversationId` (a companion-issued UUID; omitting it starts a new conversation)
  - optional `started.conversationId`
  - optional `providerSession {id?, continuity: new|resumed|unavailable, reason?}` on terminal events
  - `GET /v1/conversations` (summaries, most recent first) and `GET /v1/conversations/{id}`
  - an unknown conversation returns 404 `invalid_request`; a second concurrent execution in the same conversation returns 409
- **Multiple executions per conversation:** each execution records its executionId, provider, companion instanceId, prompt, final or partial response, status, error, `providerSession` and `contextReferences` (always `[]` until IMM-48 fills them). An execution that was `running` under an earlier companion instance loads as `interrupted` with `connection_lost`.
- **UI resume vs provider resume:** UI resume replays the history from the store. Provider resume continues the Copilot session: the Copilot CLI adapter starts each session with `--session-id=<uuid>` and continues it with `--resume=<uuid>`. If the CLI no longer has that session ("No session, task, or name matched"), the adapter starts a fresh one and reports `unavailable` with the reason. The companion also reports `unavailable` when the provider changed or no earlier session was recorded. The panel shows the result ("Continued provider session" / "Earlier context unavailable to the provider: …") per execution.
- **Panel:** conversation picker and a "New conversation" button, a transcript of earlier executions (markdown answers, status, provider and session meta), and the live area for the current execution.
- **Tests:**
  - `packages/companion/test/conversations.test.ts`: 10 tests (attach, restart, interrupted, 404/409, memory-only, provider sessions)
  - `packages/companion/test/data-dir.test.ts`
  - adapter session tests in `packages/cravat/test/copilot-cli-adapter.test.ts`
  - `test/plugin-companion-conversations.integration.test.ts`
  - smoke checks: follow-up in the same conversation, provider session continued (live: the model recalls the earlier turn), transcript, history after companion restart and after Obsidian restart

