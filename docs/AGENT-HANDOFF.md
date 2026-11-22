# Agent Handoff — Monocle Offline Execution

Implement one unblocked Monocle issue from this bundle at a time. Start with IMM-45.

1. Read README.md, EPIC-IMM-6.md, planning/MAP.md, planning/MONOCLE-MVP-SPEC.md and the relevant planning/decisions/*.md documents.
2. Read EXECUTION-ORDER.md and the chosen tickets/IMM-XX.md. Verify its `Blocked by` tickets are complete in local PROGRESS.md.
3. Inspect actual source repos and vault conventions rather than guessing. Legacy Monocle and Curator are references; do not wholesale port legacy app or rewrite Curator. Skills may include Python dependencies, but core Monocle/Cravat is TypeScript-first.
4. Use fixture vaults for tests. Never mutate a production vault during IMM-45. Keep secrets, institutional data, and private content out of shared code and fixtures.
5. Implement **only** the selected issue, run tests, record results and commit or prepare a reviewable diff.
6. Update local ticket execution record and PROGRESS.md; include linkable commit(s), tests, blockers, and anything to synchronize back to Linear.

**First issue:** tickets/IMM-45.md.

**Do not treat this snapshot as live Linear.**
