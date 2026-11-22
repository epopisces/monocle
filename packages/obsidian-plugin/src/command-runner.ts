import {
  COMMANDS_PATH,
  missingContext,
  resolveCommandArgument,
  type CommandDefinition,
  type CommandError,
  type CommandResult,
  type ExecutionContext,
  type ExecutionSettings,
} from "@monocle/contracts";
import type { ActiveNoteSnapshot } from "./context.js";
import type { ExecutionClient, ExecutionHandle, FetchLike } from "./execution-client.js";

export interface CommandRunnerOptions {
  readonly endpoint: string;
  readonly fetch: FetchLike;
  readonly executions: ExecutionClient;
}

/** One invocation of a registry command, from chat, the palette or a context menu. */
export interface CommandInvocation {
  readonly command: CommandDefinition;
  /** Typed argument; empty when none (the selection is used where the command allows it). */
  readonly argument: string;
  readonly activeNote?: ActiveNoteSnapshot | undefined;
  /** Cravat commands only: note context the user chose to share and the conversation to continue. */
  readonly context?: ExecutionContext | undefined;
  readonly conversationId?: string | undefined;
  readonly settings?: ExecutionSettings | undefined;
}

export type CommandOutcome =
  | { readonly kind: "result"; readonly result: CommandResult }
  | { readonly kind: "error"; readonly error: { readonly code: string; readonly message: string } }
  | { readonly kind: "execution"; readonly handle: ExecutionHandle };

/**
 * Dispatches registry commands: deterministic ones to `POST /v1/commands` (no Cravat), agentic ones to an
 * execution. Missing context is reported before anything is sent. Obsidian-free so it is testable in Node.
 */
export class CommandRunner {
  constructor(private readonly options: CommandRunnerOptions) {}

  async run(invocation: CommandInvocation): Promise<CommandOutcome> {
    const { command, activeNote } = invocation;
    // The companion is the authority on whether a vault is configured; it answers missing_context if not.
    const available = { argument: invocation.argument, ...(activeNote && { activeNote }), vault: true };
    const missing = missingContext(command, available);
    if (missing.length > 0) return { kind: "error", error: { code: "missing_context", message: missing.join("; ") } };
    const argument = resolveCommandArgument(command, available);

    if (command.route === "cravat") {
      const handle = this.options.executions.execute(argument, invocation.settings, {
        command: command.id,
        context: invocation.context,
        ...(invocation.conversationId !== undefined && { conversationId: invocation.conversationId }),
      });
      return { kind: "execution", handle };
    }

    let res: Response;
    try {
      res = await this.options.fetch(new URL(COMMANDS_PATH, this.options.endpoint).href, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          command: command.id,
          ...(argument && { argument }),
          ...(activeNote && { context: { activeNote: { path: activeNote.path } } }),
        }),
      });
    } catch (err) {
      return { kind: "error", error: { code: "connection_lost", message: `companion unreachable: ${(err as Error).message}` } };
    }
    let body: { error?: unknown } & Partial<CommandResult>;
    try {
      body = (await res.json()) as typeof body;
    } catch {
      return { kind: "error", error: { code: "provider_error", message: `companion returned HTTP ${res.status}` } };
    }
    if (res.status === 200 && typeof body.markdown === "string") return { kind: "result", result: body as CommandResult };
    const err = body.error as Partial<CommandError> | string | undefined;
    if (typeof err === "object" && err && typeof err.code === "string" && typeof err.message === "string") {
      return { kind: "error", error: { code: err.code, message: err.message } };
    }
    return {
      kind: "error",
      error: { code: "provider_error", message: typeof err === "string" ? `HTTP ${res.status}: ${err}` : `companion returned HTTP ${res.status}` },
    };
  }
}
