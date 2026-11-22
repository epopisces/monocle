# Read-only real-vault discovery plan

**Status:** Not yet executed. During IMM-45 no real vault, Obsidian Curator agent or `create-obsidian-note` skill was
accessible from the implementing host (see [ASSET-INVENTORY.md](ASSET-INVENTORY.md)). This plan must be run, by the
vault owner or an agent with explicit permission, **before** any ticket fixes schema rules, ID conventions or link
resolution (notably IMM-52, IMM-54, IMM-58 and IMM-59).

## Ground rules

1. **Read-only.** Never write, rename, format, move, or "fix" anything in the real vault. Do not open it in an Obsidian
   instance that has Monocle or other mutating plugins enabled. Prefer working from a **copy** (step 0).
2. **No content leaves the host.** Record only aggregate counts, field names, value *shapes* and anonymised examples.
   Never paste note bodies, names of real people, institutions, or sensitive frontmatter values into the repo, fixtures,
   tickets or shared notes.
3. Sensitive classifications are unknown: treat every folder as potentially sensitive until the owner says otherwise.
4. Record findings in `docs/bootstrap/VAULT-CONVENTIONS.md` (new file) and update `fixtures/vault/` to mirror the real
   *shapes* with synthetic content.

## Steps

0. **Snapshot.** Copy the vault to a scratch location outside any synced folder (e.g. `robocopy <vault> <scratch> /E`
   or `cp -a`). Run all remaining steps against the copy. Delete the copy afterwards.
1. **Layout.** Top-level folders, Markdown file count per folder, non-Markdown file types, attachment folder, template
   folder, any archive/excluded folders. Read `.obsidian/app.json` (link style, new-note location, attachment folder)
   and `.obsidian/core-plugins.json`/`community-plugins.json` (templates/Templater, Dataview, sync plugins).
2. **Frontmatter census.** For every `.md` file: has frontmatter? parses as YAML? Collect field names with occurrence
   counts and value types (string/list/date/object). Note inline vs block lists, date formats, and fields present on
   >80% of notes.
3. **Identity.** Is there any existing persistent ID field (e.g. `id`, `uid`, `uuid`, `note_id`, Zettelkasten-style
   filename prefixes)? Format, coverage %, and duplicate count. This decides the spec's open "stable frontmatter ID"
   field name/format and whether a migration plan is needed.
4. **Note types.** Values of `type`/`template`/equivalent; map to folders. Compare with legacy Monocle templates
   (`legacy/monocle/vault/templates/*.yaml`) and Curator's templates.
5. **Links.** Wikilinks vs Markdown links ratio; aliases `[[x|y]]`, heading/block links `[[x#h]]`/`[[x^b]]`, embeds,
   unresolved-link count, case-sensitivity reliance, duplicate basenames in different folders (affects resolution),
   structured relationship fields in frontmatter.
6. **Templates.** List template files and their placeholder syntax (core Templates `{{date}}` vs Templater `<% %>`).
7. **Curator & `create-obsidian-note`.** Locate the agent definition and skill (`SKILL.md`, scripts, Python
   dependencies). Record entry points, arguments, output path rules, the frontmatter they emit, and whether they write
   directly to the vault. Run only with `--help`/dry-run against a **fixture copy**, never the real vault.
8. **History/versioning.** Is the vault a Git repository? Which sync mechanism (Obsidian Sync, iCloud, Syncthing,
   OneDrive)? Any `.trash`/version-history folders? Informs the minimal-history and rollback decisions.
9. **Sensitivity.** Ask the owner which folders/tags are sensitive or must be excluded from provider context.

## Outputs expected

- `docs/bootstrap/VAULT-CONVENTIONS.md` with the answers above (aggregate/anonymised only).
- Updated `fixtures/vault/` and `fixtures/README.md` "provisional conventions" section.
- A decision on the persistent ID field name/format and whether legacy notes need an ID migration plan.
