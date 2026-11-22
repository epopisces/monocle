# IMM-51 — [M2] Route registered deterministic commands and agentic requests

**Source:** [Linear IMM-51](https://linear.app/immoil/issue/IMM-51/monocle-m2-route-registered-deterministic-commands-and-agentic-requests)  
**Parent:** [IMM-6](../EPIC-IMM-6.md)  
**Linear status (export):** Backlog  
**Priority:** High  
**Labels:** `ready-for-agent`, `AI`, `Feature`  
**Blocked by:** [IMM-48](IMM-48.md)  
**Blocks:** [IMM-52](IMM-52.md), [IMM-62](IMM-62.md)  

## User story

As a user, I can use chat, command palette or contextual actions without invoking an agent for deterministic work.

## Scope

Implement common command registry and arguments; route /validate and read-only operations to Monocle, /lookup and free-form requests to Cravat; include context requirements and operation permissions.

## Acceptance criteria

Same registered operation reachable by chat/palette/context where appropriate; deterministic commands do not start Cravat; errors identify missing context.

## Tests / evidence

Add automated tests for specified behaviors plus manual verification where Obsidian/agent runtime is involved. Use fixture vault; do not assume access to real vault before inspection.

## Non-goals

Do not implement an entirely new general command language.

## Architecture references

Monocle MVP specification (D01–D08), M2. Markdown authoritative; Cravat owns execution, Monocle owns knowledge services. Prioritize deterministic operations and minimal custom UI.

## Dependency rationale

Requires: 04 Supply active-note context and restricted read-only vault tools.

---

## Offline execution record (local, not synchronized to Linear)

- [x] Implementation completed
- [x] Automated checks passed: `npm ci && npm run check` (221/221 after merging origin/refactor); `npm run smoke:obsidian` passed 53/53 with the fake CLI, and `MONOCLE_SMOKE_LIVE=1` passed 48/48 against Copilot CLI
- [x] Acceptance criteria validated
- [x] Summary and artifacts committed or handed back for synchronization (branch `epopisces-imm-51-command-routing`)

**Implementation notes:**

- **One registry:** `COMMANDS` in `@monocle/contracts` (`commands.ts`). Each definition has an id, a route (`monocle` = deterministic, `cravat` = agentic), a permission (`read-vault` for all four), the context it requires (`activeNote`, `vault`), an optional argument (`fromSelection` lets a selection fill it), and the surfaces it appears on (`chat`, `palette`, `editor-menu`, `file-menu`). Chat, the palette and the menus all read from this registry.
  - `/validate`: Monocle; needs an active note and a vault; chat, palette, editor menu, file menu
  - `/backlinks`: Monocle; needs an active note and a vault; chat, palette, file menu
  - `/search <query>`: Monocle; needs a vault; chat only
  - `/lookup <question>`: Cravat; needs a vault, and a selection can fill the question; chat, palette, editor menu
- **Chat parsing:** `parseChatInput` matches `/name [argument]`. Input like `/etc/hosts …` stays free-form. An unknown name is rejected locally, before anything is sent, with a message listing the available commands.
- **Deterministic route:** `POST /v1/commands` (`{command, argument?, context?.activeNote.path}`) runs `validate`, `backlinks` or `search` against the index service. It never starts Cravat and is not recorded in conversations.
  - Result: `{command, title, markdown, data}`.
  - Errors: `unknown_command`, `agentic_command` (use `/v1/executions`), `missing_context` (with `missing`) and `invalid_request`.
- **Validate:** `validateNote` in `@monocle/core` reindexes the note from disk. It never writes.
  - Errors: `frontmatter_invalid`, `duplicate_id` (names the other paths).
  - Warnings: `missing_id`, `unresolved_link`, `ambiguous_link` (with a 1-based line).
- **Agentic route:** the optional `ExecutionRequest.command` field (additive; the contract is still 0.2.0) makes the companion replace the prompt with the `/lookup` grounding template. The template tells the agent to use the monocle_vault tools, cite paths and not modify files. The conversation records `/lookup <question>`.
  - Sending a Monocle-route command to executions returns `invalid_request`.
  - Missing context returns the new `missing_context` code.
- **Missing context:** errors name the missing argument, active note or vault (for example, "/validate needs an active note: open a Markdown note and try again"). The plugin checks the argument and active note before sending anything; the companion decides whether a vault is configured.
- **Plugin:** `CommandRunner` sends each command to the right route.
  - Palette commands: `monocle:<id>`.
  - Editor-menu and file-menu items: "Monocle: <name>".
  - The panel shows `Monocle /<id> · completed|failed` for deterministic results and the normal execution stream for `/lookup`.
- **Tests:**
  - `packages/contracts/test/commands.test.ts`
  - `packages/monocle-core/test/validate-note.test.ts`
  - `packages/companion/test/commands.test.ts`
  - `test/plugin-companion-commands.integration.test.ts`
  - smoke checks: palette, chat and file-menu routes, no Cravat execution for deterministic commands, missing active note, `/lookup` (live: the answer names Ada Example and cites the note), and vault notes unchanged

