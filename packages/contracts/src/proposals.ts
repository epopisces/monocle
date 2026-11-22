/**
 * Session-scoped portable change proposals (IMM-53).
 *
 * A change set groups the proposed note changes produced by **one** Cravat execution (the "agent execution
 * session" of D06). Proposals are Monocle-owned, stored machine-locally (never in the vault) and never ingested
 * into the authoritative note index; applying them is a separate guarded step (IMM-54).
 *
 * The portable serialized form is {@link PortableChangeSet}. It carries only vault-relative paths and content, so a
 * change set can later move between hosts; synchronization itself is out of MVP scope.
 */

export const CHANGE_SETS_PATH = "/v1/change-sets";

export function changeSetPath(changeSetId: string): string {
  return `${CHANGE_SETS_PATH}/${encodeURIComponent(changeSetId)}`;
}

/** `format` of {@link PortableChangeSet}. */
export const CHANGE_SET_FORMAT = "monocle.change-set";
/** Bump on incompatible changes to the serialized shape. */
export const CHANGE_SET_FORMAT_VERSION = 1;

/**
 * - `create`: a new note at `path` (which must not exist);
 * - `modify`: replace the content of an existing note;
 * - `delete`: remove an existing note.
 */
export type ChangeOperation = "create" | "modify" | "delete";

/** Proposer's risk classification (D06). `low` may apply without review where policy allows; `high` needs review. */
export type ChangeRisk = "low" | "high";

/**
 * - `pending`: awaiting decision;
 * - `applied`: written to the vault;
 * - `rejected`: declined by the user;
 * - `conflicted`: the note no longer matches `base` (stale);
 * - `failed`: application was attempted and failed;
 * - `superseded`: replaced by a rebased proposal (see {@link ChangeProposal.predecessorId}).
 *
 * Only `pending` proposals can change status.
 */
export type ChangeStatus = "pending" | "applied" | "rejected" | "conflicted" | "failed" | "superseded";

/** `sha256:` followed by the lowercase hex SHA-256 of the UTF-8 content (no line-ending normalization). */
export type ContentHash = `sha256:${string}`;

/**
 * Note state the proposal was made against. `hash: null` means the note must not exist (`create`). For `modify`
 * and `delete`, `content` is the base text itself, so a reviewer can diff against it and a stale proposal can be
 * rebased even after the note changed on disk.
 */
export type ChangeBase = { readonly hash: null } | { readonly hash: ContentHash; readonly content: string };

/** `replace`: the complete proposed note content. `delete`: remove the note. */
export type ChangePatch = { readonly format: "replace"; readonly content: string } | { readonly format: "delete" };

export interface ChangeProposal {
  readonly id: string;
  readonly changeSetId: string;
  readonly executionId: string;
  readonly operation: ChangeOperation;
  /** Vault-relative, `/`-separated Markdown path. */
  readonly path: string;
  /** Persistent note ID (frontmatter), when the note has or will get one. */
  readonly noteId?: string;
  readonly base: ChangeBase;
  readonly patch: ChangePatch;
  readonly risk: ChangeRisk;
  readonly status: ChangeStatus;
  /** One-line human summary of the change. */
  readonly summary?: string;
  /** Proposal this one was rebased from (IMM-57). */
  readonly predecessorId?: string;
  readonly createdAt: string;
  readonly updatedAt: string;
}

/** All proposals of one execution. Body of `GET {@link changeSetPath}(id)`. */
export interface ChangeSet {
  readonly id: string;
  readonly executionId: string;
  /** Conversation the execution belongs to, when known. */
  readonly conversationId?: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  /** Oldest first. */
  readonly changes: readonly ChangeProposal[];
}

export interface PortableChangeSet {
  readonly format: typeof CHANGE_SET_FORMAT;
  readonly version: typeof CHANGE_SET_FORMAT_VERSION;
  readonly changeSet: ChangeSet;
}

export interface ChangeSetSummary {
  readonly id: string;
  readonly executionId: string;
  readonly conversationId?: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly counts: Readonly<Record<ChangeStatus, number>>;
}

/**
 * Body of `GET {@link CHANGE_SETS_PATH}`, optionally filtered by `?executionId=` and/or `?conversationId=`;
 * most recently updated first.
 */
export interface ChangeSetListResponse {
  readonly changeSets: readonly ChangeSetSummary[];
}

/** Vault-relative, `/`-separated `.md` path without drive, root, empty, `.` or `..` segments. */
export function isPortableNotePath(path: string): boolean {
  if (!path.toLowerCase().endsWith(".md") || /^[a-zA-Z]:|\\|^\//.test(path)) return false;
  return path.split("/").every((s) => s !== "" && s !== "." && s !== "..");
}
