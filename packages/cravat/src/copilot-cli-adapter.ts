import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import type { ExecutionRequest } from "@monocle/contracts";
import { ProviderError, type ExecutionToolset, type ProviderAdapter, type ProviderEvent } from "./execution-manager.js";

export interface CopilotCliAdapterOptions {
  /** Copilot executable. Defaults to `MONOCLE_COPILOT_PATH`, else `copilot` on PATH. Must be a real executable, not a `.cmd` shim. */
  readonly command?: string;
  /** Arguments placed before Cravat's own flags (e.g. a script path when `command` is `node`). */
  readonly args?: readonly string[];
  /** Extra environment variables for the CLI process. */
  readonly env?: Readonly<Record<string, string>>;
}

/**
 * Flags for a non-interactive, read-only run: JSONL streaming output and no built-in MCP servers. Tool
 * availability is added by {@link toolFlags}: none at all by default, otherwise only the toolset's MCP tools.
 */
const CLI_FLAGS = ["--output-format", "json", "--stream", "on", "--disable-builtin-mcps"] as const;

/** Built-in tool kinds denied outright as defense in depth, even though `--available-tools` already hides them. */
const DENIED_TOOL_KINDS = ["write", "shell"] as const;

const SERVER_NAME = /^[A-Za-z0-9_]+$/;

/** Copilot CLI flags exposing exactly the toolset's tools (named `<server>-<tool>`), pre-approved per server. */
function toolFlags(tools: ExecutionToolset | undefined, configPath: string): string[] {
  const servers = tools?.mcpServers.filter((s) => s.tools.length > 0) ?? [];
  if (servers.length === 0) return ["--available-tools", "none"];
  const flags = ["--additional-mcp-config", `@${configPath}`];
  for (const s of servers) for (const t of s.tools) flags.push("--available-tools", `${s.name}-${t}`);
  for (const s of servers) flags.push("--allow-tool", s.name);
  for (const k of DENIED_TOOL_KINDS) flags.push("--deny-tool", k);
  return flags;
}

function mcpConfig(tools: ExecutionToolset): string {
  const mcpServers: Record<string, unknown> = {};
  for (const s of tools.mcpServers) {
    if (!SERVER_NAME.test(s.name)) throw new ProviderError("launch_failed", `invalid MCP server name "${s.name}"`);
    if (s.tools.length === 0) continue;
    mcpServers[s.name] = { type: "local", command: s.command, args: [...s.args], env: { ...s.env }, tools: [...s.tools] };
  }
  return JSON.stringify({ mcpServers });
}

const STDERR_LIMIT = 4_096;

function killTree(pid: number | undefined): void {
  if (pid === undefined) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true }).on("error", () => {});
  } else {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // already exited
    }
  }
}

interface CliEvent {
  type?: string;
  exitCode?: number;
  data?: { messageId?: string; deltaContent?: string; content?: string; message?: string };
}

/** Cravat adapter for the installed GitHub Copilot CLI (`copilot -p` JSONL mode), one process per execution. */
export class CopilotCliAdapter implements ProviderAdapter {
  readonly id = "copilot-cli";
  private readonly command: string;
  private readonly args: readonly string[];
  private readonly env: Readonly<Record<string, string>>;

  constructor(options: CopilotCliAdapterOptions = {}) {
    this.command = options.command ?? process.env.MONOCLE_COPILOT_PATH ?? "copilot";
    this.args = options.args ?? [];
    this.env = options.env ?? {};
  }

  async *run(request: ExecutionRequest, signal: AbortSignal, tools?: ExecutionToolset): AsyncIterable<ProviderEvent> {
    if (signal.aborted) return;
    const config = tools ? mcpConfig(tools) : undefined;
    // Empty scratch cwd: Copilot loads no repository instructions/config from wherever the companion runs.
    const cwd = mkdtempSync(join(tmpdir(), "cravat-copilot-"));
    const configPath = join(cwd, "mcp-config.json");
    if (config) writeFileSync(configPath, config);
    const child = spawn(this.command, [...this.args, ...CLI_FLAGS, ...toolFlags(tools, configPath)], {
      cwd,
      env: { ...process.env, ...this.env },
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    let launchError: Error | undefined;
    const exited = new Promise<number | null>((resolve) => {
      child.once("error", (err) => {
        launchError = err;
        resolve(null);
      });
      child.once("close", (code) => resolve(code));
    });
    let stderr = "";
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk: string) => (stderr = (stderr + chunk).slice(-STDERR_LIMIT)));
    child.stdin.on("error", () => {}); // EPIPE when launch failed; reported via launchError
    child.stdin.end(request.prompt);
    const onAbort = () => killTree(child.pid);
    signal.addEventListener("abort", onAbort, { once: true });

    let streamError: string | undefined;
    let resultExitCode: number | undefined;
    const streamed = new Set<string>();
    let emittedAny = false;
    let lastMessageId: string | undefined;
    const separate = (messageId: string | undefined): ProviderEvent | undefined => {
      const needed = emittedAny && messageId !== lastMessageId;
      lastMessageId = messageId;
      return needed ? { type: "delta", text: "\n\n" } : undefined;
    };

    try {
      for await (const line of createInterface({ input: child.stdout, crlfDelay: Infinity })) {
        if (signal.aborted) return;
        let event: CliEvent;
        try {
          event = JSON.parse(line) as CliEvent;
        } catch {
          continue;
        }
        if (event.type === "assistant.message_delta" && event.data?.deltaContent) {
          const sep = separate(event.data.messageId);
          if (sep) yield sep;
          if (event.data.messageId) streamed.add(event.data.messageId);
          emittedAny = true;
          yield { type: "delta", text: event.data.deltaContent };
        } else if (event.type === "assistant.message" && event.data?.content && !streamed.has(event.data.messageId ?? "")) {
          // Provider did not stream this message; emit it whole.
          const sep = separate(event.data.messageId);
          if (sep) yield sep;
          emittedAny = true;
          yield { type: "delta", text: event.data.content };
        } else if (event.type?.endsWith(".error") && event.data?.message) {
          streamError = event.data.message;
        } else if (event.type === "result" && typeof event.exitCode === "number") {
          resultExitCode = event.exitCode;
        }
      }
      const code = await exited;
      if (signal.aborted) return;
      if (launchError) {
        throw new ProviderError("launch_failed", `could not start Copilot CLI "${this.command}": ${launchError.message}`);
      }
      const failedCode = resultExitCode !== undefined && resultExitCode !== 0 ? resultExitCode : code !== 0 ? code : undefined;
      if (failedCode !== undefined || streamError) {
        const detail = streamError ?? (stderr.trim() || `Copilot CLI exited with code ${failedCode}`);
        throw new ProviderError("provider_error", detail);
      }
    } finally {
      signal.removeEventListener("abort", onAbort);
      if (child.exitCode === null && child.signalCode === null) killTree(child.pid);
      try {
        rmSync(cwd, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
      } catch {
        // A just-killed process may still hold the directory on Windows; it is only an empty temp dir.
      }
    }
  }
}
