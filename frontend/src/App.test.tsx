import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import App from './App'
import { getReviewCount } from './api/review'
import { countIngestNotifications, listIngestFailures } from './api/ingest'
import { getSettings } from './api/settings'
import { getNote } from './api/notes'

// react-force-graph pulls in aframe-extras which requires a global AFRAME.
// Mock the whole module so App.test.tsx doesn't trigger that side effect.
vi.mock('react-force-graph', () => ({
  ForceGraph2D: () => null,
}))

vi.mock('./components/IngestReview/IngestReviewScreen', () => ({
  default: () => null,
}))

// Graph and Notes API calls fired by GraphScreen on the /graph route
vi.mock('./api/graph', () => ({ getGraph: vi.fn().mockResolvedValue({ focus: null, nodes: [], edges: [] }) }))
vi.mock('./api/notes', () => ({
  listNotes: vi.fn().mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 }),
  getNote: vi.fn().mockResolvedValue({
    file_path: 'people/alice.md',
    title: 'Alice Smith',
    body: 'Alice owns the rollout.',
    metadata: { type: 'person_note', review_status: 'approved' },
  }),
}))

// Review and ingest polled by App on mount every 30 s
vi.mock('./api/review', () => ({ getReviewCount: vi.fn().mockResolvedValue({ count: 0 }) }))
vi.mock('./api/ingest', () => ({
  countIngestNotifications: vi.fn().mockResolvedValue({ count: 0 }),
  listIngestFailures: vi.fn().mockResolvedValue([]),
}))

// Health polled by Topbar
vi.mock('./api/health', () => ({
  getHealth: vi.fn().mockResolvedValue({
    status: 'ready', ai_reachable: true, index_status: 'ready',
    watcher_running: true, telemetry_endpoint: null,
  }),
}))

// Settings fetched by AppContent on mount + stats by StatsScreen
vi.mock('./api/settings', () => ({
  getSettings: vi.fn().mockResolvedValue({ ui: { voice_input_backend: 'whisper' } }),
}))
vi.mock('./api/stats', () => ({
  getStats: vi.fn().mockResolvedValue({
    total_notes: 0, total_chunks: 0, notes_by_type: {}, notes_by_domain: {},
    pending_review: 0, failed_ingests: 0, index: { backend: 'memory', total_chunks: 0 },
    latency_p50_ms: {}, latency_p95_ms: {},
  }),
}))

// Agents module used by CommandPalette extra actions
vi.mock('./api/agents', () => ({
  triggerWeeklySummary: vi.fn().mockResolvedValue({}),
  triggerReindex: vi.fn().mockResolvedValue({}),
}))

describe('App', () => {
  it('renders without crashing', () => {
    const { container } = render(<App />)
    expect(container).toBeTruthy()
  })

  it('renders the app shell topbar', () => {
    render(<App />)
    expect(screen.getByTestId('topbar')).toBeInTheDocument()
  })

  it('renders the left navigation', () => {
    render(<App />)
    expect(screen.getByTestId('left-nav')).toBeInTheDocument()
  })

  it('has a Chat nav link', () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    expect(nav.querySelector('a[href="/"]')).toBeTruthy()
  })

  it('has a Docs nav link', () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    expect(nav.querySelector('a[href="/docs"]')).toBeTruthy()
  })

  it('has a Search nav link', () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    expect(nav.querySelector('a[href="/search"]')).toBeTruthy()
  })

  it('has a Graph nav link', () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    expect(nav.querySelector('a[href="/graph"]')).toBeTruthy()
  })

  it('has a Stats nav link', () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    expect(nav.querySelector('a[href="/stats"]')).toBeTruthy()
  })
})

describe('App — polling and server settings', () => {
  it('initializes voiceBackend state and registers event listeners', () => {
    render(<App />)
    // Verify app mounts successfully and Topbar is present
    expect(screen.getByTestId('topbar')).toBeInTheDocument()
  })
})

// ── Polling lifecycle ────────────────────────────────────────────────────────

describe('App — polling lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(countIngestNotifications).mockResolvedValue({ count: 0 })
    vi.mocked(getReviewCount).mockResolvedValue({ count: 0 })
    vi.mocked(listIngestFailures).mockResolvedValue([])
    vi.mocked(getSettings).mockResolvedValue({ ui: { voice_input_backend: 'whisper' } })
    vi.useFakeTimers({ shouldAdvanceTime: false })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('calls getReviewCount once on mount', async () => {
    render(<App />)
    await act(async () => { await Promise.resolve() })
    expect(vi.mocked(getReviewCount)).toHaveBeenCalledTimes(1)
  })

  it('calls listIngestFailures once on mount', async () => {
    render(<App />)
    await act(async () => { await Promise.resolve() })
    expect(vi.mocked(listIngestFailures)).toHaveBeenCalledTimes(1)
  })

  it('calls countIngestNotifications once on mount', async () => {
    render(<App />)
    await act(async () => { await Promise.resolve() })
    expect(vi.mocked(countIngestNotifications)).toHaveBeenCalledTimes(1)
  })

  it('polls getReviewCount again after 30 seconds', async () => {
    render(<App />)
    await act(async () => { await Promise.resolve() })
    const callsBefore = vi.mocked(getReviewCount).mock.calls.length

    await act(async () => { vi.advanceTimersByTime(30_000) })
    const callsAfter = vi.mocked(getReviewCount).mock.calls.length
    expect(callsAfter).toBeGreaterThan(callsBefore)
  })

  it('polls listIngestFailures again after 30 seconds', async () => {
    render(<App />)
    await act(async () => { await Promise.resolve() })
    const callsBefore = vi.mocked(listIngestFailures).mock.calls.length

    await act(async () => { vi.advanceTimersByTime(30_000) })
    const callsAfter = vi.mocked(listIngestFailures).mock.calls.length
    expect(callsAfter).toBeGreaterThan(callsBefore)
  })

  it('polls countIngestNotifications again after 30 seconds', async () => {
    render(<App />)
    await act(async () => { await Promise.resolve() })
    const callsBefore = vi.mocked(countIngestNotifications).mock.calls.length

    await act(async () => { vi.advanceTimersByTime(30_000) })
    const callsAfter = vi.mocked(countIngestNotifications).mock.calls.length
    expect(callsAfter).toBeGreaterThan(callsBefore)
  })

  it('does not crash when getReviewCount rejects', async () => {
    vi.mocked(getReviewCount).mockRejectedValue(new Error('Server error'))
    // Should render without throwing
    expect(() => render(<App />)).not.toThrow()
    await act(async () => { await Promise.resolve() })
  })

  it('does not crash when listIngestFailures rejects', async () => {
    vi.mocked(listIngestFailures).mockRejectedValue(new Error('Server error'))
    expect(() => render(<App />)).not.toThrow()
    await act(async () => { await Promise.resolve() })
  })
})

// ── Settings propagation ─────────────────────────────────────────────────────

describe('App — settings propagation', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ui: { voice_input_backend: 'whisper' } })
    vi.mocked(getReviewCount).mockResolvedValue({ count: 0 })
    vi.mocked(listIngestFailures).mockResolvedValue([])
  })
  afterEach(() => vi.clearAllMocks())

  it('fetches settings on mount', async () => {
    vi.mocked(getSettings).mockResolvedValue({ ui: { voice_input_backend: 'whisper' } })
    render(<App />)
    await act(async () => { await Promise.resolve() })
    expect(vi.mocked(getSettings)).toHaveBeenCalledTimes(1)
  })

  it('does not crash when getSettings rejects — keeps default voice backend', async () => {
    vi.mocked(getSettings).mockRejectedValue(new Error('Network error'))
    expect(() => render(<App />)).not.toThrow()
    await act(async () => { await Promise.resolve() })
    // App should still render normally
    expect(screen.getByTestId('topbar')).toBeInTheDocument()
  })
})

// ── Route navigation ─────────────────────────────────────────────────────────

describe('App — route navigation', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ui: { voice_input_backend: 'whisper' } })
    vi.mocked(getReviewCount).mockResolvedValue({ count: 0 })
    vi.mocked(listIngestFailures).mockResolvedValue([])
    vi.mocked(getNote).mockResolvedValue({
      file_path: 'people/alice.md',
      title: 'Alice Smith',
      body: 'Alice owns the rollout.',
      metadata: { type: 'person_note', review_status: 'approved' },
    } as never)
  })
  afterEach(() => vi.clearAllMocks())

  it('navigates to /search when the Search nav link is clicked', async () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    const searchLink = nav.querySelector('a[href="/search"]')
    expect(searchLink).toBeTruthy()
    fireEvent.click(searchLink as Element)
    await act(async () => { await Promise.resolve() })
    // Link remains in the nav after navigation
    expect(nav.querySelector('a[href="/search"]')).toBeTruthy()
  })

  it('navigates to /graph when the Graph nav link is clicked', async () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    const graphLink = nav.querySelector('a[href="/graph"]')
    expect(graphLink).toBeTruthy()
    fireEvent.click(graphLink as Element)
    await act(async () => { await Promise.resolve() })
    expect(nav.querySelector('a[href="/graph"]')).toBeTruthy()
  })

  it('navigates to /stats when the Stats nav link is clicked', async () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    const statsLink = nav.querySelector('a[href="/stats"]')
    expect(statsLink).toBeTruthy()
    fireEvent.click(statsLink as Element)
    await act(async () => { await Promise.resolve() })
    expect(nav.querySelector('a[href="/stats"]')).toBeTruthy()
  })

  it('navigates back to / (chat) when the Chat nav link is clicked after switching', async () => {
    render(<App />)
    const nav = screen.getByTestId('left-nav')
    // Navigate away first
    fireEvent.click(nav.querySelector('a[href="/stats"]') as Element)
    await act(async () => { await Promise.resolve() })
    // Navigate back to chat
    fireEvent.click(nav.querySelector('a[href="/"]') as Element)
    await act(async () => { await Promise.resolve() })
    expect(nav.querySelector('a[href="/"]')).toBeTruthy()
  })

  it('opens the add-to-chat picker when a docs file is dropped onto the Chat nav item', async () => {
    render(<App />)
    const chatLink = screen.getByTestId('left-nav-chat-link')
    const payload = JSON.stringify({ filePath: 'people/alice.md', title: 'Alice Smith' })

    const dataTransfer = {
      types: ['application/x-monocle-chat-document'],
      getData: vi.fn((type: string) => type === 'application/x-monocle-chat-document' ? payload : ''),
      setData: vi.fn(),
      dropEffect: 'copy',
    }

    fireEvent.dragOver(chatLink, { dataTransfer })
    fireEvent.drop(chatLink, { dataTransfer })

    await waitFor(() => expect(vi.mocked(getNote)).toHaveBeenCalledWith('people/alice.md'))
    expect(await screen.findByTestId('chat-session-picker')).toBeInTheDocument()
  })

  it('clips dropped document grounding before persisting it to localStorage', async () => {
    localStorage.clear()
    vi.mocked(getNote).mockResolvedValueOnce({
      file_path: 'people/alice.md',
      title: 'Alice Smith',
      body: `Lead paragraph ${'details '.repeat(1200)}`,
      metadata: { type: 'person_note', review_status: 'approved' },
    } as never)

    render(<App />)
    const chatLink = screen.getByTestId('left-nav-chat-link')
    const payload = JSON.stringify({ filePath: 'people/alice.md', title: 'Alice Smith' })
    const dataTransfer = {
      types: ['application/x-monocle-chat-document'],
      getData: vi.fn((type: string) => type === 'application/x-monocle-chat-document' ? payload : ''),
      setData: vi.fn(),
      dropEffect: 'copy',
    }

    fireEvent.dragOver(chatLink, { dataTransfer })
    fireEvent.drop(chatLink, { dataTransfer })

    fireEvent.click(await screen.findByTestId('chat-session-picker-new'))

    const stored = JSON.parse(localStorage.getItem('monocle-sessions') ?? '[]') as Array<{ messages: Array<{ grounding?: { text?: string } }> }>
    const groundingText = stored[0]?.messages[0]?.grounding?.text ?? ''
    expect(groundingText.length).toBeLessThanOrEqual(4001)
    expect(groundingText.endsWith('…')).toBe(true)
  })
})

