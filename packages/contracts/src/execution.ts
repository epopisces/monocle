/**
 * Monocle → Cravat execution contract (since contract 0.2.0).
 *
 * Transport: `POST {@link EXECUTIONS_PATH}` with an {@link ExecutionRequest} JSON body responds `200` with an
 * NDJSON stream (`application/x-ndjson`, one {@link ExecutionEvent} per line). The first event is `started`
 * (carrying the execution ID); the stream always ends with exactly one terminal event (`completed`, `failed`
 * or `cancelled`). `POST {@link cancelExecutionPath}(id)` requests cancellation; closing the stream early also
 * cancels the execution.
 *
 * Browser-origin requests are only accepted from {@link ALLOWED_CLIENT_ORIGINS} (CORS + Origin check), and
 * request bodies must be `application/json`, so arbitrary web pages cannot start executions on this host.
 */

export const EXECUTIONS_PATH = "/v1/executions";

export function cancelExecutionPath(executionId: string): string {
  return `${EXECUTIONS_PATH}/${encodeURIComponent(executionId)}/cancel`;
}

export const EXECUTION_STREAM_CONTENT_TYPE = "application/x-ndjson";

/** Renderer origin of Obsidian desktop; the only browser origin allowed to call the companion. */
export const OBSIDIAN_ORIGIN = "app://obsidian.md";
export const ALLOWED_CLIENT_ORIGINS: readonly string[] = [OBSIDIAN_ORIGIN];

/** Upper bound on prompt length accepted by the companion. */
export const MAX_PROMPT_LENGTH = 100_000;

/** Upper bound on inline context text (active note content + selection) in one request. */
export const MAX_CONTEXT_LENGTH = 200_000;
/** Upper bound on entries in each of `context.include` / `context.exclude`. */
export const MAX_CONTEXT_PATHS = 100;

/** The note focused in the editor when the request was made, as the client sees it (may be unsaved). */
export interface ExecutionActiveNote {
  /** Vault-relative path with `/` separators. */
  readonly path: string;
  /** Full editor text; omit to not send the note body. */
  readonly content?: string;
  /** Selected text; omit when nothing is selected or the selection is not shared. */
  readonly selection?: string;
}

/**
 * Context supplied with an execution (optional; companions predating it reject it as an unsupported field). Exclusions win over everything:
 * an excluded note is neither sent to the provider (even as the active note) nor readable by vault tools.
 */
export interface ExecutionContext {
  readonly activeNote?: ExecutionActiveNote;
  /** Vault-relative note paths whose current content is added to the context. */
  readonly include?: readonly string[];
  /** Vault-relative note paths or folders that must not be disclosed in this execution. */
  readonly exclude?: readonly string[];
}

export interface ExecutionRequest {
  readonly prompt: string;
  readonly context?: ExecutionContext;
}

export type ExecutionErrorCode =
  /** The request body was malformed or contained unsupported fields. */
  | "invalid_request"
  /** The provider runtime could not be started (e.g. not installed, not on PATH). */
  | "launch_failed"
  /** The provider started but reported an error or exited abnormally. */
  | "provider_error"
  /** Client-side: the companion was unreachable or the stream ended without a terminal event (e.g. restart). */
  | "connection_lost";

export interface ExecutionError {
  readonly code: ExecutionErrorCode;
  readonly message: string;
}

interface EventBase {
  readonly executionId: string;
  /** 0-based position within this execution's stream. */
  readonly seq: number;
}

export type ExecutionEvent =
  | (EventBase & {
      readonly type: "started";
      /** Provider adapter that runs this execution, e.g. `copilot-cli`. */
      readonly provider: string;
      /** Companion `instanceId` (see health); a different value after restart means this execution is lost. */
      readonly instanceId: string;
      readonly startedAt: string;
    })
  | (EventBase & { readonly type: "delta"; readonly text: string })
  | (EventBase & { readonly type: "completed"; readonly text: string })
  | (EventBase & { readonly type: "failed"; readonly error: ExecutionError })
  | (EventBase & { readonly type: "cancelled" });

export type TerminalExecutionEvent = Extract<ExecutionEvent, { type: "completed" | "failed" | "cancelled" }>;

export function isTerminalExecutionEvent(event: ExecutionEvent): event is TerminalExecutionEvent {
  return event.type === "completed" || event.type === "failed" || event.type === "cancelled";
}

export type ExecutionRequestResult = { ok: true; request: ExecutionRequest } | { ok: false; error: string };

/**
 * Validates an execution request body. Unknown fields are rejected rather than ignored, so a client never
 * believes a setting was applied when it was not.
 */
export function parseExecutionRequest(value: unknown): ExecutionRequestResult {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, error: "request body must be a JSON object" };
  }
  const unknownKeys = unknownFields(value, ["prompt", "context"]);
  if (unknownKeys) return { ok: false, error: `unsupported request fields: ${unknownKeys}` };
  const { prompt, context } = value as { prompt?: unknown; context?: unknown };
  if (typeof prompt !== "string" || prompt.trim() === "") return { ok: false, error: "prompt must be a non-empty string" };
  if (prompt.length > MAX_PROMPT_LENGTH) return { ok: false, error: `prompt exceeds ${MAX_PROMPT_LENGTH} characters` };
  if (context === undefined) return { ok: true, request: { prompt } };
  const parsed = parseContext(context);
  return typeof parsed === "string" ? { ok: false, error: parsed } : { ok: true, request: { prompt, context: parsed } };
}

const isPlainObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function unknownFields(value: object, allowed: readonly string[]): string | undefined {
  const extra = Object.keys(value).filter((k) => !allowed.includes(k));
  return extra.length > 0 ? extra.join(", ") : undefined;
}

function parsePaths(value: unknown, field: string): readonly string[] | string | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || !value.every((p) => typeof p === "string" && p.trim() !== "" && p.length <= 1_024)) {
    return `context.${field} must be an array of non-empty strings`;
  }
  if (value.length > MAX_CONTEXT_PATHS) return `context.${field} exceeds ${MAX_CONTEXT_PATHS} entries`;
  return value as string[];
}

/** Returns the validated context or an error message. */
function parseContext(value: unknown): ExecutionContext | string {
  if (!isPlainObject(value)) return "context must be an object";
  const extra = unknownFields(value, ["activeNote", "include", "exclude"]);
  if (extra) return `unsupported context fields: ${extra}`;
  const context: { activeNote?: ExecutionActiveNote; include?: readonly string[]; exclude?: readonly string[] } = {};
  if (value.activeNote !== undefined) {
    const note = value.activeNote;
    if (!isPlainObject(note)) return "context.activeNote must be an object";
    const extraNote = unknownFields(note, ["path", "content", "selection"]);
    if (extraNote) return `unsupported activeNote fields: ${extraNote}`;
    if (typeof note.path !== "string" || note.path.trim() === "") return "context.activeNote.path must be a non-empty string";
    for (const key of ["content", "selection"] as const) {
      if (note[key] !== undefined && typeof note[key] !== "string") return `context.activeNote.${key} must be a string`;
    }
    const size = ((note.content as string | undefined)?.length ?? 0) + ((note.selection as string | undefined)?.length ?? 0);
    if (size > MAX_CONTEXT_LENGTH) return `context exceeds ${MAX_CONTEXT_LENGTH} characters`;
    context.activeNote = note as unknown as ExecutionActiveNote;
  }
  for (const field of ["include", "exclude"] as const) {
    const paths = parsePaths(value[field], field);
    if (typeof paths === "string") return paths;
    if (paths) context[field] = paths;
  }
  return context;
}
