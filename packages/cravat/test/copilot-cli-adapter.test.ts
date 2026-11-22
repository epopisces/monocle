import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CopilotCliAdapter, ProviderError, type ProviderEvent } from "@monocle/cravat";

const fakeCli = fileURLToPath(new URL("./fixtures/fake-copilot.mjs", import.meta.url));

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
