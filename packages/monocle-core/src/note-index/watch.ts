import { statSync, watch, type FSWatcher } from "node:fs";
import { extname, join } from "node:path";
import type { NoteIndex, ReconcileReport } from "./note-index.js";

export interface WatchOptions {
  /** Quiet period after the last relevant event before reconciling. Default 500 ms. */
  debounceMs?: number;
  /**
   * Safety-net full reconciliation interval for events the OS watcher drops. Default 10 minutes;
   * 0 disables it. Startup reconciliation always runs.
   */
  rescanIntervalMs?: number;
  onReconcile?: (report: ReconcileReport) => void;
  onError?: (error: unknown) => void;
}

export interface VaultWatcher {
  /** Runs any pending debounced reconciliation immediately. */
  flush(): void;
  close(): void;
}

/**
 * Decides whether a raw watcher path may affect the index. Folder events (renames/deletes of
 * directories containing notes) must pass, so only definitely irrelevant paths are dropped.
 */
function mayAffectIndex(index: NoteIndex, event: string, rel: string): boolean {
  const path = rel.replace(/\\/g, "/");
  if (path.split("/").some((segment) => segment.startsWith("."))) return false;
  if (index.isIndexable(path)) return true;
  if (!index.isIndexable(`${path}/x.md`)) return false;
  try {
    // Directory "change" events only mean its listing changed; the entries emit their own events.
    return event === "rename" && statSync(join(index.vaultRoot, path)).isDirectory();
  } catch {
    // Gone: a deleted folder could have held notes; a deleted non-Markdown file could not.
    return extname(path) === "";
  }
}

/** Reconciles once on start, then after each debounced burst of relevant filesystem events. */
export function watchVault(index: NoteIndex, options: WatchOptions = {}): VaultWatcher {
  const debounceMs = options.debounceMs ?? 500;
  const rescanIntervalMs = options.rescanIntervalMs ?? 10 * 60 * 1000;
  let timer: NodeJS.Timeout | undefined;
  let closed = false;

  const run = (): void => {
    timer = undefined;
    if (closed) return;
    try {
      options.onReconcile?.(index.reconcile());
    } catch (error) {
      options.onError?.(error);
    }
  };
  const schedule = (): void => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(run, debounceMs);
  };

  run();

  const fsWatcher: FSWatcher = watch(index.vaultRoot, { recursive: true }, (event, filename) => {
    if (filename === null || mayAffectIndex(index, event, filename.toString())) schedule();
  });
  fsWatcher.on("error", (error) => options.onError?.(error));
  const interval = rescanIntervalMs > 0 ? setInterval(run, rescanIntervalMs) : undefined;
  interval?.unref();

  return {
    flush() {
      if (timer) {
        clearTimeout(timer);
        run();
      }
    },
    close() {
      closed = true;
      if (timer) clearTimeout(timer);
      if (interval) clearInterval(interval);
      fsWatcher.close();
    },
  };
}
