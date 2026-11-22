# IMM-59 — [M4] Query metadata, persistent identities and explicit note relationships

**Source:** [Linear IMM-59](https://linear.app/immoil/issue/IMM-59/monocle-m4-query-metadata-persistent-identities-and-explicit-note-relationships)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-58](IMM-58.md)  
**Blocks:** [IMM-62](IMM-62.md)  

## User story

As an agent or user, I can deterministically find notes by metadata and traverse explicit links.

## Scope

Resolve wikilinks/frontmatter references to immutable note IDs; store relation edges and source locations; expose read/search/filter/relationship API with source references; do not promote inferred links.

## Acceptance criteria

Rename changes path but not identity; backlink/edge queries return grounded note references; broken/ambiguous links reported; tests cover aliases.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

No automatically inferred relationship graph.

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

- **Code:** `packages/monocle-core/src/note-index/` — `links.ts` (pure extraction of body wikilinks/embeds and
  wikilink-valued frontmatter, with 1-based line/column; code spans/fences ignored), `relationships.ts` (self-contained
  `links` table keyed by `notes.rowid` + vault-wide resolution) and `metadata.ts` (`NoteFilter`). New `NoteIndex`
  methods: `links(path)`, `backlinks(path)`, `brokenLinks()`, `findNotes(filter)`. `SCHEMA_VERSION` bumped to 2.
- **Identity:** links store the target's `notes.rowid`, which survives moves (paired by persistent ID, then hash), and
  results return `NoteRef { path, id, title }` read at query time — a rename changes `path`, not `id`/edges. All links
  are re-resolved after any reconcile that changed notes, so renames/deletes/new notes update every edge.
- **Resolution (Obsidian-like):** vault path (exact or suffix) for targets with `/`, else case-insensitive file name,
  else frontmatter `aliases`/`alias`; `[[#Heading]]` resolves to the same note. Outcomes: `resolved`, `ambiguous`
  (with `candidates`), `unresolved`, `attachment` (non-`.md` target with no matching note; not reported as broken).
  Heading/block subpaths are recorded but not validated. Display text (`|alias`) is never used for resolution.
- **Relations:** body → `links_to`/`embeds`; frontmatter → sibling `relation` value (e.g. `links[].relation: owner`)
  else the top-level key (e.g. `project`). Plain frontmatter strings (e.g. `people: [Ada Example]`) are not promoted
  to edges (no inferred links).
- **Automated checks:** `npm ci && npm run check` — build OK, 46/46 passed (67/67 after merging IMM-46; 9 new in
  `packages/monocle-core/test/relationships.test.ts`).
- **Acceptance:** rename keeps identity/backlinks (with Obsidian-style link rewrite) and breaks links when not rewritten;
  backlinks carry source note refs + locations; broken and ambiguous links reported; frontmatter aliases and display
  aliases covered; incremental = restart = rebuild. Manual Obsidian verification not applicable (no runtime here).
