# D01–D03 — Deployment, sync and runtime
**Status:** Decided (2026-11-20/21)

## Decision
- Local-first Monocle deployable to multiple machines, **not** a centralized mandatory network service.
- Obsidian vaults replicate through the **existing Obsidian synchronization mechanism**, external to Monocle.
- Each host builds its own local derived SQLite/Chroma indexes; files and permitted portable config may sync through the vault.
- An independently launchable local companion runs without Obsidian. The companion is a process/deployment boundary, not a separate product.
- Host paths, runtime availability, credentials and secrets remain local; portable non-secret config may reside in vault.

## Consequences
- Watch and reconcile the local filesystem; missed watch events require startup/full reconciliation.
- Treat syncing as eventually consistent; no global locks or synchronized index requirements.
- Local service endpoints should be restricted; remote exposure is deferred.

## Verification needed
Confirm actual sync settings, target host platforms, local service startup, and vault inclusion/exclusion rules when the vault is available.
