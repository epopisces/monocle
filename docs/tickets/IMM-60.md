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

- [ ] Implementation completed
- [ ] Automated checks passed (record command and outcome)
- [ ] Acceptance criteria validated
- [ ] Summary and artifacts committed or handed back for synchronization

**Implementation notes:**

