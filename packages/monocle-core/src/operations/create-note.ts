import { spawnSync } from "node:child_process";
import { closeSync, mkdirSync, openSync, readdirSync, readFileSync, unlinkSync, writeSync } from "node:fs";
import { dirname, join } from "node:path";
import type { NoteCreationErrorCode, NoteValidation } from "@monocle/contracts";
import { noteId, parseNote } from "../note-index/markdown.js";
import { DuplicateNoteIdError, type NoteIndex } from "../note-index/note-index.js";
import { validateNote } from "./validate-note.js";

/** What the user asks for. Monocle assigns the path and ID; a {@link NoteRenderer} produces the content. */
export interface NoteRequest {
  readonly title: string;
  /** Template name. For the built-in renderer: a file (without `.md`) in the vault's Obsidian templates folder. */
  readonly template: string;
  /** Vault-relative folder; defaults to Obsidian's configured new-note folder (`.obsidian/app.json`). */
  readonly folder?: string;
  /** Extra template values, e.g. `{ type: "capture" }` for `{{type}}`. */
  readonly fields?: Readonly<Record<string, string>>;
}

/** Everything a renderer needs to produce one note. Also the JSON sent to an external renderer's stdin. */
export interface NoteDraft {
  readonly title: string;
  readonly template: string;
  /** Vault-relative folder the note will be written to ("" for the vault root). */
  readonly folder: string;
  /** Vault-relative path the note will be written to. */
  readonly path: string;
  /** Frontmatter field for the persistent ID, and the ID Monocle assigned. The rendered note must carry it. */
  readonly idField: string;
  readonly id: string;
  readonly fields: Readonly<Record<string, string>>;
  /** ISO timestamp of the request (renderers use it instead of their own clock, for determinism). */
  readonly now: string;
  readonly vaultRoot: string;
}

/**
 * Adapter boundary for note conventions. Monocle owns identity, paths and integrity; the renderer owns what a
 * note of a given template looks like. The built-in {@link vaultTemplateRenderer} uses the vault's Obsidian
 * templates; {@link commandNoteRenderer} delegates to an external script such as Curator's `create-obsidian-note`.
 */
export interface NoteRenderer {
  readonly id: string;
  /** Full Markdown content of the new note. Throws {@link NoteCreationError} for actionable failures. */
  render(draft: NoteDraft): string;
}

export interface CreateNoteOptions {
  /** Frontmatter field holding the persistent ID. Must match the index's `idField`. Default `id`. */
  readonly idField?: string;
  /** Clock for `{{date}}`/`{{time}}` and timestamp IDs. */
  readonly now?: Date;
  /** Default: {@link vaultTemplateRenderer}. */
  readonly renderer?: NoteRenderer;
  /**
   * Brings the index up to date before IDs are chosen, so notes written or synced since the last reconcile are
   * seen. Defaults to `index.reconcile()`; an `IndexService` caller passes its own reconcile to keep health and
   * semantic indexing in step.
   */
  readonly reconcile?: () => void;
}

/** A checked, not-yet-written note: what {@link createNote} writes, and what a create proposal would carry. */
export interface NotePlan {
  readonly path: string;
  readonly id: string;
  readonly idField: string;
  readonly content: string;
  /** {@link NoteRenderer.id} that produced the content. */
  readonly renderer: string;
}

export interface CreatedNote extends NotePlan {
  /** Post-write validation of the note as saved (warnings such as unresolved links are allowed). */
  readonly validation: NoteValidation;
}

/** A note could not be created; `message` says what to change. Nothing was written (or it was removed again). */
export class NoteCreationError extends Error {
  constructor(
    readonly code: NoteCreationErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "NoteCreationError";
  }
}

function readJson(path: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(readFileSync(path, "utf8"));
    return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

const pad = (n: number, width = 2): string => String(n).padStart(width, "0");

/**
 * Deterministic next ID following the vault's own convention:
 * - the dominant `<prefix><digits>` sequence (e.g. `fx-0003` → `fx-0004`), keeping its zero padding;
 * - otherwise (no IDs yet, or the vault uses timestamps) Obsidian's unique-note format `YYYYMMDDHHmm` from the
 *   clock, suffixed `-1`, `-2`, … when that minute is already taken.
 */
function nextId(index: NoteIndex, now: Date): string {
  const ids = new Set<string>();
  const groups = new Map<string, { width: number; max: number; count: number }>();
  for (const note of index.listNotes()) {
    if (note.id === null) continue;
    ids.add(note.id);
    const m = /^(.*?)(\d+)$/.exec(note.id);
    if (!m || (m[1] === "" && m[2]!.length >= 12) || /^\d{12,}-$/.test(m[1]!)) continue;
    const g = groups.get(m[1]!) ?? { width: 0, max: 0, count: 0 };
    groups.set(m[1]!, { width: Math.max(g.width, m[2]!.length), max: Math.max(g.max, Number(m[2])), count: g.count + 1 });
  }
  const dominant = [...groups].sort((a, b) => b[1].count - a[1].count)[0];
  if (dominant) {
    const [prefix, g] = dominant;
    return `${prefix}${pad(g.max + 1, g.width)}`;
  }
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}`;
  let candidate = stamp;
  for (let n = 1; ids.has(candidate); n++) candidate = `${stamp}-${n}`;
  return candidate;
}

const PLACEHOLDER = /\{\{\s*[\w:-]+\s*\}\}/g;

function fillTemplate(template: string, values: Readonly<Record<string, string>>): string {
  const fill = (text: string) => text.replace(/\{\{\s*([\w-]+)\s*\}\}/g, (whole, name: string) => values[name] ?? whole);
  const fm = /^---\r?\n[\s\S]*?\r?\n---/.exec(template);
  if (!fm) return fill(template);
  // A JSON string is a valid YAML double-quoted scalar, so quotes and backslashes in values stay valid YAML.
  const frontmatter = fm[0].replace(/"\{\{\s*([\w-]+)\s*\}\}"/g, (whole, name: string) =>
    values[name] === undefined ? whole : JSON.stringify(values[name]),
  );
  return fill(frontmatter) + fill(template.slice(fm[0].length));
}

/** Obsidian's templates folder from `.obsidian/templates.json` (core Templates plugin), else `templates`. */
export function obsidianTemplatesFolder(vaultRoot: string): string {
  const folder = readJson(join(vaultRoot, ".obsidian", "templates.json")).folder;
  return typeof folder === "string" && folder.trim() ? folder.trim().replace(/\/+$/, "") : "templates";
}

function readTemplate(vault: string, folder: string, name: string): string {
  try {
    if (/[\\/]|^\.\.?$/.test(name)) throw Object.assign(new Error("not a template name"), { code: "ENOENT" });
    return readFileSync(join(vault, folder, `${name}.md`), "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    let available: string[] = [];
    try {
      available = readdirSync(join(vault, folder)).filter((f) => f.endsWith(".md")).map((f) => f.slice(0, -3)).sort();
    } catch {
      // No templates folder; reported below as no templates.
    }
    throw new NoteCreationError(
      "template_not_found",
      `No template "${name}" in ${folder}/. Available: ${available.length ? available.join(", ") : "none"}`,
    );
  }
}

/**
 * Renders the vault's own Obsidian template (the same file Obsidian's Templates plugin inserts), filling
 * `{{title}}`, `{{date}}` (YYYY-MM-DD), `{{time}}` (HH:mm), the ID field and any request fields.
 */
export const vaultTemplateRenderer: NoteRenderer = {
  id: "vault-template",
  render(draft) {
    const template = readTemplate(draft.vaultRoot, obsidianTemplatesFolder(draft.vaultRoot), draft.template);
    const now = new Date(draft.now);
    return fillTemplate(template, {
      date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
      time: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
      ...draft.fields,
      title: draft.title,
      [draft.idField]: draft.id,
      id: draft.id,
    });
  },
};

export interface CommandNoteRendererOptions {
  /** Executable, e.g. `python` or `node`. Never run through a shell. */
  readonly command: string;
  readonly args?: readonly string[];
  readonly cwd?: string;
  /** Default 30 s. */
  readonly timeoutMs?: number;
}

/**
 * Delegates rendering to an external script (the Curator `create-obsidian-note` integration point). Contract:
 * the {@link NoteDraft} as JSON on stdin; `{"content": "<markdown>"}` on stdout and exit 0; otherwise a non-zero
 * exit with a human-readable message on stderr. The script must not write to the vault: Monocle writes the note.
 */
export function commandNoteRenderer(options: CommandNoteRendererOptions): NoteRenderer {
  return {
    id: `command:${options.command}`,
    render(draft) {
      const result = spawnSync(options.command, [...(options.args ?? [])], {
        input: JSON.stringify(draft),
        encoding: "utf8",
        timeout: options.timeoutMs ?? 30_000,
        windowsHide: true,
        ...(options.cwd && { cwd: options.cwd }),
      });
      const fail = (why: string) => new NoteCreationError("renderer_failed", `Note renderer ${options.command} ${why}`);
      if (result.error) throw fail(`could not run: ${result.error.message}`);
      if (result.status !== 0) {
        const stderr = result.stderr.trim().split(/\r?\n/).slice(-5).join(" ");
        throw fail(`exited with ${result.status ?? result.signal}: ${stderr || "no message"}`);
      }
      let content: unknown;
      try {
        content = (JSON.parse(result.stdout) as { content?: unknown }).content;
      } catch {
        content = undefined;
      }
      if (typeof content !== "string") throw fail('did not print JSON {"content": "..."} on stdout');
      return content;
    },
  };
}

/** Characters Obsidian refuses in file names or that break `[[wikilinks]]`. */
const FORBIDDEN_TITLE = /[*"\\/<>:|?#^[\]]/;

function checkTitle(title: string): string {
  const trimmed = title.trim();
  if (!trimmed) throw new NoteCreationError("invalid_title", "Title is empty; give the note a title");
  if (FORBIDDEN_TITLE.test(trimmed)) {
    throw new NoteCreationError("invalid_title", `Title "${trimmed}" cannot contain any of * " \\ / < > : | ? # ^ [ ]; rename it and try again`);
  }
  return trimmed;
}

function checkFolder(index: NoteIndex, folder: string): string {
  const normalized = folder.trim().replace(/\/+$/, "");
  const segments = normalized.split("/");
  if (/^([a-zA-Z]:|\/)|\\/.test(normalized) || segments.some((s) => s === ".." || s === ".")) {
    throw new NoteCreationError("invalid_folder", `Folder "${folder}" is not inside the vault; use a vault-relative folder such as inbox`);
  }
  if (normalized && (segments.includes("") || !index.isIndexable(`${normalized}/note.md`))) {
    throw new NoteCreationError("invalid_folder", `Folder "${folder}" is not an indexed vault folder (dot-folders and excluded folders are not allowed)`);
  }
  return normalized;
}

/**
 * Works out a new note — path, next persistent ID, rendered content — and checks every creation invariant
 * (title and folder usable, path and ID free, frontmatter parses, ID present) without writing anything (IMM-52).
 */
export function planNote(index: NoteIndex, request: NoteRequest, options: CreateNoteOptions = {}): NotePlan {
  const idField = options.idField ?? "id";
  const now = options.now ?? new Date();
  const renderer = options.renderer ?? vaultTemplateRenderer;
  const vaultRoot = index.vaultRoot;
  const title = checkTitle(request.title);
  const newFileFolder = readJson(join(vaultRoot, ".obsidian", "app.json")).newFileFolderPath;
  const folder = checkFolder(index, request.folder ?? (typeof newFileFolder === "string" ? newFileFolder : ""));

  if (options.reconcile) options.reconcile();
  else index.reconcile();
  const path = (folder ? `${folder}/` : "") + `${title}.md`;
  const sameName = index.listNotes().find((n) => n.path.toLowerCase() === path.toLowerCase());
  if (sameName) throw new NoteCreationError("path_exists", `${sameName.path} already exists; choose a different title or folder`);

  const draft: NoteDraft = {
    title,
    template: request.template,
    folder,
    path,
    idField,
    id: nextId(index, now),
    fields: { ...request.fields },
    now: now.toISOString(),
    vaultRoot,
  };
  const content = renderer.render(draft);

  const unfilled = [...new Set(content.match(PLACEHOLDER) ?? [])];
  if (unfilled.length > 0) {
    throw new NoteCreationError(
      "unfilled_placeholder",
      `Template "${request.template}" needs values for ${unfilled.join(", ")}; pass them as fields (e.g. --note-field name=value)`,
    );
  }
  const parsed = parseNote(content);
  if (parsed.frontmatterError) {
    throw new NoteCreationError(
      "frontmatter_invalid",
      `Template "${request.template}" produced invalid frontmatter (${parsed.frontmatterError}); fix the template or the values passed in`,
    );
  }
  const id = noteId(parsed, idField);
  if (id === null) {
    throw new NoteCreationError(
      "missing_id",
      `Template "${request.template}" does not set ${idField}; add \`${idField}: "{{${idField}}}"\` to its frontmatter`,
    );
  }
  try {
    index.assertNoteIdAvailable(id, path);
  } catch (error) {
    if (error instanceof DuplicateNoteIdError) throw new NoteCreationError("duplicate_id", `${error.message}; new notes need a unique ID`);
    throw error;
  }
  return { path, id, idField, content, renderer: renderer.id };
}

/**
 * Creates a new note (IMM-52): {@link planNote}, then an exclusive create so an existing file is never replaced,
 * then re-indexes and validates the note as saved. A note that fails that validation (e.g. an ID that appeared
 * elsewhere in the meantime) is removed again.
 */
export function createNote(index: NoteIndex, request: NoteRequest, options: CreateNoteOptions = {}): CreatedNote {
  const plan = planNote(index, request, options);
  const target = join(index.vaultRoot, plan.path);
  mkdirSync(dirname(target), { recursive: true });
  let fd: number;
  try {
    // Exclusive create: a file that appeared at the path since planning is never replaced.
    fd = openSync(target, "wx");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EEXIST") {
      throw new NoteCreationError("path_exists", `${plan.path} already exists; choose a different title or folder`);
    }
    throw error;
  }
  try {
    writeSync(fd, plan.content);
  } finally {
    closeSync(fd);
  }
  const validation = validateNote(index, plan.path);
  const firstError = validation.issues.find((i) => i.severity === "error");
  if (firstError) {
    unlinkSync(target);
    index.reindexNote(plan.path);
    throw new NoteCreationError(firstError.code as NoteCreationErrorCode, `${plan.path} was not kept: ${firstError.message}`);
  }
  return { ...plan, validation };
}
