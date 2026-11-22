import { cpSync, mkdirSync, mkdtempSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { openNoteIndex, type NoteIndex } from "@monocle/core";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let vault: string;
const opened: NoteIndex[] = [];

function open(options: Partial<Parameters<typeof openNoteIndex>[0]> = {}): NoteIndex {
  const index = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db"), excludeFolders: ["templates"], ...options });
  opened.push(index);
  index.reconcile();
  return index;
}

function write(rel: string, content: string): void {
  mkdirSync(dirname(join(vault, rel)), { recursive: true });
  writeFileSync(join(vault, rel), content);
}

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-links-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
});

afterEach(() => {
  for (const index of opened.splice(0)) index.close();
  rmSync(work, { recursive: true, force: true });
});

describe("explicit note relationships", () => {
  it("resolves a note's body wikilinks to note identities with source locations", () => {
    const index = open();

    const links = index.links("people/Ada Example.md");
    expect(links).toMatchObject([
      {
        kind: "wikilink",
        relation: "links_to",
        raw: "[[Project Lantern]]",
        target: "Project Lantern",
        display: null,
        location: { line: 15, column: 25 },
        status: "resolved",
        resolved: { path: "projects/Project Lantern.md", id: "fx-0002", title: "Project Lantern" },
      },
      {
        raw: "[[2026-01 Adopt Fixture Vaults|the fixture decision]]",
        target: "2026-01 Adopt Fixture Vaults",
        display: "the fixture decision",
        location: { line: 15, column: 58 },
        status: "resolved",
        resolved: { path: "work/2026-01 Adopt Fixture Vaults.md", id: "fx-0003" },
      },
    ]);
    expect(links[0]!.source).toEqual({ path: "people/Ada Example.md", id: "fx-0001", title: "Ada Example" });
  });

  it("returns grounded backlinks, including heading links and case-insensitive names", () => {
    const index = open();

    expect(
      index.backlinks("people/Ada Example.md").map((l) => [l.source.path, l.kind, l.relation, l.raw, l.location]),
    ).toEqual([
      ["projects/Project Lantern.md", "frontmatter", "owner", "[[Ada Example]]", { line: 12, column: 14 }],
      ["projects/Project Lantern.md", "wikilink", "links_to", "[[Ada Example]]", { line: 18, column: 8 }],
      ["work/Legacy Note Without Frontmatter.md", "wikilink", "links_to", "[[ada example]]", { line: 3, column: 73 }],
    ]);
    expect(index.backlinks("projects/Project Lantern.md").map((l) => [l.source.id, l.subpath])).toEqual([
      ["fx-0001", null],
      ["fx-0003", "Goals"],
    ]);
  });

  it("keeps a note's identity and backlinks when it is renamed and its links are updated", () => {
    const index = open();
    renameSync(join(vault, "projects/Project Lantern.md"), join(vault, "projects/Lantern Renamed.md"));
    // Obsidian rewrites links on rename; emulate that for the two notes that link to the project.
    write(
      "people/Ada Example.md",
      "---\nid: fx-0001\ntitle: Ada Example\n---\nLeads [[Lantern Renamed]] and proposed [[2026-01 Adopt Fixture Vaults]].\n",
    );
    write("work/2026-01 Adopt Fixture Vaults.md", "---\nid: fx-0003\n---\nSee [[Lantern Renamed#Goals]].\n");
    index.reconcile();

    expect(index.getNote("projects/Project Lantern.md")).toBeUndefined();
    expect(index.links("people/Ada Example.md")[0]!.resolved).toEqual({
      path: "projects/Lantern Renamed.md",
      id: "fx-0002",
      title: "Project Lantern",
    });
    expect(index.backlinks("projects/Lantern Renamed.md").map((l) => l.source.id)).toEqual(["fx-0001", "fx-0003"]);
    // The renamed note's own outgoing links still point at Ada by identity.
    expect(index.backlinks("people/Ada Example.md").map((l) => l.source.path)).toContain("projects/Lantern Renamed.md");
  });

  it("reports a link as broken when its target is renamed without updating the link", () => {
    const index = open();
    renameSync(join(vault, "people/Ada Example.md"), join(vault, "people/Ada Renamed.md"));
    index.reconcile();

    expect(index.backlinks("people/Ada Renamed.md")).toEqual([]);
    expect(
      index
        .brokenLinks()
        .filter((l) => l.target.toLowerCase() === "ada example")
        .map((l) => [l.source.path, l.status]),
    ).toEqual([
      ["projects/Project Lantern.md", "unresolved"],
      ["projects/Project Lantern.md", "unresolved"],
      ["work/Legacy Note Without Frontmatter.md", "unresolved"],
    ]);
  });

  it("reports unresolved and ambiguous links but not embeds of attachments", () => {
    const index = open();
    write("archive/Project Lantern.md", "# Old Lantern\n");
    write("inbox/Links.md", "[[Project Lantern]] [[archive/Project Lantern]] ![[missing.pdf]]\n");
    index.reconcile();

    const broken = index.brokenLinks().map((l) => [l.source.path, l.raw, l.status, l.candidates.map((c) => c.path)]);
    expect(broken).toEqual([
      ["inbox/Links.md", "[[Project Lantern]]", "ambiguous", ["archive/Project Lantern.md", "projects/Project Lantern.md"]],
      ["people/Ada Example.md", "[[Project Lantern]]", "ambiguous", ["archive/Project Lantern.md", "projects/Project Lantern.md"]],
      ["projects/Project Lantern.md", "[[Missing Note]]", "unresolved", []],
      [
        "work/2026-01 Adopt Fixture Vaults.md",
        "[[Project Lantern#Goals]]",
        "ambiguous",
        ["archive/Project Lantern.md", "projects/Project Lantern.md"],
      ],
    ]);
    expect(index.links("inbox/Links.md").map((l) => [l.status, l.matchedBy, l.resolved?.path ?? null])).toEqual([
      ["ambiguous", "name", null],
      ["resolved", "path", "archive/Project Lantern.md"],
      ["attachment", null, null],
    ]);
    expect(index.links("work/2026-01 Adopt Fixture Vaults.md").map((l) => [l.kind, l.status])).toEqual([
      ["wikilink", "ambiguous"],
      ["embed", "attachment"],
    ]);
  });

  it("resolves links through frontmatter aliases and keeps display aliases as text only", () => {
    const index = open();
    write("people/Grace Sample.md", "---\nid: fx-0010\naliases: [Grace, G. Sample]\n---\n# Grace Sample\n");
    write(
      "inbox/Meeting.md",
      "Met [[grace]] and [[G. Sample|the sample]]; also [[Grace Sample|Ada Example]] and [[#Agenda]].\n",
    );
    index.reconcile();

    expect(
      index.links("inbox/Meeting.md").map((l) => [l.target, l.display, l.matchedBy, l.resolved?.path ?? null]),
    ).toEqual([
      ["grace", null, "alias", "people/Grace Sample.md"],
      ["G. Sample", "the sample", "alias", "people/Grace Sample.md"],
      ["Grace Sample", "Ada Example", "name", "people/Grace Sample.md"],
      ["", null, "self", "inbox/Meeting.md"],
    ]);
    expect(index.backlinks("people/Ada Example.md").map((l) => l.source.path)).not.toContain("inbox/Meeting.md");
  });

  it("ignores wikilinks inside code and does not infer links from plain frontmatter values", () => {
    const index = open();
    write(
      "inbox/Code.md",
      "---\npeople:\n  - Ada Example\nproject: \"[[Project Lantern]]\"\n---\nInline `[[Ada Example]]`.\n\n```\n[[Ada Example]]\n```\n",
    );
    index.reconcile();

    expect(index.links("inbox/Code.md").map((l) => [l.kind, l.relation, l.field, l.target, l.location])).toEqual([
      ["frontmatter", "project", "project", "Project Lantern", { line: 4, column: 11 }],
    ]);
  });
  it("derives the same links incrementally, after a restart and from a full rebuild", () => {
    const incremental = open();
    write("people/Ada Example.md", "---\nid: fx-0001\n---\nNow links [[Missing Note]] and [[Home]].\n");
    write("Missing Note.md", "# Now present\n");
    rmSync(join(vault, "work/Legacy Note Without Frontmatter.md"));
    incremental.reconcile();
    incremental.close();
    opened.length = 0;

    const restarted = open();
    const rebuilt = openNoteIndex({ vaultRoot: vault, dbPath: ":memory:", excludeFolders: ["templates"] });
    opened.push(rebuilt);
    rebuilt.rebuild();

    for (const note of rebuilt.listNotes()) {
      expect(restarted.links(note.path)).toEqual(rebuilt.links(note.path));
      expect(restarted.backlinks(note.path)).toEqual(rebuilt.backlinks(note.path));
    }
    expect(restarted.brokenLinks()).toEqual(rebuilt.brokenLinks());
    expect(restarted.backlinks("Missing Note.md").map((l) => l.source.path)).toEqual([
      "people/Ada Example.md",
      "projects/Project Lantern.md",
    ]);
  });
});

describe("metadata queries", () => {
  it("filters notes by frontmatter values, list membership, folder and presence of an ID", () => {
    const index = open();
    const paths = (filter: Parameters<NoteIndex["findNotes"]>[0]): string[] => index.findNotes(filter).map((n) => n.path);

    expect(paths({ frontmatter: { type: "project" } })).toEqual(["projects/Project Lantern.md"]);
    expect(paths({ frontmatter: { people: "Ada Example", domain: "work" } })).toEqual([
      "people/Ada Example.md",
      "projects/Project Lantern.md",
      "work/2026-01 Adopt Fixture Vaults.md",
    ]);
    expect(paths({ frontmatter: { type: ["decision", "observation"] } })).toEqual([
      "work/2026-01 Adopt Fixture Vaults.md",
      "work/Duplicate Id Note.md",
    ]);
    expect(paths({ frontmatter: { tags: "inbox" } })).toEqual(["inbox/Untyped Capture.md"]);
    expect(paths({ folder: "work", hasId: false })).toEqual(["work/Legacy Note Without Frontmatter.md"]);
    expect(paths({ frontmatter: { type: "person_note" }, folder: "work" })).toEqual([]);
  });
});
