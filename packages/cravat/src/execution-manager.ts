import { randomUUID } from "node:crypto";
import type { ExecutionError, ExecutionErrorCode, ExecutionEvent, ExecutionRequest } from "@monocle/contracts";

/** Output a provider adapter produces while running. */
export type ProviderEvent = { readonly type: "delta"; readonly text: string };

/**
 * A provider runtime behind Cravat (D04). `run` streams output and must stop work promptly when `signal`
 * aborts; it reports failures by throwing, preferably a {@link ProviderError}.
 */
export interface ProviderAdapter {
  readonly id: string;
  run(request: ExecutionRequest, signal: AbortSignal): AsyncIterable<ProviderEvent>;
}

export class ProviderError extends Error {
  constructor(
    readonly code: Exclude<ExecutionErrorCode, "invalid_request" | "connection_lost">,
    message: string,
  ) {
    super(message);
    this.name = "ProviderError";
  }
}

export interface Execution {
  readonly id: string;
  /** Single-consumer stream of this execution's events; always ends after one terminal event. */
  readonly events: AsyncIterable<ExecutionEvent>;
}

export interface ExecutionManagerOptions {
  readonly adapter: ProviderAdapter;
  /** Companion instance ID stamped on `started` events. */
  readonly instanceId: string;
  /** How long to wait for an aborted provider to stop before forcing the `cancelled` terminal state. */
  readonly cancelGraceMs?: number;
}

type Payload<E = ExecutionEvent> = E extends ExecutionEvent ? Omit<E, "executionId" | "seq"> : never;

class EventQueue {
  private readonly buffer: ExecutionEvent[] = [];
  private waiting: (() => void) | undefined;
  private closed = false;

  push(event: ExecutionEvent): void {
    this.buffer.push(event);
    this.waiting?.();
  }

  close(): void {
    this.closed = true;
    this.waiting?.();
  }

  async *drain(): AsyncGenerator<ExecutionEvent> {
    for (;;) {
      const next = this.buffer.shift();
      if (next) {
        yield next;
        continue;
      }
      if (this.closed) return;
      await new Promise<void>((resolve) => (this.waiting = resolve));
      this.waiting = undefined;
    }
  }
}

class RunningExecution {
  readonly controller = new AbortController();
  private seq = 0;
  private finished = false;

  constructor(
    readonly id: string,
    private readonly queue: EventQueue,
    private readonly onFinish: () => void,
  ) {}

  get done(): boolean {
    return this.finished;
  }

  emit(payload: Payload): void {
    if (this.finished) return;
    this.queue.push({ ...payload, executionId: this.id, seq: this.seq++ } as ExecutionEvent);
  }

  finish(payload: Payload<Extract<ExecutionEvent, { type: "completed" | "failed" | "cancelled" }>>): void {
    if (this.finished) return;
    this.emit(payload);
    this.finished = true;
    this.queue.close();
    this.onFinish();
  }
}

function toExecutionError(err: unknown): ExecutionError {
  if (err instanceof ProviderError) return { code: err.code, message: err.message };
  return { code: "provider_error", message: err instanceof Error ? err.message : String(err) };
}

/** Owns Cravat execution sessions: identity, streaming, cancellation and terminal states. */
export class ExecutionManager {
  private readonly adapter: ProviderAdapter;
  private readonly instanceId: string;
  private readonly cancelGraceMs: number;
  private readonly running = new Map<string, RunningExecution>();

  constructor(options: ExecutionManagerOptions) {
    this.adapter = options.adapter;
    this.instanceId = options.instanceId;
    this.cancelGraceMs = options.cancelGraceMs ?? 5_000;
  }

  get providerId(): string {
    return this.adapter.id;
  }

  start(request: ExecutionRequest): Execution {
    const queue = new EventQueue();
    const execution = new RunningExecution(randomUUID(), queue, () => this.running.delete(execution.id));
    this.running.set(execution.id, execution);
    execution.emit({
      type: "started",
      provider: this.adapter.id,
      instanceId: this.instanceId,
      startedAt: new Date().toISOString(),
    });
    void this.drive(execution, request);
    return { id: execution.id, events: queue.drain() };
  }

  /** Requests cancellation. Returns false if the execution is unknown or already terminal. */
  cancel(executionId: string): boolean {
    const execution = this.running.get(executionId);
    if (!execution || execution.done || execution.controller.signal.aborted) return false;
    execution.controller.abort();
    const timer = setTimeout(() => execution.finish({ type: "cancelled" }), this.cancelGraceMs);
    timer.unref?.();
    return true;
  }

  /** Cancels every running execution (companion shutdown). */
  cancelAll(): void {
    for (const id of [...this.running.keys()]) this.cancel(id);
  }

  private async drive(execution: RunningExecution, request: ExecutionRequest): Promise<void> {
    const { signal } = execution.controller;
    let text = "";
    try {
      for await (const event of this.adapter.run(request, signal)) {
        if (signal.aborted || execution.done) break;
        text += event.text;
        execution.emit({ type: "delta", text: event.text });
      }
      execution.finish(signal.aborted ? { type: "cancelled" } : { type: "completed", text });
    } catch (err) {
      execution.finish(signal.aborted ? { type: "cancelled" } : { type: "failed", error: toExecutionError(err) });
    }
  }
}
