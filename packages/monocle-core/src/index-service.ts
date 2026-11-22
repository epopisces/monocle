import { join } from "node:path";
import type {
  IndexChangeCounts,
  IndexError,
  IndexHealth,
  IndexHealthLevel,
  IndexWarning,
} from "@monocle/contracts";
import { openNoteIndex, type NoteIndex, type ReconcileReport } from "./note-index/note-index.js";
import { watchVault, type VaultWatcher, type WatchOptions } from "./note-index/watch.js";
import type { SemanticIndex } from "./semantic/semantic-index.js";

export interface IndexServiceOptions {
  /** Absolute vault root (authoritative Markdown). */
  vaultRoot: string;
  /** Host-local directory for derived state (`index.db`, `semantic.db`). Never synchronized. */
  stateDir: string;
  idField?: string;
  excludeFolders?: readonly string[];
  /** Builds the optional semantic index (e.g. via `createSemanticIndexFromConfig`); omit for lexical only. */
  semantic?: (deps: { noteIndex: NoteIndex; statePath: string; onError: (error: Error) => void }) => SemanticIndex | undefined;
  /** Filesystem watching; `false` runs a single startup reconcile instead. */
  watch?: false | Pick<WatchOptions, "debounceMs" | "rescanIntervalMs">;
  /** Operational errors kept for display. Default 20. */
  maxErrors?: number;
}

/** Owns the derived indexes for one vault and reports their health (IMM-61). */
export interface IndexService {
  readonly noteIndex: NoteIndex;
  readonly semantic: SemanticIndex | undefined;
  health(): IndexHealth;
  /** Whole-vault reconcile; changed notes are queued for semantic indexing. */
  reconcile(): IndexChangeCounts;
  /** Rebuilds the lexical index now; the semantic rebuild continues in the background (see `health()`). */
  rebuild(): IndexChangeCounts;
  /** Re-reads one note from Markdown regardless of mtime and queues it for semantic indexing. */
  reindexNote(path: string): IndexChangeCounts;
  close(): void;
}

const counts = (r: ReconcileReport): IndexChangeCounts => ({
  added: r.added.length,
  updated: r.updated.length,
  moved: r.moved.length,
  deleted: r.deleted.length,
  unchanged: r.unchanged,
});

const message = (error: unknown): string => (error instanceof Error ? error.message : String(error));

export function openIndexService(options: IndexServiceOptions): IndexService {
  const maxErrors = options.maxErrors ?? 20;
  const noteIndex = openNoteIndex({
    vaultRoot: options.vaultRoot,
    dbPath: join(options.stateDir, "index.db"),
    ...(options.idField !== undefined && { idField: options.idField }),
    ...(options.excludeFolders !== undefined && { excludeFolders: options.excludeFolders }),
  });

  let errors: IndexError[] = [];
  let semanticErrorAt: string | null = null;
  let lastReconciledAt: string | null = null;
  let lastChanges: IndexChangeCounts | null = null;
  let warnings: IndexWarning[] = [];
  let brokenLinks = 0;

  const recordError = (source: IndexError["source"], error: unknown): void => {
    errors = [...errors, { source, message: message(error), at: new Date().toISOString() }].slice(-maxErrors);
  };

  const semantic = options.semantic?.({
    noteIndex,
    statePath: join(options.stateDir, "semantic.db"),
    onError: () => {
      semanticErrorAt = new Date().toISOString();
    },
  });

  const refreshDiagnostics = (): void => {
    warnings = [
      ...noteIndex
        .listNotes()
        .filter((n) => n.frontmatterError !== null)
        .map((n): IndexWarning => ({ kind: "frontmatter", message: `Invalid frontmatter: ${n.frontmatterError}`, paths: [n.path] })),
      ...noteIndex
        .duplicateIds()
        .map((d): IndexWarning => ({ kind: "duplicate-id", message: `Duplicate note ID "${d.id}"`, paths: d.paths })),
    ];
    brokenLinks = noteIndex.brokenLinks().length;
  };

  /** A successful whole-vault pass proves the index is current again, so earlier lexical errors are cleared. */
  const recordSuccess = (report: ReconcileReport): IndexChangeCounts => {
    lastReconciledAt = new Date().toISOString();
    lastChanges = counts(report);
    errors = [];
    refreshDiagnostics();
    return lastChanges;
  };

  const run = (source: IndexError["source"], op: () => ReconcileReport): IndexChangeCounts => {
    let report: ReconcileReport;
    try {
      report = op();
    } catch (error) {
      recordError(source, error);
      throw error;
    }
    semantic?.enqueue(report);
    return recordSuccess(report);
  };

  let watcher: VaultWatcher | undefined;
  if (options.watch === false) {
    try {
      run("reconcile", () => noteIndex.reconcile());
    } catch {
      // Recorded; health reports the index as unavailable until a reconcile succeeds.
    }
  } else {
    try {
      watcher = watchVault(noteIndex, {
        ...options.watch,
        onReconcile: (report) => {
          semantic?.enqueue(report);
          recordSuccess(report);
        },
        onError: (error) => recordError("watcher", error),
      });
    } catch (error) {
      recordError("watcher", error);
    }
  }

  const health = (): IndexHealth => {
    const s = semantic?.status();
    const allErrors: IndexError[] =
      s?.lastError ? [...errors, { source: "semantic", message: s.lastError, at: semanticErrorAt ?? new Date().toISOString() }] : errors;
    const level: IndexHealthLevel =
      lastReconciledAt === null
        ? "unavailable"
        : allErrors.length > 0
          ? "degraded"
          : s && (s.state === "pending" || s.state === "indexing")
            ? "indexing"
            : "healthy";
    const notes = lastReconciledAt === null ? 0 : noteIndex.listNotes().length;
    const queued = s ? s.pendingNotes + (s.fullResyncPending ? " + full resync" : "") : "";
    const summary = {
      unavailable: `Index unavailable${allErrors.length ? `: ${allErrors.at(-1)!.message}` : ""}`,
      degraded: `Index degraded: ${allErrors.at(-1)?.message ?? ""}`,
      indexing: `${notes} notes indexed · semantic indexing (${queued} queued)`,
      healthy: `${notes} notes indexed${s ? " · semantic up to date" : " · lexical only"}`,
    }[level];
    return {
      level,
      summary,
      lexical: { notes, lastReconciledAt, lastChanges, brokenLinks },
      semantic: {
        state: s?.state ?? "disabled",
        providerId: s?.providerId ?? null,
        storeId: s?.storeId ?? null,
        pendingNotes: s?.pendingNotes ?? 0,
        fullResyncPending: s?.fullResyncPending ?? false,
        indexedNotes: s?.indexedNotes ?? 0,
        indexedPassages: s?.indexedPassages ?? 0,
        lastIndexedAt: s?.lastIndexedAt ?? null,
        rebuildReason: s?.rebuildReason ?? null,
      },
      errors: allErrors,
      warnings,
      checkedAt: new Date().toISOString(),
    };
  };

  return {
    noteIndex,
    semantic,
    health,
    reconcile: () => run("reconcile", () => noteIndex.reconcile()),
    rebuild() {
      const changes = run("reconcile", () => noteIndex.rebuild());
      // Failures surface through semantic status (degraded + retry), so the promise is not awaited here.
      void semantic?.rebuild();
      return changes;
    },
    reindexNote(path) {
      const report = noteIndex.reindexNote(path);
      semantic?.enqueuePaths([path]);
      refreshDiagnostics();
      return counts(report);
    },
    close() {
      watcher?.close();
      semantic?.close();
      noteIndex.close();
    },
  };
}
