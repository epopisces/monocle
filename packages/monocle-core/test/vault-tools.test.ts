import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { VAULT_MCP_STDIO_ENTRY, VAULT_TOOL_NAMES } from "@monocle/core";
import { McpTestClient } from "./support/mcp-client.js";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
let work: string;
let vault: string;
const clients: McpTestClient[] = [];

beforeAll(() => {
  // The Copilot CLI spawns the built server, so test that.
  execFileSync(process.execPath, [join(repoRoot, "node_modules", "typescript", "bin", "tsc"), "-b", "packages/monocle-core"], {
    cwd: repoRoot,
    stdio: "inherit",
  });
  work = mkdtempSync(join(tmpdir(), "monocle-vault-tools-"));
  vault = join(work, "vault");
  cpSync(join(repoRoot, "fixtures", "vault"), vault, { recursive: true });
}, 60_000);

afterAll(() => rmSync(work, { recursive: true, force: true }));
afterEach(() => {
  for (const c of clients.splice(0)) c.close();
});

async function server(...extraArgs: string[]): Promise<McpTestClient> {
  const client = new McpTestClient(process.execPath, [VAULT_MCP_STDIO_ENTRY, "--vault", vault, ...extraArgs]);
  clients.push(client);
  await client.initialize();
  return client;
}

const text = (r: { content: { text: string }[] }) => r.content.map((c) => c.text).join("\n");

describe("Monocle read-only vault tools (MCP stdio server)", () => {
  it("offers only read-only note tools", async () => {
    const mcp = await server();
    const { result } = await mcp.request<{ tools: { name: string; annotations?: { readOnlyHint?: boolean } }[] }>("tools/list");
    expect(result!.tools.map((t) => t.name).sort()).toEqual([...VAULT_TOOL_NAMES].sort());
    expect(VAULT_TOOL_NAMES).toEqual(["read_note", "list_notes", "search_notes"]);
    for (const tool of result!.tools) expect(tool.annotations?.readOnlyHint).toBe(true);
  });

  it("reads a note by vault-relative path", async () => {
    const mcp = await server();
    const res = await mcp.call("read_note", { path: "projects/Project Lantern.md" });
    expect(res.isError).toBeFalsy();
    expect(text(res)).toContain("Unique search token: `lanternfish-7731`");
  });

  it.each([
    ["../outside.md"],
    ["people/../../outside.md"],
    ["..\\outside.md"],
    [join(repoRoot, "README.md")],
    ["/etc/passwd.md"],
    [".obsidian/app.json"],
    ["attachments/README.txt"],
    ["people/Missing.md"],
  ])("refuses %s", async (path) => {
    writeFileSync(join(work, "outside.md"), "TOP SECRET OUTSIDE");
    const res = await (await server()).call("read_note", { path });
    expect(res.isError).toBe(true);
    expect(text(res)).not.toContain("TOP SECRET");
  });

  it("refuses notes reached through a link that leaves the vault", async () => {
    mkdirSync(join(work, "elsewhere"), { recursive: true });
    writeFileSync(join(work, "elsewhere", "Secret.md"), "TOP SECRET VIA JUNCTION");
    symlinkSync(join(work, "elsewhere"), join(vault, "linked"), "junction");
    try {
      const mcp = await server();
      const res = await mcp.call("read_note", { path: "linked/Secret.md" });
      expect(res.isError).toBe(true);
      expect(text(res)).not.toContain("TOP SECRET");
      expect(text(await mcp.call("search_notes", { query: "secret junction" }))).toBe("No matching notes.");
    } finally {
      rmSync(join(vault, "linked"), { recursive: true, force: true });
    }
  });

  it("lists and searches notes", async () => {
    const mcp = await server();
    const list = text(await mcp.call("list_notes", { folder: "people" }));
    expect(list).toBe("people/Ada Example.md");
    expect(text(await mcp.call("list_notes", {}))).toContain("projects/Project Lantern.md");
    const hits = text(await mcp.call("search_notes", { query: "LANTERNFISH-7731" }));
    expect(hits).toMatch(/^projects\/Project Lantern\.md\n.*lanternfish-7731/);
  });

  it("hides excluded notes and folders from every tool, whatever the path spelling", async () => {
    const mcp = await server("--exclude", "projects/Project Lantern.md", "--exclude", "work");
    for (const path of ["projects/Project Lantern.md", "Projects/project lantern.md", "projects\\Project Lantern.md", "work/Duplicate Id Note.md"]) {
      const res = await mcp.call("read_note", { path });
      expect(res.isError, path).toBe(true);
      expect(text(res)).toMatch(/excluded/);
    }
    const list = text(await mcp.call("list_notes", {}));
    expect(list).toContain("people/Ada Example.md");
    expect(list).not.toMatch(/Project Lantern|work\//);
    expect(text(await mcp.call("search_notes", { query: "lanternfish" }))).toBe("No matching notes.");
    expect(text(await mcp.call("search_notes", { query: "Project Lantern" }))).not.toContain("projects/");
  });

  it("has no way to write: unknown tools fail and the vault is unchanged", async () => {
    const before = hashTree(vault);
    const mcp = await server();
    for (const name of ["write_note", "edit", "create", "delete_note", "shell"]) {
      const res = await mcp.call(name, { path: "people/Ada Example.md", content: "pwned" });
      expect(res.isError).toBe(true);
    }
    await mcp.call("read_note", { path: "people/Ada Example.md" });
    await mcp.call("search_notes", { query: "ada" });
    expect(hashTree(vault)).toEqual(before);
  });
});

function hashTree(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const entry of readdirSync(root, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const abs = join(entry.parentPath, entry.name);
    out[abs.slice(root.length)] = createHash("sha256").update(readFileSync(abs)).digest("hex");
  }
  return out;
}
