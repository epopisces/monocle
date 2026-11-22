import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { COMMANDS_PATH, CONVERSATIONS_PATH, conversationPath, EXECUTIONS_PATH } from "@monocle/contracts";
import { startCompanion, type CompanionNotesOptions, type RunningCompanion } from "@monocle/companion";
import { openIndexService, type IndexService } from "@monocle/core";
import type { ProviderAdapter } from "@monocle/cravat";

let work: string | undefined;
let index: IndexService | undefined;
let running: RunningCompanion | undefined;
let providerRuns = 0;

const neverRun: ProviderAdapter = {
  id: "never",
  async *run() {
    providerRuns++;
    yield { type: "delta", text: "should not run" };
  },
};

afterEach(async () => {
  await running?.close();
  index?.close();
  if (work) rmSync(work, { recursive: true, force: true });
  running = index = work = undefined;
  providerRuns = 0;
});

async function start(withVault = true, notes?: CompanionNotesOptions): Promise<void> {
  if (withVault) {
    work = mkdtempSync(join(tmpdir(), "monocle-commands-"));
    const vault = join(work, "vault");
    cpSync(fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url)), vault, { recursive: true });
    index = openIndexService({ vaultRoot: vault, stateDir: join(work, "state"), excludeFolders: ["templates"], watch: false });
  }
  running = await startCompanion({ port: 0, adapter: neverRun, ...(index && { index }), ...(notes && { notes }) });
}

async function command(body: unknown): Promise<{ status: number; json: any }> {
  const res = await fetch(new URL(COMMANDS_PATH, running!.url), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: res.status, json: await res.json() };
}

const lantern = { activeNote: { path: "projects/Project Lantern.md" } };

describe("agentic commands", () => {
  const calls: string[] = [];
  const capture: ProviderAdapter = {
    id: "capture",
    async *run(request) {
      calls.push(request.prompt);
      yield { type: "delta", text: "answer" };
    },
  };

  async function startWithVault(): Promise<void> {
    calls.length = 0;
    work = mkdtempSync(join(tmpdir(), "monocle-commands-"));
    const vault = join(work, "vault");
    cpSync(fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url)), vault, { recursive: true });
    running = await startCompanion({ port: 0, adapter: capture, vault: { root: vault } });
  }

  async function execute(body: unknown): Promise<{ status: number; text: string }> {
    const res = await fetch(new URL(EXECUTIONS_PATH, running!.url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return { status: res.status, text: await res.text() };
  }

  it("runs /lookup in Cravat with Monocle's grounding instructions and records the command", async () => {
    await startWithVault();
    const res = await execute({ command: "lookup", prompt: "Who owns Project Lantern?" });
    expect(res.status).toBe(200);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatch(/monocle_vault/);
    expect(calls[0]).toMatch(/cite/i);
    expect(calls[0]).toContain("Who owns Project Lantern?");
    const { conversations } = await (await fetch(new URL(CONVERSATIONS_PATH, running!.url))).json();
    const conversation = await (await fetch(new URL(conversationPath(conversations[0].id), running!.url))).json();
    expect(conversation.executions[0].prompt).toBe("/lookup Who owns Project Lantern?");
  });

  it("refuses deterministic commands and agentic commands missing their context, without starting Cravat", async () => {
    await startWithVault();
    const deterministic = await execute({ command: "validate", prompt: "x" });
    expect(deterministic.status).toBe(400);
    expect(JSON.parse(deterministic.text).error.message).toContain("/v1/commands");
    expect(JSON.parse((await execute({ command: "nope", prompt: "x" })).text).error.message).toMatch(/Unknown command/);
    await running!.close();
    running = await startCompanion({ port: 0, adapter: capture });
    const noVault = await execute({ command: "lookup", prompt: "x" });
    expect(JSON.parse(noVault.text).error).toMatchObject({ code: "missing_context", message: expect.stringMatching(/--vault/) });
    expect(calls).toHaveLength(0);
  });
});

describe("deterministic commands", () => {
  it("validates the active note inside Monocle without starting Cravat or a conversation", async () => {
    await start();
    const res = await command({ command: "validate", context: lantern });
    expect(res.status).toBe(200);
    expect(res.json).toMatchObject({ command: "validate", data: { path: "projects/Project Lantern.md", valid: false } });
    expect(res.json.markdown).toContain("work/Duplicate Id Note.md");
    expect(res.json.markdown).toContain("[[Missing Note]]");
    expect(providerRuns).toBe(0);
    const conversations = await (await fetch(new URL(CONVERSATIONS_PATH, running!.url))).json();
    expect(conversations).toEqual({ conversations: [] });
  });

  it("lists backlinks of the active note", async () => {
    await start();
    const res = await command({ command: "backlinks", context: lantern });
    expect(res.status).toBe(200);
    expect(res.json.data.backlinks).toContainEqual(expect.objectContaining({ path: "people/Ada Example.md" }));
    expect(res.json.markdown).toContain("people/Ada Example.md");
  });

  it("searches the vault index", async () => {
    await start();
    const res = await command({ command: "search", argument: "lanternfish-7731" });
    expect(res.status).toBe(200);
    expect(res.json.data.hits[0]).toMatchObject({ path: "projects/Project Lantern.md" });
    expect(providerRuns).toBe(0);
  });

  it("names the missing context instead of running", async () => {
    await start();
    const noNote = await command({ command: "validate" });
    expect(noNote).toMatchObject({ status: 400, json: { error: { code: "missing_context", message: expect.stringMatching(/active note/) } } });
    const noQuery = await command({ command: "search", argument: " " });
    expect(noQuery.json.error).toMatchObject({ code: "missing_context", missing: [expect.stringMatching(/needs a query/)] });
  });

  it("asks for a vault when the companion has no index", async () => {
    await start(false);
    const res = await command({ command: "validate", context: lantern });
    expect(res.json.error).toMatchObject({ code: "missing_context", message: expect.stringMatching(/--vault/) });
  });

  it("rejects unknown commands, agentic commands and non-note paths", async () => {
    await start();
    expect((await command({ command: "nope" })).json.error).toMatchObject({ code: "unknown_command" });
    expect((await command({ command: "lookup", argument: "x" })).json.error).toMatchObject({
      code: "agentic_command",
      message: expect.stringContaining("/v1/executions"),
    });
    const excluded = await command({ command: "validate", context: { activeNote: { path: "templates/Fixture Template.md" } } });
    expect(excluded).toMatchObject({ status: 400, json: { error: { code: "invalid_request" } } });
    expect(providerRuns).toBe(0);
  });
});

describe("/new-note", () => {
  const notes: CompanionNotesOptions = { template: "Fixture Template", fields: { type: "capture" } };

  it("creates a schema-valid note with the next unique ID and indexes it, without Cravat", async () => {
    await start(true, notes);
    const { status, json } = await command({ command: "new-note", argument: "Meeting Notes" });
    expect(status).toBe(200);
    expect(json.data).toMatchObject({ path: "inbox/Meeting Notes.md", id: "fx-0004", template: "Fixture Template" });
    expect(json.data.validation.valid).toBe(true);
    expect(json.markdown).toContain("[[inbox/Meeting Notes.md|Meeting Notes]]");
    expect(readFileSync(join(index!.noteIndex.vaultRoot, "inbox", "Meeting Notes.md"), "utf8")).toContain('id: "fx-0004"');
    expect(index!.noteIndex.listNotes().some((n) => n.id === "fx-0004")).toBe(true);
    expect(providerRuns).toBe(0);
  });

  it("never overwrites an existing note and says why", async () => {
    await start(true, notes);
    const first = await command({ command: "new-note", argument: "Ada Lovelace" });
    expect(first.status).toBe(200);
    const before = readFileSync(join(index!.noteIndex.vaultRoot, "inbox", "Ada Lovelace.md"), "utf8");
    const clash = await command({ command: "new-note", argument: "ada lovelace" });
    expect(clash.status).toBe(400);
    expect(clash.json.error).toMatchObject({ code: "note_creation_failed", reason: "path_exists" });
    expect(clash.json.error.message).toContain("inbox/Ada Lovelace.md already exists");
    expect(readFileSync(join(index!.noteIndex.vaultRoot, "inbox", "Ada Lovelace.md"), "utf8")).toBe(before);
  });

  it("is not permitted until a note template is configured", async () => {
    await start(true);
    const { status, json } = await command({ command: "new-note", argument: "Meeting Notes" });
    expect(status).toBe(403);
    expect(json.error.code).toBe("not_permitted");
    expect(json.error.message).toContain("--note-template");
    expect(existsSync(join(index!.noteIndex.vaultRoot, "inbox", "Meeting Notes.md"))).toBe(false);
  });

  it("asks for a title and a vault", async () => {
    await start(true, notes);
    const untitled = await command({ command: "new-note", argument: "  " });
    expect(untitled).toMatchObject({ status: 400, json: { error: { code: "missing_context" } } });
    await running!.close();
    index!.close();
    index = undefined;
    await start(false, notes);
    const noVault = await command({ command: "new-note", argument: "Meeting Notes" });
    expect(noVault).toMatchObject({ status: 400, json: { error: { code: "missing_context" } } });
  });
});