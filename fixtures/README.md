# Test fixtures

## `vault/` — synthetic fixture vault

A small, fully synthetic Obsidian vault for automated tests. It contains **no real people, institutions or private
content**. Tests must copy it to a temporary directory before running anything that writes. Never point tests at a
real vault.

| Path | Case it exercises |
|---|---|
| `people/Ada Example.md` | Frontmatter note with `id`, wikilink with alias, link to a heading-less note |
| `projects/Project Lantern.md` | Structured `links:` frontmatter list, unique search token `lanternfish-7731`, unresolved link `[[Missing Note]]` |
| `work/2026-01 Adopt Fixture Vaults.md` | Heading link `[[Note#Heading]]`, embed `![[diagram.png]]` of a missing attachment |
| `work/Legacy Note Without Frontmatter.md` | Grandfathered legacy note: no frontmatter, no ID, lower-case link target |
| `work/Duplicate Id Note.md` | Shares `id: fx-0002` with Project Lantern (duplicate-ID diagnosis) |
| `inbox/Untyped Capture.md` | Inline-list tags, no `id`/`type` (fresh capture awaiting curation) |
| `templates/Fixture Template.md` | Template placeholders; indexers should decide whether to exclude template folders |
| `attachments/README.txt` | Non-Markdown file that must be ignored by Markdown indexing |
| `.obsidian/app.json` | Minimal Obsidian config (wikilinks, inbox as new-note folder); not vault content |

### Provisional conventions (not verified against the real vault)

The field names below come from the **legacy Monocle templates** (`legacy/monocle/vault/templates/*.yaml`) and from
the spec's "stable frontmatter ID" requirement. They are **placeholders until the read-only real-vault discovery**
(`docs/bootstrap/REAL-VAULT-DISCOVERY.md`) confirms or replaces them:

- `id` — persistent note ID field name and `fx-NNNN` format are fixture-only inventions. The real field name/format is
  undecided (spec: "Exact field name/format and legacy migration procedures require vault inspection").
- `type` / `template` / `domain` / `people` / `tags` / `links` / `created` — mirror legacy Monocle `NoteMetadata`; the
  real vault and Curator's `create-obsidian-note` may differ.

Update this fixture (not the tests' expectations alone) once real conventions are known.
