import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { openIndexService, type IndexService } from "@monocle/core";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import { IndexHealthMonitor, type CompanionRequest, type ConnectionState, type IndexView } from "@monocle/obsidian-plugin";

const fetchRequest: CompanionRequest = async ({ url, method, body }) => {
  const res = await fetch(url, {
    method,
    ...(body !== undefined && { body: JSON.stringify(body), headers: { "content-type": "application/json" } }),
  });
  return { status: res.status, json: await res.json().catch(() => undefined) };
};

let work: string;
let vault: string;
let index: IndexService | undefined;
let companion: RunningCompanion | undefined;
const monitors: IndexHealthMonitor[] = [];

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), "monocle-plugin-index-"));
  vault = join(work, "vault");
  cpSync(fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url)), vault, { recursive: true });
});

afterEach(async () => {
  for (const m of monitors.splice(0)) m.stop();
  await companion?.close();
  companion = undefined;
  index?.close();
  index = undefined;
  rmSync(work, { recursive: true, force: true });
});

async function start(withIndex = true): Promise<ConnectionState> {
  if (withIndex) {
    index = openIndexService({ vaultRoot: vault, stateDir: join(work, "state"), excludeFolders: ["templates"], watch: false });
  }
  companion = await startCompanion({ port: 0, ...(index && { index }) });
  return { kind: "connected", endpoint: companion.url, health: companion.health };
}

function monitor(): IndexHealthMonitor {
  const m = new IndexHealthMonitor({ request: fetchRequest, intervalMs: 60_000 });
  monitors.push(m);
  return m;
}

describe("index health monitor", () => {
  it("is unavailable until connected, then reflects the companion's index health", async () => {
    const m = monitor();
    expect(m.view).toMatchObject({ level: "unavailable", label: "Index unavailable" });

    const views: IndexView[] = [];
    m.onChange((v) => views.push(v));
    await m.setConnection(await start());
    expect(m.view).toMatchObject({ level: "healthy", label: "Index healthy", health: { lexical: { notes: 7 } } });
    expect(views.at(-1)?.level).toBe("healthy");

    await m.setConnection({ kind: "disconnected", endpoint: companion!.url, error: "connection refused" });
    expect(m.view).toMatchObject({ level: "unavailable", detail: "Companion disconnected: connection refused" });
  });

  it("explains that the companion has no vault configured", async () => {
    const m = monitor();
    await m.setConnection(await start(false));
    expect(m.view).toMatchObject({ level: "unavailable", detail: expect.stringContaining("--vault") });
  });

  it("invokes reconcile, current-note reindex and rebuild on the companion", async () => {
    const m = monitor();
    await m.setConnection(await start());

    writeFileSync(join(vault, "inbox/New.md"), "hello\n");
    expect(await m.reconcile()).toEqual({ ok: true, message: "Reconciled: 1 added, 0 updated, 0 moved, 0 deleted" });
    expect(m.view.health?.lexical.notes).toBe(8);

    writeFileSync(join(vault, "inbox/New.md"), "edited\n");
    expect(await m.reindexNote("inbox/New.md")).toMatchObject({ ok: true, message: expect.stringContaining("1 updated") });
    expect(await m.reindexNote("attachments/README.txt")).toMatchObject({ ok: false, message: expect.stringContaining("not an indexable") });

    expect(await m.rebuild()).toMatchObject({ ok: true, message: expect.stringContaining("Rebuilt: 8 notes") });
  });
});
