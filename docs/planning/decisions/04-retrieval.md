# D05 — Knowledge retrieval and index
**Status:** Decided (2026-11-21)

## Decision
- Index documents, frontmatter, wikilinks and **explicit** entity relationships; inferred relationships may become **curation proposals**, only accepted ones become authoritative.
- Stable persistent note IDs distinguish identity from path/title.
- Baseline search: **SQLite/FTS5** full-text, metadata and explicit relationship traversal.
- Optional semantic backend: **ChromaDB** as first vector store, behind a retrieval adapter; configurable embedding providers, **local by default**.
- Unified query/ranking/results interface; lexical/metadata search must remain functional without embeddings.
- **Tiered indexing:** promptly reconcile SQLite on changes; queue semantic indexing separately with configurable delay/limits; rebuild both from authoritative Markdown.
- Each client maintains its own indexes; no synchronized index data.

## Verification needed
Actual note schemas/relationship forms, chunking and citation semantics, Chroma TypeScript deployment compatibility, stale-index and model-change behavior.
