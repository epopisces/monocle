import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import type { ExecutionRequest, ExecutionSettings, ProviderSettingCapabilities } from "@monocle/contracts";
import { ProviderError, type ExecutionToolset, type ProviderAdapter, type ProviderEvent, type ProviderRunOptions } from "./execution-manager.js";

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
/** What CLI 1.0.104 prints (then exits 1, before any JSON output) when `--resume=<id>` matches no session. */
const SESSION_NOT_FOUND = /No session, task, or name matched/i;

/** The requested session could not be resumed; the run produced no output and may be retried fresh. */
class SessionUnavailable extends Error {}

/** Per-run session flag: start a new session with a known ID, or resume an existing one. */
type SessionTarget = { readonly kind: "new"; readonly id: string } | { readonly kind: "resume"; readonly id: string };
const HELP_TIMEOUT_MS = 15_000;

/** Runs the CLI with `args` (no prompt, no stdin) and resolves its stdout, or `undefined` if it fails. */
function readCliOutput(command: string, args: readonly string[], env: NodeJS.ProcessEnv): Promise<string | undefined> {
  return new Promise((resolve) => {
    let out = "";
    const child = spawn(command, args, { env, stdio: ["ignore", "pipe", "ignore"], windowsHide: true });
    const timer = setTimeout(() => killTree(child.pid), HELP_TIMEOUT_MS);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => (out += chunk));
    child.once("error", () => {
      clearTimeout(timer);
      resolve(undefined);
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      resolve(code === 0 ? out : undefined);
    });
  });
}

/** Lines of one `--flag` entry in `copilot --help`, up to the next option. */
function optionBlock(help: string, flag: string): string | undefined {
  const lines = help.split(/\r?\n/);
  const start = lines.findIndex((l) => new RegExp(`^\\s+${flag}\\b`).test(l));
  if (start < 0) return undefined;
  const end = lines.findIndex((l, i) => i > start && /^\s+-/.test(l));
  return lines.slice(start, end < 0 ? undefined : end).join(" ");
}

function possibleValues(help: string, flag: string): string[] | undefined {
  const match = /\[possible values: ([^\]]+)\]/.exec(optionBlock(help, flag) ?? "");
  const values = match?.[1]?.split(",").map((v) => v.trim()).filter(Boolean);
  return values && values.length > 0 ? values : undefined;
}

/** Model IDs listed under `` `model`: `` in `copilot help config`. */
function configModels(config: string): string[] {
  const lines = config.split(/\r?\n/);
  const start = lines.findIndex((l) => /^\s+`model`:/.test(l));
  if (start < 0) return [];
  const models: string[] = [];
  for (const line of lines.slice(start + 1)) {
    const m = /^\s+- "([^"]+)"\s*$/.exec(line);
    if (!m) break;
    models.push(m[1]!);
  }
  return models;
}

/** Maps Monocle execution settings to Copilot CLI flags. */
function settingFlags(settings: ExecutionSettings | undefined): string[] {
  if (!settings) return [];
  return [
    ...(settings.model ? ["--model", settings.model] : []),
    ...(settings.reasoningEffort ? ["--reasoning-effort", settings.reasoningEffort] : []),
    ...(settings.contextWindow ? ["--context", settings.contextWindow] : []),
  ];
}

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

  /**
   * Reads supported settings from the installed CLI's help (`--help` for reasoning effort and context tiers,
   * `help config` for the model catalog), so Monocle never assumes provider feature parity. Costs no
   * premium request. A setting whose values cannot be discovered is reported as unsupported.
   */
  async capabilities(): Promise<ProviderSettingCapabilities> {
    const env = { ...process.env, ...this.env };
    const [help, config] = await Promise.all([
      readCliOutput(this.command, [...this.args, "--help"], env),
      readCliOutput(this.command, [...this.args, "help", "config"], env),
    ]);
    const caps: { -readonly [K in keyof ProviderSettingCapabilities]: ProviderSettingCapabilities[K] } = {};
    const models = config ? configModels(config) : [];
    if (models.length > 0) {
      const auto = help && /'auto'/.test(optionBlock(help, "--model") ?? "") ? ["auto"] : [];
      caps.model = { options: [...auto, ...models] };
    }
    const efforts = help && possibleValues(help, "--reasoning-effort");
    if (efforts) caps.reasoningEffort = { options: efforts };
    const tiers = help && possibleValues(help, "--context");
    if (tiers) caps.contextWindow = { options: tiers };
    return caps;
  }

  /**
   * Every run uses a Copilot session whose ID it reports, so a later run can pass it as `resumeSessionId` to
   * continue with the provider's own memory of earlier turns. If that session no longer exists (deleted, or a
   * different machine), the run starts a fresh session and reports `continuity: "unavailable"`.
   */
  async *run(request: ExecutionRequest, signal: AbortSignal, options: ProviderRunOptions = {}): AsyncIterable<ProviderEvent> {
    if (options.resumeSessionId !== undefined) {
      try {
        yield* this.runOnce(request, signal, { kind: "resume", id: options.resumeSessionId }, options.tools);
        return;
      } catch (err) {
        if (!(err instanceof SessionUnavailable)) throw err;
        const id = randomUUID();
        yield { type: "session", id, continuity: "unavailable", reason: err.message };
        yield* this.runOnce(request, signal, { kind: "new", id }, options.tools);
        return;
      }
    }
    const id = randomUUID();
    yield { type: "session", id, continuity: "new" };
    yield* this.runOnce(request, signal, { kind: "new", id }, options.tools);
  }

  private async *runOnce(request: ExecutionRequest, signal: AbortSignal, session: SessionTarget, tools?: ExecutionToolset): AsyncIterable<ProviderEvent> {
    if (signal.aborted) return;
    const config = tools ? mcpConfig(tools) : undefined;
    // Empty scratch cwd: Copilot loads no repository instructions/config from wherever the companion runs.
    const cwd = mkdtempSync(join(tmpdir(), "cravat-copilot-"));
    const sessionFlag = session.kind === "resume" ? `--resume=${session.id}` : `--session-id=${session.id}`;
    const configPath = join(cwd, "mcp-config.json");
    if (config) writeFileSync(configPath, config);
    const child = spawn(this.command, [...this.args, ...CLI_FLAGS, ...settingFlags(request.settings), ...toolFlags(tools, configPath), sessionFlag], {
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
    let sawOutput = false;
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
        if (!sawOutput) {
          sawOutput = true;
          // The CLI only starts emitting JSON once it has loaded the session.
          if (session.kind === "resume") yield { type: "session", id: session.id, continuity: "resumed" };
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
      if (session.kind === "resume" && !sawOutput && SESSION_NOT_FOUND.test(stderr)) {
        const detail = stderr.trim().split(/\r?\n/, 1)[0]!.replace(/^Error:\s*/, "");
        throw new SessionUnavailable(`Copilot CLI session ${session.id} could not be resumed: ${detail}`);
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
