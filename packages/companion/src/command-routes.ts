import type { IncomingMessage, ServerResponse } from "node:http";
import {
  COMMANDS_PATH,
  findCommand,
  missingContext,
  parseCommandRequest,
  resolveCommandArgument,
  type CommandDefinition,
  type CommandError,
  type CommandRequest,
  type CommandResult,
  type ExecutionError,
  type ExecutionRequest,
  type NoteValidation,
} from "@monocle/contracts";
import { createRetriever, InvalidNotePathError, validateNote, type IndexService } from "@monocle/core";

type Send = (res: ServerResponse, status: number, body: unknown) => void;

const MAX_BODY_BYTES = 64 * 1024;
const SEARCH_LIMIT = 10;

class RequestError extends Error {}

async function readJson(req: IncomingMessage): Promise<unknown> {
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of req as AsyncIterable<Buffer>) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new RequestError("request body too large");
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new RequestError("request body is not valid JSON");
  }
}

function renderValidation(v: NoteValidation): string {
  const head = v.valid ? `**${v.path}** is valid.` : `**${v.path}** has problems.`;
  if (v.issues.length === 0) return `${head}\n\nNo issues found.`;
  const lines = v.issues.map((i) => `- **${i.severity}** (${i.code}${i.line !== undefined ? `, line ${i.line}` : ""}): ${i.message}`);
  return `${head}\n\n${lines.join("\n")}`;
}

type Runner = (index: IndexService, argument: string, request: CommandRequest) => Promise<CommandResult>;

/** Deterministic, read-only command implementations. Each runs inside Monocle; none starts Cravat. */
const RUNNERS: Record<string, Runner> = {
  async validate(index, _argument, request) {
    const data = validateNote(index.noteIndex, request.context!.activeNote!.path);
    return { command: "validate", title: `Validate ${data.path}`, markdown: renderValidation(data), data };
  },
  async backlinks(index, _argument, request) {
    const path = request.context!.activeNote!.path;
    if (!index.noteIndex.isIndexable(path)) throw new InvalidNotePathError(path);
    index.reindexNote(path);
    const backlinks = index.noteIndex.backlinks(path).map((l) => ({
      path: l.source.path,
      title: l.source.title,
      raw: l.raw,
      ...(l.location && { line: l.location.line }),
    }));
    const markdown =
      backlinks.length === 0
        ? `No notes link to **${path}**.`
        : `Notes linking to **${path}**:\n\n${backlinks.map((b) => `- [[${b.path}|${b.title}]] — \`${b.raw}\``).join("\n")}`;
    return { command: "backlinks", title: `Backlinks of ${path}`, markdown, data: { path, backlinks } };
  },
  async search(index, argument) {
    const result = await createRetriever({ noteIndex: index.noteIndex, semantic: index.semantic }).search(argument, { limit: SEARCH_LIMIT });
    const hits = result.hits.map((h) => ({ path: h.path, id: h.id, title: h.title, snippet: h.snippet ?? h.passages[0]?.text ?? null }));
    const markdown =
      hits.length === 0
        ? `No notes match \`${argument}\`.`
        : hits.map((h) => `- [[${h.path}|${h.title}]]${h.snippet ? ` — ${h.snippet.replace(/\s+/g, " ")}` : ""}`).join("\n");
    return { command: "search", title: `Search: ${argument}`, markdown, data: { query: argument, hits, semantic: result.semantic } };
  },
};

/** Instructions Monocle wraps around the argument of each Cravat-routed command. */
const AGENTIC_TEMPLATES: Record<string, (argument: string) => string> = {
  lookup: (question) =>
    [
      "Answer the question below from the user's Obsidian vault.",
      "Use the monocle_vault tools (search_notes, then read_note) to find and read the relevant notes.",
      "Answer only from notes you actually read, cite each note you rely on by its vault path, and say plainly if the vault does not contain the answer.",
      "Do not modify any files.",
      "",
      `Question: ${question}`,
    ].join("\n"),
};

export type AgenticCommandPlan =
  | { readonly ok: true; readonly request: ExecutionRequest; readonly recordedPrompt: string }
  | { readonly ok: false; readonly error: ExecutionError };

/**
 * Turns an execution request naming a registry command into what Cravat runs. Deterministic commands are refused
 * so they can never start Cravat; missing context is reported before anything runs.
 */
export function planAgenticCommand(request: ExecutionRequest, vaultConfigured: boolean): AgenticCommandPlan {
  const { command, ...rest } = request;
  if (command === undefined) return { ok: true, request: rest, recordedPrompt: rest.prompt };
  const def = findCommand(command);
  if (!def) return { ok: false, error: { code: "invalid_request", message: `Unknown command /${command}` } };
  if (def.route !== "cravat") {
    return { ok: false, error: { code: "invalid_request", message: `/${def.id} runs in Monocle: send it to POST ${COMMANDS_PATH}` } };
  }
  const active = request.context?.activeNote;
  const missing = missingContext(def, {
    argument: rest.prompt,
    ...(active && { activeNote: { path: active.path, ...(active.selection !== undefined && { selection: active.selection }) } }),
    vault: vaultConfigured,
  });
  if (missing.length > 0) return { ok: false, error: { code: "missing_context", message: missing.join("; ") } };
  const argument = rest.prompt.trim();
  return { ok: true, request: { ...rest, prompt: AGENTIC_TEMPLATES[def.id]!(argument) }, recordedPrompt: `/${def.id} ${argument}` };
}

/** `POST /v1/commands` (IMM-51): runs a deterministic registry command without Cravat. */
export async function handleCommandRoute(index: IndexService | undefined, req: IncomingMessage, res: ServerResponse, send: Send): Promise<void> {
  const fail = (status: number, error: CommandError) => send(res, status, { error });
  if (req.method !== "POST") return send(res, 405, { error: "method not allowed" });
  // Non-simple content type forces a CORS preflight, so web pages can't trigger commands.
  if (!/^application\/json\b/i.test(req.headers["content-type"] ?? "")) {
    return fail(415, { code: "invalid_request", message: "content-type must be application/json" });
  }
  let body: unknown;
  try {
    body = await readJson(req);
  } catch (error) {
    return fail(400, { code: "invalid_request", message: (error as Error).message });
  }
  const parsed = parseCommandRequest(body);
  if (!parsed.ok) return fail(400, { code: "invalid_request", message: parsed.error });
  const request = parsed.request;
  const def: CommandDefinition | undefined = findCommand(request.command);
  if (!def) return fail(400, { code: "unknown_command", message: `Unknown command /${request.command}` });
  if (def.route !== "monocle") {
    return fail(400, { code: "agentic_command", message: `/${def.id} runs in Cravat: send it to POST /v1/executions with "command": "${def.id}"` });
  }
  const available = { argument: request.argument ?? "", ...(request.context?.activeNote && { activeNote: request.context.activeNote }), vault: index !== undefined };
  const missing = missingContext(def, available);
  if (missing.length > 0) return fail(400, { code: "missing_context", message: missing.join("; "), missing });
  try {
    return send(res, 200, await RUNNERS[def.id]!(index!, resolveCommandArgument(def, available), request));
  } catch (error) {
    if (error instanceof InvalidNotePathError) return fail(400, { code: "invalid_request", message: error.message });
    throw error;
  }
}
