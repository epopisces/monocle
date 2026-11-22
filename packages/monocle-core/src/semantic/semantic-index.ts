import { createHash } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { parseNote } from "../note-index/markdown.js";
import type { NoteIndex, ReconcileReport } from "../note-index/note-index.js";
import { CHUNKER_VERSION, chunkNote, type ChunkOptions } from "./chunk.js";
import type { EmbeddingProvider, VectorRecord, VectorStore } from "./types.js";

/** Bump when the semantic state schema changes; a mismatch forces a semantic rebuild. */
const SEMANTIC_SCHEMA_VERSION = 1;

export interface SemanticIndexOptions {
  /** Foundational index; the semantic index follows its notes and never reads paths it doesn't list. */
  noteIndex: NoteIndex;
  provider: EmbeddingProvider;
  store: VectorStore;
  /** SQLite file for semantic bookkeeping (chunk ledger + embedding cache), or `:memory:`. Host-local. */
  statePath: string;
  /** Delay after an enqueue before background indexing starts. Default 5000 ms. */
  delayMs?: number;
  /** Maximum passages per embedding request. Default 32. */
  batchSize?: number;
  /** Queue bound; overflowing collapses the queue into a single full resync. Default 1000 notes. */
  maxPending?: number;
  /** Delay before retrying after a provider or store failure. Default 60000 ms. */
  retryMs?: number;
  chunk?: ChunkOptions;
  onError?: (error: Error) => void;
}

export type SemanticState = "idle" | "pending" | "indexing" | "degraded";

export interface SemanticStatus {
  state: SemanticState;
  providerId: string;
  storeId: string;
  /** Notes waiting to be (re)embedded or removed. */
  pendingNotes: number;
  /** A whole-vault comparison is queued (startup, overflow, rebuild). */
  fullResyncPending: boolean;
  indexedNotes: number;
  indexedPassages: number;
  /** Last provider/store failure; cleared by the next successful run. */
  lastError: string | null;
  /** ISO time of the last run that completed without error. */
  lastIndexedAt: string | null;
  /** Why a rebuild is in progress (initial build, model change, manual); null otherwise. */
  rebuildReason: string | null;
}

export interface PassageHit {
  passageId: string;
  path: string;
  noteId: string | null;
  title: string;
  heading: string;
  text: string;
  /** Cosine distance; lower is closer. */
  distance: number;
  /** The note changed since this passage was embedded and is queued for re-embedding. */
  stale: boolean;
}

export interface SemanticIndex {
  readonly providerId: string;
  /** Queues the notes touched by a foundational reconcile. */
  enqueue(report: ReconcileReport): void;
  enqueuePaths(paths: readonly string[]): void;
  /** Queues a whole-vault comparison against the foundational index. */
  enqueueAll(): void;
  /** Processes everything queued now, skipping the delay. Failures surface via `status()` and `onError`. */
  drain(): Promise<void>;
  /** Drops all vectors and re-embeds every note. */
  rebuild(): Promise<void>;
  /** Nearest passages to `query`. Throws when the provider or store is unavailable. */
  search(query: string, options?: { limit?: number }): Promise<PassageHit[]>;
  status(): SemanticStatus;
  close(): void;
}

interface ChunkRow {
  passage_id: string;
  text_hash: string;
}

export function openSemanticIndex(options: SemanticIndexOptions): SemanticIndex {
  const { noteIndex, provider, store } = options;
  const delayMs = options.delayMs ?? 5000;
  const batchSize = Math.max(1, options.batchSize ?? 32);
  const maxPending = Math.max(1, options.maxPending ?? 1000);
  const retryMs = options.retryMs ?? 60000;
  const chunkOptions = options.chunk ?? {};
  if (options.statePath !== ":memory:") mkdirSync(dirname(options.statePath), { recursive: true });

  const db = new DatabaseSync(options.statePath);
  db.exec(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notes (path TEXT PRIMARY KEY, note_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chunks (
      passage_id TEXT PRIMARY KEY,
      path TEXT NOT NULL,
      text_hash TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
    CREATE TABLE IF NOT EXISTS embeddings (text_hash TEXT PRIMARY KEY, vector TEXT NOT NULL);
  `);

  const fingerprint = {
    schema: SEMANTIC_SCHEMA_VERSION,
    chunker: CHUNKER_VERSION,
    maxChars: chunkOptions.maxChars ?? null,
    provider: provider.id,
    store: store.id,
  };
  const q = {
    getMeta: db.prepare("SELECT value FROM meta WHERE key = ?"),
    setMeta: db.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)"),
    delMeta: db.prepare("DELETE FROM meta WHERE key = ?"),
    notePaths: db.prepare("SELECT path FROM notes"),
    noteHash: db.prepare("SELECT note_hash FROM notes WHERE path = ?"),
    upsertNote: db.prepare("INSERT OR REPLACE INTO notes (path, note_hash) VALUES (?, ?)"),
    deleteNote: db.prepare("DELETE FROM notes WHERE path = ?"),
    chunksByPath: db.prepare("SELECT passage_id, text_hash FROM chunks WHERE path = ?"),
    insertChunk: db.prepare("INSERT OR REPLACE INTO chunks (passage_id, path, text_hash) VALUES (?, ?, ?)"),
    deleteChunks: db.prepare("DELETE FROM chunks WHERE path = ?"),
    getVector: db.prepare("SELECT vector FROM embeddings WHERE text_hash = ?"),
    putVector: db.prepare("INSERT OR REPLACE INTO embeddings (text_hash, vector) VALUES (?, ?)"),
    prune: db.prepare("DELETE FROM embeddings WHERE text_hash NOT IN (SELECT text_hash FROM chunks)"),
    countNotes: db.prepare("SELECT COUNT(*) AS n FROM notes"),
    countChunks: db.prepare("SELECT COUNT(*) AS n FROM chunks"),
  };

  const clearState = (): void => {
    db.exec("DELETE FROM notes; DELETE FROM chunks; DELETE FROM embeddings;");
    // The fingerprint is only rewritten after the store has been reset, so a crash in between re-resets.
    q.delMeta.run("fingerprint");
  };

  const pending = new Set<string>();
  // Startup reconciliation: compare everything once; notes whose hash is unchanged are skipped cheaply.
  let fullResync = true;
  let needsReset = false;
  let rebuildReason: string | null = null;
  let lastError: string | null = null;
  let lastIndexedAt: string | null = (q.getMeta.get("lastIndexedAt") as { value: string } | undefined)?.value ?? null;
  let running: Promise<void> | null = null;
  let timer: NodeJS.Timeout | null = null;
  let closed = false;

  const stored = (q.getMeta.get("fingerprint") as { value: string } | undefined)?.value;
  if (stored !== JSON.stringify(fingerprint)) {
    const previous = stored ? (JSON.parse(stored) as typeof fingerprint) : undefined;
    rebuildReason = !previous
      ? "initial build"
      : previous.provider !== provider.id
        ? `embedding model changed (${previous.provider} → ${provider.id})`
        : previous.store !== store.id
          ? `vector store changed (${previous.store} → ${store.id})`
          : "semantic index format changed";
    clearState();
    needsReset = true;
  }

  const schedule = (ms: number): void => {
    if (timer || closed) return;
    timer = setTimeout(() => {
      timer = null;
      void drain();
    }, ms);
    timer.unref?.();
  };

  const enqueuePaths = (paths: readonly string[]): void => {
    for (const path of paths) pending.add(path);
    if (pending.size > maxPending) {
      pending.clear();
      fullResync = true;
    }
    if (paths.length) schedule(delayMs);
  };

  const embedMissing = async (texts: Map<string, string>): Promise<Map<string, number[]>> => {
    const vectors = new Map<string, number[]>();
    const missing: [string, string][] = [];
    for (const [hash, text] of texts) {
      const cached = q.getVector.get(hash) as { vector: string } | undefined;
      if (cached) vectors.set(hash, JSON.parse(cached.vector) as number[]);
      else missing.push([hash, text]);
    }
    for (let i = 0; i < missing.length; i += batchSize) {
      const batch = missing.slice(i, i + batchSize);
      const out = await provider.embed(batch.map(([, text]) => text));
      if (out.length !== batch.length) throw new Error(`${provider.id} returned ${out.length} of ${batch.length} vectors`);
      batch.forEach(([hash], j) => vectors.set(hash, out[j]!));
    }
    return vectors;
  };

  const processNote = async (path: string): Promise<void> => {
    const previous = q.chunksByPath.all(path) as unknown as ChunkRow[];
    const note = noteIndex.getNote(path);
    if (!note) {
      if (previous.length) await store.delete(previous.map((r) => r.passage_id));
      db.exec("BEGIN");
      q.deleteChunks.run(path);
      q.deleteNote.run(path);
      db.exec("COMMIT");
      return;
    }
    const known = q.noteHash.get(path) as { note_hash: string } | undefined;
    if (known?.note_hash === note.hash) return;

    let bytes: Buffer;
    try {
      bytes = readFileSync(join(noteIndex.vaultRoot, path));
    } catch (error) {
      // Vanished since the last foundational reconcile; the next report will carry the delete.
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
      throw error;
    }
    const noteHash = createHash("sha256").update(bytes).digest("hex");
    const chunks = chunkNote(path, parseNote(bytes.toString("utf8")).body, chunkOptions);
    const vectors = await embedMissing(new Map(chunks.map((c) => [c.textHash, c.text])));
    const records: VectorRecord[] = chunks.map((c) => ({
      id: c.passageId,
      vector: vectors.get(c.textHash)!,
      text: c.text,
      metadata: { path, noteId: note.id, noteHash, heading: c.heading, ordinal: c.ordinal, textHash: c.textHash },
    }));
    const keep = new Set(records.map((r) => r.id));
    const removed = previous.map((r) => r.passage_id).filter((id) => !keep.has(id));
    if (records.length) await store.upsert(records);
    if (removed.length) await store.delete(removed);

    db.exec("BEGIN");
    for (const [hash, vector] of vectors) q.putVector.run(hash, JSON.stringify(vector));
    q.deleteChunks.run(path);
    for (const c of chunks) q.insertChunk.run(c.passageId, path, c.textHash);
    q.upsertNote.run(path, noteHash);
    db.exec("COMMIT");
  };

  const runOnce = async (): Promise<void> => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    try {
      if (needsReset) {
        await store.reset();
        needsReset = false;
        q.setMeta.run("fingerprint", JSON.stringify(fingerprint));
      }
      if (fullResync) {
        for (const note of noteIndex.listNotes()) pending.add(note.path);
        for (const row of q.notePaths.all() as unknown as { path: string }[]) pending.add(row.path);
        fullResync = false;
      }
      while (pending.size && !closed) {
        const path = pending.values().next().value!;
        await processNote(path);
        pending.delete(path);
      }
      if (closed) return;
      q.prune.run();
      lastError = null;
      rebuildReason = null;
      lastIndexedAt = new Date().toISOString();
      q.setMeta.run("lastIndexedAt", lastIndexedAt);
    } catch (error) {
      if (closed) return;
      if (db.isTransaction) db.exec("ROLLBACK");
      const err = error instanceof Error ? error : new Error(String(error));
      lastError = err.message;
      options.onError?.(err);
      schedule(retryMs);
    }
  };

  const drain = async (): Promise<void> => {
    while (running) await running;
    if (closed) return;
    running = runOnce().finally(() => {
      running = null;
    });
    await running;
  };

  schedule(delayMs);

  return {
    providerId: provider.id,
    enqueue(report) {
      enqueuePaths([
        ...report.added,
        ...report.updated,
        ...report.deleted,
        ...report.moved.flatMap((m) => [m.from, m.to]),
      ]);
    },
    enqueuePaths,
    enqueueAll() {
      fullResync = true;
      schedule(delayMs);
    },
    drain,
    async rebuild() {
      while (running) await running;
      clearState();
      pending.clear();
      needsReset = true;
      fullResync = true;
      rebuildReason = "manual rebuild";
      await drain();
    },
    async search(query, { limit = 10 } = {}) {
      if (!query.trim()) return [];
      if (needsReset) throw new Error(`semantic index is rebuilding (${rebuildReason ?? "reset pending"})`);
      const [vector] = await provider.embed([query]);
      if (!vector) throw new Error(`${provider.id} returned no query vector`);
      const hits: PassageHit[] = [];
      for (const m of await store.query(vector, limit * 2)) {
        const note = noteIndex.getNote(m.metadata.path);
        if (!note) continue;
        hits.push({
          passageId: m.id,
          path: m.metadata.path,
          noteId: note.id,
          title: note.title,
          heading: m.metadata.heading,
          text: m.text,
          distance: m.distance,
          stale: note.hash !== m.metadata.noteHash,
        });
        if (hits.length === limit) break;
      }
      return hits;
    },
    status() {
      const queued = pending.size > 0 || fullResync || needsReset;
      return {
        state: running ? "indexing" : lastError ? "degraded" : queued ? "pending" : "idle",
        providerId: provider.id,
        storeId: store.id,
        pendingNotes: pending.size,
        fullResyncPending: fullResync,
        indexedNotes: (q.countNotes.get() as { n: number }).n,
        indexedPassages: (q.countChunks.get() as { n: number }).n,
        lastError,
        lastIndexedAt,
        rebuildReason,
      };
    },
    close() {
      if (closed) return;
      closed = true;
      if (timer) clearTimeout(timer);
      timer = null;
      db.close();
    },
  };
}
