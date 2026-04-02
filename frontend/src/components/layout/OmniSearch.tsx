import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { omniSearch, type OmniResult } from '../../api/search'
import './OmniSearch.css'

const DEBOUNCE_MS = 300
const MIN_CHARS = 3
const LOCATION_LABELS: Record<OmniResult['match_location'], string> = {
  filename: 'In filename',
  frontmatter: 'In title / tags',
  body: 'In body',
}

type GroupedResults = {
  filename: OmniResult[]
  frontmatter: OmniResult[]
  body: OmniResult[]
}

export default function OmniSearch() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<OmniResult[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)

  // Global Ctrl+E → focus input
  useEffect(() => {
    function handleGlobalKey(e: KeyboardEvent) {
      if (e.ctrlKey && e.key === 'e') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    window.addEventListener('keydown', handleGlobalKey)
    return () => window.removeEventListener('keydown', handleGlobalKey)
  }, [])

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Debounced search
  useEffect(() => {
    if (query.length < MIN_CHARS) {
      setResults([])
      setIsOpen(false)
      return
    }

    const timer = setTimeout(async () => {
      setIsLoading(true)
      try {
        const data = await omniSearch({ q: query, limit: 20 })
        setResults(data)
        setIsOpen(true)
        setSelectedIndex(-1)
      } catch {
        setResults([])
      } finally {
        setIsLoading(false)
      }
    }, DEBOUNCE_MS)

    return () => clearTimeout(timer)
  }, [query])

  const grouped: GroupedResults = {
    filename: results.filter(r => r.match_location === 'filename'),
    frontmatter: results.filter(r => r.match_location === 'frontmatter'),
    body: results.filter(r => r.match_location === 'body'),
  }

  // Flat ordered list for keyboard navigation (+1 entry for semantic at end)
  const flatItems: Array<OmniResult | 'semantic'> = [
    ...grouped.filename,
    ...grouped.frontmatter,
    ...grouped.body,
    ...(query.length >= MIN_CHARS ? ['semantic' as const] : []),
  ]

  const navigateToResult = useCallback((item: OmniResult) => {
    setIsOpen(false)
    setQuery('')
    navigate(`/docs?path=${encodeURIComponent(item.file_path)}`)
  }, [navigate])

  const navigateToSemantic = useCallback(() => {
    setIsOpen(false)
    setQuery('')
    navigate(`/search?q=${encodeURIComponent(query)}&mode=semantic`)
  }, [navigate, query])

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || flatItems.length === 0) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(i => Math.min(i + 1, flatItems.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(i => Math.max(i - 1, 0))
        break
      case 'Enter': {
        e.preventDefault()
        const target = selectedIndex >= 0 ? flatItems[selectedIndex] : flatItems[0]
        if (target === 'semantic') {
          navigateToSemantic()
        } else if (target) {
          navigateToResult(target)
        }
        break
      }
      case 'Escape':
        setIsOpen(false)
        break
    }
  }

  let flatIdx = 0
  function renderGroup(items: OmniResult[], location: OmniResult['match_location']) {
    if (items.length === 0) return null
    return (
      <div key={location} className="omni-search__group">
        <div className="omni-search__group-label">{LOCATION_LABELS[location]}</div>
        {items.map(item => {
          const idx = flatIdx++
          const isSelected = selectedIndex === idx
          return (
            <button
              key={item.file_path}
              className={`omni-search__item${isSelected ? ' omni-search__item--selected' : ''}`}
              data-testid="omni-result"
              onClick={() => navigateToResult(item)}
              onMouseEnter={() => setSelectedIndex(idx)}
            >
              <span className="omni-search__item-title">{item.title || item.file_path.split('/').pop()?.replace('.md', '')}</span>
              <span className="omni-search__item-excerpt">{item.excerpt}</span>
            </button>
          )
        })}
      </div>
    )
  }

  // semanticIdx must equal results.length — the slot after all grouped result items.
  // Do NOT derive from flatIdx here: flatIdx is 0 until renderGroup() is called inside JSX.
  const semanticIdx = results.length

  return (
    <div className="omni-search" ref={containerRef} data-testid="omni-search">
      <div className="omni-search__input-wrap">
        <span className="omni-search__icon" aria-hidden="true">⌕</span>
        <input
          ref={inputRef}
          className="omni-search__input"
          data-testid="omni-search-input"
          type="search"
          placeholder="Search notes…  Ctrl+E"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (query.length >= MIN_CHARS && results.length > 0) setIsOpen(true) }}
          autoComplete="off"
          spellCheck={false}
          aria-label="Omnisearch"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
        />
        {isLoading && <span className="omni-search__spinner" aria-hidden="true">⟳</span>}
      </div>

      {isOpen && (
        <div className="omni-search__dropdown" data-testid="omni-search-dropdown" role="listbox">
          {results.length === 0 && !isLoading && (
            <div className="omni-search__empty">No results</div>
          )}
          {renderGroup(grouped.filename, 'filename')}
          {renderGroup(grouped.frontmatter, 'frontmatter')}
          {renderGroup(grouped.body, 'body')}

          {query.length >= MIN_CHARS && (
            <button
              className={`omni-search__item omni-search__item--semantic${selectedIndex === semanticIdx ? ' omni-search__item--selected' : ''}`}
              data-testid="omni-semantic-btn"
              onClick={navigateToSemantic}
              onMouseEnter={() => setSelectedIndex(semanticIdx)}
            >
              🤖 Search semantically for <strong>{query}</strong>
            </button>
          )}
        </div>
      )}
    </div>
  )
}
