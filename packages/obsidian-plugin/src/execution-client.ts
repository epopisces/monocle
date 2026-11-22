import {
  CAPABILITIES_PATH,
  EXECUTIONS_PATH,
  cancelExecutionPath,
  isTerminalExecutionEvent,
  type ExecutionContext,
  type ExecutionCapabilities,
  type ExecutionError,
  type ExecutionEvent,
  type ExecutionSettings,
} from "@monocle/contracts";

/** Minimal `fetch` the client needs; Obsidian's renderer `fetch` and Node's global `fetch` both satisfy it. */
export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export interface ExecutionClientOptions {
  readonly endpoint: string;
  readonly fetch: FetchLike;
}

export interface ExecuteOptions {
  /** Note context the user chose to share (IMM-48). */
  readonly context?: ExecutionContext | undefined;
  /** Continue this companion conversation; omitted starts a new one (see `started.conversationId`). */
  readonly conversationId?: string;
}

export interface ExecutionHandle {
  /** Known once the `started` event arrives. */
  readonly executionId: string | undefined;
  /**
   * Single-consumer event stream. Always ends with exactly one terminal event; transport failures are
   * reported as `failed` with code `connection_lost` (executionId is `""` if the execution never started).
   */
  readonly events: AsyncIterable<ExecutionEvent>;
  /** Requests cancellation; the stream then ends with `cancelled`. Never throws. */
  cancel(): Promise<void>;
}

async function errorFromResponse(res: Response): Promise<ExecutionError> {
  try {
    const body = (await res.json()) as { error?: unknown };
    const err = body.error as Partial<ExecutionError> | string | undefined;
    if (typeof err === "object" && err && typeof err.code === "string" && typeof err.message === "string") {
      return { code: err.code, message: err.message };
    }
    if (typeof err === "string") return { code: "provider_error", message: `HTTP ${res.status}: ${err}` };
  } catch {
    // fall through
  }
  return { code: "provider_error", message: `companion returned HTTP ${res.status}` };
}

/** Starts and cancels Cravat executions through the companion. Obsidian-free so it is testable in Node. */
export class ExecutionClient {
  private readonly endpoint: string;
  private readonly fetch: FetchLike;

  constructor(options: ExecutionClientOptions) {
    this.endpoint = options.endpoint;
    this.fetch = options.fetch;
  }

  /**
   * Settings the companion's provider supports, or `undefined` when it cannot say (unreachable, or a
   * companion older than the capabilities route). Callers should then offer no settings.
   */
  async capabilities(): Promise<ExecutionCapabilities | undefined> {
    try {
      const res = await this.fetch(new URL(CAPABILITIES_PATH, this.endpoint).href, { method: "GET" });
      if (res.status !== 200) {
        await res.body?.cancel();
        return undefined;
      }
      const body = (await res.json()) as Partial<ExecutionCapabilities>;
      return typeof body.provider === "string" && typeof body.settings === "object" && body.settings
        ? { provider: body.provider, settings: body.settings }
        : undefined;
    } catch {
      return undefined;
    }
  }

  execute(prompt: string, settings?: ExecutionSettings, options: ExecuteOptions = {}): ExecutionHandle {
    const { context } = options;
    const controller = new AbortController();
    const client = this;
    let executionId: string | undefined;
    let cancelRequested = false;
    let seq = 0;

    const local = (event: { type: "cancelled" } | { type: "failed"; error: ExecutionError }): ExecutionEvent =>
      ({ ...event, executionId: executionId ?? "", seq }) as ExecutionEvent;

    async function* stream(): AsyncGenerator<ExecutionEvent> {
      let res: Response;
      try {
        res = await client.fetch(new URL(EXECUTIONS_PATH, client.endpoint).href, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            prompt,
            ...(options.conversationId !== undefined && { conversationId: options.conversationId }),
            ...(settings && Object.keys(settings).length > 0 && { settings }),
            ...(context && { context }),
          }),
          signal: controller.signal,
        });
      } catch (err) {
        yield cancelRequested
          ? local({ type: "cancelled" })
          : local({ type: "failed", error: { code: "connection_lost", message: `companion unreachable: ${(err as Error).message}` } });
        return;
      }
      if (res.status !== 200 || !res.body) {
        yield local({ type: "failed", error: await errorFromResponse(res) });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";
      try {
        for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
          buffer += decoder.decode(chunk, { stream: true });
          let nl: number;
          while ((nl = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, nl).trim();
            buffer = buffer.slice(nl + 1);
            if (!line) continue;
            const event = JSON.parse(line) as ExecutionEvent;
            if (event.type === "started") executionId = event.executionId;
            seq = event.seq + 1;
            yield event;
            if (isTerminalExecutionEvent(event)) return;
          }
        }
      } catch {
        // stream broke; reported below
      }
      yield cancelRequested
        ? local({ type: "cancelled" })
        : local({ type: "failed", error: { code: "connection_lost", message: "connection to the companion was lost before the execution finished" } });
    }

    return {
      get executionId() {
        return executionId;
      },
      events: stream(),
      async cancel() {
        cancelRequested = true;
        if (executionId === undefined) {
          // Not started yet: closing the request makes the companion cancel it.
          controller.abort();
          return;
        }
        try {
          const res = await client.fetch(new URL(cancelExecutionPath(executionId), client.endpoint).href, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: "{}",
          });
          await res.body?.cancel();
        } catch {
          controller.abort();
        }
      },
    };
  }
}
