import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

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

