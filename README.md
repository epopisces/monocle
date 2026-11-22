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
