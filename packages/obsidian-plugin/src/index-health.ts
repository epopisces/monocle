import {
  INDEX_HEALTH_PATH,
  INDEX_REBUILD_PATH,
  INDEX_RECONCILE_PATH,
  INDEX_REINDEX_NOTE_PATH,
  isIndexHealth,
  type IndexActionResponse,
  type IndexChangeCounts,
  type IndexHealth,
  type IndexHealthLevel,
} from "@monocle/contracts";
import type { ConnectionState } from "./connection.js";

/** HTTP port for companion calls. Obsidian backs it with `requestUrl`; tests use `fetch`. */
export type CompanionRequest = (request: {
  url: string;
  method: "GET" | "POST";
  body?: unknown;
}) => Promise<{ status: number; json: unknown }>;

/** What the compact indicator and the expanded panel render. */
export interface IndexView {
  readonly level: IndexHealthLevel;
  /** Short status-bar text. */
  readonly label: string;
  /** One-line explanation (tooltip / panel subtitle). */
  readonly detail: string;
  /** Last snapshot from the companion; absent while unavailable. */
  readonly health?: IndexHealth;
}

export interface ActionResult {
  readonly ok: boolean;
  readonly message: string;
}

export interface IndexHealthMonitorOptions {
  readonly request: CompanionRequest;
  /** Polling interval while connected. Default 5000 ms. */
  readonly intervalMs?: number;
}

function labelFor(health: IndexHealth): string {
  switch (health.level) {
    case "healthy":
      return "Index healthy";
    case "indexing": {
      const { pendingNotes, fullResyncPending } = health.semantic;
      return fullResyncPending ? "Indexing…" : `Indexing (${pendingNotes} queued)`;
    }
    case "degraded":
      return "Index degraded";
    case "unavailable":
      return "Index unavailable";
  }
}

const unavailable = (detail: string): IndexView => ({ level: "unavailable", label: "Index unavailable", detail });

const describeChanges = (c: IndexChangeCounts): string =>
  `${c.added} added, ${c.updated} updated, ${c.moved} moved, ${c.deleted} deleted`;

const errorOf = (json: unknown, status: number): string =>
  typeof json === "object" && json !== null && typeof (json as { error?: unknown }).error === "string"
    ? (json as { error: string }).error
    : `HTTP ${status}`;

/**
 * Polls the companion's index health while connected and runs maintenance actions. Obsidian-free:
 * `main.ts` feeds it connection changes and renders {@link IndexView}.
 */
export class IndexHealthMonitor {
  private readonly request: CompanionRequest;
  private readonly intervalMs: number;
  private readonly listeners = new Set<(view: IndexView) => void>();
  private connection: ConnectionState | undefined;
  private current: IndexView = unavailable("Companion not connected");
  private timer: ReturnType<typeof setTimeout> | undefined;
  private generation = 0;

  constructor(options: IndexHealthMonitorOptions) {
    this.request = options.request;
    this.intervalMs = options.intervalMs ?? 5_000;
  }

  get view(): IndexView {
    return this.current;
  }

  /** Subscribes to view changes; the listener is called immediately with the current view. */
  onChange(listener: (view: IndexView) => void): () => void {
    this.listeners.add(listener);
    listener(this.current);
    return () => this.listeners.delete(listener);
  }

  /** Starts or stops polling to follow the companion connection. Resolves after the first refresh. */
  async setConnection(state: ConnectionState): Promise<void> {
    this.connection = state;
    this.clearTimer();
    const generation = ++this.generation;
    if (state.kind !== "connected") {
      const reason =
        state.kind === "disconnected"
          ? `Companion disconnected: ${state.error}`
          : state.kind === "incompatible"
            ? state.error
            : "Connecting to companion…";
      this.set(unavailable(reason));
      return;
    }
    await this.refresh();
    if (generation === this.generation) this.schedule(generation);
  }

  /** Fetches health now. Never throws. */
  async refresh(): Promise<IndexView> {
    const endpoint = this.endpoint();
    if (!endpoint) return this.current;
    try {
      const res = await this.request({ url: new URL(INDEX_HEALTH_PATH, endpoint).href, method: "GET" });
      if (this.endpoint() !== endpoint) return this.current;
      if (res.status === 404) {
        this.set(unavailable("Companion has no vault configured (start it with --vault <path>)"));
      } else if (res.status !== 200 || !isIndexHealth(res.json)) {
        this.set(unavailable(`Index health check failed: ${errorOf(res.json, res.status)}`));
      } else {
        this.set({ level: res.json.level, label: labelFor(res.json), detail: res.json.summary, health: res.json });
      }
    } catch (err) {
      this.set(unavailable(`Index health check failed: ${err instanceof Error ? err.message : String(err)}`));
    }
    return this.current;
  }

  reconcile(): Promise<ActionResult> {
    return this.act(INDEX_RECONCILE_PATH, {}, (c) => `Reconciled: ${describeChanges(c)}`);
  }

  /** Discards and rebuilds all derived indexes. Callers must confirm with the user first. */
  rebuild(): Promise<ActionResult> {
    return this.act(INDEX_REBUILD_PATH, {}, (c) => `Rebuilt: ${c.added} notes indexed`);
  }

  reindexNote(path: string): Promise<ActionResult> {
    return this.act(INDEX_REINDEX_NOTE_PATH, { path }, (c) =>
      c.deleted ? `Removed ${path} from the index` : `Reindexed ${path}: ${describeChanges(c)}`,
    );
  }

  stop(): void {
    this.generation++;
    this.clearTimer();
  }

  private async act(path: string, body: object, describe: (c: IndexChangeCounts) => string): Promise<ActionResult> {
    const endpoint = this.endpoint();
    if (!endpoint) return { ok: false, message: "Companion not connected" };
    try {
      const res = await this.request({ url: new URL(path, endpoint).href, method: "POST", body });
      const json = res.json as Partial<IndexActionResponse> | undefined;
      if (json && isIndexHealth(json.health)) {
        this.set({ level: json.health.level, label: labelFor(json.health), detail: json.health.summary, health: json.health });
      }
      if (res.status !== 200 || !json?.changes) return { ok: false, message: errorOf(res.json, res.status) };
      return { ok: true, message: describe(json.changes) };
    } catch (err) {
      return { ok: false, message: err instanceof Error ? err.message : String(err) };
    }
  }

  private endpoint(): string | undefined {
    return this.connection?.kind === "connected" ? this.connection.endpoint : undefined;
  }

  private schedule(generation: number): void {
    this.timer = setTimeout(() => {
      void this.refresh().then(() => {
        if (generation === this.generation) this.schedule(generation);
      });
    }, this.intervalMs);
  }

  private clearTimer(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
  }

  private set(next: IndexView): void {
    this.current = next;
    for (const l of this.listeners) l(next);
  }
}
