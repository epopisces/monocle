import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { InvalidNotePathError, openNoteIndex, validateNote, type NoteIndex } from "@monocle/core";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let vault: string;
let index: NoteIndex;

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-validate-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
  index = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db"), excludeFolders: ["templates"] });
  index.reconcile();
});

afterEach(() => {
  index.close();
  rmSync(work, { recursive: true, force: true });
});

describe("validate note", () => {
  it("reports a duplicate ID as an error and an unresolved link as a located warning", () => {
    const result = validateNote(index, "projects/Project Lantern.md");
    expect(result.valid).toBe(false);
    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ severity: "error", code: "duplicate_id", message: expect.stringContaining("work/Duplicate Id Note.md") }),
        expect.objectContaining({ severity: "warning", code: "unresolved_link", line: 18, message: expect.stringContaining("[[Missing Note]]") }),
      ]),
    );
  });

  it("grandfathers a legacy note without an ID as a warning, not an error", () => {
    const result = validateNote(index, "work/Legacy Note Without Frontmatter.md");
    expect(result).toEqual({
      path: "work/Legacy Note Without Frontmatter.md",
      valid: true,
      issues: [expect.objectContaining({ severity: "warning", code: "missing_id" })],
    });
  });

  it("reports malformed frontmatter from the note as saved on disk", () => {
    writeFileSync(join(vault, "people/Ada Example.md"), "---\nid: [unclosed\n---\n# Ada\n");
    const result = validateNote(index, "people/Ada Example.md");
    expect(result.valid).toBe(false);
    expect(result.issues).toContainEqual(expect.objectContaining({ severity: "error", code: "frontmatter_invalid" }));
  });

  it("refuses paths that are not indexable notes and never changes the vault", () => {
    const before = readFileSync(join(vault, "projects/Project Lantern.md"), "utf8");
    expect(() => validateNote(index, "templates/Fixture Template.md")).toThrow(InvalidNotePathError);
    validateNote(index, "projects/Project Lantern.md");
    expect(readFileSync(join(vault, "projects/Project Lantern.md"), "utf8")).toBe(before);
  });
});
