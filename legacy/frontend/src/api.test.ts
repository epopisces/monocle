import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiGet, apiPost, apiPatch, apiPut, apiDelete, ApiError } from './api/client'

// helpers
function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('apiGet', () => {
  afterEach(() => vi.restoreAllMocks())

  it('returns parsed JSON on 200', async () => {
    mockFetch(200, { status: 'ready' })
    const result = await apiGet<{ status: string }>('/api/health')
    expect(result.status).toBe('ready')
  })

  it('appends query params', async () => {
    const spy = mockFetch(200, [])
    await apiGet('/api/notes', { limit: 10, folder: 'people' })
    const url = (spy.mock.calls[0][0] as string)
    expect(url).toContain('limit=10')
    expect(url).toContain('folder=people')
  })

  it('omits null/undefined params', async () => {
    const spy = mockFetch(200, [])
    await apiGet('/api/notes', { limit: 10, folder: null, type: undefined })
    const url = (spy.mock.calls[0][0] as string)
    expect(url).not.toContain('folder')
    expect(url).not.toContain('type')
  })

  it('throws ApiError on 404', async () => {
    mockFetch(404, { detail: 'Not found' })
    await expect(apiGet('/api/notes/missing')).rejects.toBeInstanceOf(ApiError)
  })

  it('ApiError carries HTTP status', async () => {
    mockFetch(422, { detail: 'Validation error' })
    await expect(apiGet('/api/notes/x')).rejects.toMatchObject({ status: 422 })
  })
})

describe('apiPost', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends JSON body', async () => {
    const spy = mockFetch(200, { ok: true })
    await apiPost('/api/ingest', { content: 'hello' })
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ content: 'hello' })
  })

  it('returns parsed response', async () => {
    mockFetch(200, { note: { file_path: 'inbox/test.md' } })
    const r = await apiPost<{ note: { file_path: string } }>('/api/ingest', {})
    expect(r.note.file_path).toBe('inbox/test.md')
  })
})

describe('apiPatch', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends PATCH method with JSON body', async () => {
    const spy = mockFetch(200, { ai: { provider: 'ollama' } })
    await apiPatch('/api/settings', { ai: { provider: 'ollama' } })
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PATCH')
  })
})

describe('health API', () => {
  beforeEach(() => {
    mockFetch(200, {
      status: 'ready',
      version: '0.1.0',
      ai_reachable: true,
      index_status: 'ready',
      watcher_running: true,
      telemetry_endpoint: null,
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it('getHealth returns typed HealthResponse', async () => {
    const { getHealth } = await import('./api/health')
    const h = await getHealth()
    expect(h.status).toBe('ready')
    expect(h.ai_reachable).toBe(true)
  })
})

describe('notes API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('listNotes calls /api/notes', async () => {
    const spy = mockFetch(200, { items: [], total: 0, offset: 0, limit: 50 })
    const { listNotes } = await import('./api/notes')
    await listNotes({ limit: 20 })
    expect((spy.mock.calls[0][0] as string)).toContain('/api/notes')
  })
})

describe('search API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('semanticSearch calls /api/search', async () => {
    const spy = mockFetch(200, [])
    const { semanticSearch } = await import('./api/search')
    await semanticSearch({ q: 'test' })
    expect((spy.mock.calls[0][0] as string)).toContain('/api/search')
    expect((spy.mock.calls[0][0] as string)).toContain('q=test')
  })
})

describe('settings API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('getSettings calls /api/settings', async () => {
    mockFetch(200, { ai: { provider: 'ollama' }, mcp_key_last4: 'ab12' })
    const { getSettings } = await import('./api/settings')
    const s = await getSettings()
    expect(s.mcp_key_last4).toBe('ab12')
  })

  it('patchSettings sends PATCH to /api/settings', async () => {
    const spy = mockFetch(200, { ai: { provider: 'foundry_local' } })
    const { patchSettings } = await import('./api/settings')
    await patchSettings({ ai: { provider: 'foundry_local' } })
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PATCH')
  })
})

describe('apiPut', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends PUT method with JSON body', async () => {
    const spy = mockFetch(200, { file_path: 'people/alice.md' })
    await apiPut('/api/notes/people%2Falice.md', { content: 'hello', metadata: {} })
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toMatchObject({ content: 'hello' })
  })

  it('throws ApiError on 409 conflict', async () => {
    mockFetch(409, { detail: 'Conflict' })
    await expect(apiPut('/api/notes/x', {})).rejects.toMatchObject({ status: 409 })
  })
})

describe('apiDelete', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends DELETE method', async () => {
    const spy = mockFetch(200, {})
    await apiDelete('/api/notes/people%2Falice.md')
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('DELETE')
  })

  it('throws ApiError on 404', async () => {
    mockFetch(404, { detail: 'Not found' })
    await expect(apiDelete('/api/notes/missing')).rejects.toMatchObject({ status: 404 })
  })

  it('throws ApiError on 500 (no silent swallow)', async () => {
    mockFetch(500, { detail: 'Server error' })
    await expect(apiDelete('/api/ingest/failures/bad-id')).rejects.toBeInstanceOf(ApiError)
  })
})

// ---------------------------------------------------------------------------
// Error path coverage
// ---------------------------------------------------------------------------

describe('ApiError — HTTP 429 rate limit', () => {
  afterEach(() => vi.restoreAllMocks())

  it('throws ApiError with status 429', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
      }),
    )
    await expect(apiGet('/api/ingest')).rejects.toMatchObject({
      status: 429,
      message: 'Rate limit exceeded',
    })
  })

  it('ApiError is an instance of Error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Too many requests' }), { status: 429 }),
    )
    const err = await apiPost('/api/ingest', {}).catch(e => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.name).toBe('ApiError')
  })
})

describe('ApiError — HTTP 500 / 502 server errors', () => {
  afterEach(() => vi.restoreAllMocks())

  it('uses fallback message when body has no detail field', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('Internal Server Error', {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )
    const err = await apiGet('/api/notes').catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(500)
    expect(err.message).toBe('HTTP 500')
  })

  it('extracts detail message from 502 JSON body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Bad gateway' }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const err = await apiGet('/api/health').catch(e => e)
    expect(err.status).toBe(502)
    expect(err.message).toBe('Bad gateway')
  })
})

describe('ApiError — network failure', () => {
  afterEach(() => vi.restoreAllMocks())

  it('propagates TypeError from a failed fetch (not wrapped as ApiError)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(
      new TypeError('Failed to fetch'),
    )
    const err = await apiGet('/api/health').catch(e => e)
    // Network errors are NOT ApiError — they bubble as TypeError
    expect(err).toBeInstanceOf(TypeError)
    expect(err).not.toBeInstanceOf(ApiError)
  })

  it('POST network failure also propagates raw error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(
      new TypeError('Network request failed'),
    )
    const err = await apiPost('/api/ingest', {}).catch(e => e)
    expect(err).not.toBeInstanceOf(ApiError)
    expect(err.message).toBe('Network request failed')
  })
})

describe('handleResponse — 204 No Content', () => {
  afterEach(() => vi.restoreAllMocks())

  it('returns undefined for a 204 response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    )
    const result = await apiDelete('/api/notes/some-file.md')
    expect(result).toBeUndefined()
  })
})
