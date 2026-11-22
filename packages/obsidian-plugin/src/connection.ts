import {
  CONTRACT_VERSION,
  HEALTH_PATH,
  isContractCompatible,
  isHealthResponse,
  type HealthResponse,
} from "@monocle/contracts";

/**
 * Performs `GET url` and returns the status and parsed JSON body. Inside Obsidian this is backed by
 * `requestUrl` (which bypasses renderer CORS); tests use `fetch`.
 */
export type HealthProbe = (url: string) => Promise<{ status: number; json: unknown }>;

export type ConnectionState =
  | { readonly kind: "connecting"; readonly endpoint: string }
  | { readonly kind: "connected"; readonly endpoint: string; readonly health: HealthResponse }
  | { readonly kind: "disconnected"; readonly endpoint: string; readonly error: string }
  | { readonly kind: "incompatible"; readonly endpoint: string; readonly health: HealthResponse; readonly error: string };

export interface CompanionConnectionOptions {
  readonly endpoint: string;
  readonly probe: HealthProbe;
  /** Health-check polling interval while started. */
  readonly intervalMs?: number;
  /** Per-check timeout; a hung companion is reported as disconnected. */
  readonly timeoutMs?: number;
}

/**
 * Tracks the plugin's view of the companion. It only observes: it never launches or stops the
 * companion, so the companion's lifecycle stays independent of Obsidian.
 */
export class CompanionConnection {
  readonly endpoint: string;
  private readonly probe: HealthProbe;
  private readonly intervalMs: number;
  private readonly timeoutMs: number;
  private readonly listeners = new Set<(state: ConnectionState) => void>();
  private current: ConnectionState;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running = false;

  constructor(options: CompanionConnectionOptions) {
    this.endpoint = options.endpoint;
    this.probe = options.probe;
    this.intervalMs = options.intervalMs ?? 5_000;
    this.timeoutMs = options.timeoutMs ?? 3_000;
    this.current = { kind: "connecting", endpoint: this.endpoint };
  }

  get state(): ConnectionState {
    return this.current;
  }

  /** Subscribes to state changes; the listener is called immediately with the current state. */
  onChange(listener: (state: ConnectionState) => void): () => void {
    this.listeners.add(listener);
    listener(this.current);
    return () => this.listeners.delete(listener);
  }

  /** Runs one health check now and returns the resulting state. Never throws. */
  async check(): Promise<ConnectionState> {
    const next = await this.evaluate();
    this.set(next);
    return next;
  }

  /** Starts polling. Safe to call repeatedly. */
  start(): void {
    if (this.running) return;
    this.running = true;
    const tick = async () => {
      await this.check();
      if (this.running) this.timer = setTimeout(() => void tick(), this.intervalMs);
    };
    void tick();
  }

  /** Stops polling. Does not affect the companion process. */
  stop(): void {
    this.running = false;
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
  }

  private async evaluate(): Promise<ConnectionState> {
    const endpoint = this.endpoint;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const res = await Promise.race([
        this.probe(new URL(HEALTH_PATH, endpoint).href),
        new Promise<never>((_, reject) => {
          timeout = setTimeout(() => reject(new Error(`health check timed out after ${this.timeoutMs} ms`)), this.timeoutMs);
        }),
      ]);
      if (res.status !== 200) return { kind: "disconnected", endpoint, error: `health check returned HTTP ${res.status}` };
      if (!isHealthResponse(res.json)) {
        return { kind: "disconnected", endpoint, error: `service at ${endpoint} is not a Monocle companion` };
      }
      const health = res.json;
      if (!isContractCompatible({ local: CONTRACT_VERSION, remote: health.contractVersion })) {
        return {
          kind: "incompatible",
          endpoint,
          health,
          error: `companion contract ${health.contractVersion} is incompatible with plugin contract ${CONTRACT_VERSION}`,
        };
      }
      return { kind: "connected", endpoint, health };
    } catch (err) {
      return { kind: "disconnected", endpoint, error: err instanceof Error ? err.message : String(err) };
    } finally {
      if (timeout !== undefined) clearTimeout(timeout);
    }
  }

  private set(next: ConnectionState): void {
    const prev = this.current;
    this.current = next;
    const sameInstance = (s: ConnectionState) => ("health" in s ? s.health.instanceId : undefined);
    if (prev.kind === next.kind && sameInstance(prev) === sameInstance(next)) return;
    for (const l of this.listeners) l(next);
  }
}
