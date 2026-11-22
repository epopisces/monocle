import { VaultAccessError, type VaultReader } from "./vault-reader.js";

/** MCP tool names exposed by the vault server. All are read-only; the server has no write tools at all. */
export const VAULT_TOOL_NAMES = ["read_note", "list_notes", "search_notes"] as const;
export type VaultToolName = (typeof VAULT_TOOL_NAMES)[number];

export interface VaultToolDefinition {
  readonly name: VaultToolName;
  readonly description: string;
  readonly inputSchema: Record<string, unknown>;
  readonly annotations: { readonly readOnlyHint: true; readonly destructiveHint: false; readonly openWorldHint: false };
}

export interface VaultToolResult {
  readonly content: { type: "text"; text: string }[];
  readonly isError?: boolean;
}

const READ_ONLY = { readOnlyHint: true, destructiveHint: false, openWorldHint: false } as const;
const LIST_LIMIT = 500;
const SEARCH_LIMIT_MAX = 50;

export const VAULT_TOOLS: readonly VaultToolDefinition[] = [
  {
    name: "read_note",
    description: "Read the Markdown text of one note in the user's Obsidian vault. Paths are vault-relative, e.g. `folder/Note.md`.",
    inputSchema: { type: "object", properties: { path: { type: "string", description: "Vault-relative note path" } }, required: ["path"], additionalProperties: false },
    annotations: READ_ONLY,
  },
  {
    name: "list_notes",
    description: "List vault-relative paths of notes in the user's Obsidian vault, optionally only under one folder.",
    inputSchema: { type: "object", properties: { folder: { type: "string", description: "Vault-relative folder" } }, additionalProperties: false },
    annotations: READ_ONLY,
  },
  {
    name: "search_notes",
    description: "Find notes whose path or text contains all of the given words (case-insensitive). Returns paths and snippets.",
    inputSchema: {
      type: "object",
      properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: SEARCH_LIMIT_MAX } },
      required: ["query"],
      additionalProperties: false,
    },
    annotations: READ_ONLY,
  },
];

const ok = (text: string): VaultToolResult => ({ content: [{ type: "text", text }] });
const fail = (text: string): VaultToolResult => ({ content: [{ type: "text", text }], isError: true });

function str(args: Record<string, unknown>, key: string, required: boolean): string | undefined {
  const v = args[key];
  if (v === undefined && !required) return undefined;
  if (typeof v !== "string") throw new VaultAccessError(`${key} must be a string`);
  return v;
}

/** Runs one vault tool. Refusals and bad arguments become `isError` results, never exceptions. */
export function callVaultTool(reader: VaultReader, name: string, args: Record<string, unknown> = {}): VaultToolResult {
  try {
    switch (name) {
      case "read_note": {
        const note = reader.readNote(str(args, "path", true)!);
        return ok(`${note.content}${note.truncated ? "\n\n[Monocle: note truncated]" : ""}`);
      }
      case "list_notes": {
        const paths = reader.listNotes(str(args, "folder", false));
        const shown = paths.slice(0, LIST_LIMIT);
        if (shown.length === 0) return ok("No notes found.");
        return ok(shown.join("\n") + (paths.length > shown.length ? `\n[Monocle: ${paths.length - shown.length} more not shown]` : ""));
      }
      case "search_notes": {
        const limit = typeof args.limit === "number" ? Math.min(Math.max(1, Math.floor(args.limit)), SEARCH_LIMIT_MAX) : 20;
        const hits = reader.searchNotes(str(args, "query", true)!, limit);
        return ok(hits.length === 0 ? "No matching notes." : hits.map((h) => `${h.path}\n  ${h.snippet}`).join("\n"));
      }
      default:
        return fail(`unknown tool: ${name}`);
    }
  } catch (err) {
    if (err instanceof VaultAccessError) return fail(err.message);
    return fail(`vault tool failed: ${(err as Error).message}`);
  }
}
