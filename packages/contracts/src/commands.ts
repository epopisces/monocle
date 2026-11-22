/**
 * Shared command registry (IMM-51). Every Monocle command is defined once here and surfaced in chat
 * (`/<id>`), the Obsidian command palette and context menus. `route` decides who runs it:
 * `monocle` commands are deterministic and run inside Monocle (`POST /v1/commands`) without starting
 * Cravat; `cravat` commands are agentic and run as an execution (`POST /v1/executions` with `command`).
 */

export const COMMANDS_PATH = "/v1/commands";

export type CommandRoute = "monocle" | "cravat";
/**
 * What the command may do to the vault. `read-vault` never writes. `create-note` may add one new note through
 * Monocle's guarded creation (exclusive create, fresh unique ID, schema check); it never modifies existing notes.
 */
export type CommandPermission = "read-vault" | "create-note";
export type CommandRequirement = "activeNote" | "vault";
export type CommandSurface = "chat" | "palette" | "editor-menu" | "file-menu";

export interface CommandArgument {
  /** Human name used in messages, e.g. "query". */
  readonly name: string;
  readonly required: boolean;
  /** When true, the active note's selection is used if no argument is typed. */
  readonly fromSelection?: boolean;
}

export interface CommandDefinition {
  /** Slash name without the slash; also the suffix of the Obsidian command ID. */
  readonly id: string;
  /** Palette / menu label. */
  readonly name: string;
  readonly description: string;
  readonly route: CommandRoute;
  readonly permission: CommandPermission;
  readonly requires: readonly CommandRequirement[];
  readonly argument?: CommandArgument;
  readonly surfaces: readonly CommandSurface[];
}

export const COMMANDS: readonly CommandDefinition[] = [
  {
    id: "validate",
    name: "Validate note",
    description: "Check the active note's frontmatter, ID and links without changing it.",
    route: "monocle",
    permission: "read-vault",
    requires: ["activeNote", "vault"],
    surfaces: ["chat", "palette", "editor-menu", "file-menu"],
  },
  {
    id: "backlinks",
    name: "Show backlinks",
    description: "List the notes that link to the active note.",
    route: "monocle",
    permission: "read-vault",
    requires: ["activeNote", "vault"],
    surfaces: ["chat", "palette", "file-menu"],
  },
  {
    id: "search",
    name: "Search vault",
    description: "Search the vault index for a query.",
    route: "monocle",
    permission: "read-vault",
    requires: ["vault"],
    argument: { name: "query", required: true },
    surfaces: ["chat"],
  },
  {
    id: "lookup",
    name: "Look up in vault",
    description: "Ask Cravat to answer a question from your notes, citing them.",
    route: "cravat",
    permission: "read-vault",
    requires: ["vault"],
    argument: { name: "question", required: true, fromSelection: true },
    surfaces: ["chat", "palette", "editor-menu"],
  },
  {
    id: "new-note",
    name: "Create note",
    description: "Create a note from the vault's note template with a new unique ID.",
    route: "monocle",
    permission: "create-note",
    requires: ["vault"],
    argument: { name: "title", required: true },
    surfaces: ["chat"],
  },
];

export function findCommand(id: string): CommandDefinition | undefined {
  return COMMANDS.find((c) => c.id === id);
}

export type ParsedChatInput =
  | { readonly kind: "freeform"; readonly prompt: string }
  | { readonly kind: "command"; readonly command: CommandDefinition; readonly argument: string }
  | { readonly kind: "unknown"; readonly message: string };

const SLASH = /^\/([a-z][\w-]*)(?:\s+([\s\S]*))?$/i;

function commandList(): string {
  return COMMANDS.filter((c) => c.surfaces.includes("chat"))
    .map((c) => `/${c.id}`)
    .join(", ");
}

/** Decide whether chat input is a slash command or a free-form request for Cravat. */
export function parseChatInput(text: string): ParsedChatInput {
  const trimmed = text.trim();
  const m = SLASH.exec(trimmed);
  if (!m) return { kind: "freeform", prompt: trimmed };
  const id = m[1]!.toLowerCase();
  const command = findCommand(id);
  if (!command || !command.surfaces.includes("chat")) {
    return { kind: "unknown", message: `Unknown command /${m[1]}. Available commands: ${commandList()}` };
  }
  return { kind: "command", command, argument: (m[2] ?? "").trim() };
}

export interface CommandContextAvailability {
  readonly argument: string;
  readonly activeNote?: { readonly path: string; readonly selection?: string };
  /** True when the companion has a vault index (started with `--vault`). */
  readonly vault: boolean;
}

/** Argument the command runs with: the typed argument, else the selection when allowed. */
export function resolveCommandArgument(def: CommandDefinition, available: CommandContextAvailability): string {
  const typed = available.argument.trim();
  if (typed || !def.argument?.fromSelection) return typed;
  return available.activeNote?.selection?.trim() ?? "";
}

/** Actionable messages naming each piece of context the command needs but does not have. */
export function missingContext(def: CommandDefinition, available: CommandContextAvailability): string[] {
  const missing: string[] = [];
  if (def.argument?.required && !resolveCommandArgument(def, available)) {
    const how = def.argument.fromSelection ? `type /${def.id} <${def.argument.name}> or select text` : `type /${def.id} <${def.argument.name}>`;
    missing.push(`/${def.id} needs a ${def.argument.name}: ${how} and try again`);
  }
  if (def.requires.includes("activeNote") && !available.activeNote) {
    missing.push(`/${def.id} needs an active note: open a Markdown note and try again`);
  }
  if (def.requires.includes("vault") && !available.vault) {
    missing.push(`/${def.id} needs a vault: start the companion with --vault <path> and reconnect`);
  }
  return missing;
}

/** Body of `POST /v1/commands`. */
export interface CommandRequest {
  readonly command: string;
  readonly argument?: string;
  readonly context?: { readonly activeNote?: { readonly path: string } };
}

export interface ValidationIssue {
  readonly severity: "error" | "warning";
  readonly code: "frontmatter_invalid" | "duplicate_id" | "missing_id" | "unresolved_link" | "ambiguous_link";
  readonly message: string;
  /** 1-based line in the note, when the issue has a location. */
  readonly line?: number;
}

export interface NoteValidation {
  readonly path: string;
  readonly valid: boolean;
  readonly issues: readonly ValidationIssue[];
}

/** Successful `POST /v1/commands` response. `markdown` is the human rendering; `data` is typed per command. */
export interface CommandResult {
  readonly command: string;
  readonly title: string;
  readonly markdown: string;
  readonly data: unknown;
}

export type CommandErrorCode =
  | "invalid_request"
  /** No command with that ID (or it is not available in this surface). */
  | "unknown_command"
  /** Required context (active note, argument, vault) is absent; `missing` lists one message per gap. */
  | "missing_context"
  /** The command is routed to Cravat; send it to `POST /v1/executions` with `command` instead. */
  | "agentic_command"
  /** The companion does not allow this command's permission (e.g. note creation is not configured). */
  | "not_permitted"
  /** A note could not be created; `reason` says why and nothing was written. */
  | "note_creation_failed";

/** Why `/new-note` refused to create a note. Each comes with a message saying what to change. */
export type NoteCreationErrorCode =
  | "invalid_title"
  | "invalid_folder"
  /** A note already exists at the path (compared case-insensitively). Existing notes are never overwritten. */
  | "path_exists"
  | "template_not_found"
  | "unfilled_placeholder"
  | "frontmatter_invalid"
  /** The rendered note has no persistent ID in the ID field. */
  | "missing_id"
  /** The rendered note's ID is already used by another note. */
  | "duplicate_id"
  /** An external renderer (e.g. Curator's create-obsidian-note script) failed or broke its output contract. */
  | "renderer_failed";

export interface CommandError {
  readonly code: CommandErrorCode;
  readonly message: string;
  readonly missing?: readonly string[];
  /** Set with `note_creation_failed`. */
  readonly reason?: NoteCreationErrorCode;
}

/** `data` of a successful `/new-note`. */
export interface CreatedNoteData {
  readonly path: string;
  readonly id: string;
  readonly template: string;
  /** Validation of the note as saved; warnings (e.g. unresolved links from the template) are allowed. */
  readonly validation: NoteValidation;
}

const COMMAND_REQUEST_FIELDS = new Set(["command", "argument", "context"]);

export function parseCommandRequest(value: unknown): { ok: true; request: CommandRequest } | { ok: false; error: string } {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return { ok: false, error: "body must be a JSON object" };
  const body = value as Record<string, unknown>;
  const unknownKeys = Object.keys(body).filter((k) => !COMMAND_REQUEST_FIELDS.has(k));
  if (unknownKeys.length > 0) return { ok: false, error: `unsupported fields: ${unknownKeys.join(", ")}` };
  if (typeof body.command !== "string" || body.command === "") return { ok: false, error: "command must be a non-empty string" };
  if (body.argument !== undefined && typeof body.argument !== "string") return { ok: false, error: "argument must be a string" };
  let context: CommandRequest["context"];
  if (body.context !== undefined) {
    const ctx = body.context as Record<string, unknown> | null;
    if (typeof ctx !== "object" || ctx === null || Array.isArray(ctx)) return { ok: false, error: "context must be a JSON object" };
    if (ctx.activeNote !== undefined) {
      const note = ctx.activeNote as Record<string, unknown> | null;
      if (typeof note !== "object" || note === null || typeof note.path !== "string" || note.path === "") {
        return { ok: false, error: "context.activeNote.path must be a non-empty string" };
      }
      context = { activeNote: { path: note.path } };
    } else {
      context = {};
    }
  }
  return {
    ok: true,
    request: { command: body.command, ...(body.argument !== undefined ? { argument: body.argument as string } : {}), ...(context ? { context } : {}) },
  };
}
