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

export interface ExecutionRequest {
  readonly prompt: string;
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

export type ExecutionEvent =
  | (EventBase & {
      readonly type: "started";
      /** Provider adapter that runs this execution, e.g. `copilot-cli`. */
      readonly provider: string;
      /** Companion `instanceId` (see health); a different value after restart means this execution is lost. */
      readonly instanceId: string;
      readonly startedAt: string;
      /** Settings applied to this execution, when any were requested. */
      readonly settings?: ExecutionSettings;
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

const REQUEST_FIELDS = new Set(["prompt", "settings"]);

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
  const { prompt, settings } = value as { prompt?: unknown; settings?: unknown };
  if (typeof prompt !== "string" || prompt.trim() === "") return { ok: false, error: "prompt must be a non-empty string" };
  if (prompt.length > MAX_PROMPT_LENGTH) return { ok: false, error: `prompt exceeds ${MAX_PROMPT_LENGTH} characters` };
  if (settings === undefined) return { ok: true, request: { prompt } };
  const parsed = parseSettings(settings);
  if (!parsed.ok) return parsed;
  return { ok: true, request: Object.keys(parsed.settings).length > 0 ? { prompt, settings: parsed.settings } : { prompt } };
}
