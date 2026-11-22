import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  createMemoryVectorStore,
  createRetriever,
  openNoteIndex,
  openSemanticIndex,
  type NoteIndex,
  type SemanticIndex,
} from "@monocle/core";
import { fakeProvider } from "./support/fake-embedding.js";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let notes: NoteIndex;
let semantic: SemanticIndex;
let provider: ReturnType<typeof fakeProvider>;

beforeEach(async () => {
  work = mkdtempSync(join(tmpdir(), "monocle-retrieval-"));
  const vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
  writeFileSync(join(vault, "inbox/Glow.md"), "# Bioluminescence\n\nDeep sea creatures glow to lure prey.\n");
  notes = openNoteIndex({ vaultRoot: vault, dbPath: join(work, "index.db"), excludeFolders: ["templates"] });
  provider = fakeProvider();
  semantic = openSemanticIndex({
    noteIndex: notes,
    provider,
    store: createMemoryVectorStore(),
    statePath: join(work, "semantic.db"),
    delayMs: 0,
  });
  notes.reconcile();
  await semantic.drain();
});

afterEach(() => {
  semantic.close();
  notes.close();
  rmSync(work, { recursive: true, force: true });
});

describe("retriever", () => {
  it("fuses lexical and semantic hits per note, citing source passages", async () => {
    const result = await createRetriever({ noteIndex: notes, semantic }).search("creatures glow");
    expect(result.semantic).toEqual({ status: "ok", error: null });
    const [top] = result.hits;
    expect(top).toMatchObject({ path: "inbox/Glow.md", sources: ["lexical", "semantic"] });
    expect(top!.snippet).toContain("[creatures]");
    expect(top!.passages[0]!.passageId).toMatch(/^inbox\/Glow\.md#/);
    expect(top!.score).toBeGreaterThan(result.hits[1]?.score ?? 0);
  });

  it("finds conceptual matches the lexical index misses", async () => {
    const lexicalOnly = await createRetriever({ noteIndex: notes }).search("glow prey lure creatures sea deep zzz");
    expect(lexicalOnly.hits).toEqual([]);
    const hybrid = await createRetriever({ noteIndex: notes, semantic }).search("glow prey lure creatures sea deep zzz");
    expect(hybrid.hits[0]).toMatchObject({ path: "inbox/Glow.md", sources: ["semantic"], snippet: null });
  });

  it("falls back to lexical results when semantic retrieval is disabled or unavailable", async () => {
    const disabled = await createRetriever({ noteIndex: notes }).search("lanternfish-7731");
    expect(disabled.semantic).toEqual({ status: "disabled", error: null });
    expect(disabled.hits.map((h) => [h.path, h.sources])).toEqual([["projects/Project Lantern.md", ["lexical"]]]);

    provider.fail = true;
    const down = await createRetriever({ noteIndex: notes, semantic }).search("lanternfish-7731", { mode: "semantic" });
    expect(down.semantic).toEqual({ status: "unavailable", error: "provider offline" });
    expect(down.hits.map((h) => h.path)).toEqual(["projects/Project Lantern.md"]);
  });

  it("skips the embedding call entirely in lexical mode", async () => {
    provider.embedded.length = 0;
    const result = await createRetriever({ noteIndex: notes, semantic }).search("glow", { mode: "lexical" });
    expect(result.semantic.status).toBe("skipped");
    expect(provider.embedded).toEqual([]);
  });
});
