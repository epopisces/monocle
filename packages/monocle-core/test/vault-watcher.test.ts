import { cpSync, mkdtempSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { openNoteIndex, watchVault, type NoteIndex, type ReconcileReport, type VaultWatcher } from "@monocle/core";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let vault: string;
let index: NoteIndex;
let watcher: VaultWatcher | undefined;
let reports: ReconcileReport[];

function nextReport(predicate: (r: ReconcileReport) => boolean, timeoutMs = 5000): Promise<ReconcileReport> {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const poll = (): void => {
      const found = reports.find(predicate);
      if (found) resolve(found);
      else if (Date.now() - started > timeoutMs) reject(new Error("timed out waiting for reconcile"));
      else setTimeout(poll, 20);
    };
    poll();
  });
}

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-watch-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
  index = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db") });
  reports = [];
});

afterEach(() => {
  watcher?.close();
  watcher = undefined;
  index.close();
  rmSync(work, { recursive: true, force: true });
});

describe("vault watcher", () => {
  it("reconciles on start so changes missed while stopped are indexed", () => {
    watcher = watchVault(index, { debounceMs: 50, onReconcile: (r) => reports.push(r) });
    expect(reports).toHaveLength(1);
    expect(index.search("lanternfish-7731").map((h) => h.path)).toEqual(["projects/Project Lantern.md"]);
  });

  it("indexes a burst of file changes with one debounced reconciliation", async () => {
    watcher = watchVault(index, { debounceMs: 150, onReconcile: (r) => reports.push(r) });
    reports.length = 0;

    writeFileSync(join(vault, "inbox/Burst A.md"), "first capybaraword\n");
    writeFileSync(join(vault, "inbox/Burst B.md"), "second capybaraword\n");

    const report = await nextReport((r) => r.added.length > 0);
    expect(report.added.sort()).toEqual(["inbox/Burst A.md", "inbox/Burst B.md"]);
    expect(reports).toHaveLength(1);
    expect(index.search("capybaraword").map((h) => h.path).sort()).toEqual(["inbox/Burst A.md", "inbox/Burst B.md"]);
  });

  it("tracks notes when their folder is renamed", async () => {
    watcher = watchVault(index, { debounceMs: 100, onReconcile: (r) => reports.push(r) });
    reports.length = 0;

    renameSync(join(vault, "people"), join(vault, "contacts"));

    const report = await nextReport((r) => r.moved.length > 0);
    expect(report.moved).toEqual([{ from: "people/Ada Example.md", to: "contacts/Ada Example.md" }]);
    expect(index.findById("fx-0001").map((n) => n.path)).toEqual(["contacts/Ada Example.md"]);
  });

  it("ignores changes outside indexable Markdown", async () => {
    watcher = watchVault(index, { debounceMs: 50, onReconcile: (r) => reports.push(r) });
    reports.length = 0;

    writeFileSync(join(vault, ".obsidian/workspace.json"), "{}");
    writeFileSync(join(vault, "attachments/notes.txt"), "not markdown");
    await new Promise((r) => setTimeout(r, 300));
    expect(reports).toEqual([]);
  });
});
