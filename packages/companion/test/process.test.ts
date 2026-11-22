import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { HEALTH_PATH, isHealthResponse, type HealthResponse } from "@monocle/contracts";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const cli = fileURLToPath(new URL("../dist/cli.js", import.meta.url));
const children: ChildProcess[] = [];

beforeAll(() => {
  // The smoke test runs the real built entry point, as an operator would.
  execFileSync(process.execPath, [join(repoRoot, "node_modules", "typescript", "bin", "tsc"), "-b", "packages/companion"], {
    cwd: repoRoot,
    stdio: "inherit",
  });
}, 60_000);

afterEach(() => {
  for (const c of children.splice(0)) c.kill();
});

function launch(port: number): Promise<{ child: ChildProcess; url: string }> {
  const child = spawn(process.execPath, [cli, "--port", String(port)], { stdio: ["ignore", "pipe", "inherit"] });
  children.push(child);
  return new Promise((resolve, reject) => {
    child.once("exit", (code) => reject(new Error(`companion exited early with ${code}`)));
    createInterface({ input: child.stdout! }).on("line", (line) => {
      const msg = JSON.parse(line) as { event?: string; url?: string };
      if (msg.event === "listening" && msg.url) resolve({ child, url: msg.url });
    });
  });
}

async function health(url: string): Promise<HealthResponse | undefined> {
  try {
    const body: unknown = await (await fetch(new URL(HEALTH_PATH, url))).json();
    return isHealthResponse(body) ? body : undefined;
  } catch {
    return undefined;
  }
}

function exited(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => (child.exitCode !== null ? resolve() : child.once("exit", () => resolve())));
}

describe("companion process (restart smoke test)", () => {
  it("runs standalone, stops when killed and serves again as a new instance after restart", async () => {
    const first = await launch(0);
    const before = await health(first.url);
    expect(before?.status).toBe("ok");

    first.child.kill();
    await exited(first.child);
    expect(await health(first.url)).toBeUndefined();

    const port = Number(new URL(first.url).port);
    const second = await launch(port);
    expect(second.url).toBe(first.url);
    const after = await health(second.url);
    expect(after?.status).toBe("ok");
    expect(after?.instanceId).not.toBe(before?.instanceId);
  }, 30_000);
});
