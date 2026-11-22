import { describe, expect, it } from "vitest";
import type { ExecutionEvent } from "@monocle/contracts";
import { ExecutionManager, ProviderError, type ProviderAdapter } from "@monocle/cravat";

async function collect(events: AsyncIterable<ExecutionEvent>): Promise<ExecutionEvent[]> {
  const out: ExecutionEvent[] = [];
  for await (const e of events) out.push(e);
  return out;
}

const scripted = (chunks: string[]): ProviderAdapter => ({
  id: "fake",
  async *run() {
    for (const text of chunks) yield { type: "delta", text };
  },
});

/** Yields one chunk, then waits until aborted (a long-running provider). */
const hanging = (): ProviderAdapter & { aborted: boolean } => {
  const adapter = {
    id: "fake",
    aborted: false,
    async *run(_req: unknown, signal: AbortSignal) {
      yield { type: "delta" as const, text: "partial" };
      await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
      adapter.aborted = true;
    },
  };
  return adapter;
};

describe("Cravat execution manager", () => {
  it("streams provider output as ordered events ending in one completed event", async () => {
    const cravat = new ExecutionManager({ adapter: scripted(["Hel", "lo"]), instanceId: "inst-1" });
    const execution = cravat.start({ prompt: "hi" });
    const events = await collect(execution.events);

    expect(events.map((e) => e.type)).toEqual(["started", "delta", "delta", "completed"]);
    expect(events.every((e) => e.executionId === execution.id)).toBe(true);
    expect(events.map((e) => e.seq)).toEqual([0, 1, 2, 3]);
    expect(events[0]).toMatchObject({ type: "started", provider: "fake", instanceId: "inst-1" });
    expect(events[3]).toMatchObject({ type: "completed", text: "Hello" });
  });

  it("gives each execution a distinct identity", () => {
    const cravat = new ExecutionManager({ adapter: scripted([]), instanceId: "i" });
    expect(cravat.start({ prompt: "a" }).id).not.toBe(cravat.start({ prompt: "b" }).id);
  });

  it("reports provider errors as a terminal failed event with the provider's message", async () => {
    const adapter: ProviderAdapter = {
      id: "fake",
      // eslint-disable-next-line require-yield
      async *run() {
        throw new ProviderError("launch_failed", "copilot not found");
      },
    };
    const events = await collect(new ExecutionManager({ adapter, instanceId: "i" }).start({ prompt: "x" }).events);
    expect(events.at(-1)).toMatchObject({ type: "failed", error: { code: "launch_failed", message: "copilot not found" } });
  });

  it("reports unexpected adapter exceptions as provider errors", async () => {
    const adapter: ProviderAdapter = {
      id: "fake",
      async *run() {
        yield { type: "delta", text: "a" };
        throw new Error("boom");
      },
    };
    const events = await collect(new ExecutionManager({ adapter, instanceId: "i" }).start({ prompt: "x" }).events);
    expect(events.at(-1)).toMatchObject({ type: "failed", error: { code: "provider_error", message: "boom" } });
  });

  it("cancels a running execution: the provider is aborted and the stream ends with cancelled", async () => {
    const adapter = hanging();
    const cravat = new ExecutionManager({ adapter, instanceId: "i" });
    const execution = cravat.start({ prompt: "x" });
    const seen: ExecutionEvent[] = [];
    for await (const e of execution.events) {
      seen.push(e);
      if (e.type === "delta") expect(cravat.cancel(execution.id)).toBe(true);
    }
    expect(seen.map((e) => e.type)).toEqual(["started", "delta", "cancelled"]);
    expect(adapter.aborted).toBe(true);
  });

  it("emits exactly one terminal event even if cancel is requested after completion", async () => {
    const cravat = new ExecutionManager({ adapter: scripted(["a"]), instanceId: "i" });
    const execution = cravat.start({ prompt: "x" });
    const events = await collect(execution.events);
    expect(cravat.cancel(execution.id)).toBe(false);
    expect(events.filter((e) => ["completed", "failed", "cancelled"].includes(e.type))).toHaveLength(1);
  });

  it("returns false when cancelling an unknown execution", () => {
    expect(new ExecutionManager({ adapter: scripted([]), instanceId: "i" }).cancel("nope")).toBe(false);
  });

  it("forces a cancelled terminal state when the provider ignores the abort", async () => {
    const stubborn: ProviderAdapter = {
      id: "fake",
      async *run() {
        yield { type: "delta", text: "a" };
        await new Promise(() => {});
      },
    };
    const cravat = new ExecutionManager({ adapter: stubborn, instanceId: "i", cancelGraceMs: 20 });
    const execution = cravat.start({ prompt: "x" });
    const types: string[] = [];
    for await (const e of execution.events) {
      types.push(e.type);
      if (e.type === "delta") cravat.cancel(execution.id);
    }
    expect(types).toEqual(["started", "delta", "cancelled"]);
  });
});
