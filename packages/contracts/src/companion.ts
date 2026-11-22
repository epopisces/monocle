/**
 * Plugin ↔ companion transport contract. The companion serves HTTP on a loopback address only;
 * clients discover it via a host-local endpoint setting and verify it with the health check.
 */

/** Identifies a Monocle companion in health responses, so clients don't mistake another local service for it. */
export const COMPANION_SERVICE_ID = "monocle-companion";

export const HEALTH_PATH = "/v1/health";

export const DEFAULT_COMPANION_HOST = "127.0.0.1";
export const DEFAULT_COMPANION_PORT = 48765;
export const DEFAULT_COMPANION_ENDPOINT = `http://${DEFAULT_COMPANION_HOST}:${DEFAULT_COMPANION_PORT}`;

/** Body of `GET {@link HEALTH_PATH}`. */
export interface HealthResponse {
  readonly service: typeof COMPANION_SERVICE_ID;
  readonly status: "ok";
  /** Contract version the companion implements; clients check it with `isContractCompatible`. */
  readonly contractVersion: string;
  /** Opaque per-process identifier; changes when the companion restarts. */
  readonly instanceId: string;
  /** ISO-8601 start time of the companion process. */
  readonly startedAt: string;
}

const LOOPBACK_HOSTNAMES = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

/** True for hostnames that resolve to the local loopback interface. */
export function isLoopbackHostname(hostname: string): boolean {
  return LOOPBACK_HOSTNAMES.has(hostname.toLowerCase()) || /^127(\.\d{1,3}){3}$/.test(hostname);
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.service === COMPANION_SERVICE_ID &&
    v.status === "ok" &&
    typeof v.contractVersion === "string" &&
    typeof v.instanceId === "string" &&
    typeof v.startedAt === "string"
  );
}
