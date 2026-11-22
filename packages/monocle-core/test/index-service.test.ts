import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  createMemoryVectorStore,
  openIndexService,
  openSemanticIndex,
  type IndexService,
  type IndexServiceOptions,
} from "@monocle/core";
import { fakeProvider } from "./support/fake-embedding.js";

const fixtureVault = fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url));

let work: string;
let vault: string;
const opened: IndexService[] = [];

function open(options: Partial<IndexServiceOptions> = {}): IndexService {
  const service = openIndexService({
    vaultRoot: vault,
    stateDir: join(work, "state"),
    excludeFolders: ["templates"],
    watch: false,
    ...options,
  });
  opened.push(service);
  return service;
}

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-index-service-"));
  vault = join(work, "vault");
  cpSync(fixtureVault, vault, { recursive: true });
});

afterEach(() => {
  for (const service of opened.splice(0)) service.close();
  rmSync(work, { recursive: true, force: true });
});

describe("index service health", () => {
  it("is healthy after startup reconciliation and lists vault content problems as warnings", () => {
    const health = open().health();

    expect(health.level).toBe("healthy");
    expect(health.lexical.notes).toBe(7);
    expect(health.lexical.lastReconciledAt).not.toBeNull();
    expect(health.lexical.lastChanges).toMatchObject({ added: 7 });
    expect(health.semantic.state).toBe("disabled");
    expect(health.errors).toEqual([]);
    expect(health.warnings).toContainEqual(expect.objectContaining({ kind: "duplicate-id" }));
  });

  it("is unavailable while the vault cannot be read and recovers after a successful reconcile", () => {
    const real = vault;
    vault = join(work, "missing-vault");
    const service = open({ vaultRoot: vault });
    expect(service.health()).toMatchObject({ level: "unavailable", lexical: { notes: 0, lastReconciledAt: null } });
    expect(service.health().errors).toEqual([expect.objectContaining({ source: "reconcile" })]);

    cpSync(real, vault, { recursive: true });
    expect(service.reconcile()).toMatchObject({ added: 7 });
    expect(service.health()).toMatchObject({ level: "healthy", errors: [] });
  });

  it("reports semantic queue depth while indexing and degrades when the embedding provider fails", async () => {
    const provider = fakeProvider();
    const service = open({
      semantic: ({ noteIndex, statePath, onError }) =>
        openSemanticIndex({ noteIndex, provider, store: createMemoryVectorStore(), statePath, delayMs: 60_000, onError }),
    });
    await service.semantic!.drain();
    expect(service.health()).toMatchObject({ level: "healthy", semantic: { state: "idle", indexedNotes: 7 } });

    writeFileSync(join(vault, "inbox/Ocean.md"), "# Tides\n\nThe moon pulls the ocean tides.\n");
    service.reconcile();
    expect(service.health()).toMatchObject({ level: "indexing", semantic: { state: "pending", pendingNotes: 1 } });

    provider.fail = true;
    await service.semantic!.drain();
    const degraded = service.health();
    expect(degraded).toMatchObject({ level: "degraded", semantic: { state: "degraded", pendingNotes: 1 } });
    expect(degraded.errors).toEqual([expect.objectContaining({ source: "semantic", message: "provider offline" })]);

    provider.fail = false;
    await service.semantic!.drain();
    expect(service.health()).toMatchObject({ level: "healthy", errors: [], semantic: { indexedNotes: 8 } });
  });

  it("reindexes the current note and rebuilds both indexes from Markdown on request", async () => {
    const service = open({
      semantic: ({ noteIndex, statePath, onError }) =>
        openSemanticIndex({ noteIndex, provider: fakeProvider(), store: createMemoryVectorStore(), statePath, delayMs: 60_000, onError }),
    });
    await service.semantic!.drain();

    writeFileSync(join(vault, "inbox/Untyped Capture.md"), "Now mentions a zebrafinch.\n");
    expect(service.reindexNote("inbox/Untyped Capture.md")).toMatchObject({ updated: 1 });
    expect(service.noteIndex.search("zebrafinch").map((h) => h.path)).toEqual(["inbox/Untyped Capture.md"]);
    expect(service.health().semantic).toMatchObject({ state: "pending", pendingNotes: 1 });
    expect(() => service.reindexNote("../outside.md")).toThrow();

    expect(service.rebuild()).toMatchObject({ added: 7 });
    expect(service.health()).toMatchObject({ level: "indexing", semantic: { rebuildReason: "manual rebuild" } });
    await service.semantic!.drain();
    expect(service.health()).toMatchObject({ level: "healthy", semantic: { indexedNotes: 7, rebuildReason: null } });
  });
});