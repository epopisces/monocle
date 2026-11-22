import type { ExecutionContext } from "@monocle/contracts";

export interface ActiveNoteSnapshot {
  readonly path: string;
  /** Current editor text (may include unsaved edits). */
  readonly content: string;
  readonly selection?: string;
}

export interface ContextChoices {
  /** Last focused Markdown note, if any. */
  readonly activeNote?: ActiveNoteSnapshot | undefined;
  readonly includeActiveNote: boolean;
  readonly includeSelection: boolean;
  /** Extra vault-relative notes, one per line. */
  readonly include: string;
  /** Vault-relative notes or folders to keep out of the request, one per line. */
  readonly exclude: string;
}

const lines = (text: string) => [...new Set(text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean))];
const norm = (p: string) => p.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "").toLowerCase();

/**
 * Builds the request context from the panel's choices. Excluded notes are dropped here, before anything is
 * sent; the exclusions are also forwarded so the companion keeps them out of the agent's vault tools.
 */
export function buildExecutionContext(choices: ContextChoices): ExecutionContext | undefined {
  const exclude = lines(choices.exclude);
  const excluded = (path: string) => exclude.some((e) => norm(path) === norm(e) || norm(path).startsWith(`${norm(e)}/`));
  const note = choices.activeNote;
  const activeNote =
    note && !excluded(note.path) && (choices.includeActiveNote || (choices.includeSelection && note.selection))
      ? {
          path: note.path,
          ...(choices.includeActiveNote && { content: note.content }),
          ...(choices.includeSelection && note.selection && { selection: note.selection }),
        }
      : undefined;
  const include = lines(choices.include).filter((p) => !excluded(p));
  const context: ExecutionContext = {
    ...(activeNote && { activeNote }),
    ...(include.length > 0 && { include }),
    ...(exclude.length > 0 && { exclude }),
  };
  return Object.keys(context).length > 0 ? context : undefined;
}
