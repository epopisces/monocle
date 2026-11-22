import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CopilotCliAdapter, ProviderError, type ExecutionToolset, type ProviderEvent } from "@monocle/cravat";

const fakeCli = fileURLToPath(new URL("./fixtures/fake-copilot.mjs", import.meta.url));
const fakeMcp = fileURLToPath(new URL("./fixtures/fake-mcp-server.mjs", import.meta.url));

const fakeAdapter = (mode: string) =>
  new CopilotCliAdapter({ command: process.execPath, args: [fakeCli], env: { FAKE_COPILOT_MODE: mode } });

async function run(adapter: CopilotCliAdapter, prompt: string, signal = new AbortController().signal): Promise<string> {
  let text = "";
  for await (const e of adapter.run({ prompt }, signal)) text += (e as ProviderEvent).text;
  return text;
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

describe("Copilot CLI adapter", () => {
  it("streams assistant message deltas and passes the prompt via stdin", async () => {
    expect(await run(fakeAdapter("stream"), "what is a monocle?")).toBe("echo: what is a monocle?");
  });

  it("launches Copilot non-interactively with no tools in an empty scratch directory", async () => {
    const out = JSON.parse(await run(fakeAdapter("args"), "x")) as { args: string[]; cwd: string };
    expect(out.args).toEqual(expect.arrayContaining(["--output-format", "json", "--stream", "on"]));
    expect(out.args.join(" ")).toContain("--available-tools none");
    expect(out.args).not.toContain("--allow-all-tools");
    expect(out.args).not.toContain("x");
    expect(existsSync(out.cwd)).toBe(false); // scratch dir removed after the run
  });

  it("reports a failed launch when the Copilot executable cannot be started", async () => {
    const adapter = new CopilotCliAdapter({ command: "definitely-not-copilot-xyz" });
    const err = await run(adapter, "x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ProviderError);
    expect(err).toMatchObject({ code: "launch_failed" });
    expect((err as Error).message).toMatch(/definitely-not-copilot-xyz/);
  });

  it("reports the CLI's stderr when it exits with an error", async () => {
    const err = await run(fakeAdapter("fail"), "x").catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "provider_error", message: expect.stringMatching(/not available/) });
  });

  it("reports provider errors signalled in the event stream", async () => {
    const err = await run(fakeAdapter("result-error"), "x").catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "provider_error", message: expect.stringMatching(/rate limited/) });
  });

  it("kills the Copilot process when the execution is aborted", async () => {
    const controller = new AbortController();
    let pid = 0;
    for await (const e of fakeAdapter("hang").run({ prompt: "x" }, controller.signal)) {
      pid = Number(e.text.replace("pid:", ""));
      controller.abort();
    }
    expect(pid).toBeGreaterThan(0);
    for (let i = 0; i < 100 && isAlive(pid); i++) await new Promise((r) => setTimeout(r, 20));
    expect(isAlive(pid)).toBe(false);
  });
});

describe("Copilot CLI adapter with an execution toolset", () => {
  const toolset: ExecutionToolset = {
    mcpServers: [
      { name: "monocle_vault", command: process.execPath, args: [fakeMcp], env: { FAKE_MCP_TAG: "vault" }, tools: ["echo"] },
    ],
  };

  async function runWith(mode: string, prompt: string, tools?: ExecutionToolset): Promise<string> {
    let text = "";
    for await (const e of fakeAdapter(mode).run({ prompt }, new AbortController().signal, tools)) text += e.text;
    return text;
  }

  it("exposes exactly the toolset's MCP tools, pre-approved per server, and nothing else", async () => {
    const out = JSON.parse(await runWith("args", "x", toolset)) as { args: string[]; mcpConfig: unknown };
    const flagValues = (flag: string) => out.args.flatMap((a, i) => (a === flag ? [out.args[i + 1]] : []));
    expect(flagValues("--available-tools")).toEqual(["monocle_vault-echo"]);
    expect(flagValues("--allow-tool")).toEqual(["monocle_vault"]);
    expect(flagValues("--deny-tool")).toEqual(expect.arrayContaining(["write", "shell"]));
    expect(out.args).not.toContain("--allow-all-tools");
    expect(out.args).not.toContain("--allow-all");
    expect(out.args).not.toContain("none");
    expect(out.mcpConfig).toEqual({
      mcpServers: {
        monocle_vault: { type: "local", command: process.execPath, args: [fakeMcp], env: { FAKE_MCP_TAG: "vault" }, tools: ["echo"] },
      },
    });
  });

  it("lets the agent call allowed tools but not other tools of the same server", async () => {
    const out = await runWith("stream", 'look [tool:monocle_vault-echo {"text":"hi"}] [tool:monocle_vault-hidden {}]', toolset);
    expect(out).toContain('[monocle_vault-echo] echo:{"text":"hi"}:vault');
    expect(out).toContain("[monocle_vault-hidden] unavailable");
  });

  it("keeps all tools disabled without a toolset", async () => {
    const out = await runWith("stream", '[tool:monocle_vault-echo {"text":"hi"}]');
    expect(out).toContain("[monocle_vault-echo] unavailable");
  });
});
