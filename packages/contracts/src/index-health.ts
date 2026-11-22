/**
 * Index health and maintenance contract (IMM-61). Additive to the companion transport: a companion
 * without an index service answers these routes with 404, which clients show as "unavailable".
 */

/** `GET` → {@link IndexHealth}. */
export const INDEX_HEALTH_PATH = "/v1/index/health";
/** `POST` (no body) → {@link IndexActionResponse}. Whole-vault reconcile; cheap, no confirmation needed. */
export const INDEX_RECONCILE_PATH = "/v1/index/reconcile";
/** `POST` (no body) → {@link IndexActionResponse}. Discards and rebuilds all derived indexes from Markdown. */
export const INDEX_REBUILD_PATH = "/v1/index/rebuild";
/** `POST` {@link ReindexNoteRequest} → {@link IndexActionResponse}. Re-reads one note regardless of mtime. */
export const INDEX_REINDEX_NOTE_PATH = "/v1/index/reindex-note";

/**
 * At-a-glance level. `unavailable` means the lexical index cannot serve (never built, vault unreadable,
 * or — client-side — companion unreachable / without an index service).
 */
export type IndexHealthLevel = "healthy" | "indexing" | "degraded" | "unavailable";

export type SemanticHealthState = "disabled" | "idle" | "pending" | "indexing" | "degraded";

export interface IndexChangeCounts {
  readonly added: number;
  readonly updated: number;
  readonly moved: number;
  readonly deleted: number;
  readonly unchanged: number;
}

/** Operational failure (reconcile, watcher, semantic). Errors make the index `degraded`. */
export interface IndexError {
  readonly source: "reconcile" | "watcher" | "semantic";
  readonly message: string;
  /** ISO-8601 time the error was recorded. */
  readonly at: string;
}

/** Vault content problem found while indexing; informational, does not degrade the index. */
export interface IndexWarning {
  readonly kind: "frontmatter" | "duplicate-id";
  readonly message: string;
  readonly paths: readonly string[];
}

export interface IndexHealth {
  readonly level: IndexHealthLevel;
  /** One-line human summary for the compact indicator tooltip. */
  readonly summary: string;
  readonly lexical: {
    readonly notes: number;
    /** ISO time of the last successful reconcile/rebuild/reindex; null before the first one. */
    readonly lastReconciledAt: string | null;
    readonly lastChanges: IndexChangeCounts | null;
    readonly brokenLinks: number;
  };
  readonly semantic: {
    readonly state: SemanticHealthState;
    readonly providerId: string | null;
    readonly storeId: string | null;
    /** Queue depth: notes waiting to be (re)embedded or removed. */
    readonly pendingNotes: number;
    readonly fullResyncPending: boolean;
    readonly indexedNotes: number;
    readonly indexedPassages: number;
    readonly lastIndexedAt: string | null;
    readonly rebuildReason: string | null;
  };
  /** Most recent operational errors, newest last (bounded). */
  readonly errors: readonly IndexError[];
  readonly warnings: readonly IndexWarning[];
  /** ISO time this snapshot was taken. */
  readonly checkedAt: string;
}

export interface ReindexNoteRequest {
  /** Vault-relative note path with `/` separators. */
  readonly path: string;
}

export interface IndexActionResponse {
  readonly changes: IndexChangeCounts;
  readonly health: IndexHealth;
}

export function isIndexHealth(value: unknown): value is IndexHealth {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    ["healthy", "indexing", "degraded", "unavailable"].includes(v.level as string) &&
    typeof v.summary === "string" &&
    typeof v.lexical === "object" &&
    v.lexical !== null &&
    typeof v.semantic === "object" &&
    v.semantic !== null &&
    Array.isArray(v.errors) &&
    Array.isArray(v.warnings)
  );
}
