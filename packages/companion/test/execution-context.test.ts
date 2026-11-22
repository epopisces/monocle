import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  conversationPath,
  EXECUTIONS_PATH,
  type Conversation,
  type ExecutionEvent,
  type ExecutionRequest,
} from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import { CopilotCliAdapter, type ExecutionToolset, type ProviderAdapter } from "@monocle/cravat";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const fakeCli = join(repoRoot, "packages", "cravat", "test", "fixtures", "fake-copilot.mjs");
let work: string;
let vault: string;
let running: RunningCompanion | undefined;

beforeAll(() => {
  // The agent's tools run as the built Monocle vault MCP server.
  execFileSync(process.execPath, [join(repoRoot, "node_modules", "typescript", "bin", "tsc"), "-b", "packages/monocle-core"], {
    cwd: repoRoot,
    stdio: "inherit",
  });
  work = mkdtempSync(join(tmpdir(), "monocle-exec-context-"));
  vault = join(work, "vault");
  cpSync(join(repoRoot, "fixtures", "vault"), vault, { recursive: true });
}, 60_000);
afterAll(() => rmSync(work, { recursive: true, force: true }));
afterEach(async () => {
  await running?.close();
  running = undefined;
});

function capturing(): ProviderAdapter & { calls: { request: ExecutionRequest; tools?: ExecutionToolset }[] } {
  const calls: { request: ExecutionRequest; tools?: ExecutionToolset }[] = [];
  return {
    id: "capture",
    calls,
    async *run(request, _signal, options) {
      const tools = options?.tools;
      calls.push({ request, tools });
      yield { type: "delta", text: "ok" };
    },
  };
}

async function execute(body: unknown): Promise<{ status: number; events: ExecutionEvent[]; json?: unknown }> {
  const res = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (res.status !== 200) return { status: res.status, events: [], json: JSON.parse(text) };
  return { status: 200, events: text.split("\n").filter(Boolean).map((l) => JSON.parse(l) as ExecutionEvent) };
}

const completedText = (events: ExecutionEvent[]) => {
  const last = events.at(-1);
  if (last?.type !== "completed") throw new Error(`execution did not complete: ${JSON.stringify(last)}`);
  return last.text;
};

function vaultHashes(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const entry of readdirSync(root, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const full = join(entry.parentPath, entry.name);
    out[full.slice(root.length)] = createHash("sha256").update(readFileSync(full)).digest("hex");
  }
  return out;
}

describe("execution context", () => {
  it("sends the active note and selection to the provider, with read-only vault tools", async () => {
    const adapter = capturing();
    running = await startCompanion({ port: 0, adapter, vault: { root: vault } });
    const { events } = await execute({
      prompt: "Summarize this note",
      context: { activeNote: { path: "people/Ada Example.md", content: "Ada leads Lantern (unsaved edit).", selection: "Ada leads" } },
    });
    expect(completedText(events)).toBe("ok");
    const [call] = adapter.calls;
    expect(call!.request.prompt).toContain("Summarize this note");
    expect(call!.request.prompt).toContain("people/Ada Example.md");
    expect(call!.request.prompt).toContain("Ada leads Lantern (unsaved edit).");
    expect(call!.request.prompt).toContain("Selected text");
    expect(call!.request).not.toHaveProperty("context");
    expect(call!.tools?.mcpServers.map((s) => [s.name, s.tools])).toEqual([
      ["monocle_vault", ["read_note", "list_notes", "search_notes"]],
    ]);
  });

  it("reads the active note from the vault when the client sends only its path, and adds included notes", async () => {
    const adapter = capturing();
    running = await startCompanion({ port: 0, adapter, vault: { root: vault } });
    await execute({
      prompt: "q",
      context: { activeNote: { path: "people/Ada Example.md" }, include: ["projects/Project Lantern.md"] },
    });
    const prompt = adapter.calls[0]!.request.prompt;
    expect(prompt).toContain("Synthetic person. Leads [[Project Lantern]]");
    expect(prompt).toContain("lanternfish-7731");
  });

  it("does not transmit excluded context, and keeps it out of the agent's tools", async () => {
    const adapter = capturing();
    running = await startCompanion({ port: 0, adapter, vault: { root: vault } });
    await execute({
      prompt: "q",
      context: {
        activeNote: { path: "projects/Project Lantern.md", content: "secret-active", selection: "secret-sel" },
        include: ["people/Ada Example.md", "work/2026-01 Adopt Fixture Vaults.md"],
        exclude: ["projects", "people/Ada Example.md"],
      },
    });
    const { request, tools } = adapter.calls[0]!;
    expect(request.prompt).not.toMatch(/secret-active|secret-sel|lanternfish|Project Lantern\.md|Synthetic person/);
    expect(request.prompt).toContain("2026-01 Adopt Fixture Vaults.md");
    const args = tools!.mcpServers[0]!.args;
    expect(args).toEqual(expect.arrayContaining(["--exclude=projects", "--exclude=people/Ada Example.md"]));
  });

  it("records what context was shared on the conversation, as references only", async () => {
    running = await startCompanion({ port: 0, adapter: capturing(), vault: { root: vault } });
    const { events } = await execute({
      prompt: "q",
      context: {
        activeNote: { path: "people/Ada Example.md", content: "secret-body", selection: "secret-sel" },
        include: ["projects/Project Lantern.md", "work/2026-01 Adopt Fixture Vaults.md"],
        exclude: ["projects"],
      },
    });
    const started = events[0];
    if (started?.type !== "started") throw new Error("no started event");
    const res = await fetch(new URL(conversationPath(started.conversationId!), running.url));
    const conversation = (await res.json()) as Conversation;
    const recorded = conversation.executions[0]!.contextReferences;
    expect(recorded).toEqual([
      { kind: "note", path: "people/Ada Example.md", label: "Active note" },
      { kind: "selection", path: "people/Ada Example.md", label: "Selection" },
      { kind: "note", path: "work/2026-01 Adopt Fixture Vaults.md", label: "Included note" },
    ]);
    expect(JSON.stringify(conversation)).not.toMatch(/secret-body|secret-sel|Project Lantern/);
  });

  it("rejects included paths that escape the vault, and includes without a configured vault", async () => {
    running = await startCompanion({ port: 0, adapter: capturing(), vault: { root: vault } });
    const escape = await execute({ prompt: "q", context: { include: ["../outside.md"] } });
    expect(escape.status).toBe(400);
    expect(escape.json).toMatchObject({ error: { code: "invalid_request" } });
    await running.close();

    running = await startCompanion({ port: 0, adapter: capturing() });
    const noVault = await execute({ prompt: "q", context: { include: ["Home.md"] } });
    expect(noVault.status).toBe(400);
  });

  it("gives no tools when no vault is configured", async () => {
    const adapter = capturing();
    running = await startCompanion({ port: 0, adapter });
    await execute({ prompt: "q", context: { activeNote: { path: "a.md", content: "hello" } } });
    expect(adapter.calls[0]!.request.prompt).toContain("hello");
    expect(adapter.calls[0]!.tools).toBeUndefined();
  });

  it("lets the agent read another allowed note through the Copilot adapter, but not escape, excluded notes or write", async () => {
    const before = vaultHashes(vault);
    running = await startCompanion({
      port: 0,
      adapter: new CopilotCliAdapter({ command: process.execPath, args: [fakeCli], env: { FAKE_COPILOT_MODE: "stream" } }),
      vault: { root: vault },
    });
    const prompt = [
      '[tool:monocle_vault-read_note {"path":"projects/Project Lantern.md"}]',
      '[tool:monocle_vault-read_note {"path":"../../outside.md"}]',
      '[tool:monocle_vault-read_note {"path":"work/Duplicate Id Note.md"}]',
      '[tool:monocle_vault-write_note {"path":"Home.md","content":"x"}]',
      '[tool:write {"path":"Home.md"}]',
    ].join(" ");
    const { events } = await execute({ prompt, context: { exclude: ["work/Duplicate Id Note.md"] } });
    const out = completedText(events);
    expect(out).toContain("lanternfish-7731");
    expect(out).toMatch(/\[monocle_vault-read_note\] .*may not contain .*\.\./);
    expect(out).toMatch(/\[monocle_vault-read_note\] .*excluded from this request/);
    expect(out).toContain("[monocle_vault-write_note] unavailable");
    expect(out).toContain("[write] unavailable");
    expect(vaultHashes(vault)).toEqual(before);
  }, 30_000);
});
