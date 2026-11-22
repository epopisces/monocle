# IMM-46 — [M1] Connect Obsidian panel to independent companion

**Source:** [Linear IMM-46](https://linear.app/immoil/issue/IMM-46/monocle-m1-connect-obsidian-panel-to-independent-companion)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-45](IMM-45.md)  
**Blocks:** [IMM-47](IMM-47.md)  

## User story

As an Obsidian user, I can open a Monocle panel and connect to the independently running local companion.

## Scope

Implement minimal plugin panel and loopback companion endpoint; configurable host-specific endpoint and health check; lifecycle independent of Obsidian; errors shown without blocking native editing.

## Acceptance criteria

Plugin connects to companion; closing Obsidian does not stop companion; disconnected/reconnected states visible; integration test and restart smoke test pass.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No agent execution, indexing or vault mutation yet.

## Architecture references

Monocle MVP specification (D01–D08), M1. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 01 Inspect assets and bootstrap Monocle monorepo.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed (record command and outcome)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

- Branch `epopisces-imm-46-obsidian-panel` (based on `refactor` @ 01861e4).
- **Contract** (`@monocle/contracts`, `companion.ts`): `GET /v1/health` → `HealthResponse { service: "monocle-companion",
  status, contractVersion, instanceId, startedAt }`, default endpoint `http://127.0.0.1:48765`, `isLoopbackHostname`,
  `isHealthResponse`. `CONTRACT_VERSION` stays `0.1.0` (first published surface).
- **Companion** (`@monocle/companion`): `startCompanion({host, port})` HTTP server on loopback only (non-loopback bind
  refused; non-loopback `Host` header → 403 as DNS-rebinding guard). Standalone CLI `dist/cli.js`
  (`npm run companion`, `--host/--port` or `MONOCLE_COMPANION_HOST/PORT`) prints one JSON `listening` line and exits on
  SIGINT/SIGTERM.
- **Plugin** (`@monocle/obsidian-plugin`): Obsidian-free `CompanionConnection` state machine
  (`connecting → connected | disconnected | incompatible`, polling, timeout, contract-version check) and
  `parseCompanionEndpoint` (http loopback origins only). `main.ts`: side panel view (status, endpoint, error, Reconnect),
  status bar item, commands *Open panel* / *Reconnect to companion*, settings tab. Endpoint is stored per host via
  `app.saveLocalStorage` (not synced through the vault), so `minAppVersion` is now 1.8.7. Health uses `requestUrl` to
  avoid renderer CORS. Unloading the plugin only stops polling; it never launches/stops the companion. Errors are shown
  in the panel/status bar only (no modals), so native editing is unaffected.
- **Bundling**: esbuild → `main.js` (CJS, `obsidian` external) via `npm run bundle:plugin -- --vault <path>`.
- **Automated checks**: `npm ci && npm run check` → 43/43 passed. New: companion HTTP seam (5), process restart smoke
  test (1), plugin↔companion integration (6: connect, disconnect→reconnect, plugin stop leaves companion up,
  incompatible version, foreign service, timeout), endpoint validation (8), bundle loads requiring only `obsidian` (1).
- **Acceptance in real Obsidian** (1.8.9 on the implementing host): `npm run smoke:obsidian` → 8/8 passed — plugin
  loads; panel and status bar show Connected; companion killed → Disconnected with error visible; a fixture note opens
  in the native editor while disconnected; companion restarted → Connected; Obsidian closed → companion still healthy.
  Runs against a temp fixture-vault copy with a temp `--user-data-dir`, so no real vault or user profile is touched.
- **Manual verification** (other hosts): copy `fixtures/vault` to a temp dir; `npm run companion`;
  `npm run bundle:plugin -- --vault <copy>`; open the copy in Obsidian, enable community plugins and *Monocle*; run
  *Monocle: Open panel* → Connected; stop the companion (Ctrl+C) → Disconnected within ~5 s with the error shown, and
  editing still works; restart → Connected; quit Obsidian → `curl http://127.0.0.1:48765/v1/health` still answers.
- Non-goals respected: no agent execution, indexing or vault mutation.

