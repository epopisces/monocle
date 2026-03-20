/**
 * M20 — Command Palette
 *
 * Triggered by Ctrl+/ (or Cmd+/). Provides a searchable list of all
 * application actions with keyboard navigation (↑/↓ arrows + Enter).
 *
 * Actions defined here cover:
 *   - Screen navigation (Chat, Docs, Search, Graph, Stats)
 *   - Open modals (Settings, Voice Capture, Review Queue)
 *   - Agent actions (Run weekly summary, Trigger reindex)
 *   - Search (Jump to semantic search, keyword search)
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import './CommandPalette.css'

// ── Action definition ─────────────────────────────────────────────────────────

export interface PaletteAction {
  id: string
  /** Human-readable label shown in the palette */
  label: string
  /** Additional keywords for fuzzy matching (not shown) */
  keywords?: string[]
  /** Icon character or emoji */
  icon?: string
  /** Called when the action is selected */
  onExecute: () => void
}

// ── Fuzzy score — simple substring / initials matching ───────────────────────

function scoreMatch(query: string, action: PaletteAction): number {
  if (!query) return 1
  const q = query.toLowerCase()
  const label = action.label.toLowerCase()
  const keywords = (action.keywords ?? []).join(' ').toLowerCase()

  // Exact prefix on label gets highest score
  if (label.startsWith(q)) return 3
  // Substring in label
  if (label.includes(q)) return 2
  // Match in keywords
  if (keywords.includes(q)) return 1
  // Every char of query appears in order (initials style)
  let idx = 0
  for (const ch of q) {
    const found = label.indexOf(ch, idx)
    if (found === -1) return 0
    idx = found + 1
  }
  return 0.5
}

// ── Component ─────────────────────────────────────────────────────────────────

export interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  /** Extra actions injected at call-site (modal openers, agent triggers) */
  extraActions?: PaletteAction[]
}

export default function CommandPalette({ open, onClose, extraActions = [] }: CommandPaletteProps) {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)

  // ── Static navigation actions ─────────────────────────────────────────────
  const baseActions: PaletteAction[] = useMemo(() => [
    {
      id: 'nav-chat',
      label: 'Go to Chat',
      icon: '💬',
      keywords: ['chat', 'home', 'assistant'],
      onExecute: () => { navigate('/'); onClose() },
    },
    {
      id: 'nav-docs',
      label: 'Go to Docs',
      icon: '📄',
      keywords: ['docs', 'browser', 'notes', 'documents'],
      onExecute: () => { navigate('/docs'); onClose() },
    },
    {
      id: 'nav-search',
      label: 'Go to Search',
      icon: '🔍',
      keywords: ['search', 'find', 'semantic'],
      onExecute: () => { navigate('/search'); onClose() },
    },
    {
      id: 'nav-graph',
      label: 'Go to Graph',
      icon: '◉',
      keywords: ['graph', 'knowledge', 'network', 'links'],
      onExecute: () => { navigate('/graph'); onClose() },
    },
    {
      id: 'nav-stats',
      label: 'Go to Stats',
      icon: '📊',
      keywords: ['stats', 'statistics', 'overview', 'analytics'],
      onExecute: () => { navigate('/stats'); onClose() },
    },
  ], [navigate, onClose])

  const allActions = [...baseActions, ...extraActions]

  // ── Filter & sort ─────────────────────────────────────────────────────────
  const filtered = allActions
    .map(action => ({ action, score: scoreMatch(query, action) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .map(({ action }) => action)

  // ── Reset state when opened ───────────────────────────────────────────────
  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIdx(0)
      // Focus input on next tick so the element is visible
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  // ── Keep active item clamped ──────────────────────────────────────────────
  useEffect(() => {
    setActiveIdx(prev => (filtered.length > 0 ? Math.min(prev, filtered.length - 1) : 0))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  // ── Scroll active item into view ──────────────────────────────────────────
  useEffect(() => {
    const el = listRef.current?.children[activeIdx] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  const execute = useCallback(
    (idx: number) => {
      const action = filtered[idx]
      if (action) action.onExecute()
    },
    [filtered],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          // Guard against empty results — no navigation possible
          if (filtered.length > 0) {
            setActiveIdx(i => Math.min(i + 1, filtered.length - 1))
          }
          break
        case 'ArrowUp':
          e.preventDefault()
          // Guard against empty results — no navigation possible
          if (filtered.length > 0) {
            setActiveIdx(i => Math.max(i - 1, 0))
          }
          break
        case 'Enter':
          e.preventDefault()
          // Guard against empty results — no action to execute
          if (filtered.length > 0) {
            execute(activeIdx)
          }
          break
        case 'Escape':
          e.preventDefault()
          onClose()
          break
      }
    },
    [filtered.length, activeIdx, execute, onClose],
  )

  if (!open) return null

  return (
    /* Backdrop */
    <div
      className="cp-backdrop"
      data-testid="command-palette"
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div className="cp-panel">
        {/* Search input */}
        <div className="cp-search-row">
          <span className="cp-search-icon" aria-hidden="true">⌘</span>
          <input
            ref={inputRef}
            className="cp-input"
            type="text"
            placeholder="Search actions…"
            value={query}
            onChange={e => { setQuery(e.target.value); setActiveIdx(0) }}
            onKeyDown={handleKeyDown}
            aria-label="Command palette search"
            aria-autocomplete="list"
            aria-controls="cp-list"
            aria-activedescendant={filtered[activeIdx] ? `cp-item-${filtered[activeIdx].id}` : undefined}
            autoComplete="off"
            spellCheck="false"
          />
          <kbd className="cp-esc-hint">ESC</kbd>
        </div>

        {/* Results list */}
        <ul
          id="cp-list"
          ref={listRef}
          className="cp-list"
          role="listbox"
          aria-label="Actions"
        >
          {filtered.length === 0 ? (
            <li className="cp-empty">No actions found</li>
          ) : (
            filtered.map((action, idx) => (
              <li
                key={action.id}
                id={`cp-item-${action.id}`}
                className={`cp-item ${idx === activeIdx ? 'cp-item--active' : ''}`}
                role="option"
                aria-selected={idx === activeIdx}
                onMouseEnter={() => setActiveIdx(idx)}
                onClick={() => execute(idx)}
                data-testid={`cp-item-${action.id}`}
              >
                {action.icon && (
                  <span className="cp-item__icon" aria-hidden="true">{action.icon}</span>
                )}
                <span className="cp-item__label">{action.label}</span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  )
}
