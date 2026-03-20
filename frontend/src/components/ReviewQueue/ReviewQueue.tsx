import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  listReview,
  approveNote,
  approveAll,
  type ReviewListResponse,
} from '../../api/review'
import type { NoteRef } from '../../api/review'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import './ReviewQueue.css'

// ── Types ─────────────────────────────────────────────────────────────────────

type Status = 'loading' | 'loaded' | 'error'

interface State {
  status: Status
  items: NoteRef[]
  total: number
  error: string | null
  approvingIds: Set<string>
  approvingAll: boolean
}

type Action =
  | { type: 'LOADED'; payload: ReviewListResponse }
  | { type: 'LOAD_ERROR'; payload: string }
  | { type: 'APPROVING'; id: string }
  | { type: 'APPROVED'; id: string }
  | { type: 'APPROVE_ERROR'; id: string; message: string }
  | { type: 'APPROVING_ALL' }
  | { type: 'APPROVED_ALL' }
  | { type: 'APPROVE_ALL_ERROR'; message: string }
  | { type: 'RESET' }

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'LOADED':
      return {
        ...state,
        status: 'loaded',
        // Sort by confidence ascending (lowest confidence = needs most review)
        items: [...action.payload.items].sort((a, b) => a.confidence - b.confidence),
        total: action.payload.total,
        error: null,
      }
    case 'LOAD_ERROR':
      return { ...state, status: 'error', error: action.payload }
    case 'APPROVING': {
      const next = new Set(state.approvingIds)
      next.add(action.id)
      return { ...state, approvingIds: next }
    }
    case 'APPROVED': {
      const next = new Set(state.approvingIds)
      next.delete(action.id)
      return {
        ...state,
        approvingIds: next,
        items: state.items.filter(i => i.file_path !== action.id),
        total: Math.max(0, state.total - 1),
      }
    }
    case 'APPROVE_ERROR': {
      const next = new Set(state.approvingIds)
      next.delete(action.id)
      return { ...state, approvingIds: next, error: action.message }
    }
    case 'APPROVING_ALL':
      return { ...state, approvingAll: true, error: null }
    case 'APPROVED_ALL':
      return { ...state, approvingAll: false, items: [], total: 0 }
    case 'APPROVE_ALL_ERROR':
      return { ...state, approvingAll: false, error: action.message }
    case 'RESET':
      return INITIAL
    default:
      return state
  }
}

const INITIAL: State = {
  status: 'loading',
  items: [],
  total: 0,
  error: null,
  approvingIds: new Set(),
  approvingAll: false,
}

// ── Confidence colour helper ──────────────────────────────────────────────────

function confidenceColor(c: number): string {
  if (c >= 0.85) return 'var(--success)'
  if (c >= 0.60) return 'var(--warning)'
  return 'var(--error)'
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  onApprove?: () => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ReviewQueue({ open, onClose, onApprove }: Props) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const panelRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // Load review items when panel opens
  useEffect(() => {
    if (!open) {
      dispatch({ type: 'RESET' })
      return
    }
    listReview({ limit: 50 })
      .then(r => dispatch({ type: 'LOADED', payload: r }))
      .catch(e => dispatch({ type: 'LOAD_ERROR', payload: mapErrorToUserMessage(e) }))
  }, [open])

  // Escape key to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleApprove = useCallback(async (filePath: string) => {
    dispatch({ type: 'APPROVING', id: filePath })
    try {
      await approveNote(filePath)
      dispatch({ type: 'APPROVED', id: filePath })
      onApprove?.()
    } catch (e) {
      dispatch({ type: 'APPROVE_ERROR', id: filePath, message: mapErrorToUserMessage(e) })
    }
  }, [onApprove])

  const handleApproveAll = useCallback(async () => {
    dispatch({ type: 'APPROVING_ALL' })
    try {
      await approveAll()
      dispatch({ type: 'APPROVED_ALL' })
      onApprove?.()
    } catch (e) {
      dispatch({ type: 'APPROVE_ALL_ERROR', message: mapErrorToUserMessage(e) })
    }
  }, [onApprove])

  const handleFix = useCallback((filePath: string) => {
    onClose()
    navigate(`/docs?path=${encodeURIComponent(filePath)}`)
  }, [navigate, onClose])

  if (!open) return null

  const { status, items, error, approvingIds, approvingAll } = state
  const isEmpty = status === 'loaded' && items.length === 0

  return (
    <>
      <div className="review-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        className="review-panel"
        ref={panelRef}
        data-testid="review-queue"
        role="complementary"
        aria-label="Review queue"
      >
        <div className="review-panel__header">
          <h2 className="review-panel__title">
            Review Queue
            {state.total > 0 && (
              <span className="review-panel__count" data-testid="review-queue-count">
                {state.total}
              </span>
            )}
          </h2>
          <div className="review-panel__header-actions">
            {!isEmpty && status === 'loaded' && (
              <button
                className="review-panel__approve-all-btn"
                onClick={handleApproveAll}
                disabled={approvingAll}
                data-testid="approve-all-btn"
              >
                {approvingAll ? 'Approving…' : 'Approve All'}
              </button>
            )}
            <button
              className="review-panel__close"
              onClick={onClose}
              aria-label="Close review queue"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="review-panel__body">
          {status === 'loading' && (
            <div className="review-panel__loading" data-testid="review-loading">
              <div className="review-panel__spinner" />
              <p>Loading…</p>
            </div>
          )}

          {status === 'error' && (
            <p className="review-panel__error" role="alert">{error}</p>
          )}

          {isEmpty && (
            <div className="review-panel__empty" data-testid="review-empty">
              <span className="review-panel__empty-icon" aria-hidden="true">✓</span>
              <p>All reviewed</p>
            </div>
          )}

          {status === 'loaded' && !isEmpty && (
            <ul className="review-panel__list" role="list">
              {items.map(item => (
                <li key={item.file_path} className="review-card" data-testid="review-item">
                  <div className="review-card__meta">
                    <span
                      className="review-card__confidence"
                      style={{ color: confidenceColor(item.confidence) }}
                      data-testid="review-item-confidence"
                    >
                      {Math.round(item.confidence * 100)}%
                    </span>
                    <span className="review-card__type">{item.type}</span>
                  </div>
                  <p className="review-card__title" data-testid="review-item-title">
                    {item.title || item.file_path}
                  </p>
                  <div className="review-card__actions">
                    <button
                      className="review-card__btn review-card__btn--approve"
                      onClick={() => handleApprove(item.file_path)}
                      disabled={approvingIds.has(item.file_path) || approvingAll}
                      data-testid="approve-btn"
                      aria-label={`Approve ${item.title || item.file_path}`}
                    >
                      {approvingIds.has(item.file_path) ? '…' : '✓ Approve'}
                    </button>
                    <button
                      className="review-card__btn review-card__btn--fix"
                      onClick={() => handleFix(item.file_path)}
                      disabled={approvingAll}
                      data-testid="fix-btn"
                      aria-label={`Fix ${item.title || item.file_path}`}
                    >
                      ✎ Fix
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
