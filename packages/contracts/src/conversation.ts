/**
 * Locally persisted Monocle conversations (since contract 0.2.0, IMM-50).
 *
 * A conversation groups the Cravat executions a user ran one after another. The companion records each
 * execution's prompt, final (or partial) response and outcome in a machine-local data directory — never in the
 * vault — so reopening Obsidian or restarting the companion restores the history ("UI resume").
 *
 * Whether the *provider* still remembers earlier turns is separate ("provider resume"): see
 * {@link ProviderSessionInfo}. Conversations do not sync between machines.
 */
import type { ExecutionError } from "./execution.js";

export const CONVERSATIONS_PATH = "/v1/conversations";

export function conversationPath(conversationId: string): string {
  return `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}`;
}

/**
 * How a provider runtime's own session relates to earlier executions of the conversation:
 * - `new`: the provider started a fresh session (first execution, or nothing to continue);
 * - `resumed`: the provider continued the session of an earlier execution, so it has that context;
 * - `unavailable`: an earlier session should have been continued but could not be (see `reason`), so this
 *   execution started a fresh provider session without the earlier context.
 */
export type ProviderSessionContinuity = "new" | "resumed" | "unavailable";

export interface ProviderSessionInfo {
  /** Provider-specific session ID (e.g. a Copilot CLI session); absent if the provider reported none. */
  readonly id?: string;
  readonly continuity: ProviderSessionContinuity;
  /** Why an earlier provider session was not continued (only when `continuity` is `unavailable`). */
  readonly reason?: string;
}

/**
 * Something an execution was given as context (e.g. the active note). Stored as a reference only, never the
 * referenced content.
 */
export interface ConversationContextReference {
  /** e.g. `note`, `selection`. */
  readonly kind: string;
  /** Vault-relative path, when the reference is a vault file. */
  readonly path?: string;
  readonly label?: string;
}

/**
 * - `running`: still executing on the companion instance recorded in `instanceId`;
 * - `interrupted`: was running when that companion instance stopped, so its outcome is unknown.
 */
export type ConversationExecutionStatus = "running" | "completed" | "failed" | "cancelled" | "interrupted";

export interface ConversationExecution {
  readonly executionId: string;
  readonly provider: string;
  /** Companion instance that ran the execution. */
  readonly instanceId: string;
  readonly startedAt: string;
  readonly endedAt?: string;
  readonly status: ConversationExecutionStatus;
  readonly prompt: string;
  /** Final text when completed; streamed text so far when cancelled or failed. */
  readonly response?: string;
  readonly error?: ExecutionError;
  readonly providerSession?: ProviderSessionInfo;
  readonly contextReferences: readonly ConversationContextReference[];
}

/** Body of `GET {@link conversationPath}(id)`. */
export interface Conversation {
  readonly id: string;
  readonly title: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  /** Oldest first. */
  readonly executions: readonly ConversationExecution[];
}

export interface ConversationSummary {
  readonly id: string;
  readonly title: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly executionCount: number;
}

/** Body of `GET {@link CONVERSATIONS_PATH}`; most recently updated first. */
export interface ConversationListResponse {
  readonly conversations: readonly ConversationSummary[];
}
