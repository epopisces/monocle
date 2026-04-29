import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type {
  CaptureWorkbenchItem,
  CaptureWorkbenchResponse,
  CaptureWorkbenchSection,
  CaptureWorkbenchSectionKind,
} from '../../api/captureWorkbench'
import { deleteIngestFailure, retryIngestFailure } from '../../api/ingest'
import { approveNote, rejectNote } from '../../api/review'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import './CaptureWorkbench.css'

interface Props {
  open: boolean
  onClose: () => void
  summary: CaptureWorkbenchResponse | null
  loading?: boolean
  error?: string | null
  onRefresh?: () => Promise<void> | void
}

const SECTION_ORDER: CaptureWorkbenchSectionKind[] = ['prepared', 'pending_review', 'failures']

const SECTION_LABELS: Record<CaptureWorkbenchSectionKind, string> = {
  prepared: 'Prepared',
  pending_review: 'Pending Review',
  failures: 'Failures',
}

function emptySection(section: CaptureWorkbenchSectionKind, count: number): CaptureWorkbenchSection {
  return {
    section,
    count,
    items: [],
  }
}

function formatStateLabel(state?: string | null): string | null {
  if (!state) return null
  return state.split('_').join(' ')
}

function formatConfidence(confidence?: number | null): string | null {
  if (confidence === undefined || confidence === null) return null
  return `${Math.round(confidence * 100)}% confidence`
}

export default function CaptureWorkbench({
  open,
  onClose,
  summary,
  loading = false,
  error = null,
  onRefresh,
}: Props) {
  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState<CaptureWorkbenchSectionKind>('prepared')
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set())

  const counts = useMemo(
    () => ({
      prepared: summary?.counts?.prepared ?? 0,
      pending_review: summary?.counts?.pending_review ?? 0,
      failures: summary?.counts?.failures ?? 0,
    }),
    [summary],
  )

  const sections = useMemo(
    () => SECTION_ORDER.map(section => {
      const matched = summary?.sections?.find(item => item.section === section)
      return matched ?? emptySection(section, counts[section])
    }),
    [counts, summary],
  )

  const fallbackSection = useMemo(
    () => sections.find(section => section.count > 0)?.section ?? 'prepared',
    [sections],
  )

  const activeData = useMemo(
    () => sections.find(section => section.section === activeSection) ?? emptySection(activeSection, counts[activeSection]),
    [activeSection, counts, sections],
  )

  useEffect(() => {
    if (!open) {
      setActionError(null)
      setBusyKeys(new Set())
      return
    }
    if (activeData.count === 0 && activeData.items?.length === 0 && activeSection !== fallbackSection) {
      setActiveSection(fallbackSection)
    }
  }, [activeData.count, activeData.items, activeSection, fallbackSection, open])

  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const runMutation = useCallback(async (key: string, action: () => Promise<void>) => {
    setBusyKeys(current => {
      const next = new Set(current)
      next.add(key)
      return next
    })
    setActionError(null)
    try {
      await action()
      await onRefresh?.()
    } catch (mutationError) {
      setActionError(mapErrorToUserMessage(mutationError))
    } finally {
      setBusyKeys(current => {
        const next = new Set(current)
        next.delete(key)
        return next
      })
    }
  }, [onRefresh])

  const isItemBusy = useCallback(
    (itemId: string) => Array.from(busyKeys).some(key => key.endsWith(`:${itemId}`)),
    [busyKeys],
  )

  const openReviewSession = useCallback((sessionId?: string | null) => {
    if (!sessionId) return
    onClose()
    navigate(`/ingest-review?session=${encodeURIComponent(sessionId)}`)
  }, [navigate, onClose])

  const openNoteEditor = useCallback((filePath?: string | null) => {
    if (!filePath) return
    onClose()
    navigate(`/docs?path=${encodeURIComponent(filePath)}`)
  }, [navigate, onClose])

  const renderPreparedItem = useCallback((item: CaptureWorkbenchItem) => (
    <article className="capture-workbench__card capture-workbench__card--prepared" data-testid="capture-workbench-item" key={item.item_id}>
      <div className="capture-workbench__card-header">
        <div>
          <h3 className="capture-workbench__card-title">{item.title}</h3>
          {item.state && <p className="capture-workbench__card-kicker">{formatStateLabel(item.state)}</p>}
        </div>
        <span className="capture-workbench__pill capture-workbench__pill--prepared">Prepared</span>
      </div>
      {item.summary && <p className="capture-workbench__card-summary">{item.summary}</p>}
      <div className="capture-workbench__meta">
        <span>{item.open_questions_count} questions</span>
        <span>{item.contradictions_count} warnings</span>
        <span>{item.proposed_actions_count} drafts</span>
      </div>
      <div className="capture-workbench__actions">
        <button className="capture-workbench__btn capture-workbench__btn--primary" onClick={() => openReviewSession(item.session_id)}>
          Open Review
        </button>
      </div>
    </article>
  ), [openReviewSession])

  const renderPendingItem = useCallback((item: CaptureWorkbenchItem) => {
    const busy = isItemBusy(item.item_id)
    return (
      <article className="capture-workbench__card capture-workbench__card--pending" data-testid="capture-workbench-item" key={item.item_id}>
        <div className="capture-workbench__card-header">
          <div>
            <h3 className="capture-workbench__card-title">{item.title}</h3>
            <p className="capture-workbench__card-kicker">{item.file_path}</p>
          </div>
          <div className="capture-workbench__pill-row">
            {item.note_type && <span className="capture-workbench__pill">{item.note_type}</span>}
            {formatConfidence(item.confidence) && <span className="capture-workbench__pill capture-workbench__pill--pending">{formatConfidence(item.confidence)}</span>}
          </div>
        </div>
        <div className="capture-workbench__actions">
          <button className="capture-workbench__btn" disabled={busy} onClick={() => openNoteEditor(item.file_path)}>
            Edit
          </button>
          <button
            className="capture-workbench__btn capture-workbench__btn--success"
            disabled={busy || !item.file_path}
            onClick={() => runMutation(`approve:${item.item_id}`, async () => {
              if (!item.file_path) return
              await approveNote(item.file_path)
            })}
          >
            {busyKeys.has(`approve:${item.item_id}`) ? 'Approving…' : 'Approve'}
          </button>
          <button
            className="capture-workbench__btn capture-workbench__btn--danger"
            disabled={busy || !item.file_path}
            onClick={() => runMutation(`reject:${item.item_id}`, async () => {
              if (!item.file_path) return
              await rejectNote(item.file_path)
            })}
          >
            {busyKeys.has(`reject:${item.item_id}`) ? 'Rejecting…' : 'Reject'}
          </button>
        </div>
      </article>
    )
  }, [busyKeys, isItemBusy, openNoteEditor, runMutation])

  const renderFailureItem = useCallback((item: CaptureWorkbenchItem) => {
    if (item.item_type === 'failed_session') {
      return (
        <article className="capture-workbench__card capture-workbench__card--failure" data-testid="capture-workbench-item" key={item.item_id}>
          <div className="capture-workbench__card-header">
            <div>
              <h3 className="capture-workbench__card-title">{item.title}</h3>
              {item.state && <p className="capture-workbench__card-kicker">{formatStateLabel(item.state)}</p>}
            </div>
            <span className="capture-workbench__pill capture-workbench__pill--warning">Session failure</span>
          </div>
          {item.summary && <p className="capture-workbench__card-summary">{item.summary}</p>}
          <div className="capture-workbench__meta">
            <span>{item.open_questions_count} questions</span>
            <span>{item.contradictions_count} warnings</span>
            <span>{item.proposed_actions_count} drafts</span>
          </div>
          <div className="capture-workbench__actions">
            <button className="capture-workbench__btn capture-workbench__btn--primary" onClick={() => openReviewSession(item.session_id)}>
              Open Session
            </button>
          </div>
        </article>
      )
    }

    const busy = isItemBusy(item.item_id)
    return (
      <article className="capture-workbench__card capture-workbench__card--failure" data-testid="capture-workbench-item" key={item.item_id}>
        <div className="capture-workbench__card-header">
          <div>
            <h3 className="capture-workbench__card-title">{item.title}</h3>
            {item.source && <p className="capture-workbench__card-kicker">{item.source}</p>}
          </div>
          <span className="capture-workbench__pill capture-workbench__pill--warning">Failed capture</span>
        </div>
        {item.summary && <p className="capture-workbench__card-summary">{item.summary}</p>}
        {item.error_message && <p className="capture-workbench__error-block">{item.error_message}</p>}
        <div className="capture-workbench__actions">
          <button
            className="capture-workbench__btn capture-workbench__btn--primary"
            disabled={busy || !item.failure_id || item.retryable === false}
            onClick={() => runMutation(`retry:${item.item_id}`, async () => {
              if (!item.failure_id) return
              await retryIngestFailure(item.failure_id)
            })}
          >
            {busyKeys.has(`retry:${item.item_id}`) ? 'Retrying…' : 'Retry'}
          </button>
          <button
            className="capture-workbench__btn"
            disabled={busy || !item.failure_id}
            onClick={() => runMutation(`dismiss:${item.item_id}`, async () => {
              if (!item.failure_id) return
              await deleteIngestFailure(item.failure_id)
            })}
          >
            {busyKeys.has(`dismiss:${item.item_id}`) ? 'Dismissing…' : 'Dismiss'}
          </button>
        </div>
      </article>
    )
  }, [busyKeys, isItemBusy, openReviewSession, runMutation])

  if (!open) return null

  const activeItems = activeData.items ?? []
  const hasSummary = summary !== null
  const emptyMessage =
    activeSection === 'prepared'
      ? 'No prepared sessions are waiting right now.'
      : activeSection === 'pending_review'
        ? 'No pending notes are below the current workbench threshold.'
        : 'No failed capture work is waiting right now.'

  return (
    <>
      <div className="capture-workbench__backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="capture-workbench" data-testid="capture-workbench" role="complementary" aria-label="Capture workbench">
        <div className="capture-workbench__header">
          <div>
            <p className="capture-workbench__eyebrow">Actionable capture work</p>
            <h2 className="capture-workbench__title">
              Capture Workbench
              <span className="capture-workbench__count">{summary?.actionable_count ?? 0}</span>
            </h2>
            <p className="capture-workbench__subtitle">Prepared sessions, pending review, and failures in one place.</p>
          </div>
          <div className="capture-workbench__header-actions">
            <button className="capture-workbench__btn" onClick={() => { void onRefresh?.() }} disabled={loading}>
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
            <button className="capture-workbench__close" onClick={onClose} aria-label="Close capture workbench">✕</button>
          </div>
        </div>

        <div className="capture-workbench__body">
          <div className="capture-workbench__tabs" role="tablist" aria-label="Capture workbench sections">
            {sections.map(section => (
              <button
                key={section.section}
                className={`capture-workbench__tab${activeSection === section.section ? ' capture-workbench__tab--active' : ''}`}
                data-testid={`capture-workbench-tab-${section.section}`}
                onClick={() => setActiveSection(section.section)}
                role="tab"
                aria-selected={activeSection === section.section}
              >
                <span>{SECTION_LABELS[section.section]}</span>
                <span className="capture-workbench__tab-count">{section.count}</span>
              </button>
            ))}
          </div>

          {activeSection === 'pending_review' && hasSummary && (
            <p className="capture-workbench__hint">
              Showing notes at or below {Math.round((summary.queue_threshold ?? 1) * 100)}% confidence.
            </p>
          )}

          {error && !hasSummary && <p className="capture-workbench__error" role="alert">{error}</p>}
          {actionError && <p className="capture-workbench__error" role="alert">{actionError}</p>}

          {loading && !hasSummary && <div className="capture-workbench__status">Loading workbench…</div>}
          {!loading && !hasSummary && !error && <div className="capture-workbench__status">No workbench summary available.</div>}
          {hasSummary && activeItems.length === 0 && <div className="capture-workbench__status">{emptyMessage}</div>}
          {hasSummary && activeItems.length > 0 && (
            <>
              {activeData.count > activeItems.length && (
                <p className="capture-workbench__hint">Showing the first {activeItems.length} of {activeData.count} items in this section.</p>
              )}
              <div className="capture-workbench__list">
                {activeSection === 'prepared' && activeItems.map(renderPreparedItem)}
                {activeSection === 'pending_review' && activeItems.map(renderPendingItem)}
                {activeSection === 'failures' && activeItems.map(renderFailureItem)}
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  )
}