import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExecutionEvent } from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import { ProviderError, type ProviderAdapter } from "@monocle/cravat";
import { ExecutionClient, buildExecutionContext } from "@monocle/obsidian-plugin";

let companion: RunningCompanion | undefined;
afterEach(async () => {
  await companion?.close();
  companion = undefined;
});

async function collect(events: AsyncIterable<ExecutionEvent>): Promise<ExecutionEvent[]> {
  const out: ExecutionEvent[] = [];
  for await (const e of events) out.push(e);
  return out;
}

const echo: ProviderAdapter = {
  id: "fake",
  async *run(req) {
    for (const word of req.prompt.split(" ")) yield { type: "delta", text: `${word} ` };
  },
};

function hanging(): ProviderAdapter & { aborted: Promise<void> } {
  let markAborted!: () => void;
  const aborted = new Promise<void>((r) => (markAborted = r));
  return {
    id: "fake",
    aborted,
    async *run(_req, signal) {
      yield { type: "delta", text: "working" };
      await new Promise<void>((r) => signal.addEventListener("abort", () => r(), { once: true }));
      markAborted();
    },
  };
}

const client = () => new ExecutionClient({ endpoint: companion!.url, fetch: globalThis.fetch.bind(globalThis) });

describe("Obsidian plugin → companion → Cravat execution", () => {
  it("streams a prompt round-trip with the execution ID", async () => {
    companion = await startCompanion({ port: 0, adapter: echo });
    const handle = client().execute("summarise this note");
    const events = await collect(handle.events);
    expect(events.map((e) => e.type)).toEqual(["started", "delta", "delta", "delta", "completed"]);
    expect(handle.executionId).toBe(events[0]!.executionId);
    expect(events.at(-1)).toMatchObject({ type: "completed", text: "summarise this note " });
  });

  it("cancels a running execution, which stops provider work and completes terminally", async () => {
    const adapter = hanging();
    companion = await startCompanion({ port: 0, adapter });
    const handle = client().execute("long task");
    const types: string[] = [];
    for await (const e of handle.events) {
      types.push(e.type);
      if (e.type === "delta") await handle.cancel();
    }
    expect(types).toEqual(["started", "delta", "cancelled"]);
    await adapter.aborted;
  });

  it("cancels before the execution has started streaming", async () => {
    const adapter = hanging();
    companion = await startCompanion({ port: 0, adapter });
    const handle = client().execute("x");
    await handle.cancel();
    const events = await collect(handle.events);
    expect(events.at(-1)?.type).toBe("cancelled");
  });

  it("surfaces provider errors such as a failed Copilot launch", async () => {
    const adapter: ProviderAdapter = {
      id: "fake",
      // eslint-disable-next-line require-yield
      async *run() {
        throw new ProviderError("launch_failed", 'could not start Copilot CLI "copilot": spawn copilot ENOENT');
      },
    };
    companion = await startCompanion({ port: 0, adapter });
    const events = await collect(client().execute("x").events);
    expect(events.at(-1)).toMatchObject({ type: "failed", error: { code: "launch_failed", message: expect.stringMatching(/ENOENT/) } });
  });

  it("surfaces rejected requests as a failed event with the companion's reason", async () => {
    companion = await startCompanion({ port: 0, adapter: echo });
    const events = await collect(client().execute("   ").events);
    expect(events).toEqual([
      expect.objectContaining({ type: "failed", error: { code: "invalid_request", message: expect.stringMatching(/prompt/) } }),
    ]);
  });

  it("discovers the provider's settings and applies the chosen ones to an execution", async () => {
    const requests: unknown[] = [];
    const adapter: ProviderAdapter = {
      id: "fake",
      capabilities: async () => ({ model: { options: ["a", "b"] }, reasoningEffort: { options: ["low"] } }),
      async *run(req) {
        requests.push(req.settings);
        yield { type: "delta", text: "ok" };
      },
    };
    companion = await startCompanion({ port: 0, adapter });
    expect(await client().capabilities()).toEqual({
      provider: "fake",
      settings: { model: { options: ["a", "b"] }, reasoningEffort: { options: ["low"] } },
    });

    const events = await collect(client().execute("x", { model: "b", reasoningEffort: "low" }).events);
    expect(events[0]).toMatchObject({ type: "started", settings: { model: "b", reasoningEffort: "low" } });
    const rejected = await collect(client().execute("x", { contextWindow: "long_context" }).events);
    expect(rejected).toEqual([
      expect.objectContaining({ type: "failed", error: { code: "invalid_request", message: expect.stringMatching(/contextWindow/) } }),
    ]);
    expect(requests).toEqual([{ model: "b", reasoningEffort: "low" }]);
  });

  it("reports no capabilities when the companion cannot be reached", async () => {
    const offline = new ExecutionClient({ endpoint: "http://127.0.0.1:1", fetch: globalThis.fetch.bind(globalThis) });
    expect(await offline.capabilities()).toBeUndefined();
  });

  it("reports a lost connection when the companion is not running", async () => {
    const offline = new ExecutionClient({ endpoint: "http://127.0.0.1:1", fetch: globalThis.fetch.bind(globalThis) });
    const events = await collect(offline.execute("x").events);
    expect(events).toEqual([expect.objectContaining({ type: "failed", error: expect.objectContaining({ code: "connection_lost" }) })]);
  });

  it("reports a lost connection when the companion stops mid-execution", async () => {
    companion = await startCompanion({ port: 0, adapter: hanging() });
    const handle = client().execute("x");
    const types: string[] = [];
    for await (const e of handle.events) {
      types.push(e.type);
      if (e.type === "delta") void companion.close();
    }
    companion = undefined;
    expect(types.at(-1)).toBe("failed");
  });

  it("sends the panel's active-note context, without anything the user excluded", async () => {
    let seen = "";
    const capture: ProviderAdapter = {
      id: "fake",
      async *run(req) {
        seen = req.prompt;
        yield { type: "delta", text: "ok" };
      },
    };
    const vault = mkdtempSync(join(tmpdir(), "monocle-plugin-context-"));
    try {
      writeFileSync(join(vault, "Other.md"), "other-note-body");
      writeFileSync(join(vault, "Private.md"), "private-note-body");
      companion = await startCompanion({ port: 0, adapter: capture, vault: { root: vault } });
      const context = buildExecutionContext({
        activeNote: { path: "Current.md", content: "current-note-body", selection: "picked-text" },
        includeActiveNote: true,
        includeSelection: false,
        include: "Other.md\nPrivate.md\n",
        exclude: " Private.md ",
      });
      const events = await collect(client().execute("Summarise", undefined, context).events);
      expect(events.at(-1)?.type).toBe("completed");
      expect(seen).toContain("current-note-body");
      expect(seen).toContain("other-note-body");
      expect(seen).not.toContain("picked-text");
      expect(seen).not.toContain("private-note-body");
    } finally {
      rmSync(vault, { recursive: true, force: true });
    }
  });
});
