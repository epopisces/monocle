import type { IndexedNote } from "./note-index.js";

type Scalar = string | number | boolean;

export interface NoteFilter {
  /**
   * Every key must match. A note value matches a filter scalar when equal (compared as strings) or, for list values,
   * when the list contains it. A filter array matches if any of its values matches.
   */
  frontmatter?: Record<string, Scalar | readonly Scalar[]>;
  /** Vault-relative folder; matches notes in it or its subfolders. */
  folder?: string;
  /** true: only notes with a persistent ID; false: only legacy notes without one. */
  hasId?: boolean;
}

const scalars = (value: unknown): string[] =>
  (Array.isArray(value) ? value : [value])
    .filter((v) => v !== null && v !== undefined && typeof v !== "object")
    .map(String);

export function matchesFilter(note: IndexedNote, filter: NoteFilter): boolean {
  if (filter.hasId !== undefined && (note.id !== null) !== filter.hasId) return false;
  if (filter.folder !== undefined) {
    const folder = filter.folder.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
    if (folder && !note.path.startsWith(`${folder}/`)) return false;
  }
  for (const [key, wanted] of Object.entries(filter.frontmatter ?? {})) {
    const have = scalars(note.frontmatter[key]);
    const options = (Array.isArray(wanted) ? wanted : [wanted]).map(String);
    if (!options.some((o) => have.includes(o))) return false;
  }
  return true;
}
