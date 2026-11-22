import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import {
  COMPANION_SERVICE_ID,
  CONTRACT_VERSION,
  DEFAULT_COMPANION_HOST,
  DEFAULT_COMPANION_PORT,
  HEALTH_PATH,
  isLoopbackHostname,
  type HealthResponse,
} from "@monocle/contracts";

export interface CompanionOptions {
  /** Loopback address to bind. Non-loopback hosts are refused; remote exposure is out of MVP scope (D01). */
  readonly host?: string;
  /** TCP port; `0` picks a free port. */
  readonly port?: number;
}

export interface RunningCompanion {
  /** Base URL clients should use, e.g. `http://127.0.0.1:48765`. */
  readonly url: string;
  readonly health: HealthResponse;
  close(): Promise<void>;
}

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

  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    // Guards against DNS-rebinding: browsers send the attacker's hostname in Host.
    const reqHost = hostnameOf(req.headers.host);
    if (!reqHost || !isLoopbackHostname(reqHost)) return sendJson(res, 403, { error: "forbidden host" });
    const path = new URL(req.url ?? "/", "http://localhost").pathname;
    if (req.method === "GET" && path === HEALTH_PATH) return sendJson(res, 200, health);
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
        server.close((err) => (err ? reject(err) : resolve()));
        server.closeAllConnections();
      }),
  };
}
