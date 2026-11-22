# IMM-60 — [M4] Add configurable optional ChromaDB semantic retrieval

**Source:** [Linear IMM-60](https://linear.app/immoil/issue/IMM-60/monocle-m4-add-configurable-optional-chromadb-semantic-retrieval)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** Medium  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-58](IMM-58.md)  
**Blocks:** [IMM-61](IMM-61.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can enable local embeddings and semantic search without losing lexical behavior when disabled.

## Scope

Implement embedding-provider adapter (local default, optional policy-permitted remote), ChromaDB storage adapter, chunk IDs linked to note IDs and hashes, bounded background queue, common result interface and fusion fallback.

## Acceptance criteria

Semantic retrieval returns source passage IDs; disabling/unavailable provider leaves SQLite searches healthy; changed chunks reembed; model/version change triggers rebuild path.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No remote embedding mandated; no Chroma as authoritative store.

## Architecture references

Monocle MVP specification (D01–D08), M4. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 14 Incrementally index synchronized notes in SQLite FTS5.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed (record command and outcome)
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

- **Code:** `packages/monocle-core/src/semantic/` — `chunkNote()` (heading-aware passages), `EmbeddingProvider` /
  `VectorStore` adapters (`createOllamaEmbeddingProvider` local default, `createOpenAICompatibleEmbeddingProvider`,
  `createChromaVectorStore`, `createMemoryVectorStore`), `openSemanticIndex()` (bounded background queue, ledger and
  embedding cache), `createRetriever()` (unified results, RRF fusion, lexical fallback) and
  `createSemanticIndexFromConfig()` (disabled by default; remote providers need `allowRemoteProviders`). Exported from
  `@monocle/core`. No new dependencies: adapters use `fetch` against the Ollama, OpenAI-style and Chroma v2 REST APIs.
- **Self-contained state:** semantic bookkeeping lives in its own host-local SQLite file (`statePath`), so the note
  index `SCHEMA_VERSION` is untouched. Passage IDs are `<path>#<12 hex of passage hash>` (`~N` for repeats), linked to
  note ID, note hash and passage hash in vector metadata; keyed by path rather than `notes.rowid` so a note-index
  rebuild never orphans vectors.
- **Chunking:** split on Markdown headings (fence-aware), heading trail kept per passage, oversized sections split on
  paragraphs (`maxChars` default 1500). Chunking/ranking choices are provisional per spec.
- **Model/version change:** a fingerprint (semantic schema, chunker version, `maxChars`, provider ID, store ID) mismatch
  clears the ledger, resets the store (Chroma collection delete) and re-embeds everything; `status().rebuildReason`
  explains why; search refuses (and the retriever falls back to lexical) until the reset has run.
- **Automated checks:** `npm ci && npm run check` — build OK, 90/90 tests passed (23 new in
  `packages/monocle-core/test/semantic-*.test.ts`; fake embedding provider, in-memory store and fake `fetch`; no
  Chroma/Ollama server required).
- **Acceptance:** semantic search returns source passage IDs; disabled or failing provider leaves SQLite search
  healthy and the retriever answers lexically (`semantic.status` = `disabled`/`unavailable`); only changed passages
  re-embed (moves reuse cached vectors); model change triggers the rebuild path — all covered by tests.
- **Manual verification (not run here):** against a live Chroma ≥ 1.0 server (`chroma run --path ./chroma_data`) and
  Ollama (`ollama pull nomic-embed-text`): enable `{ enabled: true }`, reconcile the fixture vault, `drain()`, then
  check `createRetriever(...).search("...")` returns semantic passages; stop Chroma and confirm results degrade to
  lexical with `status().state === "degraded"`. The Chroma `configuration: { hnsw: { space: "cosine" } }` create body
  and `DELETE .../collections/{name}` reset follow the v2 OpenAPI client but are unverified against a live server.
- **Not done (later tickets):** companion wiring/config persistence and contracts types (IMM-61/62), distance
  threshold for weak semantic matches.