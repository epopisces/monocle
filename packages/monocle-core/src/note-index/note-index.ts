import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { extractLinks, type ExtractedLink } from "./links.js";
import { frontmatterText, noteId, noteTitle, parseNote } from "./markdown.js";
import { matchesFilter, type NoteFilter } from "./metadata.js";
import { createLinkStore, type NoteLink } from "./relationships.js";
import { isIndexablePath, scanVault, type ScanOptions } from "./scan.js";

/** Bump when the on-disk schema or derived content changes; a mismatch forces a rebuild from Markdown. */
const SCHEMA_VERSION = 2;

export interface NoteIndexOptions {
  /** Absolute path of the vault root (authoritative Markdown). */
  vaultRoot: string;
  /** SQLite file for the derived index, or `:memory:`. Host-local; never synchronized. */
  dbPath: string;
  /**
   * Frontmatter field holding the persistent note ID. Defaults to `id`, which is a provisional
   * placeholder until real-vault discovery confirms the field name.
   */
  idField?: string;
  /** Vault-relative folders to skip (e.g. templates). Dot-folders such as `.obsidian` are always skipped. */
  excludeFolders?: readonly string[];
}

export interface IndexedNote {
  /** Vault-relative path with `/` separators. */
  path: string;
  /** Persistent note ID from frontmatter, or null for legacy/unidentified notes. */
  id: string | null;
  title: string;
  /** SHA-256 of the file's bytes. */
  hash: string;
  frontmatter: Record<string, unknown>;
  frontmatterError: string | null;
}

export interface NoteMove {
  from: string;
  to: string;
}

export interface ReconcileReport {
  added: string[];
  updated: string[];
  moved: NoteMove[];
  deleted: string[];
  unchanged: number;
}

export interface SearchHit {
  path: string;
  id: string | null;
  title: string;
  /** Excerpt with matches wrapped in `[` `]`. */
  snippet: string;
  /** bm25 score; lower is more relevant. */
  score: number;
}

export interface SearchOptions {
  limit?: number;
}

export interface DuplicateId {
  id: string;
  paths: string[];
}

export class DuplicateNoteIdError extends Error {
  constructor(
    readonly id: string,
    readonly conflictingPaths: string[],
  ) {
    super(`Note ID "${id}" is already used by: ${conflictingPaths.join(", ")}`);
    this.name = "DuplicateNoteIdError";
  }
}

export class InvalidNotePathError extends Error {
  constructor(readonly path: string) {
    super(`"${path}" is not an indexable note path`);
    this.name = "InvalidNotePathError";
  }
}

export interface NoteIndex {
  readonly vaultRoot: string;
  /** True when a vault-relative path would be indexed (Markdown, not in a dot- or excluded folder). */
  isIndexable(path: string): boolean;
  /** Brings the index in line with the vault: adds, updates, moves and deletes. Safe to call any time. */
  reconcile(): ReconcileReport;
  /** Discards all derived state and re-indexes every note from Markdown. */
  rebuild(): ReconcileReport;
  /**
   * Re-reads one note from Markdown regardless of its mtime/size, or drops it when the file is gone.
   * Throws for paths that are not indexable notes. Does not detect moves (use `reconcile`).
   */
  reindexNote(path: string): ReconcileReport;
  /** Exact full-text search over title, frontmatter values and body. All terms must match. */
  search(query: string, options?: SearchOptions): SearchHit[];
  listNotes(): IndexedNote[];
  getNote(path: string): IndexedNote | undefined;
  findById(id: string): IndexedNote[];
  /** Legacy duplicate IDs present in the vault (diagnosis only; they are still indexed). */
  duplicateIds(): DuplicateId[];
  /**
   * Rejects a managed mutation that would give `path` an ID already used by another note.
   * Reflects the index as of the last reconcile, so callers should reconcile first.
   */
  assertNoteIdAvailable(id: string, path: string): void;
  /** Notes whose metadata matches every condition of `filter`, ordered by path. */
  findNotes(filter: NoteFilter): IndexedNote[];
  /** Explicit links written in the note at `path` (body wikilinks/embeds and wikilink-valued frontmatter), in order. */
  links(path: string): NoteLink[];
  /** Resolved explicit links from other notes (or itself) that point to the note at `path`. */
  backlinks(path: string): NoteLink[];
  /** Unresolved and ambiguous links across the vault (missing attachments are not included). */
  brokenLinks(): NoteLink[];
  close(): void;
}

interface NoteRow {
  rowid: number;
  path: string;
  note_id: string | null;
  title: string;
  hash: string;
  mtime_ms: number;
  size: number;
  frontmatter: string;
  frontmatter_error: string | null;
}

const sha256 = (data: Buffer): string => createHash("sha256").update(data).digest("hex");

function toNote(row: NoteRow): IndexedNote {
  return {
    path: row.path,
    id: row.note_id,
    title: row.title,
    hash: row.hash,
    frontmatter: JSON.parse(row.frontmatter) as Record<string, unknown>,
    frontmatterError: row.frontmatter_error,
  };
}

/** Quotes each whitespace-separated term as an FTS5 string so user input never becomes query syntax. */
function toFtsQuery(query: string): string {
  return query
    .split(/\s+/)
    .filter(Boolean)
    .map((term) => `"${term.replace(/"/g, '""')}"`)
    .join(" ");
}

export function openNoteIndex(options: NoteIndexOptions): NoteIndex {
  const idField = options.idField ?? "id";
  const scan: ScanOptions = { excludeFolders: options.excludeFolders ?? [] };
  if (options.dbPath !== ":memory:") mkdirSync(dirname(options.dbPath), { recursive: true });

  const db = new DatabaseSync(options.dbPath);
  db.exec(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notes (
      rowid INTEGER PRIMARY KEY,
      path TEXT NOT NULL UNIQUE,
      note_id TEXT,
      title TEXT NOT NULL,
      hash TEXT NOT NULL,
      mtime_ms REAL NOT NULL,
      size INTEGER NOT NULL,
      frontmatter TEXT NOT NULL,
      frontmatter_error TEXT
    );
    CREATE INDEX IF NOT EXISTS notes_note_id ON notes(note_id);
    CREATE INDEX IF NOT EXISTS notes_hash ON notes(hash);
    CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, frontmatter, body, tokenize = 'unicode61');
  `);

  const fingerprint = JSON.stringify({
    schema: SCHEMA_VERSION,
    idField,
    excludeFolders: [...scan.excludeFolders].sort(),
  });
  const stored = db.prepare("SELECT value FROM meta WHERE key = 'fingerprint'").get() as { value: string } | undefined;
  const linkStore = createLinkStore(db);
  const clear = (): void => {
    db.exec("DELETE FROM notes; DELETE FROM notes_fts;");
    linkStore.clear();
  };
  if (stored?.value !== fingerprint) {
    clear();
    db.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('fingerprint', ?)").run(fingerprint);
  }

  const q = {
    all: db.prepare("SELECT * FROM notes ORDER BY path"),
    byPath: db.prepare("SELECT * FROM notes WHERE path = ?"),
    byId: db.prepare("SELECT * FROM notes WHERE note_id = ? ORDER BY path"),
    insert: db.prepare(
      `INSERT INTO notes (path, note_id, title, hash, mtime_ms, size, frontmatter, frontmatter_error)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ),
    update: db.prepare(
      `UPDATE notes SET path = ?, note_id = ?, title = ?, hash = ?, mtime_ms = ?, size = ?,
       frontmatter = ?, frontmatter_error = ? WHERE rowid = ?`,
    ),
    touch: db.prepare("UPDATE notes SET path = ?, mtime_ms = ?, size = ? WHERE rowid = ?"),
    remove: db.prepare("DELETE FROM notes WHERE rowid = ?"),
    ftsInsert: db.prepare("INSERT INTO notes_fts (rowid, title, frontmatter, body) VALUES (?, ?, ?, ?)"),
    ftsRemove: db.prepare("DELETE FROM notes_fts WHERE rowid = ?"),
    duplicates: db.prepare(
      `SELECT note_id, path FROM notes WHERE note_id IN
         (SELECT note_id FROM notes WHERE note_id IS NOT NULL GROUP BY note_id HAVING COUNT(*) > 1)
       ORDER BY note_id, path`,
    ),
    search: db.prepare(
      `SELECT n.path, n.note_id, n.title, snippet(notes_fts, -1, '[', ']', '…', 12) AS snippet,
              bm25(notes_fts) AS score
       FROM notes_fts JOIN notes n ON n.rowid = notes_fts.rowid
       WHERE notes_fts MATCH ? ORDER BY score, n.path LIMIT ?`,
    ),
  };

  interface Loaded {
    path: string;
    mtimeMs: number;
    size: number;
    hash: string;
    id: string | null;
    title: string;
    frontmatter: Record<string, unknown>;
    frontmatterError: string | null;
    body: string;
    links: ExtractedLink[];
  }

  const load = (path: string, mtimeMs: number, size: number): Loaded | undefined => {
    let bytes: Buffer;
    try {
      bytes = readFileSync(join(options.vaultRoot, path));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
      throw error;
    }
    const content = bytes.toString("utf8");
    const parsed = parseNote(content);
    return {
      path,
      mtimeMs,
      size,
      hash: sha256(bytes),
      id: noteId(parsed, idField),
      title: noteTitle(parsed, path),
      frontmatter: parsed.frontmatter,
      frontmatterError: parsed.frontmatterError,
      body: parsed.body,
      links: extractLinks(content, parsed),
    };
  };

  const writeFts = (rowid: number | bigint, note: Loaded): void => {
    q.ftsRemove.run(rowid);
    q.ftsInsert.run(rowid, note.title, frontmatterText(note.frontmatter), note.body);
    linkStore.replace(rowid, note.links);
  };

  const rowValues = (n: Loaded) =>
    [n.path, n.id, n.title, n.hash, n.mtimeMs, n.size, JSON.stringify(n.frontmatter), n.frontmatterError] as const;

  const reconcile = (): ReconcileReport => {
    const report: ReconcileReport = { added: [], updated: [], moved: [], deleted: [], unchanged: 0 };
    db.exec("BEGIN");
    try {
      const existing = new Map((q.all.all() as unknown as NoteRow[]).map((r) => [r.path, r]));
      const fresh: Loaded[] = [];

      for (const file of scanVault(options.vaultRoot, scan)) {
        const row = existing.get(file.path);
        if (row) {
          existing.delete(file.path);
          if (row.mtime_ms === file.mtimeMs && row.size === file.size) {
            report.unchanged++;
            continue;
          }
          const note = load(file.path, file.mtimeMs, file.size);
          if (!note) {
            existing.set(file.path, row);
          } else if (note.hash === row.hash) {
            q.touch.run(note.path, note.mtimeMs, note.size, row.rowid);
            report.unchanged++;
          } else {
            q.update.run(...rowValues(note), row.rowid);
            writeFts(row.rowid, note);
            report.updated.push(note.path);
          }
        } else {
          const note = load(file.path, file.mtimeMs, file.size);
          if (note) fresh.push(note);
        }
      }

      // Paths left in `existing` vanished; pair them with new paths by persistent ID, then by content hash.
      const vanished = [...existing.values()];
      const claim = (match: (row: NoteRow) => boolean): NoteRow | undefined => {
        const i = vanished.findIndex(match);
        return i < 0 ? undefined : vanished.splice(i, 1)[0];
      };
      for (const note of fresh) {
        const from =
          (note.id !== null ? claim((r) => r.note_id === note.id) : undefined) ?? claim((r) => r.hash === note.hash);
        if (from) {
          q.update.run(...rowValues(note), from.rowid);
          if (from.hash !== note.hash || from.path !== note.path) writeFts(from.rowid, note);
          report.moved.push({ from: from.path, to: note.path });
        } else {
          const { lastInsertRowid } = q.insert.run(...rowValues(note));
          writeFts(lastInsertRowid, note);
          report.added.push(note.path);
        }
      }
      for (const row of vanished) {
        q.remove.run(row.rowid);
        q.ftsRemove.run(row.rowid);
        linkStore.remove(row.rowid);
        report.deleted.push(row.path);
      }
      if (report.added.length || report.updated.length || report.moved.length || report.deleted.length) {
        linkStore.resolveAll();
      }
      db.exec("COMMIT");
    } catch (error) {
      db.exec("ROLLBACK");
      throw error;
    }
    report.deleted.sort();
    return report;
  };

  const reindexNote = (path: string): ReconcileReport => {
    // Paths must match stored keys exactly: vault-relative, `/`-separated, no drive or root.
    if (!isIndexablePath(path, scan) || /^([a-zA-Z]:|\/)|\\/.test(path)) {
      throw new InvalidNotePathError(path);
    }
    const report: ReconcileReport = { added: [], updated: [], moved: [], deleted: [], unchanged: 0 };
    db.exec("BEGIN");
    try {
      const row = q.byPath.get(path) as NoteRow | undefined;
      let note: Loaded | undefined;
      try {
        const stat = statSync(join(options.vaultRoot, path));
        note = load(path, stat.mtimeMs, stat.size);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
      if (!note) {
        if (row) {
          q.remove.run(row.rowid);
          q.ftsRemove.run(row.rowid);
          linkStore.remove(row.rowid);
          report.deleted.push(path);
        }
      } else if (!row) {
        const { lastInsertRowid } = q.insert.run(...rowValues(note));
        writeFts(lastInsertRowid, note);
        report.added.push(path);
      } else if (row.hash === note.hash) {
        q.touch.run(note.path, note.mtimeMs, note.size, row.rowid);
        report.unchanged++;
      } else {
        q.update.run(...rowValues(note), row.rowid);
        writeFts(row.rowid, note);
        report.updated.push(path);
      }
      if (report.added.length || report.updated.length || report.deleted.length) {
        linkStore.resolveAll();
      }
      db.exec("COMMIT");
    } catch (error) {
      db.exec("ROLLBACK");
      throw error;
    }
    return report;
  };

  const duplicateIds = (): DuplicateId[] => {
    const groups = new Map<string, string[]>();
    for (const row of q.duplicates.all() as unknown as { note_id: string; path: string }[]) {
      groups.set(row.note_id, [...(groups.get(row.note_id) ?? []), row.path]);
    }
    return [...groups].map(([id, paths]) => ({ id, paths }));
  };

  return {
    vaultRoot: options.vaultRoot,
    isIndexable: (path) => isIndexablePath(path, scan),
    reconcile,
    rebuild() {
      clear();
      return reconcile();
    },
    reindexNote,
    search(query, { limit = 20 } = {}) {
      const match = toFtsQuery(query);
      if (!match) return [];
      return (q.search.all(match, limit) as unknown as {
        path: string;
        note_id: string | null;
        title: string;
        snippet: string;
        score: number;
      }[]).map((r) => ({ path: r.path, id: r.note_id, title: r.title, snippet: r.snippet, score: r.score }));
    },
    listNotes: () => (q.all.all() as unknown as NoteRow[]).map(toNote),
    getNote(path) {
      const row = q.byPath.get(path) as NoteRow | undefined;
      return row ? toNote(row) : undefined;
    },
    findById: (id) => (q.byId.all(id) as unknown as NoteRow[]).map(toNote),
    duplicateIds,
    assertNoteIdAvailable(id, path) {
      const conflicts = (q.byId.all(id) as unknown as NoteRow[]).map((r) => r.path).filter((p) => p !== path);
      if (conflicts.length > 0) throw new DuplicateNoteIdError(id, conflicts);
    },
    findNotes: (filter) => (q.all.all() as unknown as NoteRow[]).map(toNote).filter((n) => matchesFilter(n, filter)),
    links: (path) => linkStore.outgoing(path),
    backlinks: (path) => linkStore.incoming(path),
    brokenLinks: () => linkStore.problems(),
    close: () => db.close(),
  };
}
