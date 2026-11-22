import type { IncomingMessage, ServerResponse } from "node:http";
import {
  INDEX_HEALTH_PATH,
  INDEX_REBUILD_PATH,
  INDEX_RECONCILE_PATH,
  INDEX_REINDEX_NOTE_PATH,
  type IndexActionResponse,
  type IndexChangeCounts,
} from "@monocle/contracts";
import { InvalidNotePathError, type IndexService } from "@monocle/core";

export const INDEX_ROUTE_PREFIX = "/v1/index/";

type Send = (res: ServerResponse, status: number, body: unknown) => void;

const MAX_BODY_BYTES = 64 * 1024;

function readJson(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("request body too large"));
        req.destroy();
      } else chunks.push(chunk);
    });
    req.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8").trim();
      try {
        resolve(text === "" ? {} : JSON.parse(text));
      } catch {
        reject(new Error("request body is not valid JSON"));
      }
    });
    req.on("error", reject);
  });
}

/** Handles `/v1/index/*` (IMM-61). Without an index service every route answers 404. */
export async function handleIndexRoute(
  index: IndexService | undefined,
  req: IncomingMessage,
  res: ServerResponse,
  path: string,
  send: Send,
): Promise<void> {
  const actions: Record<string, (body: Record<string, unknown>) => IndexChangeCounts | "bad-request"> = {
    [INDEX_RECONCILE_PATH]: () => index!.reconcile(),
    [INDEX_REBUILD_PATH]: () => index!.rebuild(),
    [INDEX_REINDEX_NOTE_PATH]: (body) => (typeof body.path === "string" ? index!.reindexNote(body.path) : "bad-request"),
  };
  const isAction = Object.hasOwn(actions, path);
  if (path !== INDEX_HEALTH_PATH && !isAction) return send(res, 404, { error: "not found" });
  if (!index) return send(res, 404, { error: "index service not configured (start the companion with --vault)" });

  if (path === INDEX_HEALTH_PATH) {
    return req.method === "GET" ? send(res, 200, index.health()) : send(res, 405, { error: "method not allowed" });
  }
  if (req.method !== "POST") return send(res, 405, { error: "method not allowed" });
  // Non-simple content type forces a CORS preflight, which the companion never grants, so web pages can't trigger it.
  if (!/^application\/json\b/i.test(req.headers["content-type"] ?? "")) {
    return send(res, 415, { error: "content-type must be application/json" });
  }
  let body: unknown;
  try {
    body = await readJson(req);
  } catch (error) {
    return send(res, 400, { error: (error as Error).message });
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return send(res, 400, { error: "request body must be a JSON object" });
  }
  try {
    const changes = actions[path]!(body as Record<string, unknown>);
    if (changes === "bad-request") return send(res, 400, { error: "body.path must be a vault-relative note path" });
    const response: IndexActionResponse = { changes, health: index.health() };
    return send(res, 200, response);
  } catch (error) {
    if (error instanceof InvalidNotePathError) return send(res, 400, { error: error.message });
    return send(res, 500, { error: error instanceof Error ? error.message : String(error), health: index.health() });
  }
}
