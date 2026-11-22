# Monocle Offline Execution Bundle

**Export source:** Linear workspace Immoil / Personal Engineering / IMM-6  
**Snapshot:** November 21, 2026 (issue content and relations fetched from connected Linear)  
**Includes:** 1 epic, 18 approved execution tickets, dependency graph, execution runbook, Wayfinder map, D01–D08 decisions, and MVP specification.

## Start here

1. Read [EPIC-IMM-6.md](EPIC-IMM-6.md) and [planning/MONOCLE-MVP-SPEC.md](planning/MONOCLE-MVP-SPEC.md).
2. Read [planning/MAP.md](planning/MAP.md) and the relevant [Wayfinder decisions](planning/decisions/).
3. Read [EXECUTION-ORDER.md](EXECUTION-ORDER.md) and open the first unblocked ticket, **[IMM-45](tickets/IMM-45.md)**.
4. Use the ticket's exact scope and acceptance criteria. Work in the source repository; treat Markdown vault data as authoritative and do not write to a production vault during discovery.
5. Update the **local offline execution record** in the ticket and the [PROGRESS.md](PROGRESS.md) checklist. When Linear is accessible again, sync completed work and comments manually.

## Authority and sync caveats

This is a **snapshot**, not a live Linear integration. Statuses and blockers may change remotely. Do not mark a ticket executable while its listed blockers remain incomplete locally. No automatic Linear updates occur from these files.

**Precedence:** confirmed Wayfinder decisions → MVP specification → Linear ticket scope → implementation detail. If an implementation issue contradicts an architectural decision, surface the conflict for review.

**Data separation:** keep organizational/private vault contents, credentials, tokens, agent logs and machine-local configuration out of a shared repository; provide only redacted or synthetic fixture notes.
