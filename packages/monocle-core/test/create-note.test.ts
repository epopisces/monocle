import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ProposalStore, commandNoteRenderer, createNote, noteCreationProposal, openNoteIndex, planNote, type NoteIndex } from "@monocle/core";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));
const now = new Date(2026, 10, 22, 9, 5, 0);

let work: string;
let vault: string;
let index: NoteIndex;

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-create-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
  index = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db"), excludeFolders: ["templates"] });
  index.reconcile();
});

afterEach(() => {
  index.close();
  rmSync(work, { recursive: true, force: true });
});

describe("create note", () => {
  it("writes the vault's template into the new-note folder with the next ID in the vault's sequence", () => {
    const created = createNote(index, { title: "Harbor Survey", template: "Fixture Template", fields: { type: "capture" } }, { now });

    expect(created.path).toBe("inbox/Harbor Survey.md");
    expect(created.id).toBe("fx-0004");
    expect(readFileSync(join(vault, "inbox/Harbor Survey.md"), "utf8")).toBe(
      ['---', 'id: "fx-0004"', 'type: "capture"', 'title: "Harbor Survey"', 'created: "2026-11-22"', '---', '# Harbor Survey', ''].join("\n"),
    );
    expect(created.validation).toEqual({ path: "inbox/Harbor Survey.md", valid: true, issues: [] });
    expect(index.findById("fx-0004").map((n) => n.path)).toEqual(["inbox/Harbor Survey.md"]);
  });

  it("refuses to overwrite an existing note and leaves it untouched", () => {
    const before = readFileSync(join(vault, "inbox/Untyped Capture.md"), "utf8");
    const attempt = () => createNote(index, { title: "Untyped Capture", template: "Fixture Template", fields: { type: "capture" } }, { now });

    expect(attempt).toThrow(expect.objectContaining({ code: "path_exists", message: expect.stringContaining("inbox/Untyped Capture.md already exists") }));
    expect(readFileSync(join(vault, "inbox/Untyped Capture.md"), "utf8")).toBe(before);
  });

  it("does not reuse an ID taken by a note written since the index last reconciled", () => {
    writeFileSync(join(vault, "work/Synced Elsewhere.md"), "---\nid: fx-0004\n---\n# Synced Elsewhere\n");

    const created = createNote(index, { title: "Harbor Survey", template: "Fixture Template", fields: { type: "capture" } }, { now });

    expect(created.id).toBe("fx-0005");
    expect(created.validation.valid).toBe(true);
  });

  it("names the available templates when the requested one does not exist", () => {
    const attempt = () => createNote(index, { title: "Harbor Survey", template: "Meeting" }, { now });

    expect(attempt).toThrow(expect.objectContaining({ code: "template_not_found", message: 'No template "Meeting" in templates/. Available: Fixture Template' }));
    expect(existsSync(join(vault, "inbox/Harbor Survey.md"))).toBe(false);
  });

  it("refuses to write a note with template placeholders nobody filled in", () => {
    const attempt = () => createNote(index, { title: "Harbor Survey", template: "Fixture Template" }, { now });

    expect(attempt).toThrow(
      expect.objectContaining({ code: "unfilled_placeholder", message: expect.stringContaining("{{type}}") }),
    );
    expect(existsSync(join(vault, "inbox/Harbor Survey.md"))).toBe(false);
  });

  it.each([
    ["No Id", "---\ntitle: \"{{title}}\"\n---\n", "missing_id", 'Template "No Id" does not set id'],
    ["Pinned Id", "---\nid: fx-0001\n---\n", "duplicate_id", 'ID "fx-0001" is already used by: people/Ada Example.md'],
    ["Broken", "---\nid: \"{{id}}\"\ntags: [unclosed\n---\n", "frontmatter_invalid", 'Template "Broken" produced invalid frontmatter'],
  ])("rejects a template whose note would break ID or schema integrity (%s)", (name, template, code, message) => {
    writeFileSync(join(vault, `templates/${name}.md`), template);

    const attempt = () => createNote(index, { title: "Harbor Survey", template: name }, { now });

    expect(attempt).toThrow(expect.objectContaining({ code, message: expect.stringContaining(message) }));
    expect(existsSync(join(vault, "inbox/Harbor Survey.md"))).toBe(false);
  });

  it("keeps quoted frontmatter valid when a title or field contains quotes", () => {
    const created = createNote(index, { title: "Ada's Lantern Review", template: "Fixture Template", fields: { type: 'a "b" \\c' } }, { now });

    expect(created.validation.valid).toBe(true);
    expect(index.getNote(created.path)!.frontmatter).toMatchObject({ title: "Ada's Lantern Review", type: 'a "b" \\c' });
  });

  it.each([
    ["title", { title: "Q3: plan?" }, "invalid_title", 'cannot contain any of * " \\ / < > : | ? # ^ [ ]'],
    ["title", { title: "  " }, "invalid_title", "Title is empty"],
    ["folder", { title: "Harbor Survey", folder: "../outside" }, "invalid_folder", 'Folder "../outside" is not inside the vault'],
    ["folder", { title: "Harbor Survey", folder: ".obsidian" }, "invalid_folder", 'Folder ".obsidian" is not an indexed vault folder'],
    ["template", { title: "Harbor Survey", template: "../people/Ada Example" }, "template_not_found", 'No template "../people/Ada Example"'],
  ])("rejects an unusable %s before touching the vault", (_kind, request, code, message) => {
    const attempt = () => createNote(index, { template: "Fixture Template", fields: { type: "capture" }, ...request }, { now });

    expect(attempt).toThrow(expect.objectContaining({ code, message: expect.stringContaining(message) }));
    expect(existsSync(join(work, "outside"))).toBe(false);
  });

  it("treats a title that differs only in case from an existing note as taken", () => {
    const attempt = () => createNote(index, { title: "untyped capture", template: "Fixture Template", fields: { type: "capture" } }, { now });

    expect(attempt).toThrow(expect.objectContaining({ code: "path_exists", message: expect.stringContaining("inbox/Untyped Capture.md") }));
  });

  it("uses a timestamp ID (Obsidian's unique-note format) in a vault with no numbered IDs, in a configured ID field", () => {
    const uidVault = join(work, "uid-vault");
    cpSync(join(vault, ".obsidian"), join(uidVault, ".obsidian"), { recursive: true });
    mkdirSync(join(uidVault, "templates"), { recursive: true });
    writeFileSync(join(uidVault, "templates/Plain.md"), '---\nuid: "{{uid}}"\n---\n');
    const uidIndex = openNoteIndex({ vaultRoot: uidVault, dbPath: ":memory:", idField: "uid", excludeFolders: ["templates"] });
    try {
      const first = createNote(uidIndex, { title: "First", template: "Plain" }, { now, idField: "uid" });
      const second = createNote(uidIndex, { title: "Second", template: "Plain" }, { now, idField: "uid" });

      expect([first.id, second.id]).toEqual(["202611220905", "202611220905-1"]);
      expect(second.validation.valid).toBe(true);
    } finally {
      uidIndex.close();
    }
  });

  it("plans a note without writing it, so a later proposal can carry the exact content", () => {
    const plan = planNote(index, { title: "Harbor Survey", template: "Fixture Template", fields: { type: "capture" } }, { now });

    expect(plan).toMatchObject({ path: "inbox/Harbor Survey.md", id: "fx-0004", idField: "id", renderer: "vault-template" });
    expect(plan.content).toContain('id: "fx-0004"');
    expect(existsSync(join(vault, "inbox/Harbor Survey.md"))).toBe(false);
  });
});

describe("external note renderer (Curator create-obsidian-note boundary)", () => {
  const fakeCurator = fileURLToPath(new URL("./fixtures/fake-curator.mjs", import.meta.url));

  it("writes what the script renders while Monocle still assigns the path and ID", () => {
    const renderer = commandNoteRenderer({ command: process.execPath, args: [fakeCurator] });

    const created = createNote(index, { title: "Harbor Survey", template: "capture", fields: { domain: "work" } }, { now, renderer });

    expect(created).toMatchObject({ path: "inbox/Harbor Survey.md", id: "fx-0004", validation: { valid: true } });
    expect(created.content).toBe(
      ['---', 'id: fx-0004', 'type: capture', 'title: Harbor Survey', 'domain: work', `created: ${now.toISOString()}`, '---', '# Harbor Survey', ''].join("\n"),
    );
  });

  it.each([
    ["fail", "renderer_failed", "fake-curator: template capture is not installed"],
    ["no-id", "missing_id", "does not set id"],
  ])("reports a script that %s as an actionable error and writes nothing", (mode, code, message) => {
    const renderer = commandNoteRenderer({ command: process.execPath, args: [fakeCurator, `--mode=${mode}`] });

    const attempt = () => createNote(index, { title: "Harbor Survey", template: "capture" }, { now, renderer });

    expect(attempt).toThrow(expect.objectContaining({ code, message: expect.stringContaining(message) }));
    expect(existsSync(join(vault, "inbox/Harbor Survey.md"))).toBe(false);
  });

  it("can hold a planned note as a pending create proposal without touching the vault", async () => {
    const plan = planNote(index, { title: "Harbor Survey", template: "Fixture Template", fields: { type: "capture" } }, { now });
    const store = await ProposalStore.open();

    const change = store.propose(noteCreationProposal(plan, { executionId: "exec-1", conversationId: "conv-1" }));

    expect(change).toMatchObject({
      operation: "create",
      path: "inbox/Harbor Survey.md",
      noteId: "fx-0004",
      base: { hash: null },
      patch: { format: "replace", content: plan.content },
      status: "pending",
    });
    expect(existsSync(join(vault, "inbox/Harbor Survey.md"))).toBe(false);
  });
});
