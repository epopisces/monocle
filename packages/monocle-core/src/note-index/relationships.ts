import type { DatabaseSync } from "node:sqlite";
import type { ExtractedLink, LinkKind, SourceLocation } from "./links.js";

/** A grounded reference to an indexed note. `id` is the persistent frontmatter ID (null for legacy notes). */
export interface NoteRef {
  path: string;
  id: string | null;
  title: string;
}

/**
 * `resolved`: exactly one note matches. `ambiguous`: several notes match (see `candidates`).
 * `unresolved`: no note matches (broken link). `attachment`: no note matches and the target names a non-Markdown file.
 */
export type LinkStatus = "resolved" | "ambiguous" | "unresolved" | "attachment";

/** How a resolved/ambiguous target was matched: vault path, file name, frontmatter alias, or same-note `[[#...]]`. */
export type LinkMatch = "path" | "name" | "alias" | "self";

export interface NoteLink {
  source: NoteRef;
  kind: LinkKind;
  relation: string;
  field: string | null;
  raw: string;
  target: string;
  subpath: string | null;
  display: string | null;
  location: SourceLocation | null;
  status: LinkStatus;
  matchedBy: LinkMatch | null;
  resolved: NoteRef | null;
  candidates: NoteRef[];
}

interface LinkRow {
  source_path: string;
  source_id: string | null;
  source_title: string;
  kind: LinkKind;
  relation: string;
  field: string | null;
  raw: string;
  target: string;
  subpath: string | null;
  display: string | null;
  line: number | null;
  col: number | null;
  status: LinkStatus;
  matched_by: LinkMatch | null;
  target_path: string | null;
  target_id: string | null;
  target_title: string | null;
  candidates: string | null;
}

export interface LinkStore {
  clear(): void;
  /** Replaces the stored links written in one note (resolution is deferred to `resolveAll`). */
  replace(sourceRowid: number | bigint, links: readonly ExtractedLink[]): void;
  remove(sourceRowid: number | bigint): void;
  /** Re-resolves every link against the current set of notes (names, paths and aliases may all have changed). */
  resolveAll(): void;
  outgoing(path: string): NoteLink[];
  incoming(path: string): NoteLink[];
  problems(): NoteLink[];
}

const normalize = (s: string): string =>
  s.trim().replace(/\\/g, "/").replace(/^\/+/, "").replace(/\.md$/i, "").toLowerCase();

function aliasesOf(frontmatter: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const key of ["aliases", "alias"]) {
    const value = frontmatter[key];
    for (const item of Array.isArray(value) ? value : [value]) {
      if (typeof item === "string" && item.trim()) out.push(item);
    }
  }
  return out;
}

export function createLinkStore(db: DatabaseSync): LinkStore {
  db.exec(`
    CREATE TABLE IF NOT EXISTS links (
      source_rowid INTEGER NOT NULL,
      ordinal INTEGER NOT NULL,
      kind TEXT NOT NULL,
      relation TEXT NOT NULL,
      field TEXT,
      raw TEXT NOT NULL,
      target TEXT NOT NULL,
      subpath TEXT,
      display TEXT,
      line INTEGER,
      col INTEGER,
      status TEXT NOT NULL DEFAULT 'unresolved',
      matched_by TEXT,
      target_rowid INTEGER,
      candidates TEXT,
      PRIMARY KEY (source_rowid, ordinal)
    );
    CREATE INDEX IF NOT EXISTS links_target ON links(target_rowid);
  `);

  const select = `
    SELECT s.path AS source_path, s.note_id AS source_id, s.title AS source_title,
           l.kind, l.relation, l.field, l.raw, l.target, l.subpath, l.display, l.line, l.col,
           l.status, l.matched_by, t.path AS target_path, t.note_id AS target_id, t.title AS target_title,
           l.candidates
    FROM links l JOIN notes s ON s.rowid = l.source_rowid LEFT JOIN notes t ON t.rowid = l.target_rowid`;
  const q = {
    clear: db.prepare("DELETE FROM links"),
    insert: db.prepare(
      `INSERT INTO links (source_rowid, ordinal, kind, relation, field, raw, target, subpath, display, line, col)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ),
    remove: db.prepare("DELETE FROM links WHERE source_rowid = ?"),
    notes: db.prepare("SELECT rowid, path, frontmatter FROM notes"),
    allTargets: db.prepare("SELECT source_rowid, ordinal, target FROM links"),
    resolve: db.prepare(
      `UPDATE links SET status = ?, matched_by = ?, target_rowid = ?, candidates = ?
       WHERE source_rowid = ? AND ordinal = ?`,
    ),
    ref: db.prepare("SELECT path, note_id, title FROM notes WHERE rowid = ?"),
    outgoing: db.prepare(`${select} WHERE s.path = ? ORDER BY l.ordinal`),
    incoming: db.prepare(
      `${select} WHERE l.status = 'resolved' AND t.path = ? ORDER BY s.path, l.ordinal`,
    ),
    problems: db.prepare(`${select} WHERE l.status IN ('unresolved', 'ambiguous') ORDER BY s.path, l.ordinal`),
  };

  const toRef = (rowid: number): NoteRef => {
    const r = q.ref.get(rowid) as { path: string; note_id: string | null; title: string };
    return { path: r.path, id: r.note_id, title: r.title };
  };

  const toLink = (r: LinkRow): NoteLink => ({
    source: { path: r.source_path, id: r.source_id, title: r.source_title },
    kind: r.kind,
    relation: r.relation,
    field: r.field,
    raw: r.raw,
    target: r.target,
    subpath: r.subpath,
    display: r.display,
    location: r.line === null || r.col === null ? null : { line: r.line, column: r.col },
    status: r.status,
    matchedBy: r.matched_by,
    resolved: r.target_path === null ? null : { path: r.target_path, id: r.target_id, title: r.target_title! },
    candidates: r.candidates ? (JSON.parse(r.candidates) as number[]).map(toRef) : [],
  });

  return {
    clear: () => void q.clear.run(),
    replace(sourceRowid, links) {
      q.remove.run(sourceRowid);
      links.forEach((l, i) =>
        q.insert.run(
          sourceRowid,
          i,
          l.kind,
          l.relation,
          l.field,
          l.raw,
          l.target,
          l.subpath,
          l.display,
          l.location?.line ?? null,
          l.location?.column ?? null,
        ),
      );
    },
    remove: (sourceRowid) => void q.remove.run(sourceRowid),
    resolveAll() {
      const byPath = new Map<string, number>();
      const byName = new Map<string, number[]>();
      const byAlias = new Map<string, number[]>();
      const add = (map: Map<string, number[]>, key: string, rowid: number): void => {
        const list = map.get(key) ?? [];
        if (!list.includes(rowid)) list.push(rowid);
        map.set(key, list);
      };
      const notes = q.notes.all() as unknown as { rowid: number; path: string; frontmatter: string }[];
      for (const n of notes) {
        const key = normalize(n.path);
        byPath.set(key, n.rowid);
        add(byName, key.slice(key.lastIndexOf("/") + 1), n.rowid);
        for (const alias of aliasesOf(JSON.parse(n.frontmatter) as Record<string, unknown>)) {
          add(byAlias, normalize(alias), n.rowid);
        }
      }

      const match = (sourceRowid: number, target: string): { matchedBy: LinkMatch | null; rowids: number[] } => {
        const key = normalize(target);
        if (!key) return { matchedBy: "self", rowids: [sourceRowid] };
        if (key.includes("/")) {
          const exact = byPath.get(key);
          if (exact !== undefined) return { matchedBy: "path", rowids: [exact] };
          const suffix = [...byPath].filter(([p]) => p.endsWith(`/${key}`)).map(([, r]) => r);
          if (suffix.length) return { matchedBy: "path", rowids: suffix };
        } else if (byName.has(key)) {
          return { matchedBy: "name", rowids: byName.get(key)! };
        }
        if (byAlias.has(key)) return { matchedBy: "alias", rowids: byAlias.get(key)! };
        return { matchedBy: null, rowids: [] };
      };

      const rows = q.allTargets.all() as unknown as {
        source_rowid: number;
        ordinal: number;
        target: string;
      }[];
      for (const row of rows) {
        const { matchedBy, rowids } = match(row.source_rowid, row.target);
        if (rowids.length === 1) {
          q.resolve.run("resolved", matchedBy, rowids[0]!, null, row.source_rowid, row.ordinal);
        } else if (rowids.length > 1) {
          const sorted = [...rowids].sort((a, b) => (toRef(a).path < toRef(b).path ? -1 : 1));
          q.resolve.run("ambiguous", matchedBy, null, JSON.stringify(sorted), row.source_rowid, row.ordinal);
        } else {
          const status = /\.[A-Za-z0-9]+$/.test(row.target) && !/\.md$/i.test(row.target) ? "attachment" : "unresolved";
          q.resolve.run(status, null, null, null, row.source_rowid, row.ordinal);
        }
      }
    },
    outgoing: (path) => (q.outgoing.all(path) as unknown as LinkRow[]).map(toLink),
    incoming: (path) => (q.incoming.all(path) as unknown as LinkRow[]).map(toLink),
    problems: () => (q.problems.all() as unknown as LinkRow[]).map(toLink),
  };
}
