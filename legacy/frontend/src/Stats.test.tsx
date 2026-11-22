/**
 * M20 – Stats, Keyboard Shortcuts & Command Palette
 *
 * Tests for:
 *  - StatsScreen (stat cards, charts, loading/error states)
 *  - useHotkeys (keyboard shortcut firing)
 *  - CommandPalette (open/close, search/filter, keyboard navigation, execute action)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StatsScreen from './components/Stats/StatsScreen'
import CommandPalette, { type PaletteAction } from './components/CommandPalette/CommandPalette'
import { useHotkeys } from './hooks/useHotkeys'
import { renderHook } from '@testing-library/react'

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('./api/stats', () => ({
  getStats: vi.fn(),
}))

// Recharts uses SVG + ResizeObserver; no-op the internal hooks
vi.mock('recharts', async () => {
  const actual = await vi.importActual<object>('recharts')
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 500, height: 300 }}>
        {children}
      </div>
    ),
  }
})

import { getStats } from './api/stats'

// ── Helpers ───────────────────────────────────────────────────────────────────

const MOCK_STATS = {
  total_notes: 42,
  total_chunks: 130,
  notes_by_type: { person_note: 10, decision: 8, idea: 5, other: 19 },
  notes_by_domain: { work: 25, personal: 17 },
  pending_review: 3,
  failed_ingests: 1,
  index: { backend: 'chroma', total_chunks: 130, total_files: 42, collection_name: 'monocle' },
  latency_p50_ms: { embed: 45.2, chat: 1200.0 },
  latency_p95_ms: { embed: 120.5, chat: 3100.0 },
}

function renderStats() {
  return render(
    <MemoryRouter>
      <StatsScreen />
    </MemoryRouter>,
  )
}

// ── StatsScreen ───────────────────────────────────────────────────────────────

describe('StatsScreen', () => {
  beforeEach(() => {
    vi.mocked(getStats).mockReset()
  })

  it('shows loading state initially', async () => {
    // Never resolves during this test
    vi.mocked(getStats).mockReturnValue(new Promise(() => {}))
    renderStats()
    expect(screen.getByTestId('stats-loading')).toBeInTheDocument()
  })

  it('renders stat cards with live data', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => {
      expect(screen.getByTestId('stats-screen')).toBeInTheDocument()
    })
    const cards = screen.getByTestId('stats-cards')
    expect(cards).toBeInTheDocument()
    // Check values appear
    expect(cards.textContent).toContain('42')   // total notes
    expect(cards.textContent).toContain('3')    // pending review
    expect(cards.textContent).toContain('1')    // failed ingests
  })

  it('renders total notes stat card', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText('Total Notes')).toBeInTheDocument()
  })

  it('renders pending review stat card', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText('Pending Review')).toBeInTheDocument()
  })

  it('renders failed ingests stat card', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText('Failed Ingests')).toBeInTheDocument()
  })

  it('renders notes-by-type chart section', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText('Notes by Type')).toBeInTheDocument()
  })

  it('renders notes-by-domain chart section', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText('Notes by Domain')).toBeInTheDocument()
  })

  it('renders source quality index section', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText(/Source Quality Index/)).toBeInTheDocument()
  })

  it('renders latency table when data is present', async () => {
    vi.mocked(getStats).mockResolvedValue(MOCK_STATS)
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.getByText('Latency (ms)')).toBeInTheDocument()
  })

  it('does not render latency table when no latency data', async () => {
    vi.mocked(getStats).mockResolvedValue({ ...MOCK_STATS, latency_p50_ms: {}, latency_p95_ms: {} })
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.queryByText('Latency (ms)')).not.toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    vi.mocked(getStats).mockRejectedValue(new Error('network error'))
    renderStats()
    await waitFor(() => {
      expect(screen.getByTestId('stats-error')).toBeInTheDocument()
    })
  })

  it('does not render charts when no type data', async () => {
    vi.mocked(getStats).mockResolvedValue({
      ...MOCK_STATS,
      notes_by_type: {},
      notes_by_domain: {},
    })
    renderStats()
    await waitFor(() => screen.getByTestId('stats-screen'))
    expect(screen.queryByText('Notes by Type')).not.toBeInTheDocument()
  })
})

// ── useHotkeys ────────────────────────────────────────────────────────────────

describe('useHotkeys', () => {
  function fireCtrl(key: string, options: Partial<KeyboardEventInit> = {}) {
    fireEvent.keyDown(window, { key, ctrlKey: true, ...options })
  }

  it('calls onCommandPalette on Ctrl+/', () => {
    const onCommandPalette = vi.fn()
    renderHook(() => useHotkeys({ onCommandPalette }))
    fireCtrl('/')
    expect(onCommandPalette).toHaveBeenCalledOnce()
  })

  it('calls onSearch on Ctrl+K (not in input)', () => {
    const onSearch = vi.fn()
    renderHook(() => useHotkeys({ onSearch }))
    fireCtrl('k')
    expect(onSearch).toHaveBeenCalledOnce()
  })

  it('calls onKeywordSearch on Ctrl+Shift+K', () => {
    const onKeywordSearch = vi.fn()
    renderHook(() => useHotkeys({ onKeywordSearch }))
    fireCtrl('k', { shiftKey: true })
    expect(onKeywordSearch).toHaveBeenCalledOnce()
  })

  it('calls onCloseModal on Escape', () => {
    const onCloseModal = vi.fn()
    renderHook(() => useHotkeys({ onCloseModal }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onCloseModal).toHaveBeenCalledOnce()
  })

  it('calls onToggleSidebar on Ctrl+\\', () => {
    const onToggleSidebar = vi.fn()
    renderHook(() => useHotkeys({ onToggleSidebar }))
    fireCtrl('\\')
    expect(onToggleSidebar).toHaveBeenCalledOnce()
  })

  it('calls onNewNote on Ctrl+N (not in input)', () => {
    const onNewNote = vi.fn()
    renderHook(() => useHotkeys({ onNewNote }))
    fireCtrl('n')
    expect(onNewNote).toHaveBeenCalledOnce()
  })

  it('does NOT call onSearch when focused on an input element', () => {
    const onSearch = vi.fn()
    renderHook(() => useHotkeys({ onSearch }))
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    fireEvent.keyDown(input, { key: 'k', ctrlKey: true })
    document.body.removeChild(input)
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('does NOT call onKeywordSearch when focused on an input element', () => {
    const onKeywordSearch = vi.fn()
    renderHook(() => useHotkeys({ onKeywordSearch }))
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    fireEvent.keyDown(input, { key: 'k', ctrlKey: true, shiftKey: true })
    document.body.removeChild(input)
    expect(onKeywordSearch).not.toHaveBeenCalled()
  })

  it('calls onSaveNote on Ctrl+S even in an input', () => {
    const onSaveNote = vi.fn()
    renderHook(() => useHotkeys({ onSaveNote }))
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    fireEvent.keyDown(input, { key: 's', ctrlKey: true })
    document.body.removeChild(input)
    expect(onSaveNote).toHaveBeenCalledOnce()
  })

  it('removes the event listener on unmount', () => {
    const onSearch = vi.fn()
    const { unmount } = renderHook(() => useHotkeys({ onSearch }))
    unmount()
    fireCtrl('k')
    expect(onSearch).not.toHaveBeenCalled()
  })
})

// ── CommandPalette ────────────────────────────────────────────────────────────

describe('CommandPalette', () => {
  const onClose = vi.fn()

  function renderPalette(props: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
    const actions: PaletteAction[] = [
      {
        id: 'weekly-summary',
        label: 'Run weekly summary',
        icon: '📅',
        keywords: ['weekly', 'summary'],
        onExecute: vi.fn(),
      },
      {
        id: 'open-settings',
        label: 'Open Settings',
        icon: '⚙️',
        keywords: ['settings', 'config'],
        onExecute: vi.fn(),
      },
    ]

    return render(
      <MemoryRouter>
        <CommandPalette
          open={true}
          onClose={onClose}
          extraActions={actions}
          {...props}
        />
      </MemoryRouter>,
    )
  }

  beforeEach(() => {
    onClose.mockReset()
  })

  it('renders nothing when closed', () => {
    renderPalette({ open: false })
    expect(screen.queryByTestId('command-palette')).not.toBeInTheDocument()
  })

  it('renders when open', () => {
    renderPalette()
    expect(screen.getByTestId('command-palette')).toBeInTheDocument()
  })

  it('shows default navigation actions', () => {
    renderPalette()
    expect(screen.getByText('Go to Chat')).toBeInTheDocument()
    expect(screen.getByText('Go to Search')).toBeInTheDocument()
    expect(screen.getByText('Go to Stats')).toBeInTheDocument()
  })

  it('shows extra actions', () => {
    renderPalette()
    expect(screen.getByText('Run weekly summary')).toBeInTheDocument()
    expect(screen.getByText('Open Settings')).toBeInTheDocument()
  })

  it('filters actions by query — "weekly" shows Run weekly summary', async () => {
    renderPalette()
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'weekly' } })
    expect(screen.getByText('Run weekly summary')).toBeInTheDocument()
    // Navigation actions should not appear for "weekly"
    expect(screen.queryByText('Go to Chat')).not.toBeInTheDocument()
  })

  it('shows "No actions found" for unmatched query', () => {
    renderPalette()
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'xyznonexistent' } })
    expect(screen.getByText('No actions found')).toBeInTheDocument()
  })

  it('closes on Escape key', () => {
    renderPalette()
    const input = screen.getByRole('textbox')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('closes when backdrop is clicked', () => {
    renderPalette()
    const backdrop = screen.getByTestId('command-palette')
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not close when panel content is clicked', () => {
    renderPalette()
    const input = screen.getByRole('textbox')
    fireEvent.click(input)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('navigates items with arrow keys', () => {
    renderPalette({
      extraActions: [],  // only base nav actions for predictable order
    })
    const input = screen.getByRole('textbox')
    // First item should be active by default
    const firstItem = screen.getByTestId('cp-item-nav-chat')
    expect(firstItem.getAttribute('aria-selected')).toBe('true')
    // Arrow down moves to second
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(firstItem.getAttribute('aria-selected')).toBe('false')
    const secondItem = screen.getByTestId('cp-item-nav-docs')
    expect(secondItem.getAttribute('aria-selected')).toBe('true')
    // Arrow up moves back
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(firstItem.getAttribute('aria-selected')).toBe('true')
  })

  it('executes the active action on Enter', () => {
    const executeHandler = vi.fn()
    const action: PaletteAction = {
      id: 'test-action',
      label: 'Test Action',
      onExecute: executeHandler,
    }
    render(
      <MemoryRouter>
        <CommandPalette open={true} onClose={onClose} extraActions={[action]} />
      </MemoryRouter>,
    )
    const input = screen.getByRole('textbox')
    // Search to isolate to just our action
    fireEvent.change(input, { target: { value: 'Test Action' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(executeHandler).toHaveBeenCalledOnce()
  })

  it('executes action on click', () => {
    const executeHandler = vi.fn()
    const action: PaletteAction = {
      id: 'click-action',
      label: 'Click Me',
      onExecute: executeHandler,
    }
    render(
      <MemoryRouter>
        <CommandPalette open={true} onClose={onClose} extraActions={[action]} />
      </MemoryRouter>,
    )
    // Search for it
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Click Me' } })
    fireEvent.click(screen.getByTestId('cp-item-click-action'))
    expect(executeHandler).toHaveBeenCalledOnce()
  })

  it('has accessible role=dialog on the backdrop', () => {
    renderPalette()
    const el = screen.getByRole('dialog')
    expect(el).toBeInTheDocument()
  })

  it('input has aria-autocomplete=list', () => {
    renderPalette()
    const input = screen.getByRole('textbox')
    expect(input.getAttribute('aria-autocomplete')).toBe('list')
  })
})
