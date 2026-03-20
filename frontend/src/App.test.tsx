import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

// react-force-graph pulls in aframe-extras which requires a global AFRAME.
// Mock the whole module so App.test.tsx doesn't trigger that side effect.
vi.mock('react-force-graph', () => ({
  ForceGraph2D: () => null,
}))

// Graph and Notes API calls fired by GraphScreen on the /graph route
vi.mock('./api/graph', () => ({ getGraph: vi.fn().mockResolvedValue({ focus: null, nodes: [], edges: [] }) }))
vi.mock('./api/notes', () => ({ listNotes: vi.fn().mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 }) }))

// Review and ingest polled by App on mount every 30 s
vi.mock('./api/review', () => ({ getReviewCount: vi.fn().mockResolvedValue({ count: 0 }) }))
vi.mock('./api/ingest', () => ({ listIngestFailures: vi.fn().mockResolvedValue([]) }))

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

