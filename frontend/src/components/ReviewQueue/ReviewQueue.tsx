import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import {
  listReview,
  approveNote,
  rejectNote,
  approveAll,
  type ReviewListResponse,
} from '../../api/review'
import type { NoteRef } from '../../api/review'
import { getNote } from '../../api/notes'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import { splitFrontmatter } from '../../utils/yamlUtils'
import './ReviewQueue.css'

// ── Types ─────────────────────────────────────────────────────────────────────

type Status = 'loading' | 'loaded' | 'error'

interface State {
  status: Status
  items: NoteRef[]
  total: number
  error: string | null
  approvingIds: Set<string>
  rejectingIds: Set<string>
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
  | { type: 'REJECTING'; id: string }
  | { type: 'REJECTED'; id: string }
  | { type: 'REJECT_ERROR'; id: string; message: string }
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
    case 'REJECTING': {
      const next = new Set(state.rejectingIds)
      next.add(action.id)
      return { ...state, rejectingIds: next }
    }
    case 'REJECTED': {
      const next = new Set(state.rejectingIds)
      next.delete(action.id)
      return {
        ...state,
        rejectingIds: next,
        items: state.items.filter(i => i.file_path !== action.id),
        total: Math.max(0, state.total - 1),
      }
    }
    case 'REJECT_ERROR': {
      const next = new Set(state.rejectingIds)
      next.delete(action.id)
      return { ...state, rejectingIds: next, error: action.message }
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
  total: 0,
  error: null,
  approvingIds: new Set(),
  rejectingIds: new Set(),
  approvingAll: false,
}

// ── Confidence colour helper ──────────────────────────────────────────────────

function confidenceColor(c: number): string {
  if (c >= 0.85) return 'var(--success)'
  if (c >= 0.60) return 'var(--warning)'
  return 'var(--error)'
}

// ── Custom link component — opens external links in new tab ──

function PreviewLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const navigate = useNavigate()
  if (href?.startsWith('/docs?path=')) {
    const path = decodeURIComponent(href.slice('/docs?path='.length))
    return (
      <button
        className="review-preview__link"
        onClick={() => navigate(`/docs?path=${encodeURIComponent(path)}`)}
      >
        {children}
      </button>
    )
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="review-preview__link">
      {children}
    </a>
  )
}

const PREVIEW_MARKDOWN_COMPONENTS: Components = { a: PreviewLink }

// ── Preview state ─────────────────────────────────────────────────────────────

interface PreviewState {
  item: NoteRef
  body: string | null
  loading: boolean
  y: number
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
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const bodyCacheRef = useRef<Map<string, string>>(new Map())
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const navigate = useNavigate()

  // Load review items when panel opens
  useEffect(() => {
    if (!open) {
      dispatch({ type: 'RESET' })
      setPreview(null)
      bodyCacheRef.current.clear()
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
    setPreview(null)
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
    setPreview(null)
    dispatch({ type: 'APPROVING_ALL' })
    try {
      await approveAll()
      dispatch({ type: 'APPROVED_ALL' })
      onApprove?.()
    } catch (e) {
      dispatch({ type: 'APPROVE_ALL_ERROR', message: mapErrorToUserMessage(e) })
    }
  }, [onApprove])

  const handleReject = useCallback(async (filePath: string) => {
    setPreview(null)
    dispatch({ type: 'REJECTING', id: filePath })
    try {
      await rejectNote(filePath)
      dispatch({ type: 'REJECTED', id: filePath })
    } catch (e) {
      dispatch({ type: 'REJECT_ERROR', id: filePath, message: mapErrorToUserMessage(e) })
    }
  }, [])

  const handleEdit = useCallback((filePath: string) => {
    setPreview(null)
    onClose()
    navigate(`/docs?path=${encodeURIComponent(filePath)}`)
  }, [navigate, onClose])

  const handleCardMouseEnter = useCallback((item: NoteRef, cardEl: HTMLElement) => {
    if (leaveTimerRef.current !== null) {
      clearTimeout(leaveTimerRef.current)
      leaveTimerRef.current = null
    }
    const rect = cardEl.getBoundingClientRect()
    const cached = bodyCacheRef.current.get(item.file_path)
    if (cached !== undefined) {
      setPreview({ item, body: cached, loading: false, y: rect.top })
    } else {
      setPreview({ item, body: null, loading: true, y: rect.top })
      getNote(item.file_path)
        .then(note => {
          const noteBody = note.body ?? ''
          bodyCacheRef.current.set(item.file_path, noteBody)
          setPreview(p => p?.item.file_path === item.file_path
            ? { ...p, body: noteBody, loading: false }
            : p
          )
        })
        .catch(e => {
          console.error('[ReviewQueue] Failed to fetch note preview:', e)
          setPreview(p => p?.item.file_path === item.file_path
            ? { ...p, loading: false }
            : p
          )
        })
    }
  }, [])

  const handleMouseLeave = useCallback(() => {
    leaveTimerRef.current = setTimeout(() => {
      setPreview(null)
      leaveTimerRef.current = null
    }, 150)
  }, [])

  const handlePreviewMouseEnter = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      clearTimeout(leaveTimerRef.current)
      leaveTimerRef.current = null
    }
  }, [])

  if (!open) return null

  const { status, items, error, approvingIds, rejectingIds, approvingAll } = state
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
                <li
                  key={item.file_path}
                  className="review-card"
                  data-testid="review-item"
                  onMouseEnter={e => handleCardMouseEnter(item, e.currentTarget)}
                  onMouseLeave={handleMouseLeave}
                >
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
                      disabled={approvingIds.has(item.file_path) || rejectingIds.has(item.file_path) || approvingAll}
                      data-testid="approve-btn"
                      aria-label={`Approve ${item.title || item.file_path}`}
                    >
                      {approvingIds.has(item.file_path) ? '…' : '✓ Approve'}
                    </button>
                    <button
                      className="review-card__btn review-card__btn--edit"
                      onClick={() => handleEdit(item.file_path)}
                      disabled={approvingAll}
                      data-testid="edit-btn"
                      aria-label={`Edit ${item.title || item.file_path}`}
                    >
                      ✎ Edit
                    </button>
                    <button
                      className="review-card__btn review-card__btn--reject"
                      onClick={() => handleReject(item.file_path)}
                      disabled={approvingIds.has(item.file_path) || rejectingIds.has(item.file_path) || approvingAll}
                      data-testid="reject-btn"
                      aria-label={`Reject ${item.title || item.file_path}`}
                    >
                      {rejectingIds.has(item.file_path) ? '…' : '✕ Reject'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {preview && (
        <div
          className="review-preview"
          style={{
            top: Number.isFinite(preview.y)
              ? Math.max(60, Math.min(preview.y, (typeof window !== 'undefined' ? window.innerHeight : 800) - 300))
              : 60
          }}
          data-testid="review-preview"
          onMouseEnter={handlePreviewMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <p className="review-preview__title">{preview.item.title || preview.item.file_path}</p>
          <div className="review-preview__body">
            {preview.loading && <span className="review-preview__loading">Loading…</span>}
            {!preview.loading && preview.body
              ? (() => {
                  try {
                    const { body: markdownBody } = splitFrontmatter(preview.body)
                    const truncated = markdownBody.slice(0, 400)
                    const displayText = truncated + (markdownBody.length > 400 ? '…' : '')
                    return (
                      <ReactMarkdown components={PREVIEW_MARKDOWN_COMPONENTS}>
                        {displayText}
                      </ReactMarkdown>
                    )
                  } catch {
                    return <span className="review-preview__empty">Error rendering preview</span>
                  }
                })()
              : !preview.loading && <span className="review-preview__empty">No preview available</span>
            }
          </div>
          <div className="review-preview__actions">
            <button
              className="review-card__btn review-card__btn--approve"
              onClick={() => handleApprove(preview.item.file_path)}
              disabled={approvingIds.has(preview.item.file_path) || rejectingIds.has(preview.item.file_path) || approvingAll}
              data-testid="preview-approve-btn"
              aria-label={`Approve ${preview.item.title || preview.item.file_path}`}
            >
              ✓ Approve
            </button>
            <button
              className="review-card__btn review-card__btn--edit"
              onClick={() => handleEdit(preview.item.file_path)}
              disabled={approvingAll}
              data-testid="preview-edit-btn"
              aria-label={`Edit ${preview.item.title || preview.item.file_path}`}
            >
              ✎ Edit
            </button>
            <button
              className="review-card__btn review-card__btn--reject"
              onClick={() => handleReject(preview.item.file_path)}
              disabled={approvingIds.has(preview.item.file_path) || rejectingIds.has(preview.item.file_path) || approvingAll}
              data-testid="preview-reject-btn"
              aria-label={`Reject ${preview.item.title || preview.item.file_path}`}
            >
              ✕ Reject
            </button>
          </div>
        </div>
      )}
    </>
  )
}
