# D06 — Vault access, validation and conflict behavior
**Status:** Decided (2026-11-21)

## Decision
- Preserve native human edits in Obsidian; Monocle observes all local filesystem changes.
- **Policy-based hybrid:** managed writes preferred and mandatory for designated operations; trusted deterministic scripts and authorized agents may write directly under defined policies. A hard boundary requires filesystem restriction, not just prompts.
- **Progressive validation:** new notes must conform; pre-existing unrelated schema issues are grandfathered; new violations and critical integrity conflicts are rejected.
- Every note uses a persistent unique frontmatter ID (actual field/format and migration to be validated against vault).
- Managed writes check current content/version. When a pending proposal is stale, **rebase against current note and raise a new proposal**, preserving lineage; never implicitly approve a changed proposal.
- Local-first proposals have a portable versioned serialization format; cross-device review is deferred.

## Verification needed
Inspect frontmatter schema and existing note-creation script; design concrete file hash/patch guards, atomic writes, filesystem permissions, merge/rebase behavior and recovery.
