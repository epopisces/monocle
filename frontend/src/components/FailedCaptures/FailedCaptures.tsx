import { useCallback, useEffect, useReducer } from 'react'
import {
  listIngestFailures,
  retryIngestFailure,
  deleteIngestFailure,
  type FailedIngestRecord,
} from '../../api/ingest'
import './FailedCaptures.css'

// ── Types ─────────────────────────────────────────────────────────────────────

type Status = 'loading' | 'loaded' | 'error'

interface State {
  status: Status
  items: FailedIngestRecord[]
  error: string | null
  retryingIds: Set<string>
  dismissingIds: Set<string>
}

type Action =
  | { type: 'LOADED'; payload: FailedIngestRecord[] }
  | { type: 'LOAD_ERROR'; payload: string }
  | { type: 'RETRYING'; id: string }
  | { type: 'RETRIED'; id: string }
  | { type: 'RETRY_ERROR'; id: string; message: string }
  | { type: 'DISMISSING'; id: string }
  | { type: 'DISMISSED'; id: string }
  | { type: 'DISMISS_ERROR'; id: string; message: string }
  | { type: 'RESET' }

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'LOADED':
      return { ...state, status: 'loaded', items: action.payload, error: null }
    case 'LOAD_ERROR':
      return { ...state, status: 'error', error: action.payload }
    case 'RETRYING': {
      const next = new Set(state.retryingIds)
      next.add(action.id)
      return { ...state, retryingIds: next }
    }
    case 'RETRIED': {
      const next = new Set(state.retryingIds)
      next.delete(action.id)
      return { ...state, retryingIds: next, items: state.items.filter(i => i.id !== action.id) }
    }
    case 'RETRY_ERROR': {
      const next = new Set(state.retryingIds)
      next.delete(action.id)
      return { ...state, retryingIds: next, error: action.message }
    }
    case 'DISMISSING': {
      const next = new Set(state.dismissingIds)
      next.add(action.id)
      return { ...state, dismissingIds: next }
    }
    case 'DISMISSED': {
      const next = new Set(state.dismissingIds)
      next.delete(action.id)
      return { ...state, dismissingIds: next, items: state.items.filter(i => i.id !== action.id) }
    }
    case 'DISMISS_ERROR': {
      const next = new Set(state.dismissingIds)
      next.delete(action.id)
      return { ...state, dismissingIds: next, error: action.message }
    }
    case 'RESET':
      return INITIAL
    default:
      return state
  }
}

const INITIAL: State = {
  status: 'loading',
  items: [],
  error: null,
  retryingIds: new Set(),
  dismissingIds: new Set(),
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  onUpdate?: () => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function FailedCaptures({ open, onClose, onUpdate }: Props) {
  const [state, dispatch] = useReducer(reducer, INITIAL)

  // Load failures when panel opens
  useEffect(() => {
    if (!open) {
      dispatch({ type: 'RESET' })
      return
    }
    listIngestFailures()
      .then(items => dispatch({ type: 'LOADED', payload: items }))
      .catch(e => dispatch({ type: 'LOAD_ERROR', payload: String(e) }))
  }, [open])

  // Escape key to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleRetry = useCallback(async (id: string) => {
    dispatch({ type: 'RETRYING', id })
    try {
      await retryIngestFailure(id)
      dispatch({ type: 'RETRIED', id })
      onUpdate?.()
    } catch (e) {
      dispatch({ type: 'RETRY_ERROR', id, message: String(e) })
    }
  }, [onUpdate])

  const handleDismiss = useCallback(async (id: string) => {
    dispatch({ type: 'DISMISSING', id })
    try {
      await deleteIngestFailure(id)
      dispatch({ type: 'DISMISSED', id })
      onUpdate?.()
    } catch (e) {
      dispatch({ type: 'DISMISS_ERROR', id, message: String(e) })
    }
  }, [onUpdate])

  if (!open) return null

  const { status, items, error, retryingIds, dismissingIds } = state
  const isEmpty = status === 'loaded' && items.length === 0

  return (
    <>
      <div className="failed-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        className="failed-panel"
        data-testid="failed-captures"
        role="complementary"
        aria-label="Failed captures"
      >
        <div className="failed-panel__header">
          <h2 className="failed-panel__title">
            ⚠ Failed Captures
            {items.length > 0 && (
              <span className="failed-panel__count" data-testid="failed-captures-count">
                {items.length}
              </span>
            )}
          </h2>
          <button
            className="failed-panel__close"
            onClick={onClose}
            aria-label="Close failed captures"
          >
            ✕
          </button>
        </div>

        <div className="failed-panel__body">
          {status === 'loading' && (
            <div className="failed-panel__loading" data-testid="failed-loading">
              <div className="failed-panel__spinner" />
              <p>Loading…</p>
            </div>
          )}

          {status === 'error' && (
            <p className="failed-panel__error" role="alert">{error}</p>
          )}

          {isEmpty && (
            <div className="failed-panel__empty" data-testid="failed-empty">
              <span aria-hidden="true">✓</span>
              <p>No failed captures</p>
            </div>
          )}

          {status === 'loaded' && !isEmpty && (
            <ul className="failed-panel__list" role="list">
              {items.map(item => (
                <li key={item.id} className="failed-card" data-testid="failed-item">
                  <div className="failed-card__meta">
                    <span className="failed-card__source">{item.source}</span>
                    <span className="failed-card__date">
                      {new Date(item.failed_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="failed-card__preview" data-testid="failed-item-preview">
                    {item.content_preview}
                    {item.content_truncated && (
                      <span className="failed-card__truncated"> …</span>
                    )}
                  </p>
                  <p className="failed-card__error" data-testid="failed-item-error">
                    {item.error_message}
                  </p>
                  <div className="failed-card__actions">
                    <button
                      className="failed-card__btn failed-card__btn--retry"
                      onClick={() => handleRetry(item.id)}
                      disabled={retryingIds.has(item.id) || dismissingIds.has(item.id)}
                      data-testid="retry-btn"
                      aria-label={`Retry ${item.id}`}
                    >
                      {retryingIds.has(item.id) ? '…' : '↺ Retry'}
                    </button>
                    <button
                      className="failed-card__btn failed-card__btn--dismiss"
                      onClick={() => handleDismiss(item.id)}
                      disabled={dismissingIds.has(item.id) || retryingIds.has(item.id)}
                      data-testid="dismiss-btn"
                      aria-label={`Dismiss ${item.id}`}
                    >
                      {dismissingIds.has(item.id) ? '…' : '✕ Dismiss'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  )
}
