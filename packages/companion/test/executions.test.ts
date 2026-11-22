import { afterEach, describe, expect, it } from "vitest";
import {
  EXECUTIONS_PATH,
  OBSIDIAN_ORIGIN,
  cancelExecutionPath,
  type ExecutionEvent,
} from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import type { ProviderAdapter } from "@monocle/cravat";

let running: RunningCompanion | undefined;
afterEach(async () => {
  await running?.close();
  running = undefined;
});

const echo: ProviderAdapter = {
  id: "fake",
  async *run(req) {
    yield { type: "delta", text: "you said: " };
    yield { type: "delta", text: req.prompt };
  },
};

function hanging(): ProviderAdapter & { aborted: Promise<void> } {
  let markAborted!: () => void;
  const aborted = new Promise<void>((r) => (markAborted = r));
  return {
    id: "fake",
    aborted,
    async *run(_req, signal) {
      yield { type: "delta", text: "thinking" };
      await new Promise<void>((r) => signal.addEventListener("abort", () => r(), { once: true }));
      markAborted();
    },
  };
}

const post = (path: string, body: unknown, headers: Record<string, string> = {}) =>
  fetch(new URL(path, running!.url), {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });

async function* lines(res: Response): AsyncGenerator<ExecutionEvent> {
  const decoder = new TextDecoder();
  let buf = "";
  for await (const chunk of res.body!) {
    buf += decoder.decode(chunk, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl);
      buf = buf.slice(nl + 1);
      if (line.trim()) yield JSON.parse(line) as ExecutionEvent;
    }
  }
}

describe("companion execution endpoint", () => {
  it("streams an execution as NDJSON events stamped with the companion instance", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    const res = await post(EXECUTIONS_PATH, { prompt: "hi" });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toMatch(/application\/x-ndjson/);
    const events: ExecutionEvent[] = [];
    for await (const e of lines(res)) events.push(e);
    expect(events.map((e) => e.type)).toEqual(["started", "delta", "delta", "completed"]);
    expect(events[0]).toMatchObject({ instanceId: running.health.instanceId, provider: "fake" });
    expect(events.at(-1)).toMatchObject({ type: "completed", text: "you said: hi" });
  });

  it("cancels a running execution by ID and ends the stream terminally", async () => {
    const adapter = hanging();
    running = await startCompanion({ port: 0, adapter });
    const res = await post(EXECUTIONS_PATH, { prompt: "long" });
    const types: string[] = [];
    for await (const e of lines(res)) {
      types.push(e.type);
      if (e.type === "delta") expect((await post(cancelExecutionPath(e.executionId), {})).status).toBe(202);
    }
    expect(types).toEqual(["started", "delta", "cancelled"]);
    await adapter.aborted;
  });

  it("returns 404 when cancelling an unknown or finished execution", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    expect((await post(cancelExecutionPath("nope"), {})).status).toBe(404);
  });

  it("cancels the execution when the client disconnects mid-stream", async () => {
    const adapter = hanging();
    running = await startCompanion({ port: 0, adapter });
    const controller = new AbortController();
    const res = await fetch(new URL(EXECUTIONS_PATH, running.url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "x" }),
      signal: controller.signal,
    });
    for await (const e of lines(res)) {
      if (e.type === "delta") break;
    }
    controller.abort();
    await adapter.aborted;
  });

  it("rejects invalid requests with an actionable invalid_request error", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    const empty = await post(EXECUTIONS_PATH, { prompt: "" });
    expect(empty.status).toBe(400);
    expect(await empty.json()).toMatchObject({ error: { code: "invalid_request", message: expect.stringMatching(/prompt/) } });

    const extra = await post(EXECUTIONS_PATH, { prompt: "x", model: "gpt" });
    expect(await extra.json()).toMatchObject({ error: { message: expect.stringMatching(/model/) } });

    expect((await post(EXECUTIONS_PATH, "{not json")).status).toBe(400);
  });

  it("requires a JSON content type so cross-site simple requests cannot start executions", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    expect((await post(EXECUTIONS_PATH, { prompt: "x" }, { "content-type": "text/plain" })).status).toBe(415);
  });

  it("rejects browser requests from origins other than Obsidian", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    expect((await post(EXECUTIONS_PATH, { prompt: "x" }, { origin: "https://evil.example" })).status).toBe(403);
  });

  it("allows Obsidian's renderer origin via CORS, including the preflight", async () => {
    running = await startCompanion({ port: 0, adapter: echo });
    const preflight = await fetch(new URL(EXECUTIONS_PATH, running.url), {
      method: "OPTIONS",
      headers: {
        origin: OBSIDIAN_ORIGIN,
        "access-control-request-method": "POST",
        "access-control-request-headers": "content-type",
      },
    });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get("access-control-allow-origin")).toBe(OBSIDIAN_ORIGIN);
    expect(preflight.headers.get("access-control-allow-headers")).toMatch(/content-type/i);

    const res = await post(EXECUTIONS_PATH, { prompt: "x" }, { origin: OBSIDIAN_ORIGIN });
    expect(res.headers.get("access-control-allow-origin")).toBe(OBSIDIAN_ORIGIN);
    await res.text();
  });
});
