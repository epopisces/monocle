import { cpSync, mkdirSync, mkdtempSync, renameSync, rmSync, statSync, unlinkSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DuplicateNoteIdError, InvalidNotePathError, openNoteIndex, type NoteIndex } from "@monocle/core";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let vault: string;
const opened: NoteIndex[] = [];

function open(options: Partial<Parameters<typeof openNoteIndex>[0]> = {}): NoteIndex {
  const index = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db"), ...options });
  opened.push(index);
  return index;
}

function write(rel: string, content: string): void {
  mkdirSync(dirname(join(vault, rel)), { recursive: true });
  writeFileSync(join(vault, rel), content);
}

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-index-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
});

afterEach(() => {
  for (const index of opened.splice(0)) index.close();
  rmSync(work, { recursive: true, force: true });
});

describe("note index", () => {
  it("finds a note by an exact token after reconciliation", () => {
    const index = open();
    index.reconcile();

    const hits = index.search("lanternfish-7731");
    expect(hits.map((h) => h.path)).toEqual(["projects/Project Lantern.md"]);
    expect(hits[0]).toMatchObject({ id: "fx-0002", title: "Project Lantern" });
  });

  it("reflects create, edit, move and delete after reconciliation", () => {
    const index = open();
    index.reconcile();

    write("inbox/New Idea.md", "---\nid: fx-0100\n---\nA brand new quokkaword idea.\n");
    expect(index.reconcile().added).toEqual(["inbox/New Idea.md"]);
    expect(index.search("quokkaword").map((h) => h.path)).toEqual(["inbox/New Idea.md"]);

    write("inbox/New Idea.md", "---\nid: fx-0100\n---\nRevised: now about wombatword instead.\n");
    expect(index.reconcile().updated).toEqual(["inbox/New Idea.md"]);
    expect(index.search("quokkaword")).toEqual([]);
    expect(index.search("wombatword").map((h) => h.path)).toEqual(["inbox/New Idea.md"]);

    mkdirSync(join(vault, "ideas"));
    renameSync(join(vault, "inbox/New Idea.md"), join(vault, "ideas/Renamed Idea.md"));
    expect(index.reconcile().moved).toEqual([{ from: "inbox/New Idea.md", to: "ideas/Renamed Idea.md" }]);
    expect(index.findById("fx-0100").map((n) => n.path)).toEqual(["ideas/Renamed Idea.md"]);
    expect(index.search("wombatword").map((h) => h.path)).toEqual(["ideas/Renamed Idea.md"]);

    rmSync(join(vault, "ideas/Renamed Idea.md"));
    expect(index.reconcile().deleted).toEqual(["ideas/Renamed Idea.md"]);
    expect(index.search("wombatword")).toEqual([]);
    expect(index.getNote("ideas/Renamed Idea.md")).toBeUndefined();
  });

  it("tracks a move of a note without an ID by its content hash", () => {
    const index = open();
    index.reconcile();
    renameSync(join(vault, "work/Legacy Note Without Frontmatter.md"), join(vault, "work/Legacy Moved.md"));

    const report = index.reconcile();
    expect(report.moved).toEqual([{ from: "work/Legacy Note Without Frontmatter.md", to: "work/Legacy Moved.md" }]);
    expect(report.added).toEqual([]);
    expect(report.deleted).toEqual([]);
  });

  it("recovers changes made while it was not running on the next startup reconciliation", () => {
    open().close();
    opened.length = 0;

    write("inbox/Offline Edit.md", "Written while Monocle was stopped: numbatword.\n");
    rmSync(join(vault, "Home.md"));

    const index = open();
    const report = index.reconcile();
    expect(report.added).toContain("inbox/Offline Edit.md");
    expect(index.search("numbatword").map((h) => h.path)).toEqual(["inbox/Offline Edit.md"]);
    expect(index.getNote("Home.md")).toBeUndefined();
  });

  it("only reports unchanged notes on a second reconciliation with no changes", () => {
    const index = open();
    const first = index.reconcile();
    const second = index.reconcile();
    expect(second).toEqual({ added: [], updated: [], moved: [], deleted: [], unchanged: first.added.length });
  });

  it("searches frontmatter values and requires every term to match", () => {
    const index = open();
    index.reconcile();

    expect(index.search("person_note").map((h) => h.path)).toEqual(["people/Ada Example.md"]);
    expect(index.search("inbox fixture").map((h) => h.path)).toEqual(["inbox/Untyped Capture.md"]);
    expect(index.search('lanternfish-7731 "unrelatedterm')).toEqual([]);
  });

  it("indexes Markdown only, skipping Obsidian config, attachments and excluded folders", () => {
    const index = open({ excludeFolders: ["templates"] });
    index.reconcile();

    expect(index.listNotes().map((n) => n.path)).toEqual([
      "Home.md",
      "inbox/Untyped Capture.md",
      "people/Ada Example.md",
      "projects/Project Lantern.md",
      "work/2026-01 Adopt Fixture Vaults.md",
      "work/Duplicate Id Note.md",
      "work/Legacy Note Without Frontmatter.md",
    ]);
  });

  it("produces the same index from a full rebuild as from incremental updates", () => {
    const incremental = open();
    incremental.reconcile();
    write("projects/Project Lantern.md", "---\nid: fx-0002\ntitle: Project Lantern\n---\nRewritten body.\n");
    renameSync(join(vault, "Home.md"), join(vault, "Start Here.md"));
    rmSync(join(vault, "inbox/Untyped Capture.md"));
    write("work/Fresh.md", "# Fresh\nfresh text\n");
    incremental.reconcile();

    const rebuilt = openNoteIndex({ vaultRoot: vault, dbPath: ":memory:" });
    opened.push(rebuilt);
    rebuilt.rebuild();

    expect(incremental.listNotes()).toEqual(rebuilt.listNotes());
    for (const query of ["Rewritten", "Fixture", "fresh", "Ada"]) {
      expect(incremental.search(query)).toEqual(rebuilt.search(query));
    }
  });

  it("diagnoses legacy duplicate IDs while still indexing both notes", () => {
    const index = open();
    index.reconcile();

    expect(index.duplicateIds()).toEqual([
      { id: "fx-0002", paths: ["projects/Project Lantern.md", "work/Duplicate Id Note.md"] },
    ]);
    expect(index.findById("fx-0002")).toHaveLength(2);
  });

  it("rejects a managed mutation that would reuse another note's ID", () => {
    const index = open();
    index.reconcile();

    expect(() => index.assertNoteIdAvailable("fx-0001", "inbox/Untyped Capture.md")).toThrow(DuplicateNoteIdError);
    expect(() => index.assertNoteIdAvailable("fx-0001", "people/Ada Example.md")).not.toThrow();
    expect(() => index.assertNoteIdAvailable("fx-9999", "inbox/Untyped Capture.md")).not.toThrow();
  });

  it("reads the persistent ID from a configurable frontmatter field and reindexes when it changes", () => {
    write("work/Uid Note.md", "---\nuid: u-42\nid: fx-0042\n---\nbody\n");
    const byId = open();
    byId.reconcile();
    expect(byId.getNote("work/Uid Note.md")?.id).toBe("fx-0042");
    byId.close();
    opened.length = 0;

    const byUid = open({ idField: "uid" });
    byUid.reconcile();
    expect(byUid.getNote("work/Uid Note.md")?.id).toBe("u-42");
    expect(byUid.getNote("people/Ada Example.md")?.id).toBeNull();
  });

  it("reindexes a single note on demand even when its mtime and size are unchanged", () => {
    const path = "projects/Project Lantern.md";
    const file = join(vault, path);
    utimesSync(file, 1_700_000_000, 1_700_000_000);
    const index = open();
    index.reconcile();
    writeFileSync(file, "x".repeat(statSync(file).size));
    utimesSync(file, 1_700_000_000, 1_700_000_000);
    expect(index.reconcile().updated).toEqual([]);

    expect(index.reindexNote(path)).toMatchObject({ updated: [path], added: [], deleted: [] });
    expect(index.search("lanternfish-7731")).toEqual([]);

    unlinkSync(file);
    expect(index.reindexNote(path)).toMatchObject({ deleted: [path] });
    expect(index.getNote(path)).toBeUndefined();
    expect(() => index.reindexNote(".obsidian/app.json")).toThrow(InvalidNotePathError);
    expect(() => index.reindexNote("projects\\Project Lantern.md")).toThrow(InvalidNotePathError);
    expect(() => index.reindexNote("/etc/notes.md")).toThrow(InvalidNotePathError);
  });
});