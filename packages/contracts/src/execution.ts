import type { ProviderSessionInfo } from "./conversation.js";

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
  /** Monocle vault context for this execution (since 0.2.x). */
  readonly context?: ExecutionContext;
  /**
   * Conversation to attach this execution to (see `conversation.ts`). Omitted: the companion starts a new
   * conversation and reports its ID on the `started` event.
   */
  readonly conversationId?: string;
  /** Provider execution options (since 0.2.x). Omitted settings use the provider's defaults. */
  readonly settings?: ExecutionSettings;
}

/** Execution options Monocle can request. Which ones apply, and their values, depend on the provider. */
export const EXECUTION_SETTING_NAMES = ["model", "reasoningEffort", "contextWindow"] as const;
export type ExecutionSettingName = (typeof EXECUTION_SETTING_NAMES)[number];

export type ExecutionSettings = { readonly [K in ExecutionSettingName]?: string };

/** One supported setting: the values the provider accepts. */
export interface SettingCapability {
  readonly options: readonly string[];
}

/** Settings a provider supports; a missing key means the setting is unsupported and will be rejected. */
export type ProviderSettingCapabilities = { readonly [K in ExecutionSettingName]?: SettingCapability };

export const CAPABILITIES_PATH = "/v1/capabilities";

/** Body of `GET {@link CAPABILITIES_PATH}`. */
export interface ExecutionCapabilities {
  /** Provider adapter id, as in `started.provider`. */
  readonly provider: string;
  readonly settings: ProviderSettingCapabilities;
}

/**
 * Checks requested settings against a provider's capabilities. Returns an actionable error message for the
 * first unsupported setting or value, or `undefined` when every setting can be applied.
 */
export function validateExecutionSettings(
  settings: ExecutionSettings | undefined,
  capabilities: ExecutionCapabilities,
): string | undefined {
  for (const name of EXECUTION_SETTING_NAMES) {
    const value = settings?.[name];
    if (value === undefined) continue;
    const capability = capabilities.settings[name];
    if (!capability) return `setting ${name} is not supported by ${capabilities.provider}`;
    if (!capability.options.includes(value)) {
      return `${name} "${value}" is not supported by ${capabilities.provider}; supported: ${capability.options.join(", ")}`;
    }
  }
  return undefined;
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

interface TerminalBase extends EventBase {
  /** Provider runtime session this execution ran in, when the provider reports one. */
  readonly providerSession?: ProviderSessionInfo;
}

export type ExecutionEvent =
  | (EventBase & {
      readonly type: "started";
      /** Provider adapter that runs this execution, e.g. `copilot-cli`. */
      readonly provider: string;
      /** Companion `instanceId` (see health); a different value after restart means this execution is lost. */
      readonly instanceId: string;
      readonly startedAt: string;
      /** Conversation the companion recorded this execution in (absent from companions before IMM-50). */
      readonly conversationId?: string;
      /** Settings applied to this execution, when any were requested. */
      readonly settings?: ExecutionSettings;
    })
  | (EventBase & { readonly type: "delta"; readonly text: string })
  | (TerminalBase & { readonly type: "completed"; readonly text: string })
  | (TerminalBase & { readonly type: "failed"; readonly error: ExecutionError })
  | (TerminalBase & { readonly type: "cancelled" });

export type TerminalExecutionEvent = Extract<ExecutionEvent, { type: "completed" | "failed" | "cancelled" }>;

export function isTerminalExecutionEvent(event: ExecutionEvent): event is TerminalExecutionEvent {
  return event.type === "completed" || event.type === "failed" || event.type === "cancelled";
}

/** Conversation IDs are companion-issued UUIDs; also keeps them safe to use as file names. */
const CONVERSATION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isConversationId(value: string): boolean {
  return CONVERSATION_ID.test(value);
}

export type ExecutionRequestResult = { ok: true; request: ExecutionRequest } | { ok: false; error: string };

const REQUEST_FIELDS = new Set(["prompt", "conversationId", "settings", "context"]);

function parseSettings(value: unknown): { ok: true; settings: ExecutionSettings } | { ok: false; error: string } {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, error: "settings must be a JSON object" };
  }
  const names: readonly string[] = EXECUTION_SETTING_NAMES;
  const unknownKeys = Object.keys(value).filter((k) => !names.includes(k));
  if (unknownKeys.length > 0) {
    return { ok: false, error: `unsupported settings: ${unknownKeys.join(", ")} (known: ${names.join(", ")})` };
  }
  const settings: Record<string, string> = {};
  for (const [name, v] of Object.entries(value)) {
    if (v === undefined || v === null) continue;
    if (typeof v !== "string" || v.trim() === "") return { ok: false, error: `setting ${name} must be a non-empty string` };
    settings[name] = v;
  }
  return { ok: true, settings };
}

/**
 * Validates an execution request body. Unknown fields are rejected rather than ignored, so a client never
 * believes a setting was applied when it was not.
 */
export function parseExecutionRequest(value: unknown): ExecutionRequestResult {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, error: "request body must be a JSON object" };
  }
  const unknownKeys = Object.keys(value).filter((k) => !REQUEST_FIELDS.has(k));
  if (unknownKeys.length > 0) return { ok: false, error: `unsupported request fields: ${unknownKeys.join(", ")}` };
  const { prompt, conversationId, settings, context } = value as {
    prompt?: unknown;
    conversationId?: unknown;
    settings?: unknown;
    context?: unknown;
  };
  if (typeof prompt !== "string" || prompt.trim() === "") return { ok: false, error: "prompt must be a non-empty string" };
  if (prompt.length > MAX_PROMPT_LENGTH) return { ok: false, error: `prompt exceeds ${MAX_PROMPT_LENGTH} characters` };
  if (conversationId !== undefined && (typeof conversationId !== "string" || !CONVERSATION_ID.test(conversationId))) {
    return { ok: false, error: "conversationId must be a conversation ID returned by the companion" };
  }
  let request: ExecutionRequest = { prompt, ...(conversationId !== undefined && { conversationId }) };
  if (settings !== undefined) {
    const parsed = parseSettings(settings);
    if (!parsed.ok) return parsed;
    if (Object.keys(parsed.settings).length > 0) request = { ...request, settings: parsed.settings };
  }
  if (context !== undefined) {
    const parsed = parseContext(context);
    if (typeof parsed === "string") return { ok: false, error: parsed };
    request = { ...request, context: parsed };
  }
  return { ok: true, request };
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
