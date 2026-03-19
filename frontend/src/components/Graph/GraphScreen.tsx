import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ForceGraph2D } from 'react-force-graph'
import { getGraph, type GraphData, type GraphNode, type GraphEdge } from '../../api/graph'
import { listNotes, type NoteRef } from '../../api/notes'
import './GraphScreen.css'

// ── Constants ──────────────────────────────────────────────────────

const POSITIONS_KEY = 'monocle.graph.positions'

const PERSON_COLOR_DARK = '#7c8af7'
const TOPIC_COLOR_DARK = '#3dbf84'
const EDGE_COLOR = '#5a6072'

const NOTE_TYPES_PERSON = ['person_note'] as const
const NOTE_TYPES_NOTE = [
  'decision',
  'idea',
  'observation',
  'reference',
  'meeting_note',
  'project',
  'action_item',
  'weekly_summary',
  'other',
] as const

type FilterKey = 'person' | 'note' | 'tag'
type FilterState = Record<FilterKey, boolean>

// ── Helpers ────────────────────────────────────────────────────────

function buildTypesParam(filters: FilterState): string | undefined {
  if (filters.person && filters.note && filters.tag) return undefined

  const types: string[] = []
  if (filters.person) types.push(...NOTE_TYPES_PERSON)
  if (filters.note) types.push(...NOTE_TYPES_NOTE)
  if (filters.tag) types.push('tag')

  // Safety net: all-off filters produce `__empty__` which matches no backend type.
  // Normal UI flow prevents reaching this via the guard in handleTypeToggle.
  return types.length > 0 ? types.join(',') : '__empty__'
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function getNodeColor(node: GraphNode): string {
  const base = node.type === 'person_note' ? PERSON_COLOR_DARK : TOPIC_COLOR_DARK
  const degree = node.degree ?? 0
  const opacity = Math.max(0.2, 1.0 - degree * 0.25)
  return hexToRgba(base, opacity)
}

function getNodeSize(node: GraphNode): number {
  const degree = node.degree ?? 0
  return Math.max(3, 15 * Math.pow(0.85, degree))
}

function loadPositions(): Record<string, { x: number; y: number }> {
  const MAX_COORD = 10000  // Reasonable bounds for graph coordinates
  try {
    const raw = JSON.parse(localStorage.getItem(POSITIONS_KEY) ?? '{}') as unknown
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return {}
    const result: Record<string, { x: number; y: number }> = {}
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      const x = (v as Record<string, unknown>).x
      const y = (v as Record<string, unknown>).y
      // Validate: must be numbers, must be finite, must be within reasonable bounds
      if (
        typeof v === 'object' && v !== null &&
        typeof x === 'number' && Number.isFinite(x) && Math.abs(x) <= MAX_COORD &&
        typeof y === 'number' && Number.isFinite(y) && Math.abs(y) <= MAX_COORD
      ) {
        result[k] = { x, y }
      }
    }
    return result
  } catch {
    return {}
  }
}

// ── Types used when react-force-graph mutates node objects ──────────

interface ForceNode extends GraphNode {
  x?: number
  y?: number
}

// ── Component ──────────────────────────────────────────────────────

export default function GraphScreen() {
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const lastClickedNodeIdRef = useRef<string | undefined>(undefined)

  const [dimensions, setDimensions] = useState({ width: 600, height: 500 })
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [focusInput, setFocusInput] = useState('')
  const [focus, setFocus] = useState<string | undefined>(undefined)
  const [maxDegree, setMaxDegree] = useState<number>(3)
  const [filters, setFilters] = useState<FilterState>({ person: true, note: true, tag: true })

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>(loadPositions)

  const [allNotes, setAllNotes] = useState<NoteRef[]>([])
  const [suggestions, setSuggestions] = useState<NoteRef[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)

  // ── Data fetching ────────────────────────────────────────────────

  const loadGraph = useCallback(async (params: {
    focus?: string
    maxDegree: number
    filters: FilterState
  }) => {
    // Clear any pending single-click timer to prevent selecting stale nodes after reload
    if (clickTimerRef.current !== undefined) {
      clearTimeout(clickTimerRef.current)
      clickTimerRef.current = undefined
      lastClickedNodeIdRef.current = undefined
    }
    setLoading(true)
    setError(null)
    setSelectedNode(null)
    try {
      const types = buildTypesParam(params.filters)
      const data = await getGraph({
        focus: params.focus,
        max_degree: params.maxDegree,
        ...(types !== undefined ? { types } : {}),
      })
      setGraphData(data)
    } catch (err) {
      setError((err as Error).message)
      setGraphData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadGraph({ focus: undefined, maxDegree: 3, filters: { person: true, note: true, tag: true } })
  }, [loadGraph])

  // Load all notes for autocomplete (best-effort)
  useEffect(() => {
    listNotes({ limit: 500 }).then(page => setAllNotes(page.items)).catch(() => {})
  }, [])

  // Track container size
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setDimensions({ width, height })
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // Cleanup click timer on unmount
  useEffect(() => {
    return () => {
      if (clickTimerRef.current !== undefined) clearTimeout(clickTimerRef.current)
    }
  }, [])

  // ── Focus input ──────────────────────────────────────────────────

  function handleFocusInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    setFocusInput(val)
    if (val.length >= 1) {
      const lower = val.toLowerCase()
      const matches = allNotes
        .filter(n => n.title.toLowerCase().includes(lower) || n.file_path.toLowerCase().includes(lower))
        .slice(0, 8)
      setSuggestions(matches)
      setShowSuggestions(matches.length > 0)
    } else {
      setShowSuggestions(false)
    }
  }

  function handleSelectSuggestion(note: NoteRef) {
    setFocusInput(note.title)
    setFocus(note.file_path)
    setShowSuggestions(false)
    loadGraph({ focus: note.file_path, maxDegree, filters })
  }

  function handleFocusInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      setShowSuggestions(false)
      const matched = allNotes.find(n => n.file_path === focusInput || n.title === focusInput)
      const focusPath = matched?.file_path ?? (focusInput.trim() || undefined)
      setFocus(focusPath)
      loadGraph({ focus: focusPath, maxDegree, filters })
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  // ── Depth / type controls ────────────────────────────────────────

  function handleDepthChange(d: number) {
    setMaxDegree(d)
    loadGraph({ focus, maxDegree: d, filters })
  }

  function handleTypeToggle(chip: FilterKey) {
    const next = { ...filters, [chip]: !filters[chip] }
    setFilters(next)
    // All chips off: render empty graph locally rather than sending the `__empty__` sentinel.
    if (!next.person && !next.note && !next.tag) {
      setGraphData({ focus: focus ?? null, nodes: [], edges: [] })
      return
    }
    loadGraph({ focus, maxDegree, filters: next })
  }

  function handleResetView() {
    setFocus(undefined)
    setFocusInput('')
    setSelectedNode(null)
    const resetFilters: FilterState = { person: true, note: true, tag: true }
    setFilters(resetFilters)
    loadGraph({ focus: undefined, maxDegree, filters: resetFilters })
  }

  // ── Node interactions ────────────────────────────────────────────

  function handleNodeClick(node: unknown) {
    const n = node as ForceNode
    // Detect double-click: timer must exist AND same node must be clicked twice
    if (clickTimerRef.current !== undefined && lastClickedNodeIdRef.current === n.id) {
      clearTimeout(clickTimerRef.current)
      clickTimerRef.current = undefined
      lastClickedNodeIdRef.current = undefined
      // Double-click detected → navigate
      navigate(`/docs?path=${encodeURIComponent(n.id)}`)
      return
    }
    // Clear any previous pending timer (different node was clicked)
    if (clickTimerRef.current !== undefined) {
      clearTimeout(clickTimerRef.current)
    }
    // Start new single-click timer for this node
    lastClickedNodeIdRef.current = n.id
    clickTimerRef.current = setTimeout(() => {
      clickTimerRef.current = undefined
      lastClickedNodeIdRef.current = undefined
      setSelectedNode(n)
    }, 250)
  }

  function handleNodeDragEnd(node: unknown) {
    const n = node as ForceNode
    const x = n.x
    const y = n.y
    if (typeof x === 'number' && typeof y === 'number') {
      setPositions(prev => {
        const next = Object.assign({}, prev, { [n.id]: { x, y } })
        localStorage.setItem(POSITIONS_KEY, JSON.stringify(next))
        return next
      })
    }
  }

  // ── Derived state ─────────────────────────────────────────────────

  const nodeCount = graphData?.nodes.length ?? 0
  const edgeCount = graphData?.edges.length ?? 0

  const relatedNotes: { id: string; relation: string; weight: number }[] = []
  if (selectedNode && graphData) {
    const seen = new Set<string>()
    for (const e of graphData.edges) {
      const isRelated = e.source === selectedNode.id || e.target === selectedNode.id
      if (!isRelated) continue
      const neighborId = e.source === selectedNode.id ? e.target : e.source
      if (!seen.has(neighborId)) {
        seen.add(neighborId)
        relatedNotes.push({ id: neighborId, relation: e.relation, weight: e.weight })
      }
    }
    relatedNotes.sort((a, b) => b.weight - a.weight)
    relatedNotes.splice(5) // keep top 5
  }

  // Build react-force-graph data structure
  const fgData = {
    nodes: (graphData?.nodes ?? []).map(n => ({
      ...n,
      ...(positions[n.id] ?? {}),
    })),
    links: graphData?.edges ?? [],
  }

  const showGraph = !loading && !error && nodeCount > 0

  return (
    <div className="graph-screen" data-testid="graph-screen">

      {/* ── Controls ─────────────────────────────────────────────── */}
      <div className="graph-screen__controls" data-testid="graph-controls">

        {/* Focus input with autocomplete */}
        <div className="graph-screen__focus-wrap">
          <input
            className="graph-screen__focus-input"
            type="text"
            placeholder="Focus on a note…"
            value={focusInput}
            onChange={handleFocusInputChange}
            onKeyDown={handleFocusInputKeyDown}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            data-testid="focus-input"
            autoComplete="off"
          />
          {showSuggestions && (
            <ul className="graph-screen__suggestions" data-testid="focus-suggestions">
              {suggestions.map(s => (
                <li
                  key={s.file_path}
                  className="graph-screen__suggestion-item"
                  onMouseDown={() => handleSelectSuggestion(s)}
                  data-testid="suggestion-item"
                >
                  <span className="graph-screen__suggestion-title">{s.title}</span>
                  <span className="graph-screen__suggestion-path">{s.file_path}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Depth toggle */}
        <div
          className="graph-screen__depth-toggle"
          role="group"
          aria-label="Graph depth"
          data-testid="depth-toggle"
        >
          {([1, 2, 3] as const).map(d => (
            <button
              key={d}
              className={`graph-screen__depth-btn${maxDegree === d ? ' graph-screen__depth-btn--active' : ''}`}
              onClick={() => handleDepthChange(d)}
              data-testid={`depth-btn-${d}`}
              aria-pressed={maxDegree === d}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Type filter chips */}
        <div
          className="graph-screen__type-chips"
          role="group"
          aria-label="Node type filter"
          data-testid="type-chips"
        >
          {(['person', 'note', 'tag'] as const).map(chip => (
            <button
              key={chip}
              className={`graph-screen__type-chip${filters[chip] ? ' graph-screen__type-chip--active' : ''}`}
              onClick={() => handleTypeToggle(chip)}
              data-testid={`type-chip-${chip}`}
              aria-pressed={filters[chip]}
            >
              {chip === 'person' ? 'Person' : chip === 'note' ? 'Note' : 'Tag'}
              {filters[chip] && <span className="graph-screen__chip-check"> ✓</span>}
            </button>
          ))}
        </div>

        {/* Reset View */}
        <button
          className="graph-screen__reset-btn"
          onClick={handleResetView}
          data-testid="reset-btn"
        >
          Reset View
        </button>
      </div>

      {/* ── Stats bar ─────────────────────────────────────────────── */}
      {graphData !== null && (
        <div className="graph-screen__stats" data-testid="graph-stats">
          {nodeCount} nodes · {edgeCount} edges
          {focus && (
            <span> · Focused on <strong>{focus}</strong></span>
          )}
        </div>
      )}

      {/* ── Canvas + side panel ───────────────────────────────────── */}
      <div className="graph-screen__body">

        <div className="graph-screen__canvas" ref={containerRef} data-testid="graph-canvas">
          {loading && (
            <div className="graph-screen__overlay" data-testid="graph-loading">
              <div className="graph-screen__spinner" />
              <span>Loading graph…</span>
            </div>
          )}
          {!loading && error && (
            <div className="graph-screen__overlay graph-screen__overlay--error" data-testid="graph-error">
              {error}
            </div>
          )}
          {!loading && !error && nodeCount === 0 && graphData !== null && (
            <div className="graph-screen__overlay graph-screen__overlay--empty" data-testid="graph-empty">
              No nodes found. Adjust filters or check your vault.
            </div>
          )}
          {showGraph && (
            <ForceGraph2D
              graphData={fgData}
              nodeId="id"
              nodeLabel={(node: unknown) => (node as GraphNode).label}
              nodeColor={(node: unknown) => getNodeColor(node as GraphNode)}
              nodeVal={(node: unknown) => getNodeSize(node as GraphNode)}
              linkColor={() => EDGE_COLOR}
              linkLabel={(link: unknown) => (link as GraphEdge).relation || ''}
              onNodeClick={handleNodeClick}
              onNodeDragEnd={handleNodeDragEnd}
              width={dimensions.width}
              height={dimensions.height}
              backgroundColor="transparent"
            />
          )}
        </div>

        {/* ── Side panel ──────────────────────────────────────────── */}
        {selectedNode && (
          <aside className="graph-screen__side-panel" data-testid="side-panel">
            <div className="graph-screen__side-panel-header">
              <h3 className="graph-screen__side-panel-title">{selectedNode.label}</h3>
              <button
                className="graph-screen__side-panel-close"
                onClick={() => setSelectedNode(null)}
                data-testid="side-panel-close"
                aria-label="Close side panel"
              >
                ×
              </button>
            </div>

            <div className="graph-screen__side-panel-meta">
              <span className="graph-screen__tag">{selectedNode.type}</span>
              {selectedNode.degree !== null && (
                <span className="graph-screen__degree-badge">Degree {selectedNode.degree}</span>
              )}
            </div>

            {relatedNotes.length > 0 && (
              <div className="graph-screen__related">
                <h4 className="graph-screen__related-title">Related notes</h4>
                <ul className="graph-screen__related-list">
                  {relatedNotes.map(r => {
                    const node = graphData?.nodes.find(n => n.id === r.id)
                    return (
                      <li key={r.id} className="graph-screen__related-item">
                        <button
                          className="graph-screen__related-link"
                          onClick={() => navigate(`/docs?path=${encodeURIComponent(r.id)}`)}
                        >
                          {node?.label ?? r.id}
                        </button>
                        {r.relation && (
                          <span className="graph-screen__related-relation">{r.relation}</span>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}

            {relatedNotes.length === 0 && (
              <p className="graph-screen__side-panel-empty">No related notes found.</p>
            )}

            <button
              className="graph-screen__open-note-btn"
              onClick={() => navigate(`/docs?path=${encodeURIComponent(selectedNode.id)}`)}
              data-testid="open-note-btn"
            >
              Open in Document Browser →
            </button>
          </aside>
        )}
      </div>
    </div>
  )
}
