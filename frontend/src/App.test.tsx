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

