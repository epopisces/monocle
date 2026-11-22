# D06 — Approval, proposals and provenance
**Status:** Decided (2026-11-21)

## Decision
- Human approval is **risk-based**; low-risk authorized operations may run without review, while destructive, ambiguous, sensitive or high-impact edits require approval.
- Proposals are **local for MVP**, portable for future sync; review state and individual changes scoped to sessions.
- Native Obsidian diff view supports individual accept/reject, next/previous and mandatory **Approve All Pending for the current agent session**; bulk action must report applied/skipped/conflicted/failed.
- Stale proposals are rebased against latest note and re-issued as **new pending proposals**; they are not silently included in bulk approval.
- **Minimal change history**: lightweight managed mutation records (note IDs, actor/session, time, operation, before/after hashes, approval outcome, optional Git ref). Depend on existing Git/filesystem history when available; sync alone is not version history.
- Distinguish Cravat execution diagnostics from Monocle mutation metadata; no comprehensive audit subsystem in MVP.

## Verification needed
Existing version-control mechanism, rollback approach, risk-classification defaults, persistence format, invalid proposal handling.
