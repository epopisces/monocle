import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GraphScreen from './components/Graph/GraphScreen'

// ── Mock useNavigate ───────────────────────────────────────────────

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

// ── Mock react-force-graph ──────────────────────────────────────────
// ForceGraph2D requires WebGL/canvas — replace with a simple DOM proxy
vi.mock('react-force-graph', () => ({
  ForceGraph2D: ({
    graphData,
    onNodeClick,
    onNodeDragEnd,
  }: {
    graphData: { nodes: { id: string; label: string; type: string; degree: number | null; weight: number }[]; links: unknown[] }
    onNodeClick?: (node: unknown) => void
    onNodeDragEnd?: (node: unknown) => void
  }) => (
    <div data-testid="force-graph">
      <span data-testid="fg-node-count">{graphData.nodes.length}</span>
      {graphData.nodes.map(n => (
        <button
          key={n.id}
          data-testid={`fg-node-${n.id}`}
          onClick={() => onNodeClick?.(n)}
          onDragEnd={() => onNodeDragEnd?.({ ...n, x: 100, y: 200 })}
        >
          {n.label}
        </button>
      ))}
    </div>
  ),
}))

// ── Mock API modules ───────────────────────────────────────────────

const mockGetGraph = vi.fn()
const mockListNotes = vi.fn()

vi.mock('./api/graph', () => ({
  getGraph: (...args: unknown[]) => mockGetGraph(...args),
}))

vi.mock('./api/notes', () => ({
  listNotes: (...args: unknown[]) => mockListNotes(...args),
}))

// ── Reset between tests ────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  // Default: empty graph
  mockGetGraph.mockResolvedValue({ focus: null, nodes: [], edges: [] })
  mockListNotes.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 })
})

// ── Data fixtures ──────────────────────────────────────────────────

const GRAPH_PERSON = {
  id: 'people/alice.md',
  label: 'Alice',
  type: 'person_note',
  degree: 0,
  weight: 3,
}

const GRAPH_NOTE = {
  id: 'work/decision.md',
  label: 'Team Decision',
  type: 'decision',
  degree: 1,
  weight: 2,
}

const GRAPH_DATA = {
  focus: 'people/alice.md',
  nodes: [GRAPH_PERSON, GRAPH_NOTE],
  edges: [
    {
      source: 'people/alice.md',
      target: 'work/decision.md',
      edge_type: 'structured',
      relation: 'mentioned-in',
      weight: 2,
      metadata: {},
    },
  ],
}

const NOTE_LIST_PAGE = {
  items: [
    { file_path: 'people/alice.md', title: 'Alice', type: 'person_note' as const, domain: 'work', confidence: 0.9, review_status: 'approved' },
    { file_path: 'work/decision.md', title: 'Team Decision', type: 'decision' as const, domain: 'work', confidence: 0.8, review_status: 'approved' },
  ],
  total: 2,
  offset: 0,
  limit: 50,
}

function renderGraph() {
  return render(
    <MemoryRouter>
      <GraphScreen />
    </MemoryRouter>,
  )
}

// ── Layout tests ───────────────────────────────────────────────────

describe('GraphScreen — layout', () => {
  it('renders the graph screen container', async () => {
    renderGraph()
    expect(screen.getByTestId('graph-screen')).toBeInTheDocument()
  })

  it('renders the focus input', async () => {
    renderGraph()
    expect(screen.getByTestId('focus-input')).toBeInTheDocument()
  })

  it('renders depth toggle buttons [1][2][3]', () => {
    renderGraph()
    const toggle = screen.getByTestId('depth-toggle')
    expect(toggle).toBeInTheDocument()
    expect(screen.getByTestId('depth-btn-1')).toBeInTheDocument()
    expect(screen.getByTestId('depth-btn-2')).toBeInTheDocument()
    expect(screen.getByTestId('depth-btn-3')).toBeInTheDocument()
  })

  it('renders type filter chips', () => {
    renderGraph()
    expect(screen.getByTestId('type-chip-person')).toBeInTheDocument()
    expect(screen.getByTestId('type-chip-note')).toBeInTheDocument()
    expect(screen.getByTestId('type-chip-tag')).toBeInTheDocument()
  })

  it('renders reset view button', () => {
    renderGraph()
    expect(screen.getByTestId('reset-btn')).toBeInTheDocument()
  })

  it('all type chips are active by default', () => {
    renderGraph()
    expect(screen.getByTestId('type-chip-person')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('type-chip-note')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('type-chip-tag')).toHaveAttribute('aria-pressed', 'true')
  })

  it('depth 3 is the default active depth', () => {
    renderGraph()
    expect(screen.getByTestId('depth-btn-3')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('depth-btn-1')).toHaveAttribute('aria-pressed', 'false')
  })
})

// ── Graph fetch ────────────────────────────────────────────────────

describe('GraphScreen — graph fetch', () => {
  it('calls getGraph on mount', async () => {
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    expect(mockGetGraph).toHaveBeenCalledWith(expect.objectContaining({ max_degree: 3 }))
  })

  it('shows loading state during fetch', async () => {
    let resolve: (v: unknown) => void = () => {}
    mockGetGraph.mockReturnValue(new Promise(r => { resolve = r }))
    renderGraph()
    expect(screen.getByTestId('graph-loading')).toBeInTheDocument()
    await act(async () => { resolve({ focus: null, nodes: [], edges: [] }) })
  })

  it('shows stats bar after successful fetch with nodes', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(screen.getByTestId('graph-stats')).toBeInTheDocument())
    expect(screen.getByTestId('graph-stats').textContent).toContain('2 nodes')
    expect(screen.getByTestId('graph-stats').textContent).toContain('1 edges')
  })

  it('shows error state when fetch fails', async () => {
    mockGetGraph.mockRejectedValue(new Error('Network error'))
    renderGraph()
    await waitFor(() => expect(screen.getByTestId('graph-error')).toBeInTheDocument())
    expect(screen.getByTestId('graph-error').textContent).toContain('Network error')
  })

  it('shows empty state when graph has no nodes', async () => {
    mockGetGraph.mockResolvedValue({ focus: null, nodes: [], edges: [] })
    renderGraph()
    await waitFor(() => expect(screen.getByTestId('graph-empty')).toBeInTheDocument())
  })

  it('renders ForceGraph2D when nodes are present', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument())
  })

  it('passes correct node count to ForceGraph2D', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(screen.getByTestId('fg-node-count').textContent).toBe('2'))
  })
})

// ── Controls ───────────────────────────────────────────────────────

describe('GraphScreen — depth toggle', () => {
  it('clicking depth [1] refetches with max_degree=1', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByTestId('depth-btn-1'))
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    const secondCall = mockGetGraph.mock.calls[1][0] as Record<string, unknown>
    expect(secondCall.max_degree).toBe(1)
  })

  it('active depth button has aria-pressed=true', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByTestId('depth-btn-2'))
    expect(screen.getByTestId('depth-btn-2')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('depth-btn-3')).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('GraphScreen — type filter chips', () => {
  it('deselecting Person chip triggers refetch', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByTestId('type-chip-person'))
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    const secondCall = mockGetGraph.mock.calls[1][0] as Record<string, unknown>
    // types should exclude person_note
    expect(secondCall.types).toBeDefined()
    expect(String(secondCall.types)).not.toContain('person_note')
  })

  it('deselecting Note chip triggers refetch', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByTestId('type-chip-note'))
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    const secondCall = mockGetGraph.mock.calls[1][0] as Record<string, unknown>
    expect(secondCall.types).toBeDefined()
    expect(String(secondCall.types)).toContain('person_note')
    expect(String(secondCall.types)).not.toContain('decision')
  })

  it('toggled chip gets aria-pressed=false', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByTestId('type-chip-person'))
    expect(screen.getByTestId('type-chip-person')).toHaveAttribute('aria-pressed', 'false')
  })

  it('re-enabling chip includes its types again', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    // Deselect
    fireEvent.click(screen.getByTestId('type-chip-person'))
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    // Re-enable — all chips active → no types param
    fireEvent.click(screen.getByTestId('type-chip-person'))
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(3))
    const thirdCall = mockGetGraph.mock.calls[2][0] as Record<string, unknown>
    expect(thirdCall.types).toBeUndefined()
  })
})

describe('GraphScreen — focus input', () => {
  it('shows autocomplete suggestions when typing', async () => {
    mockListNotes.mockResolvedValue(NOTE_LIST_PAGE)
    renderGraph()
    await waitFor(() => expect(mockListNotes).toHaveBeenCalled())
    const input = screen.getByTestId('focus-input')
    fireEvent.change(input, { target: { value: 'Alice' } })
    await waitFor(() => expect(screen.getByTestId('focus-suggestions')).toBeInTheDocument())
    expect(screen.getAllByTestId('suggestion-item').length).toBeGreaterThan(0)
  })

  it('pressing Enter refetches with focus path', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    const input = screen.getByTestId('focus-input')
    fireEvent.change(input, { target: { value: 'people/alice.md' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    const secondCall = mockGetGraph.mock.calls[1][0] as Record<string, unknown>
    expect(secondCall.focus).toBe('people/alice.md')
  })

  it('clicking a suggestion sets focus and refetches', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    mockListNotes.mockResolvedValue(NOTE_LIST_PAGE)
    renderGraph()
    await waitFor(() => expect(mockListNotes).toHaveBeenCalled())
    const input = screen.getByTestId('focus-input')
    fireEvent.change(input, { target: { value: 'Alice' } })
    await waitFor(() => screen.getByTestId('focus-suggestions'))
    const items = screen.getAllByTestId('suggestion-item')
    fireEvent.mouseDown(items[0])
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    const secondCall = mockGetGraph.mock.calls[1][0] as Record<string, unknown>
    expect(secondCall.focus).toBe('people/alice.md')
  })
})

describe('GraphScreen — reset view', () => {
  it('clicking Reset View clears focus and refetches without focus param', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(1))
    // Set a focus first via Enter
    const input = screen.getByTestId('focus-input')
    fireEvent.change(input, { target: { value: 'people/alice.md' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(2))
    // Reset
    fireEvent.click(screen.getByTestId('reset-btn'))
    await waitFor(() => expect(mockGetGraph).toHaveBeenCalledTimes(3))
    const thirdCall = mockGetGraph.mock.calls[2][0] as Record<string, unknown>
    expect(thirdCall.focus).toBeUndefined()
    expect(screen.getByTestId('focus-input')).toHaveValue('')
  })
})

// ── Side panel ─────────────────────────────────────────────────────

describe('GraphScreen — side panel', () => {
  it('side panel is not shown initially', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    expect(screen.queryByTestId('side-panel')).toBeNull()
  })

  it('clicking a node shows the side panel', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    // Use the mock node button rendered by our ForceGraph2D mock
    const nodeBtn = screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`)
    // Need to use fake timers for double-click prevention
    vi.useFakeTimers()
    fireEvent.click(nodeBtn)
    await act(async () => { vi.advanceTimersByTime(300) })
    vi.useRealTimers()
    expect(screen.getByTestId('side-panel')).toBeInTheDocument()
  })

  it('side panel shows selected node label', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    vi.useFakeTimers()
    fireEvent.click(screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`))
    await act(async () => { vi.advanceTimersByTime(300) })
    vi.useRealTimers()
    expect(screen.getByTestId('side-panel')).toHaveTextContent(GRAPH_PERSON.label)
  })

  it('side panel close button dismisses the panel', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    vi.useFakeTimers()
    fireEvent.click(screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`))
    await act(async () => { vi.advanceTimersByTime(300) })
    vi.useRealTimers()
    expect(screen.getByTestId('side-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('side-panel-close'))
    expect(screen.queryByTestId('side-panel')).toBeNull()
  })

  it('side panel shows related notes for the selected node', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    vi.useFakeTimers()
    fireEvent.click(screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`))
    await act(async () => { vi.advanceTimersByTime(300) })
    vi.useRealTimers()
    const panel = screen.getByTestId('side-panel')
    // Should contain the connected note's label
    expect(panel).toHaveTextContent(GRAPH_NOTE.label)
  })

  it('open-note button is rendered in side panel', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    vi.useFakeTimers()
    fireEvent.click(screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`))
    await act(async () => { vi.advanceTimersByTime(300) })
    vi.useRealTimers()
    expect(screen.getByTestId('open-note-btn')).toBeInTheDocument()
  })
})

// ── localStorage position persistence ─────────────────────────────

describe('GraphScreen — node positions', () => {
  it('restores persisted node positions from localStorage', async () => {
    const positions = { 'people/alice.md': { x: 100, y: 200 } }
    localStorage.setItem('monocle.graph.positions', JSON.stringify(positions))
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    // Just verify render doesn't crash with pre-set positions
    await waitFor(() => screen.getByTestId('force-graph'))
    expect(screen.getByTestId('fg-node-count').textContent).toBe('2')
  })

  it('ignores invalid (non-object) localStorage positions silently', () => {
    localStorage.setItem('monocle.graph.positions', '"not-an-object"')
    mockGetGraph.mockResolvedValue({ focus: null, nodes: [], edges: [] })
    expect(() => renderGraph()).not.toThrow()
  })

  it('ignores positions with non-numeric coordinates', async () => {
    localStorage.setItem(
      'monocle.graph.positions',
      JSON.stringify({ 'people/alice.md': { x: 'bad', y: 0 } }),
    )
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))
    expect(screen.getByTestId('fg-node-count').textContent).toBe('2')
  })

  it('saves node position to localStorage when a node is dragged', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))

    const nodeBtn = screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`)
    fireEvent.dragEnd(nodeBtn)

    const stored = JSON.parse(localStorage.getItem('monocle.graph.positions') ?? '{}') as Record<string, unknown>
    expect(stored[GRAPH_PERSON.id]).toEqual({ x: 100, y: 200 })
  })
})

// ── Double-click navigation ────────────────────────────────────────

describe('GraphScreen — double-click navigation', () => {
  it('double-clicking a node navigates to its note in the document browser', async () => {
    mockGetGraph.mockResolvedValue(GRAPH_DATA)
    renderGraph()
    await waitFor(() => screen.getByTestId('force-graph'))

    const nodeBtn = screen.getByTestId(`fg-node-${GRAPH_PERSON.id}`)
    vi.useFakeTimers()
    // First click sets the single-click detection timer
    fireEvent.click(nodeBtn)
    // Second click before 250 ms clears the timer and triggers navigation
    fireEvent.click(nodeBtn)
    vi.useRealTimers()

    expect(mockNavigate).toHaveBeenCalledWith(
      `/docs?path=${encodeURIComponent(GRAPH_PERSON.id)}`,
    )
  })
})
