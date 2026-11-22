import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExecutionEvent, ExecutionStartedEvent } from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import type { ProviderAdapter } from "@monocle/cravat";
import { ConversationClient, ExecutionClient } from "@monocle/obsidian-plugin";

let companion: RunningCompanion | undefined;
const dirs: string[] = [];
afterEach(async () => {
  await companion?.close();
  companion = undefined;
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

const echo: ProviderAdapter = {
  id: "fake",
  async *run(req) {
    yield { type: "delta", text: `echo: ${req.prompt}` };
  },
};

const fetchLike = globalThis.fetch.bind(globalThis);

async function run(prompt: string, conversationId?: string): Promise<ExecutionEvent[]> {
  const handle = new ExecutionClient({ endpoint: companion!.url, fetch: fetchLike }).execute(
    prompt,
    undefined,
    conversationId === undefined ? {} : { conversationId },
  );
  const out: ExecutionEvent[] = [];
  for await (const e of handle.events) out.push(e);
  return out;
}

describe("Obsidian plugin → companion conversations", () => {
  it("continues a conversation and reads its history back after a companion restart", async () => {
    const dataDir = mkdtempSync(join(tmpdir(), "monocle-plugin-conv-"));
    dirs.push(dataDir);
    companion = await startCompanion({ port: 0, adapter: echo, dataDir });
    const first = await run("hello");
    const conversationId = (first[0] as ExecutionStartedEvent).conversationId!;
    const second = await run("again", conversationId);
    expect((second[0] as ExecutionStartedEvent).conversationId).toBe(conversationId);
    await companion.close();

    companion = await startCompanion({ port: 0, adapter: echo, dataDir });
    const conversations = new ConversationClient({ endpoint: companion.url, fetch: fetchLike });
    expect(await conversations.list()).toEqual([expect.objectContaining({ id: conversationId, executionCount: 2 })]);
    const conversation = await conversations.get(conversationId);
    expect(conversation?.executions.map((e) => [e.prompt, e.response, e.status])).toEqual([
      ["hello", "echo: hello", "completed"],
      ["again", "echo: again", "completed"],
    ]);
  });

  it("returns undefined for a conversation the companion does not know", async () => {
    companion = await startCompanion({ port: 0, adapter: echo });
    const conversations = new ConversationClient({ endpoint: companion.url, fetch: fetchLike });
    expect(await conversations.get("00000000-0000-4000-8000-000000000000")).toBeUndefined();
  });
});
