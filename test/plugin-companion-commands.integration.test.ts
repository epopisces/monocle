import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { findCommand, parseChatInput, type ExecutionEvent } from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import { openIndexService, type IndexService } from "@monocle/core";
import type { ProviderAdapter } from "@monocle/cravat";
import { CommandRunner, ExecutionClient } from "@monocle/obsidian-plugin";

let work: string;
let index: IndexService | undefined;
let companion: RunningCompanion | undefined;
const prompts: string[] = [];
const requests: string[] = [];

const capture: ProviderAdapter = {
  id: "fake",
  async *run(req) {
    prompts.push(req.prompt);
    yield { type: "delta", text: "Ada Example owns it (projects/Project Lantern.md)" };
  },
};

afterEach(async () => {
  await companion?.close();
  index?.close();
  rmSync(work, { recursive: true, force: true });
  companion = index = undefined;
  prompts.length = 0;
  requests.length = 0;
});

async function runner(): Promise<CommandRunner> {
  work = mkdtempSync(join(tmpdir(), "monocle-plugin-commands-"));
  const vault = join(work, "vault");
  cpSync(fileURLToPath(new URL("../fixtures/vault/", import.meta.url)), vault, { recursive: true });
  index = openIndexService({ vaultRoot: vault, stateDir: join(work, "state"), excludeFolders: ["templates"], watch: false });
  companion = await startCompanion({ port: 0, adapter: capture, index, vault: { root: vault } });
  const fetch = (input: string, init: RequestInit) => {
    requests.push(new URL(input).pathname);
    return globalThis.fetch(input, init);
  };
  return new CommandRunner({ endpoint: companion.url, fetch, executions: new ExecutionClient({ endpoint: companion.url, fetch }) });
}

const lantern = { path: "projects/Project Lantern.md", content: "" };

async function collect(events: AsyncIterable<ExecutionEvent>): Promise<ExecutionEvent[]> {
  const out: ExecutionEvent[] = [];
  for await (const e of events) out.push(e);
  return out;
}

describe("Obsidian plugin commands → companion", () => {
  it("runs a palette /validate on the active note in Monocle, never starting an execution", async () => {
    const run = await runner();
    const outcome = await run.run({ command: findCommand("validate")!, argument: "", activeNote: lantern });
    expect(outcome).toMatchObject({ kind: "result", result: { command: "validate", data: { valid: false } } });
    expect(requests).toEqual(["/v1/commands"]);
    expect(prompts).toEqual([]);
  });

  it("runs a chat /search typed by the user", async () => {
    const run = await runner();
    const parsed = parseChatInput("/search lanternfish-7731");
    if (parsed.kind !== "command") throw new Error("expected a command");
    const outcome = await run.run({ command: parsed.command, argument: parsed.argument });
    expect(outcome.kind === "result" && outcome.result.markdown).toContain("projects/Project Lantern.md");
  });

  it("reports missing context before contacting the companion", async () => {
    const run = await runner();
    const outcome = await run.run({ command: findCommand("backlinks")!, argument: "" });
    expect(outcome).toEqual({
      kind: "error",
      error: { code: "missing_context", message: expect.stringMatching(/\/backlinks needs an active note/) },
    });
    expect(requests).toEqual([]);
  });

  it("sends /lookup of the selected text to Cravat as a grounded execution", async () => {
    const run = await runner();
    const outcome = await run.run({ command: findCommand("lookup")!, argument: "", activeNote: { ...lantern, selection: "Project Lantern" } });
    if (outcome.kind !== "execution") throw new Error(`expected an execution, got ${JSON.stringify(outcome)}`);
    const events = await collect(outcome.handle.events);
    expect(events.at(-1)).toMatchObject({ type: "completed" });
    expect(prompts[0]).toContain("Question: Project Lantern");
    expect(requests).toEqual(["/v1/executions"]);
  });
});
