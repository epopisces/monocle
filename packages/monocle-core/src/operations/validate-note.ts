import type { NoteValidation, ValidationIssue } from "@monocle/contracts";
import { InvalidNotePathError, type NoteIndex } from "../note-index/note-index.js";

/**
 * Read-only check of one note as saved on disk (IMM-51 `/validate`). Re-indexes the note first so the
 * result reflects the current file, then reports frontmatter, persistent-ID and link issues. Never writes
 * to the vault. Errors make the note invalid; warnings (legacy notes without an ID, broken links) do not.
 */
export function validateNote(index: NoteIndex, path: string): NoteValidation {
  if (!index.isIndexable(path)) throw new InvalidNotePathError(path);
  index.reindexNote(path);
  const note = index.getNote(path);
  if (!note) throw new InvalidNotePathError(path);

  const issues: ValidationIssue[] = [];
  if (note.frontmatterError) {
    issues.push({ severity: "error", code: "frontmatter_invalid", message: `Frontmatter could not be parsed: ${note.frontmatterError}` });
  }
  if (note.id === null) {
    if (!note.frontmatterError) {
      issues.push({ severity: "warning", code: "missing_id", message: "Note has no persistent ID (legacy notes are allowed)" });
    }
  } else {
    const others = index.findById(note.id).filter((n) => n.path !== note.path).map((n) => n.path);
    if (others.length > 0) {
      issues.push({ severity: "error", code: "duplicate_id", message: `ID "${note.id}" is also used by: ${others.join(", ")}` });
    }
  }
  for (const link of index.links(path)) {
    if (link.status !== "unresolved" && link.status !== "ambiguous") continue;
    const line = link.location ? { line: link.location.line } : {};
    if (link.status === "unresolved") {
      issues.push({ severity: "warning", code: "unresolved_link", message: `${link.raw} does not match any note`, ...line });
    } else {
      const candidates = link.candidates.map((c) => c.path).join(", ");
      issues.push({ severity: "warning", code: "ambiguous_link", message: `${link.raw} matches several notes: ${candidates}`, ...line });
    }
  }
  return { path: note.path, valid: !issues.some((i) => i.severity === "error"), issues };
}
