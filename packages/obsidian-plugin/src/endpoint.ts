import { DEFAULT_COMPANION_ENDPOINT, isLoopbackHostname } from "@monocle/contracts";

export type EndpointResult = { ok: true; endpoint: string } | { ok: false; error: string };

/**
 * Validates the host-specific companion endpoint. Only plain-HTTP loopback origins are accepted:
 * the companion is never exposed remotely in the MVP (D01). An empty value means the default.
 */
export function parseCompanionEndpoint(input: string): EndpointResult {
  const text = input.trim();
  if (text === "") return { ok: true, endpoint: DEFAULT_COMPANION_ENDPOINT };
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return { ok: false, error: `"${text}" is not a valid URL` };
  }
  if (url.protocol !== "http:") return { ok: false, error: "endpoint must use http:" };
  if (!isLoopbackHostname(url.hostname)) return { ok: false, error: "endpoint must be a loopback address" };
  if (url.pathname !== "/" || url.search || url.hash) return { ok: false, error: "endpoint must not include a path" };
  return { ok: true, endpoint: url.origin };
}
