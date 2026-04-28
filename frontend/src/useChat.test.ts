/**
 * useChat hook — unit tests.
 *
 * Covers:
 *  - initial state
 *  - send(): message appending, SSE event handling (token, tool_call,
 *    tool_error, note_created, done, error), network exception fallback
 *  - selectSession(): restore saved session, noop on unknown id
 *  - newSession(): clear thread and session id
 *  - localStorage persistence (load on mount, write after done, corrupt data, cap)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChat } from './hooks/useChat'
import { createGroundingMessage, replaceSessions, type Session } from './components/Chat/sessionStore'
import * as sessionStore from './components/Chat/sessionStore'

vi.mock('./api/chat', () => ({
  streamChat: vi.fn(),
}))

// Lazily import the mocked streamChat for typed access
import { streamChat } from './api/chat'
const mockStreamChat = vi.mocked(streamChat)

/** Async generator that yields each event then finishes. */
async function* makeStream(...events: Array<{ event: string; data: Record<string, unknown> }>) {
  for (const evt of events) {
    yield evt as never
  }
}

const DONE = (sessionId = 'sess-test') =>
  ({ event: 'done', data: { session_id: sessionId } }) as const

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

describe('useChat — initial state', () => {
  beforeEach(() => localStorage.clear())

  it('starts with an empty thread', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.thread).toEqual([])
  })

  it('starts with isStreaming=false', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.isStreaming).toBe(false)
  })

  it('starts with no current session', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.currentSessionId).toBeNull()
  })

  it('starts with empty sessions when localStorage is empty', () => {
    localStorage.clear()
    const { result } = renderHook(() => useChat())
    expect(result.current.sessions).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// send() — message construction
// ---------------------------------------------------------------------------

describe('useChat — send() message construction', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('appends user message to thread immediately', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE()))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.thread[0]).toMatchObject({ role: 'user', content: 'hello' })
  })

  it('appends assistant placeholder immediately after user message', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE()))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.thread[1]).toMatchObject({ role: 'assistant', content: '' })
  })

  it('sets isStreaming=true while events are in-flight', async () => {
    // Stream never finishes — verify isStreaming goes true
    let resolver: (() => void) | null = null
    async function* hangingStream() {
      yield { event: 'token', data: { delta: 'x' } } as never
      await new Promise<void>(res => { resolver = res })
    }
    mockStreamChat.mockReturnValue(hangingStream())
    const { result } = renderHook(() => useChat())

    let sendPromise: Promise<void>
    act(() => { sendPromise = result.current.send('test') })
    // Allow the first yield to process
    await act(async () => { await Promise.resolve() })
    expect(result.current.isStreaming).toBe(true)

    // Resolve to let the hook finish
    resolver!()
    await act(async () => { await sendPromise! })
  })

  it('serializes persisted grounding entries as explicit user-added context', async () => {
    const seeded: Session = {
      id: 'sess-grounding',
      title: 'Alice context',
      createdAt: '2026-04-24T00:00:00Z',
      messages: [
        createGroundingMessage({
          id: 'ctx_1',
          scope: 'document',
          sourcePath: 'people/alice.md',
          sourceTitle: 'Alice Smith',
          text: 'Alice owns the rollout.',
          addedAt: '2026-04-24T00:00:00Z',
        }),
      ],
    }
    replaceSessions([seeded])
    mockStreamChat.mockReturnValue(makeStream(DONE('sess-grounding')))

    const { result } = renderHook(() => useChat())
    act(() => result.current.selectSession('sess-grounding'))
    await act(async () => { await result.current.send('What is Alice focused on?') })

    expect(mockStreamChat).toHaveBeenCalledWith(
      {
        messages: [
          {
            role: 'user',
            content: [
              '[User-added grounding]',
              'Source: Alice Smith (people/alice.md)',
              'Scope: document',
              '',
              'Alice owns the rollout.',
            ].join('\n'),
          },
          { role: 'user', content: 'What is Alice focused on?' },
        ],
        session_id: 'sess-grounding',
        tool_hint: undefined,
        fetch_urls: undefined,
      },
      expect.any(AbortSignal),
    )
  })
})

// ---------------------------------------------------------------------------
// send() — SSE event handling
// ---------------------------------------------------------------------------

describe('useChat — send() SSE events', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('accumulates token deltas into assistant content', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'token', data: { delta: 'Hello' } },
      { event: 'token', data: { delta: ' world' } },
      DONE(),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hi') })
    expect(result.current.thread[1].content).toBe('Hello world')
  })

  it('adds tool_call entry to assistant message', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'tool_call', data: { name: 'search_vault', result_count: 3 } },
      DONE(),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('search notes') })
    const toolCalls = result.current.thread[1].toolCalls
    expect(toolCalls).toHaveLength(1)
    expect(toolCalls![0]).toMatchObject({ name: 'search_vault', resultCount: 3 })
  })

  it('multiple tool_call events accumulate on the same message', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'tool_call', data: { name: 'search_vault', result_count: 2 } },
      { event: 'tool_call', data: { name: 'read_note', result_count: 1 } },
      DONE(),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('multi-tool') })
    expect(result.current.thread[1].toolCalls).toHaveLength(2)
  })

  it('tool_error event sets error on matching tool call', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'tool_call', data: { name: 'update_note', result_count: 0 } },
      { event: 'tool_error', data: { name: 'update_note', error: 'Permission denied' } },
      DONE(),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('write something') })
    const tc = result.current.thread[1].toolCalls![0]
    expect(tc.name).toBe('update_note')
    expect(tc.error).toBe('Permission denied')
  })

  it('tool_error does not corrupt non-matching tool calls', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'tool_call', data: { name: 'search_vault', result_count: 1 } },
      { event: 'tool_call', data: { name: 'update_note', result_count: 0 } },
      { event: 'tool_error', data: { name: 'update_note', error: 'err' } },
      DONE(),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('multi') })
    const calls = result.current.thread[1].toolCalls!
    expect(calls[0].error).toBeUndefined()
    expect(calls[1].error).toBe('err')
  })

  it('note_created event sets noteCreated on the assistant message', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'note_created', data: { file_path: 'people/bob.md', type: 'person_note' } },
      DONE(),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('create note for Bob') })
    expect(result.current.thread[1].noteCreated).toEqual({
      filePath: 'people/bob.md',
      type: 'person_note',
    })
  })

  it('done event clears isStreaming and removes isStreaming flag from message', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE()))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.isStreaming).toBe(false)
    expect(result.current.thread[1].isStreaming).toBe(false)
  })

  it('done event sets currentSessionId from server-returned session_id', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE('server-assigned-id')))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.currentSessionId).toBe('server-assigned-id')
  })

  it('error SSE event sets error message on assistant content and stops streaming', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'error', data: { message: 'LLM unavailable' } },
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.thread[1].content).toBe('LLM unavailable')
    expect(result.current.isStreaming).toBe(false)
  })

  it('network exception sets connection error fallback and stops streaming', async () => {
    mockStreamChat.mockImplementation(async function* () {
      throw new Error('Network failure')
    })
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.thread[1].content).toBe('Connection error — please try again.')
    expect(result.current.isStreaming).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// send() — session persistence
// ---------------------------------------------------------------------------

describe('useChat — send() session persistence', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('persists session to localStorage after done', async () => {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'token', data: { delta: 'Hi there' } },
      DONE('sess-persist'),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    const stored = JSON.parse(localStorage.getItem('monocle-sessions') ?? '[]') as unknown[]
    expect(stored).toHaveLength(1)
    expect((stored[0] as Record<string, unknown>).id).toBe('sess-persist')
  })

  it('adds session to the sessions state after done', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE('s1')))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    expect(result.current.sessions).toHaveLength(1)
    expect(result.current.sessions[0].id).toBe('s1')
  })

  it('does not reload sessions after persisting its own send result', async () => {
    const loadSessionsSpy = vi.spyOn(sessionStore, 'loadSessions')
    mockStreamChat.mockReturnValue(makeStream(DONE('self-write')))

    const { result } = renderHook(() => useChat())
    loadSessionsSpy.mockClear()

    await act(async () => { await result.current.send('hello') })

    expect(result.current.sessions).toHaveLength(1)
    expect(loadSessionsSpy).not.toHaveBeenCalled()
    loadSessionsSpy.mockRestore()
  })

  it('does not persist to localStorage when stream throws before done', async () => {
    mockStreamChat.mockImplementation(async function* () { throw new Error('fail') })
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('hello') })
    const stored = JSON.parse(localStorage.getItem('monocle-sessions') ?? '[]') as unknown[]
    expect(stored).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// selectSession()
// ---------------------------------------------------------------------------

describe('useChat — selectSession()', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  async function createSession(sessionId: string) {
    mockStreamChat.mockReturnValue(makeStream(
      { event: 'token', data: { delta: 'Response' } },
      DONE(sessionId),
    ))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('question') })
    return result
  }

  it('restores thread messages from the chosen session', async () => {
    const result = await createSession('sess-A')
    act(() => result.current.newSession())
    act(() => result.current.selectSession('sess-A'))
    expect(result.current.thread).toHaveLength(2)
    expect(result.current.currentSessionId).toBe('sess-A')
  })

  it('marks no message as isStreaming after restore', async () => {
    const result = await createSession('sess-B')
    act(() => result.current.newSession())
    act(() => result.current.selectSession('sess-B'))
    result.current.thread.forEach(m => expect(m.isStreaming).toBeFalsy())
  })

  it('does nothing when session id is not found', () => {
    const { result } = renderHook(() => useChat())
    act(() => result.current.selectSession('nonexistent'))
    expect(result.current.thread).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// newSession()
// ---------------------------------------------------------------------------

describe('useChat — newSession()', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('clears thread, currentSessionId, and isStreaming', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE('s1')))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('something') })
    act(() => result.current.newSession())
    expect(result.current.thread).toHaveLength(0)
    expect(result.current.currentSessionId).toBeNull()
    expect(result.current.isStreaming).toBe(false)
  })

  it('does not wipe the sessions list (history preserved)', async () => {
    mockStreamChat.mockReturnValue(makeStream(DONE('keepme')))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('keep') })
    act(() => result.current.newSession())
    expect(result.current.sessions).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// localStorage
// ---------------------------------------------------------------------------

describe('useChat — localStorage', () => {
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('loads persisted sessions from localStorage on mount', () => {
    const sessions = [
      { id: 'old-1', title: 'Old session', createdAt: new Date().toISOString(), messages: [] },
    ]
    localStorage.setItem('monocle-sessions', JSON.stringify(sessions))
    const { result } = renderHook(() => useChat())
    expect(result.current.sessions).toHaveLength(1)
    expect(result.current.sessions[0].id).toBe('old-1')
  })

  it('handles corrupt localStorage gracefully — starts with empty sessions', () => {
    localStorage.setItem('monocle-sessions', 'not-valid-json{{{{')
    const { result } = renderHook(() => useChat())
    expect(result.current.sessions).toEqual([])
  })

  it('filters out valid JSON entries that do not match the session schema', () => {
    localStorage.setItem('monocle-sessions', JSON.stringify([
      { id: 'broken', createdAt: '2026-04-25T00:00:00Z', messages: 'nope' },
      { id: 'also-broken', title: 'Broken', createdAt: '2026-04-25T00:00:00Z', messages: [{ role: 'system', content: 'bad role' }] },
    ]))
    const { result } = renderHook(() => useChat())
    expect(result.current.sessions).toEqual([])
  })

  it('filters out grounding messages whose kind does not match the grounding payload', () => {
    localStorage.setItem('monocle-sessions', JSON.stringify([
      {
        id: 'grounding-mismatch',
        title: 'Mismatch',
        createdAt: '2026-04-25T00:00:00Z',
        messages: [
          {
            role: 'user',
            content: 'Context payload',
            grounding: {
              id: 'ctx-1',
              scope: 'document',
              sourcePath: 'people/alice.md',
              sourceTitle: 'Alice Smith',
              text: 'Alice owns the rollout.',
              addedAt: '2026-04-25T00:00:00Z',
            },
          },
          {
            role: 'user',
            content: 'Also bad',
            kind: 'message',
            grounding: {
              id: 'ctx-2',
              scope: 'document',
              sourcePath: 'people/bob.md',
              sourceTitle: 'Bob Jones',
              text: 'Bob owns the follow-up.',
              addedAt: '2026-04-25T00:00:00Z',
            },
          },
        ],
      },
    ]))
    const { result } = renderHook(() => useChat())
    expect(result.current.sessions).toEqual([])
  })

  it('caps sessions at 10 — oldest session is evicted when limit exceeded', async () => {
    const existing = Array.from({ length: 10 }, (_, i) => ({
      id: `old-${i}`, title: `Session ${i}`,
      createdAt: new Date().toISOString(), messages: [],
    }))
    localStorage.setItem('monocle-sessions', JSON.stringify(existing))

    mockStreamChat.mockReturnValue(makeStream(DONE('new-session')))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('eleventh') })
    expect(result.current.sessions).toHaveLength(10)
    expect(result.current.sessions[0].id).toBe('new-session')
    // 'old-9' (inserted last = oldest in a newest-first list) was evicted
    expect(result.current.sessions.find(s => s.id === 'old-9')).toBeUndefined()
    // 'old-0' (inserted first = newest of the pre-existing) still present
    expect(result.current.sessions.find(s => s.id === 'old-0')).toBeDefined()
  })

  it('newer session appears at the top of the list', async () => {
    mockStreamChat.mockReturnValueOnce(makeStream(DONE('first')))
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('msg1') })

    act(() => result.current.newSession())
    mockStreamChat.mockReturnValueOnce(makeStream(DONE('second')))
    await act(async () => { await result.current.send('msg2') })

    expect(result.current.sessions[0].id).toBe('second')
    expect(result.current.sessions[1].id).toBe('first')
  })
})
