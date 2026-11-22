export type FetchLike = typeof globalThis.fetch;

/** JSON request helper; non-2xx responses throw with the status in the message. */
export async function postJson(
  fetch: FetchLike,
  url: string,
  body: unknown,
  headers: Record<string, string> = {},
  method = "POST",
): Promise<unknown> {
  const response = await fetch(url, {
    method,
    headers: { "content-type": "application/json", ...headers },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${url} failed: ${response.status} ${text.slice(0, 200)}`);
  return text ? (JSON.parse(text) as unknown) : undefined;
}
