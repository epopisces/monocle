# IMM-6 — Epic: Monocle Knowledge Layer

**Source:** https://linear.app/immoil/issue/IMM-6/epic-monocle-knowledge-layer  
**Linear status at export:** Backlog  
**Priority:** High  
**Labels:** Infrastructure, Documentation, AI  
**Related issue:** IMM-39 — Define platform responsibilities and shared service boundaries (not included in execution bundle)

## Original Linear epic description

Build Monocle as the knowledge management layer over Obsidian-compatible Markdown vaults.

Purpose:

* Replace ad hoc note organization with a durable, queryable knowledge layer.
* Preserve Markdown/Obsidian-compatible source of truth while enabling AI-assisted organization and retrieval.

Scope:

* Vault structure and conventions
* Markdown ingestion and indexing
* Weekly summaries and knowledge maintenance
* Integration with AI agents via MCP/tooling
* Interfaces for task and project context

Initial child issues may include vault schema, ingest pipeline, vector index, summary workflow, and Codex handoff docs.

## Execution scope

The 18 approved implementation children IMM-45–IMM-62 implement the MVP architecture D01–D08. The original epic is broader than this MVP: weekly summaries, broad MCP and Top Hat integration are not automatically added to this execution bundle. Five earlier child planning issues IMM-19–IMM-23 remain in Linear but are not part of the approved 18-ticket execution slice.

See [EXECUTION-ORDER.md](EXECUTION-ORDER.md) and [planning/MONOCLE-MVP-SPEC.md](planning/MONOCLE-MVP-SPEC.md).
