import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  CONVERSATIONS_PATH,
  EXECUTIONS_PATH,
  conversationPath,
  type Conversation,
  type ConversationSummary,
  type ExecutionEvent,
} from "@monocle/contracts";
import { startCompanion, type CompanionOptions, type RunningCompanion } from "@monocle/companion";
import type { ProviderAdapter } from "@monocle/cravat";

let running: RunningCompanion | undefined;
let dataDir: string;
beforeEach(() => {
  dataDir = mkdtempSync(join(tmpdir(), "monocle-conv-test-"));
});
afterEach(async () => {
  await running?.close();
  running = undefined;
  rmSync(dataDir, { recursive: true, force: true });
});

const echo: ProviderAdapter = {
  id: "fake",
  async *run(req) {
    yield { type: "delta", text: `you said: ${req.prompt}` };
  },
};

const start = (options: Partial<CompanionOptions> = {}) =>
  startCompanion({ port: 0, adapter: echo, dataDir, ...options }).then((c) => (running = c));

async function execute(body: Record<string, unknown>): Promise<ExecutionEvent[]> {
  const res = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status !== 200) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return (await res.text())
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as ExecutionEvent);
}

const startedOf = (events: ExecutionEvent[]) => events.find((e) => e.type === "started") as Extract<ExecutionEvent, { type: "started" }>;

async function getConversation(id: string): Promise<{ status: number; body: Conversation }> {
  const res = await fetch(new URL(conversationPath(id), running!.url));
  return { status: res.status, body: (await res.json()) as Conversation };
}

describe("companion conversations", () => {
  it("records an execution without a conversation in a new conversation", async () => {
    await start();
    const events = await execute({ prompt: "hello" });
    const started = startedOf(events);
    expect(started.conversationId).toEqual(expect.any(String));

    const { status, body } = await getConversation(started.conversationId!);
    expect(status).toBe(200);
    expect(body.title).toBe("hello");
    expect(body.executions).toEqual([
      expect.objectContaining({
        executionId: started.executionId,
        provider: "fake",
        prompt: "hello",
        response: "you said: hello",
        status: "completed",
      }),
    ]);
  });

  it("attaches later executions to the same conversation and lists it", async () => {
    await start();
    const first = startedOf(await execute({ prompt: "one" }));
    const second = startedOf(await execute({ prompt: "two", conversationId: first.conversationId }));
    expect(second.conversationId).toBe(first.conversationId);

    const { body } = await getConversation(first.conversationId!);
    expect(body.executions.map((e) => [e.prompt, e.response])).toEqual([
      ["one", "you said: one"],
      ["two", "you said: two"],
    ]);
    const list = (await (await fetch(new URL(CONVERSATIONS_PATH, running!.url))).json()) as { conversations: ConversationSummary[] };
    expect(list.conversations).toEqual([expect.objectContaining({ id: first.conversationId, title: "one", executionCount: 2 })]);
  });

  it("preserves conversation history across a companion restart", async () => {
    await start();
    const first = startedOf(await execute({ prompt: "before restart" }));
    await running!.close();

    await start();
    const { status, body } = await getConversation(first.conversationId!);
    expect(status).toBe(200);
    expect(body.executions).toEqual([expect.objectContaining({ prompt: "before restart", status: "completed" })]);

    const next = startedOf(await execute({ prompt: "after restart", conversationId: first.conversationId }));
    expect(next.instanceId).not.toBe(first.instanceId);
    expect((await getConversation(first.conversationId!)).body.executions).toHaveLength(2);
  });

  it("marks an execution that was running when the companion stopped as interrupted", async () => {
    const hang: ProviderAdapter = {
      id: "fake",
      async *run(_req, signal) {
        yield { type: "delta", text: "partial" };
        await new Promise<void>((r) => signal.addEventListener("abort", () => r(), { once: true }));
        // Simulate a provider that does not stop before the process dies.
        await new Promise(() => {});
      },
    };
    await start({ adapter: hang });
    const res = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "long" }),
    });
    const reader = res.body!.getReader();
    const first = JSON.parse(new TextDecoder().decode((await reader.read()).value).split("\n")[0]!) as ExecutionEvent;
    const conversationId = (first as Extract<ExecutionEvent, { type: "started" }>).conversationId!;
    await running!.close();

    await start();
    const { body } = await getConversation(conversationId);
    expect(body.executions).toEqual([
      expect.objectContaining({ status: "interrupted", error: expect.objectContaining({ code: "connection_lost" }) }),
    ]);
  });

  it("rejects executions for unknown conversations", async () => {
    await start();
    const res = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "x", conversationId: "00000000-0000-4000-8000-000000000000" }),
    });
    expect(res.status).toBe(404);
    expect(await res.json()).toMatchObject({ error: { code: "invalid_request", message: expect.stringMatching(/conversation/) } });
    expect((await getConversation("00000000-0000-4000-8000-000000000000")).status).toBe(404);
  });

  it("refuses a second concurrent execution in the same conversation", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const slow: ProviderAdapter = {
      id: "fake",
      async *run() {
        yield { type: "delta", text: "a" };
        await gate;
      },
    };
    await start({ adapter: slow });
    const res = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "first" }),
    });
    const reader = res.body!.getReader();
    const started = JSON.parse(new TextDecoder().decode((await reader.read()).value).split("\n")[0]!) as Extract<
      ExecutionEvent,
      { type: "started" }
    >;
    const busy = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "second", conversationId: started.conversationId }),
    });
    expect(busy.status).toBe(409);
    release();
    while (!(await reader.read()).done);
  });

  it("does not persist anything without a data directory", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    const first = startedOf(await execute({ prompt: "ephemeral" }));
    await running.close();
    running = await startCompanion({ port: 0, adapter: echo });
    expect((await getConversation(first.conversationId!)).status).toBe(404);
  });

  describe("provider sessions", () => {
    /** Reports a provider session per run: resumes the requested one, else starts `<id>-<n>`. */
    const sessions = (id: string) => {
      const resumed: (string | undefined)[] = [];
      const adapter: ProviderAdapter = {
        id,
        async *run(req, _signal, options) {
          resumed.push(options?.resumeSessionId);
          yield options?.resumeSessionId
            ? { type: "session", id: options.resumeSessionId, continuity: "resumed" }
            : { type: "session", id: `${id}-${resumed.length}`, continuity: "new" };
          yield { type: "delta", text: req.prompt };
        },
      };
      return { adapter, resumed };
    };

    it("continues the provider session of the previous execution, even after a restart", async () => {
      const { adapter, resumed } = sessions("p");
      await start({ adapter });
      const first = await execute({ prompt: "one" });
      const conversationId = startedOf(first).conversationId!;
      expect(first.at(-1)).toMatchObject({ type: "completed", providerSession: { id: "p-1", continuity: "new" } });
      await running!.close();

      await start({ adapter });
      const second = await execute({ prompt: "two", conversationId });
      expect(resumed).toEqual([undefined, "p-1"]);
      expect(second.at(-1)).toMatchObject({ providerSession: { id: "p-1", continuity: "resumed" } });
      const { body } = await getConversation(conversationId);
      expect(body.executions.map((e) => e.providerSession?.continuity)).toEqual(["new", "resumed"]);
    });

    it("reports earlier context as unavailable when the provider changed", async () => {
      await start({ adapter: sessions("a").adapter });
      const conversationId = startedOf(await execute({ prompt: "one" })).conversationId!;
      await running!.close();

      const b = sessions("b");
      await start({ adapter: b.adapter });
      const events = await execute({ prompt: "two", conversationId });
      expect(b.resumed).toEqual([undefined]);
      expect(events.at(-1)).toMatchObject({
        providerSession: { id: "b-1", continuity: "unavailable", reason: expect.stringMatching(/\ba\b.*\bb\b/) },
      });
      const { body } = await getConversation(conversationId);
      expect(body.executions[1]!.providerSession).toMatchObject({ continuity: "unavailable" });
    });

    it("reports earlier context as unavailable when no provider session was recorded", async () => {
      await start();
      const conversationId = startedOf(await execute({ prompt: "one" })).conversationId!;
      const events = await execute({ prompt: "two", conversationId });
      expect(events.at(-1)).toMatchObject({ providerSession: { continuity: "unavailable", reason: expect.any(String) } });
    });
  });
});
