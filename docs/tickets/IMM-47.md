# IMM-47 — [M1] Stream and cancel a Cravat execution through Copilot adapter

**Source:** [Linear IMM-47](https://linear.app/immoil/issue/IMM-47/monocle-m1-stream-and-cancel-a-cravat-execution-through-copilot-adapter)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-46](IMM-46.md)  
**Blocks:** [IMM-48](IMM-48.md), [IMM-49](IMM-49.md), [IMM-50](IMM-50.md)  

## User story

As an Obsidian user, I can submit a prompt and see a streamed answer with execution identity and cancellation.

## Scope

Define versioned Monocle→Cravat execution request/event contract; keep Cravat separate module inside companion; implement one supported installed Copilot CLI/SDK adapter; stream outputs and terminal states; enforce requested cancellation and error reporting.

## Acceptance criteria

Prompt round-trip streams tokens/events to panel; execution ID and provider errors shown; cancellation stops work and completes terminally; provider adapter tests include failed launch.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No second provider, long-term trace store or write tools.

## Architecture references

Monocle MVP specification (D01–D08), M1. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 02 Connect Obsidian panel to independent companion.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed (record command and outcome)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization

**Commands and outcomes:**

- `npm ci && npm run check` (lint/typecheck/build/test): 87/87 tests passed pre-merge, 119/119 after merging `origin/refactor` (IMM-59/60).
  IMM-47 adds 29 tests: Cravat `ExecutionManager` (8), `CopilotCliAdapter` against a fake CLI incl. failed launch,
  provider error and kill-on-cancel (6), companion execution routes incl. Origin/CORS/415/413/404 (8),
  plugin `ExecutionClient` ↔ real companion integration incl. cancel and connection loss (7). No live credentials needed.
- `npm run smoke:obsidian` (real Obsidian 1.8.9, fake Copilot CLI): 14/14 — prompt streams into panel, execution ID
  shown, cancel ends `cancelled` and the provider process is killed.
- `MONOCLE_SMOKE_LIVE=1 npm run smoke:obsidian` (installed Copilot CLI 1.0.104, signed in): 11/11 — live answer streamed.
- Manual live checks: cancel mid-stream → `202`, stream `started, delta…, cancelled`, no lingering `copilot` processes;
  `MONOCLE_COPILOT_PATH=copilot-not-installed` → `failed launch_failed: spawn copilot-not-installed ENOENT` in panel.

**Implementation notes:**

- Contract `0.2.0` (`packages/contracts/src/execution.ts`): `POST /v1/executions` → NDJSON events `started`/`delta`/
  exactly one of `completed`/`failed`/`cancelled`; `POST /v1/executions/{id}/cancel`. Request parser rejects unknown fields.
- Transport: renderer `fetch` streaming NDJSON with CORS (`requestUrl` buffers whole responses). Companion rejects
  browser Origins other than `app://obsidian.md` and requires JSON content type (forces preflight). No auth token yet.
- Cravat `ExecutionManager` owns IDs, ordering, single terminal event, cancel (abort + forced terminal after grace) and
  shutdown; `CopilotCliAdapter` spawns `copilot --output-format json --stream on --available-tools none
  --disable-builtin-mcps`, prompt via stdin, empty temp cwd, kills the process tree on cancel.
- Panel: prompt box, Send/Cancel, execution ID/state, error `code: message`, streamed text rendered as Markdown on
  completion; closing the panel cancels. Follow-up notes for IMM-48/49/50 are in the shared implementer notes
  (`IMM-47-cravat-execution.md`).