import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  semanticSearch,
  keywordSearch,
  type SearchResult,
  type KeywordResult,
} from '../../api/search'
import { approveNote } from '../../api/review'
import './SearchScreen.css'

type SearchMode = 'semantic' | 'keyword'

export default function SearchScreen() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<SearchMode>('semantic')
  const [query, setQuery] = useState('')
  const [threshold, setThreshold] = useState(0.5)
  const [semanticResults, setSemanticResults] = useState<SearchResult[]>([])
  const [keywordResults, setKeywordResults] = useState<KeywordResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 4000)
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      if (mode === 'semantic') {
        const results = await semanticSearch({ q: query, limit: 20, threshold })
        setSemanticResults(results)
        setKeywordResults([])
      } else {
        const results = await keywordSearch({ q: query, limit: 20 })
        setKeywordResults(results)
        setSemanticResults([])
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function openNote(filePath: string) {
    navigate(`/docs?path=${encodeURIComponent(filePath)}`)
  }

  async function handleApprove(filePath: string) {
    try {
      await approveNote(filePath)
      showToast(`Approved: ${filePath}`)
    } catch (err) {
      showToast(`Approve failed: ${(err as Error).message}`)
    }
  }

  const totalResults = mode === 'semantic' ? semanticResults.length : keywordResults.length

  return (
    <div className="search-screen" data-testid="search-screen">
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="search-screen__header">
        <h2 className="search-screen__title">Search</h2>

        {/* Mode toggle */}
        <div className="search-screen__mode-toggle" role="group" aria-label="Search mode">
          <button
            className={`search-screen__mode-btn${mode === 'semantic' ? ' search-screen__mode-btn--active' : ''}`}
            onClick={() => setMode('semantic')}
            data-testid="mode-btn-semantic"
            aria-pressed={mode === 'semantic'}
          >
            Semantic
          </button>
          <button
            className={`search-screen__mode-btn${mode === 'keyword' ? ' search-screen__mode-btn--active' : ''}`}
            onClick={() => setMode('keyword')}
            data-testid="mode-btn-keyword"
            aria-pressed={mode === 'keyword'}
          >
            Keyword
          </button>
        </div>
      </div>

      {/* ── Search form ─────────────────────────────────────── */}
      <form className="search-screen__form" onSubmit={handleSearch}>
        <div className="search-screen__input-row">
          <input
            type="search"
            className="search-screen__input"
            placeholder={mode === 'semantic' ? 'Search by meaning…' : 'Search by keyword…'}
            value={query}
            onChange={e => setQuery(e.target.value)}
            data-testid="search-input"
            autoFocus
          />
          <button type="submit" className="search-screen__submit-btn" data-testid="search-btn">
            {loading ? 'Searching…' : 'Search'}
          </button>
        </div>

        {/* Semantic threshold slider */}
        {mode === 'semantic' && (
          <div className="search-screen__threshold" data-testid="threshold-control">
            <label className="search-screen__threshold-label">
              Min similarity: <strong>{Math.round(threshold * 100)}%</strong>
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={threshold}
              onChange={e => setThreshold(Number(e.target.value))}
              className="search-screen__slider"
              data-testid="threshold-slider"
              aria-label="Minimum similarity threshold"
            />
          </div>
        )}
      </form>

      {/* ── Toast ──────────────────────────────────────────── */}
      {toast && (
        <div className="search-screen__toast" role="alert" data-testid="search-toast">
          {toast}
        </div>
      )}

      {/* ── Error ──────────────────────────────────────────── */}
      {error && (
        <p className="search-screen__error" data-testid="search-error">{error}</p>
      )}

      {/* ── Results ──────────────────────────────────────────── */}
      {!loading && totalResults > 0 && (
        <p className="search-screen__count">
          {totalResults} result{totalResults === 1 ? '' : 's'}
        </p>
      )}

      <div className="search-screen__results" data-testid="search-results">
        {/* Semantic results */}
        {mode === 'semantic' &&
          semanticResults.map(r => (
            <div
              key={r.chunk_id}
              className="search-result-card"
              data-testid="search-result"
            >
              <div className="search-result-card__header">
                <span className="search-result-card__path">{r.file_path}</span>
                <span
                  className="search-result-card__score"
                  data-testid="result-score"
                  title="Similarity score"
                >
                  {Math.round(r.score * 100)}%
                </span>
              </div>
              <p className="search-result-card__excerpt">{r.text}</p>
              <div className="search-result-card__actions">
                <button
                  className="search-result-card__btn search-result-card__btn--open"
                  onClick={() => openNote(r.file_path)}
                  data-testid="result-open-btn"
                >
                  Open
                </button>
                <button
                  className="search-result-card__btn search-result-card__btn--approve"
                  onClick={() => handleApprove(r.file_path)}
                  data-testid="result-approve-btn"
                >
                  Approve
                </button>
              </div>
            </div>
          ))}

        {/* Keyword results */}
        {mode === 'keyword' &&
          keywordResults.map((r, i) => (
            <div key={i} className="search-result-card" data-testid="search-result">
              <div className="search-result-card__header">
                <span className="search-result-card__title">{r.title}</span>
                <span className="search-result-card__path">{r.file_path}</span>
              </div>
              <p className="search-result-card__excerpt">{r.excerpt}</p>
              <div className="search-result-card__actions">
                <button
                  className="search-result-card__btn search-result-card__btn--open"
                  onClick={() => openNote(r.file_path)}
                  data-testid="result-open-btn"
                >
                  Open
                </button>
                <button
                  className="search-result-card__btn search-result-card__btn--approve"
                  onClick={() => handleApprove(r.file_path)}
                  data-testid="result-approve-btn"
                >
                  Approve
                </button>
              </div>
            </div>
          ))}

        {/* Empty state */}
        {!loading && !error && totalResults === 0 && query.trim() && (
          <p className="search-screen__empty" data-testid="search-empty">
            No results found for <em>{query}</em>
          </p>
        )}
      </div>
    </div>
  )
}
