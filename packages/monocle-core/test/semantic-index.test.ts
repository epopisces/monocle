import { cpSync, mkdtempSync, renameSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  createMemoryVectorStore,
  openNoteIndex,
  openSemanticIndex,
  type NoteIndex,
  type SemanticIndex,
  type SemanticIndexOptions,
} from "@monocle/core";
import { fakeProvider } from "./support/fake-embedding.js";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let vault: string;
let notes: NoteIndex;
const opened: SemanticIndex[] = [];

function openSemantic(options: Partial<SemanticIndexOptions> = {}): SemanticIndex {
  const index = openSemanticIndex({
    noteIndex: notes,
    provider: fakeProvider(),
    store: createMemoryVectorStore(),
    statePath: join(work, "semantic.db"),
    delayMs: 0,
    ...options,
  });
  opened.push(index);
  return index;
}

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-semantic-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
  notes = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db"), excludeFolders: ["templates"] });
});

afterEach(() => {
  for (const index of opened.splice(0)) index.close();
  notes.close();
  rmSync(work, { recursive: true, force: true });
});

describe("semantic index", () => {
  it("returns source passage IDs for notes queued from a reconcile report", async () => {
    writeFileSync(join(vault, "inbox/Ocean.md"), "---\nid: fx-0200\n---\n# Tides\n\nThe moon pulls the ocean tides.\n");
    const semantic = openSemantic();
    semantic.enqueue(notes.reconcile());
    await semantic.drain();

    const [hit] = await semantic.search("ocean tides moon");
    expect(hit).toMatchObject({ path: "inbox/Ocean.md", noteId: "fx-0200", heading: "Tides" });
    expect(hit!.passageId).toMatch(/^inbox\/Ocean\.md#[0-9a-f]{12}$/);
    expect(hit!.text).toContain("moon pulls");
    expect(semantic.status()).toMatchObject({ state: "idle", pendingNotes: 0, lastError: null });
  });

  it("re-embeds only changed passages, follows moves without re-embedding and drops deleted notes", async () => {
    const provider = fakeProvider();
    const store = createMemoryVectorStore();
    writeFileSync(join(vault, "inbox/Ocean.md"), "# Tides\n\nThe moon pulls tides.\n\n# Reefs\n\nCoral reefs grow slowly.\n");
    const semantic = openSemantic({ provider, store });
    semantic.enqueue(notes.reconcile());
    await semantic.drain();

    provider.embedded.length = 0;
    writeFileSync(join(vault, "inbox/Ocean.md"), "# Tides\n\nThe moon pulls tides.\n\n# Reefs\n\nCoral reefs bleach in heat.\n");
    semantic.enqueue(notes.reconcile());
    await semantic.drain();
    expect(provider.embedded).toEqual(["# Reefs\n\nCoral reefs bleach in heat."]);
    expect((await semantic.search("coral reefs", { limit: 5 })).some((h) => h.text.includes("grow slowly"))).toBe(false);

    provider.embedded.length = 0;
    renameSync(join(vault, "inbox/Ocean.md"), join(vault, "inbox/Sea.md"));
    semantic.enqueue(notes.reconcile());
    await semantic.drain();
    expect(provider.embedded).toEqual([]);
    const paths = (await semantic.search("moon tides", { limit: 20 })).map((h) => h.path);
    expect(paths).toContain("inbox/Sea.md");
    expect(paths).not.toContain("inbox/Ocean.md");

    const before = store.size;
    unlinkSync(join(vault, "inbox/Sea.md"));
    semantic.enqueue(notes.reconcile());
    await semantic.drain();
    expect(store.size).toBe(before - 2);
  });

  it("degrades without losing queued work when the provider is unavailable, then recovers", async () => {
    const provider = fakeProvider();
    const errors: string[] = [];
    const semantic = openSemantic({ provider, onError: (e) => errors.push(e.message) });
    provider.fail = true;
    semantic.enqueue(notes.reconcile());
    await semantic.drain();

    expect(semantic.status()).toMatchObject({ state: "degraded", lastError: "provider offline" });
    expect(errors).toEqual(["provider offline"]);
    await expect(semantic.search("lantern")).rejects.toThrow("provider offline");
    expect(notes.search("lanternfish-7731").map((h) => h.path)).toEqual(["projects/Project Lantern.md"]);

    provider.fail = false;
    await semantic.drain();
    expect(semantic.status()).toMatchObject({ state: "idle", lastError: null, indexedNotes: notes.listNotes().length });
  });

  it("rebuilds from Markdown when the embedding model changes", async () => {
    const store = createMemoryVectorStore();
    const first = openSemantic({ provider: fakeProvider("fake:bow@1"), store });
    notes.reconcile();
    await first.drain();
    expect(first.status().indexedNotes).toBe(notes.listNotes().length);
    first.close();

    const upgraded = fakeProvider("fake:bow@2");
    const second = openSemantic({ provider: upgraded, store });
    expect(second.status()).toMatchObject({
      state: "pending",
      indexedNotes: 0,
      rebuildReason: "embedding model changed (fake:bow@1 → fake:bow@2)",
    });
    await expect(second.search("lantern")).rejects.toThrow(/rebuilding/);
    await second.drain();
    expect(second.status()).toMatchObject({ state: "idle", rebuildReason: null, indexedNotes: notes.listNotes().length });
    expect(upgraded.embedded.length).toBe(second.status().indexedPassages);
  });

  it("catches up on reopen without re-embedding unchanged notes", async () => {
    const store = createMemoryVectorStore();
    const first = openSemantic({ store });
    notes.reconcile();
    await first.drain();
    first.close();

    writeFileSync(join(vault, "inbox/Offline.md"), "Written while Monocle was closed about narwhals.\n");
    notes.reconcile();
    const provider = fakeProvider();
    const second = openSemantic({ provider, store });
    expect(second.status().rebuildReason).toBeNull();
    await second.drain();
    expect(provider.embedded).toEqual(["Written while Monocle was closed about narwhals."]);
  });

  it("collapses an overflowing queue into one full resync", async () => {
    const semantic = openSemantic({ maxPending: 2 });
    await semantic.drain();
    for (const i of [1, 2, 3]) writeFileSync(join(vault, `inbox/Q${i}.md`), `Queued note ${i}.\n`);
    semantic.enqueue(notes.reconcile());
    expect(semantic.status()).toMatchObject({ pendingNotes: 0, fullResyncPending: true, state: "pending" });
    await semantic.drain();
    expect(semantic.status().indexedNotes).toBe(notes.listNotes().length);
  });

  it("runs queued work in the background after the configured delay", async () => {
    const semantic = openSemantic({ delayMs: 10 });
    semantic.enqueue(notes.reconcile());
    await new Promise((r) => setTimeout(r, 200));
    expect(semantic.status()).toMatchObject({ state: "idle", indexedNotes: notes.listNotes().length });
  });
});
