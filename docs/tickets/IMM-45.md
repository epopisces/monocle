# IMM-45 — [M0] Inspect assets and bootstrap Monocle monorepo

**Source:** [Linear IMM-45](https://linear.app/immoil/issue/IMM-45/monocle-m0-inspect-assets-and-bootstrap-monocle-monorepo)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** None  
**Blocks:** [IMM-46](IMM-46.md), [IMM-58](IMM-58.md)  

## User story

As an implementer, I can build and test a fresh TypeScript workspace while preserving reusable legacy assets.

## Scope

Inspect read-only where available: legacy Monocle UI/trace/model abstractions; Obsidian Curator; create-obsidian-note scripts; vault frontmatter, templates, IDs and links. Create TS workspace with plugin, companion, Monocle core/index, Cravat and contracts boundaries. Document unverifiable assumptions rather than inventing schemas.

## Acceptance criteria

Clean install/build/test command succeeds; basic package contract test runs; inventory identifies keep/replace/defer; fixture vault and explicit read-only real-vault discovery plan exist.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not edit production vault, migrate legacy app wholesale, or rebuild markdown editor.

## Architecture references

Monocle MVP specification (D01–D08), M0. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Entry point; no implementation predecessors.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed — `npm ci && npm run check` (tsc -b + vitest): 2 files, 22 tests passed (2026-11-22)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed (branch `epopisces-imm-45-bootstrap-monorepo`)

**Implementation notes:**

- **Workspace:** npm workspaces + TypeScript project references + vitest (Node ≥ 22). Packages: `@monocle/contracts`,
  `@monocle/core`, `@monocle/cravat`, `@monocle/companion` and `@monocle/obsidian-plugin` (minimal `Plugin` subclass and
  `manifest.json`). There is a root `.gitignore` and `README.md`.
- **Contract tests:** `packages/contracts/test/contract-version.test.ts` covers semver contract compatibility.
  `test/workspace-boundaries.test.ts` checks that every package exports a matching `packageDescriptor` with a compatible
  contract version, and enforces the allowed dependency/import graph: Cravat must never depend on `@monocle/core`, and
  the plugin depends on contracts only. A mutation check confirmed that an illegal import fails the test.
- **Inventory (keep/replace/defer):** [docs/bootstrap/ASSET-INVENTORY.md](../bootstrap/ASSET-INVENTORY.md).
- **Fixture vault:** [fixtures/vault](../../fixtures/vault) is synthetic and described in
  [fixtures/README.md](../../fixtures/README.md).
- **Read-only real-vault discovery plan:** [docs/bootstrap/REAL-VAULT-DISCOVERY.md](../bootstrap/REAL-VAULT-DISCOVERY.md).
- **Unverifiable on this host:** Obsidian Curator, `create-obsidian-note` and the real vault were not found. The vault's
  ID field name/format and schema are therefore placeholders (`id: fx-NNNN` in fixtures only). Legacy Monocle has no
  persistent note ID; it identifies notes by path.
- **Manual verification not done:** the plugin has not been loaded into Obsidian. Bundling and installation belong to
  IMM-46.

