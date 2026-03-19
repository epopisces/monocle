/**
 * Typed fetch wrapper for the Monocle API.
 *
 * All requests go to the same origin (Vite dev proxy forwards /api → :8000).
 * Errors are thrown as `ApiError` instances so callers can distinguish
 * HTTP error codes from network failures.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: string }
      if (body?.detail) message = String(body.detail)
    } catch {
      // ignore parse error — keep generic message
    }
    throw new ApiError(res.status, message)
  }
  // 204 No Content
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** GET a JSON endpoint. */
export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
): Promise<T> {
  let url = path
  if (params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined) qs.set(k, String(v))
    }
    const s = qs.toString()
    if (s) url = `${path}?${s}`
  }
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  return handleResponse<T>(res)
}

/** POST a JSON body, receive JSON. */
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}

/** PATCH a JSON body, receive JSON. */
export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

/** PUT a JSON body, receive JSON. */
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

/** DELETE, optionally receive JSON. */
export async function apiDelete<T = void>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  return handleResponse<T>(res)
}

/**
 * Open an SSE stream.  The caller is responsible for closing the
 * `EventSource` when done.  Each `message` event calls `onEvent`.
 * Named events (e.g. `event: token`) are dispatched as custom events.
 *
 * For endpoints that use `POST` to start the stream, use `apiPostSse`.
 */
export function apiSse(
  url: string,
  handlers: Partial<Record<string, (data: unknown) => void>>,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(url)
  for (const [event, handler] of Object.entries(handlers)) {
    if (!handler) continue
    es.addEventListener(event, (e: MessageEvent) => {
      try {
        handler(JSON.parse(e.data as string))
      } catch {
        handler(e.data)
      }
    })
  }
  if (onError) es.addEventListener('error', onError)
  return () => es.close()
}

/**
 * Stream SSE from a POST body via fetch + ReadableStream.
 * Returns an async generator that yields `{ event, data }` pairs.
 */
export async function* apiPostSseStream(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<{ event: string; data: unknown }> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, `SSE stream failed: HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = 'message'

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          let parsed: unknown = raw
          try { parsed = JSON.parse(raw) } catch { /* keep as string */ }
          yield { event: currentEvent, data: parsed }
          currentEvent = 'message'
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
