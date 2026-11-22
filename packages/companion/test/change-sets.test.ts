import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CHANGE_SETS_PATH, changeSetPath, type ChangeSet, type ChangeSetListResponse } from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import type { ProviderAdapter } from "@monocle/cravat";

let running: RunningCompanion | undefined;
let dataDir: string;
beforeEach(() => {
  dataDir = mkdtempSync(join(tmpdir(), "monocle-changes-test-"));
});
afterEach(async () => {
  await running?.close();
  running = undefined;
  rmSync(dataDir, { recursive: true, force: true });
});

const idle: ProviderAdapter = { id: "fake", async *run() {} };
const start = () => startCompanion({ port: 0, adapter: idle, dataDir }).then((c) => (running = c));

async function get<T>(path: string): Promise<{ status: number; body: T }> {
  const res = await fetch(new URL(path, running!.url));
  return { status: res.status, body: (await res.json()) as T };
}

const edit = (executionId: string, path: string) =>
  running!.proposals.propose({
    executionId,
    conversationId: "conv-1",
    operation: "modify",
    path,
    base: { content: "# Before\n" },
    patch: { format: "replace", content: "# After\n" },
    risk: "high",
  });

describe("companion change sets", () => {
  it("lists one execution's pending changes, isolated from other executions, across a restart", async () => {
    await start();
    const a = edit("exec-1", "notes/A.md");
    const b = edit("exec-1", "notes/B.md");
    edit("exec-2", "notes/C.md");
    await running!.close();
    running = undefined;

    await start();
    const listed = await get<ChangeSetListResponse>(`${CHANGE_SETS_PATH}?executionId=exec-1`);
    expect(listed.status).toBe(200);
    expect(listed.body.changeSets).toHaveLength(1);
    expect(listed.body.changeSets[0]).toMatchObject({ executionId: "exec-1", conversationId: "conv-1", counts: { pending: 2 } });

    const set = await get<ChangeSet>(changeSetPath(listed.body.changeSets[0]!.id));
    expect(set.body.changes.map((c) => [c.id, c.path, c.status])).toEqual([
      [a.id, "notes/A.md", "pending"],
      [b.id, "notes/B.md", "pending"],
    ]);

    const all = await get<ChangeSetListResponse>(`${CHANGE_SETS_PATH}?conversationId=conv-1`);
    expect(all.body.changeSets.map((s) => s.executionId).sort()).toEqual(["exec-1", "exec-2"]);
    expect((await get(changeSetPath("missing"))).status).toBe(404);
  });
});
