# IMM-49 — [M2] Configure model, context window and thinking effort in Monocle

**Source:** [Linear IMM-49](https://linear.app/immoil/issue/IMM-49/monocle-m2-configure-model-context-window-and-thinking-effort-in-monocle)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-47](IMM-47.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As a user, I can select execution options in Monocle while Cravat validates and applies provider-supported settings.

## Scope

Expose model, context budget and effort in panel; query adapter capabilities; pass parameters through execution contract; report unsupported settings rather than silently ignoring.

## Acceptance criteria

Supported settings appear in adapter request; invalid settings return actionable errors; switching models does not change Monocle knowledge services.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No custom model gateway or assumption of provider feature parity.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 03 Stream and cancel a Cravat execution through Copilot adapter.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed (record command and outcome)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization

**Commands and outcomes:**

- `npm ci && npm run check`: 129/129 tests passed (10 new: companion settings pass-through/rejection/capabilities route (4),
  `CopilotCliAdapter` flag mapping + capability discovery from a fake CLI's help (4), plugin `ExecutionClient` ↔ real
  companion settings + capabilities (2)).
- `npm run smoke:obsidian` (real Obsidian 1.8.9, fake Copilot CLI): 19/19 — model/effort/context selects populated from
  the CLI's help, a saved unsupported model shows `invalid_request: model "no-such-model" is not supported by copilot-cli;
  supported: …`, chosen model + effort arrive as `--model fake-pro --reasoning-effort low` on the CLI command line.
- `MONOCLE_SMOKE_LIVE=1 npm run smoke:obsidian` (Copilot CLI 1.0.104): 16/16 — 31 real models + `auto`, efforts
  `none…max`, tiers `default, long_context`; live run with thinking effort `low` completed.

**Acceptance criteria:**

- *Supported settings appear in adapter request*: `ExecutionRequest.settings` reaches `ProviderAdapter.run`, the Copilot
  adapter maps them to `--model`, `--reasoning-effort`, `--context`; `started.settings` echoes what was applied.
- *Invalid settings return actionable errors*: unknown setting names, non-string values, settings the provider doesn't
  declare and values outside its options → `400 invalid_request` naming the setting and listing supported values, before
  any provider process starts. A model the catalog lists but the account can't use still fails as `provider_error` with
  the CLI's message.
- *Switching models does not change Monocle knowledge services*: settings live only in contracts/Cravat/plugin; Cravat
  still has no dependency on `@monocle/core` (`test/workspace-boundaries.test.ts`); nothing in knowledge services reads them.

**Implementation notes:**

- Contract stays `0.2.0` (additive): optional `ExecutionRequest.settings { model?, reasoningEffort?, contextWindow? }`,
  optional `started.settings`, `GET /v1/capabilities` → `{ provider, settings: { <name>: { options } } }` (missing key =
  unsupported), `validateExecutionSettings()`.
- `ProviderAdapter.capabilities?()` (optional; absent = no settings). `ExecutionManager.capabilities()` caches per
  companion process; `validate()` runs before `start()`.
- `CopilotCliAdapter.capabilities()` parses `copilot --help` (`[possible values: …]` for `--reasoning-effort`,
  `--context`) and `copilot help config` (`model` catalog, plus `auto`); no premium request, ~1 s.
- Panel: one select per supported setting ("Provider default" = omit), persisted host-locally in
  `localStorage["monocle:execution-settings"]`; re-fetched per companion `instanceId`; meta line shows applied settings while running.
