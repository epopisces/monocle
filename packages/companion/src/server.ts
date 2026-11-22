import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import {
  ALLOWED_CLIENT_ORIGINS,
  CAPABILITIES_PATH,
  COMPANION_SERVICE_ID,
  CONVERSATIONS_PATH,
  CONTRACT_VERSION,
  DEFAULT_COMPANION_HOST,
  DEFAULT_COMPANION_PORT,
  EXECUTION_STREAM_CONTENT_TYPE,
  EXECUTIONS_PATH,
  HEALTH_PATH,
  MAX_PROMPT_LENGTH,
  isLoopbackHostname,
  isTerminalExecutionEvent,
  parseExecutionRequest,
  type Conversation,
  type ConversationListResponse,
  type ExecutionError,
  type HealthResponse,
  type ProviderSessionInfo,
} from "@monocle/contracts";
import { ConversationStore, conversationTitle, type IndexService } from "@monocle/core";
import { handleIndexRoute, INDEX_ROUTE_PREFIX } from "./index-routes.js";
import { CopilotCliAdapter, ExecutionManager, type ProviderAdapter } from "@monocle/cravat";

export interface CompanionOptions {
  /** Loopback address to bind. Non-loopback hosts are refused; remote exposure is out of MVP scope (D01). */
  readonly host?: string;
  /** TCP port; `0` picks a free port. */
  readonly port?: number;
  /** Derived indexes for the configured vault; index routes answer 404 without one. Owned by the caller. */
  readonly index?: IndexService;
  /** Cravat provider adapter; defaults to the installed Copilot CLI. */
  readonly adapter?: ProviderAdapter;
  /**
   * Machine-local directory for companion state such as conversations (never the vault). Omitted: state is kept
   * in memory and lost when the companion stops.
   */
  readonly dataDir?: string;
}

export interface RunningCompanion {
  /** Base URL clients should use, e.g. `http://127.0.0.1:48765`. */
  readonly url: string;
  readonly health: HealthResponse;
  close(): Promise<void>;
}

/** UTF-16 prompt limit times the worst-case UTF-8 expansion, plus JSON overhead. */
const MAX_BODY_BYTES = MAX_PROMPT_LENGTH * 4 + 4_096;
const CANCEL_PATH = new RegExp(`^${EXECUTIONS_PATH}/([^/]+)/cancel$`);
const CONVERSATION_PATH = new RegExp(`^${CONVERSATIONS_PATH}/([^/]+)$`);

function hostnameOf(hostHeader: string | undefined): string | undefined {
  if (!hostHeader) return undefined;
  try {
    return new URL(`http://${hostHeader}`).hostname;
  } catch {
    return undefined;
  }
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(body));
}

const sendError = (res: ServerResponse, status: number, error: ExecutionError) => sendJson(res, status, { error });

class BodyTooLarge extends Error {}

async function readBody(req: IncomingMessage): Promise<string> {
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of req as AsyncIterable<Buffer>) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new BodyTooLarge();
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

interface ResumePlan {
  /** Provider session to continue, when the previous one belongs to the current provider. */
  readonly resumeId?: string;
  /** Why earlier context cannot be carried over, when the conversation has earlier executions. */
  readonly unavailable?: string;
}

/** Decides how a new execution relates to the provider context of earlier executions in its conversation. */
function planResume(conversation: Conversation, providerId: string): ResumePlan {
  if (conversation.executions.length === 0) return {};
  const previous = [...conversation.executions].reverse().find((e) => e.providerSession?.id !== undefined);
  if (!previous) return { unavailable: "no provider session was recorded for earlier messages" };
  if (previous.provider !== providerId) {
    return { unavailable: `provider changed from ${previous.provider} to ${providerId}` };
  }
  return { resumeId: previous.providerSession!.id! };
}

/** Combines the adapter's report with what the companion asked for into the recorded session outcome. */
function sessionOutcome(plan: ResumePlan, reported: ProviderSessionInfo | undefined): ProviderSessionInfo | undefined {
  if (reported?.continuity === "unavailable") return reported;
  if (plan.unavailable !== undefined) {
    return { ...(reported?.id !== undefined && { id: reported.id }), continuity: "unavailable", reason: plan.unavailable };
  }
  if (plan.resumeId !== undefined && reported?.continuity !== "resumed") {
    return {
      ...(reported?.id !== undefined && { id: reported.id }),
      continuity: "unavailable",
      reason: `provider did not confirm resuming session ${plan.resumeId}`,
    };
  }
  return reported;
}

/** Starts the companion's loopback HTTP endpoint. Its lifetime is owned by the caller, never by Obsidian. */
export async function startCompanion(options: CompanionOptions = {}): Promise<RunningCompanion> {
  const host = options.host ?? DEFAULT_COMPANION_HOST;
  const port = options.port ?? DEFAULT_COMPANION_PORT;
  if (!isLoopbackHostname(host)) {
    throw new Error(`Companion host must be a loopback address, got "${host}"`);
  }

  const health: HealthResponse = {
    service: COMPANION_SERVICE_ID,
    status: "ok",
    contractVersion: CONTRACT_VERSION,
    instanceId: randomUUID(),
    startedAt: new Date().toISOString(),
  };
  const cravat = new ExecutionManager({ adapter: options.adapter ?? new CopilotCliAdapter(), instanceId: health.instanceId });
  const conversations = await ConversationStore.open({
    instanceId: health.instanceId,
    ...(options.dataDir !== undefined && { dir: options.dataDir }),
  });

  async function startExecution(req: IncomingMessage, res: ServerResponse): Promise<void> {
    // Requiring JSON forces a CORS preflight for browser callers, so a web page cannot fire a "simple" POST.
    if (!/^application\/json\b/i.test(req.headers["content-type"] ?? "")) {
      return sendError(res, 415, { code: "invalid_request", message: "content-type must be application/json" });
    }
    let body: unknown;
    try {
      body = JSON.parse(await readBody(req));
    } catch (err) {
      if (err instanceof BodyTooLarge) return sendError(res, 413, { code: "invalid_request", message: "request body too large" });
      return sendError(res, 400, { code: "invalid_request", message: "request body is not valid JSON" });
    }
    const parsed = parseExecutionRequest(body);
    if (!parsed.ok) return sendError(res, 400, { code: "invalid_request", message: parsed.error });
    const unsupported = await cravat.validate(parsed.request);
    if (unsupported) return sendError(res, 400, { code: "invalid_request", message: unsupported });

    const { prompt, conversationId } = parsed.request;
    let conversation;
    if (conversationId === undefined) {
      conversation = conversations.create(conversationTitle(prompt));
    } else {
      conversation = conversations.get(conversationId);
      if (!conversation) return sendError(res, 404, { code: "invalid_request", message: `unknown conversation ${conversationId}` });
      if (conversations.running(conversationId)) {
        return sendError(res, 409, { code: "invalid_request", message: "this conversation already has a running execution" });
      }
    }

    const plan = planResume(conversation, cravat.providerId);
    const execution = cravat.start(parsed.request, plan.resumeId !== undefined ? { resumeProviderSessionId: plan.resumeId } : {});
    conversations.beginExecution(conversation.id, {
      executionId: execution.id,
      provider: cravat.providerId,
      instanceId: health.instanceId,
      startedAt: new Date().toISOString(),
      prompt,
      contextReferences: [],
    });
    let terminal = false;
    let streamed = "";
    // Closing the stream early (panel closed, client aborted) cancels the work instead of orphaning it.
    res.once("close", () => {
      if (!terminal) cravat.cancel(execution.id);
    });
    res.writeHead(200, {
      "content-type": `${EXECUTION_STREAM_CONTENT_TYPE}; charset=utf-8`,
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    });
    for await (let event of execution.events) {
      if (event.type === "started") event = { ...event, conversationId: conversation.id };
      else if (event.type === "delta") streamed += event.text;
      else if (isTerminalExecutionEvent(event)) {
        terminal = true;
        const providerSession = sessionOutcome(plan, event.providerSession);
        if (providerSession) event = { ...event, providerSession };
        conversations.finishExecution(conversation.id, execution.id, {
          status: event.type,
          ...(providerSession && { providerSession }),
          ...(event.type === "completed" ? { response: event.text } : streamed && { response: streamed }),
          ...(event.type === "failed" && { error: event.error }),
        });
      }
      if (!res.writableEnded && !res.destroyed) res.write(`${JSON.stringify(event)}\n`);
    }
    res.end();
  }

  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    // Guards against DNS-rebinding: browsers send the attacker's hostname in Host.
    const reqHost = hostnameOf(req.headers.host);
    if (!reqHost || !isLoopbackHostname(reqHost)) return sendJson(res, 403, { error: "forbidden host" });
    // Browsers always send Origin on cross-origin requests; only Obsidian's renderer may call us.
    const origin = req.headers.origin;
    if (origin !== undefined) {
      if (!ALLOWED_CLIENT_ORIGINS.includes(origin)) return sendJson(res, 403, { error: "forbidden origin" });
      res.setHeader("access-control-allow-origin", origin);
      res.setHeader("vary", "Origin");
    }
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "access-control-allow-methods": "GET, POST",
        "access-control-allow-headers": "content-type",
        "access-control-max-age": "600",
        ...(req.headers["access-control-request-private-network"] === "true" && {
          "access-control-allow-private-network": "true",
        }),
      });
      return res.end();
    }

    const path = new URL(req.url ?? "/", "http://localhost").pathname;
    if (req.method === "GET" && path === HEALTH_PATH) return sendJson(res, 200, health);
    if (path.startsWith(INDEX_ROUTE_PREFIX)) return void handleIndexRoute(options.index, req, res, path, sendJson);
    if (req.method === "GET" && path === CAPABILITIES_PATH) {
      cravat.capabilities().then(
        (caps) => sendJson(res, 200, caps),
        (err: unknown) => sendError(res, 500, { code: "provider_error", message: `capability discovery failed: ${String(err)}` }),
      );
      return;
    }
    if (req.method === "GET" && path === CONVERSATIONS_PATH) {
      return sendJson(res, 200, { conversations: conversations.list() } satisfies ConversationListResponse);
    }
    const conversationMatch = req.method === "GET" ? CONVERSATION_PATH.exec(path) : null;
    if (conversationMatch) {
      const conversation = conversations.get(decodeURIComponent(conversationMatch[1]!));
      return conversation ? sendJson(res, 200, conversation) : sendJson(res, 404, { error: "no conversation with that ID" });
    }
    if (req.method === "POST" && path === EXECUTIONS_PATH) {
      startExecution(req, res).catch((err: unknown) => {
        if (!res.headersSent) sendError(res, 500, { code: "provider_error", message: String(err) });
        else res.destroy();
      });
      return;
    }
    const cancel = req.method === "POST" ? CANCEL_PATH.exec(path) : null;
    if (cancel) {
      req.resume();
      const id = decodeURIComponent(cancel[1]!);
      return cravat.cancel(id)
        ? sendJson(res, 202, { executionId: id, status: "cancelling" })
        : sendJson(res, 404, { error: "no running execution with that ID" });
    }
    return sendJson(res, 404, { error: "not found" });
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, () => {
      server.off("error", reject);
      resolve();
    });
  });

  const address = server.address() as AddressInfo;
  const urlHost = address.family === "IPv6" ? `[${address.address}]` : address.address;
  return {
    url: `http://${urlHost}:${address.port}`,
    health,
    close: () =>
      new Promise<void>((resolve, reject) => {
        cravat.cancelAll();
        server.close((err) => (err ? reject(err) : resolve()));
        server.closeAllConnections();
      }).then(() => conversations.close()),
  };
}
