# IMM-52 — [M2] Create schema-valid notes via existing Curator skill

**Source:** [Linear IMM-52](https://linear.app/immoil/issue/IMM-52/monocle-m2-create-schema-valid-notes-via-existing-curator-skill)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-48](IMM-48.md), [IMM-51](IMM-51.md)  
**Blocks:** [IMM-53](IMM-53.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can create a note using Obsidian Curator and create-obsidian-note with the vault's established conventions.

## Scope

Inspect and integrate existing skill/script including Python dependencies; define deterministic note generation/ID semantics after vault inspection; test against fixture vault and same templates as Obsidian; use safe managed mutation as applicable.

## Acceptance criteria

New note has valid unique persistent frontmatter ID and expected template; deterministic generated fields match existing conventions; no overwrite of existing path/ID; failures are actionable.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not rewrite existing Curator agent or invent vault schema.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 04 Supply active-note context and restricted read-only vault tools; 07 Route registered deterministic commands and agentic requests.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed: `npm ci && npm run check` 245/245 (20 new create-note tests in core, 4 `/new-note` route tests in companion); `npm run smoke:obsidian` 60/60 (fake CLI), `MONOCLE_SMOKE_LIVE=1` 55/55 (real companion CLI with `--note-template`)
- [x] Acceptance criteria validated (fixture/temp vaults only; Curator gap below)
- [x] Summary and artifacts committed or handed back for synchronization (branch `epopisces-imm-52-curator-note-creation`)

**Implementation notes:**

- **Curator gap.** Neither Obsidian Curator nor `create-obsidian-note` is installed on this host (searched `~/.copilot`, `~/.agents`, `~/.claude`, `C:\development`), so nothing could be inspected or reused. Per the ticket's non-goal (don't rewrite Curator, don't invent a schema), note generation sits behind a `NoteRenderer` adapter boundary in `@monocle/core` (`operations/create-note.ts`):
  - `vaultTemplateRenderer` (default) fills the vault's own Obsidian template (`.obsidian/templates.json` folder, else `templates/`) — the same file Obsidian's Templates plugin inserts.
  - `commandNoteRenderer` is the Curator integration point: runs an external script (no shell, 30 s timeout) with the `NoteDraft` JSON on stdin and expects `{"content": "<markdown>"}` on stdout; non-zero exit → `renderer_failed` with its stderr. Tested with `packages/monocle-core/test/fixtures/fake-curator.mjs`. CLI: `--note-renderer <exe> --note-renderer-arg ...`. Python dependencies of the real script remain to be verified on a host that has it.
- **Monocle owns integrity, the renderer owns content.** `planNote` (no writes) checks title (Obsidian-forbidden characters rejected, not sanitized), folder (vault-relative, indexed, no dot/excluded folders; default `.obsidian/app.json` `newFileFolderPath`), reconciles the index first, refuses a case-insensitive path clash, assigns the next ID, renders, then rejects unfilled `{{placeholders}}`, unparsable frontmatter, a missing ID and an ID already in use. `createNote` writes with an exclusive create (`wx`, never replaces a file that appeared meanwhile), re-indexes, runs `validateNote`, and removes the note again if it fails with an error.
- **ID semantics (deterministic, from the vault's existing IDs).** The dominant `<prefix><digits>` sequence continues with the same padding (fixture: `fx-0003` → `fx-0004`); otherwise Obsidian's unique-note timestamp `YYYYMMDDHHmm` (local clock), suffixed `-1`, `-2`, … on collision. Generated fields `{{date}}` (YYYY-MM-DD) and `{{time}}` (HH:mm) follow Obsidian's Templates defaults. Request fields cannot override the ID.
- **Command.** Registry command `/new-note <title>` (chat surface, `route: "monocle"`, new permission `create-note`) via `POST /v1/commands`; enabled only when the companion is started with `--note-template <name>` (optional `--note-folder`, repeatable `--note-field key=value`), otherwise `403 not_permitted` saying how to enable it. Failures are `400 note_creation_failed` with a `reason` (`NoteCreationErrorCode`) and a message saying what to change. `monocle_vault` stays read-only; agents get no write tool (IMM-53/54).
- **Unverified conventions** (need real-vault inspection): the real ID field/format, the real templates (fixture `{{id}}`/`{{type}}` are not stock Obsidian Templates variables), and whether new notes should go to `newFileFolderPath`.

