# Monocle

Local-first knowledge-management system: **Monocle for Obsidian** (plugin) + an independently running local
**companion** hosting **Monocle knowledge services** and **Cravat** agent execution. Markdown in the synced vault is
authoritative; indexes are derived per host.

- Planning, spec and tickets: [`docs/`](docs/README.md)
- Asset inventory and real-vault discovery plan: [`docs/bootstrap/`](docs/bootstrap/ASSET-INVENTORY.md)
- Archived legacy app (read-only reference): [`legacy/`](legacy/README.md)

## Development

Requires Node.js ≥ 22 and npm.

```sh
npm ci          # clean install
npm run build   # tsc -b across all packages
npm test        # vitest (package contract + boundary tests)
npm run check   # build + test
```

| Package | Role |
|---|---|
| `packages/contracts` (`@monocle/contracts`) | Shared, versioned contracts; no workspace deps |
| `packages/monocle-core` (`@monocle/core`) | Knowledge services (read/search/index/validate/change) |
| `packages/cravat` (`@monocle/cravat`) | Agent execution and provider adapters; independent of `@monocle/core` |
| `packages/companion` (`@monocle/companion`) | Local process hosting core + Cravat; runs without Obsidian |
| `packages/obsidian-plugin` (`@monocle/obsidian-plugin`) | Obsidian client; depends only on contracts |

Tests use the synthetic vault in [`fixtures/vault`](fixtures/README.md). Never point tests or tools at a real vault.

## Running the companion and plugin

The companion is a separate process with its own lifecycle; Obsidian never starts or stops it.

```sh
npm run companion                       # listens on http://127.0.0.1:48765 (loopback only)
npm run companion -- --port 49000       # or MONOCLE_COMPANION_PORT / MONOCLE_COMPANION_HOST
npm run bundle:plugin -- --vault <vault> # installs main.js, manifest.json, styles.css into <vault>/.obsidian/plugins/monocle
npm run smoke:obsidian                  # isolated end-to-end check in a real Obsidian (≥ 1.8.7) install
```

`GET /v1/health` returns the companion's service ID, contract version and per-process instance ID. In Obsidian,
enable **Monocle**, run **Monocle: Open panel**, and set **Settings → Monocle → Companion endpoint** if the companion is
not on the default. The endpoint is stored in this machine's local storage, not in the synced vault. `smoke:obsidian`
uses a temporary vault copy and a temporary Obsidian profile (`--user-data-dir`), so it never touches your vaults.
Override the executable path with `OBSIDIAN_EXE` if needed.

### Agent executions (Cravat)

The panel's prompt box sends free-form requests to Cravat, which runs them through the installed **GitHub Copilot
CLI** (`copilot`, signed in via `copilot login`). Point the companion at a specific executable with
`MONOCLE_COPILOT_PATH` (must be a real executable, not an npm `.cmd` shim). Executions run with **no tools** in an empty
scratch directory, so the agent cannot read or change files yet. The answer streams into the panel with its execution
ID; **Cancel** (or closing the panel) stops the Copilot process. `npm run smoke:obsidian` uses a fake Copilot CLI;
`MONOCLE_SMOKE_LIVE=1 npm run smoke:obsidian` exercises the real one (one premium request).

Contract (0.2.0): `POST /v1/executions` `{"prompt": "…"}` → NDJSON stream of `started`, `delta`… and exactly one of
`completed` / `failed` / `cancelled`; `POST /v1/executions/{id}/cancel`. Browser callers must send
`content-type: application/json` and may only come from Obsidian's `app://obsidian.md` origin.
