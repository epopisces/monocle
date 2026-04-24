import { useCallback, useEffect, useState } from 'react'
import {
  countIngestNotifications,
  dismissIngestNotification,
  getIngestSession,
  listIngestNotifications,
  markIngestNotificationRead,
  trueUpIngestSession,
  type IngestNotificationSummary,
  type IngestSessionDetailResponse,
} from '../../api/ingest'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import './IngestInbox.css'

interface Props {
  open: boolean
  onClose: () => void
  onCountUpdate?: (count: number) => void
}

export default function IngestInbox({ open, onClose, onCountUpdate }: Props) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')
  const [items, setItems] = useState<IngestNotificationSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<IngestSessionDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set())

  const refreshUnreadCount = useCallback(async () => {
    try {
      const count = await countIngestNotifications({ status: 'unread', kind: 'ingest_ready' })
      onCountUpdate?.(count.count)
    } catch {
      // non-fatal
    }
  }, [onCountUpdate])

  const loadNotifications = useCallback(async () => {
    try {
      setStatus('loading')
      setError(null)
      const notifications = await listIngestNotifications({ kind: 'ingest_ready', limit: 50 })
      setItems(notifications)
      setStatus('loaded')
      if (notifications.length > 0 && !selectedId) {
        setSelectedId(notifications[0].notification_id)
      }
    } catch (e) {
      setStatus('error')
      setError(mapErrorToUserMessage(e))
    }
  }, [selectedId])

  useEffect(() => {
    if (!open) {
      setItems([])
      setSelectedId(null)
      setDetail(null)
      setError(null)
      setStatus('loading')
      return
    }
    loadNotifications()
  }, [open, loadNotifications])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  useEffect(() => {
    if (!open || !selectedId) return
    const selected = items.find(item => item.notification_id === selectedId)
    if (!selected) return

    let cancelled = false
    setDetailLoading(true)
    setError(null)

    getIngestSession(selected.session_id)
      .then(async data => {
        if (cancelled) return
        setDetail(data)
        if (selected.status === 'unread') {
          await markIngestNotificationRead(selected.notification_id)
          if (cancelled) return
          setItems(current => current.map(item => (
            item.notification_id === selected.notification_id
              ? { ...item, status: 'read' }
              : item
          )))
          refreshUnreadCount()
        }
      })
      .catch(e => {
        if (!cancelled) setError(mapErrorToUserMessage(e))
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, selectedId, items, refreshUnreadCount])

  const handleDismiss = useCallback(async (notificationId: string) => {
    setDismissingIds(current => new Set(current).add(notificationId))
    try {
      await dismissIngestNotification(notificationId)
      setItems(current => current.filter(item => item.notification_id !== notificationId))
      setSelectedId(current => (current === notificationId ? null : current))
      setDetail(current => (current?.session.session_id === items.find(item => item.notification_id === notificationId)?.session_id ? null : current))
      await refreshUnreadCount()
    } catch (e) {
      setError(mapErrorToUserMessage(e))
    } finally {
      setDismissingIds(current => {
        const next = new Set(current)
        next.delete(notificationId)
        return next
      })
    }
  }, [items, refreshUnreadCount])

  const handleTrueUp = useCallback(async () => {
    if (!detail) return
    try {
      setRefreshing(true)
      await trueUpIngestSession(detail.session.session_id)
      setItems(current => current.filter(item => item.session_id !== detail.session.session_id))
      setSelectedId(null)
      setDetail(null)
      await refreshUnreadCount()
    } catch (e) {
      setError(mapErrorToUserMessage(e))
    } finally {
      setRefreshing(false)
    }
  }, [detail, refreshUnreadCount])

  useEffect(() => {
    if (!selectedId && items.length > 0) {
      setSelectedId(items[0].notification_id)
    }
  }, [selectedId, items])

  if (!open) return null

  const selected = items.find(item => item.notification_id === selectedId) ?? null

  return (
    <>
      <div className="ingest-inbox__backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="ingest-inbox" data-testid="ingest-inbox" role="complementary" aria-label="Prepared ingest sessions">
        <div className="ingest-inbox__header">
          <h2 className="ingest-inbox__title">Prepared Ingest Sessions</h2>
          <button className="ingest-inbox__close" onClick={onClose} aria-label="Close ingest inbox">✕</button>
        </div>

        <div className="ingest-inbox__body">
          <section className="ingest-inbox__list-panel">
            {status === 'loading' && <p className="ingest-inbox__status" data-testid="ingest-inbox-loading">Loading…</p>}
            {status === 'error' && error && <p className="ingest-inbox__error" role="alert">{error}</p>}
            {status === 'loaded' && items.length === 0 && (
              <div className="ingest-inbox__empty" data-testid="ingest-inbox-empty">
                <p>No prepared ingest sessions</p>
              </div>
            )}
            {status === 'loaded' && items.length > 0 && (
              <ul className="ingest-inbox__list" role="list">
                {items.map(item => (
                  <li key={item.notification_id}>
                    <button
                      className={`ingest-inbox__item${selectedId === item.notification_id ? ' ingest-inbox__item--active' : ''}`}
                      onClick={() => setSelectedId(item.notification_id)}
                      data-testid="ingest-inbox-item"
                    >
                      <div className="ingest-inbox__item-topline">
                        <span className="ingest-inbox__item-title">{item.session_title ?? item.source_names[0] ?? 'Captured source'}</span>
                        {item.status === 'unread' && <span className="ingest-inbox__item-pill">new</span>}
                      </div>
                      <p className="ingest-inbox__item-digest">{item.session_digest ?? 'Prepared session ready for review.'}</p>
                      <div className="ingest-inbox__item-meta">
                        <span>{item.open_questions_count} questions</span>
                        <span>{item.contradictions_count} warnings</span>
                        <span>{item.proposed_actions_count} drafts</span>
                      </div>
                    </button>
                    <button
                      className="ingest-inbox__dismiss"
                      onClick={() => handleDismiss(item.notification_id)}
                      disabled={dismissingIds.has(item.notification_id)}
                      aria-label={`Dismiss ${item.session_title ?? item.session_id}`}
                    >
                      {dismissingIds.has(item.notification_id) ? '…' : 'Dismiss'}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="ingest-inbox__detail-panel">
            {!selected && <p className="ingest-inbox__status">Select a prepared session</p>}
            {selected && detailLoading && <p className="ingest-inbox__status">Loading session details…</p>}
            {selected && detail && (
              <div className="ingest-inbox__detail" data-testid="ingest-inbox-detail">
                <h3>{detail.session.title ?? selected.session_title ?? 'Prepared session'}</h3>
                <p className="ingest-inbox__detail-digest">{detail.session.digest ?? selected.session_digest}</p>
                <div className="ingest-inbox__detail-actions">
                  <button className="ingest-inbox__refresh" onClick={handleTrueUp} disabled={refreshing}>
                    {refreshing ? 'Refreshing…' : 'True-up Preparation'}
                  </button>
                </div>

                <div className="ingest-inbox__detail-grid">
                  <div>
                    <h4>Sources</h4>
                    <ul>
                      {detail.sources.map(source => (
                        <li key={source.source_id}>{source.source_name}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4>Open Questions</h4>
                    <ul>
                      {detail.session.open_questions.length > 0 ? detail.session.open_questions.map((question, idx) => (
                        <li key={String(question.id ?? idx)}>{String(question.question ?? question.reason ?? 'Question')}</li>
                      )) : <li>No follow-up questions</li>}
                    </ul>
                  </div>
                  <div>
                    <h4>Linked Notes</h4>
                    <ul>
                      {detail.session.related_notes.length > 0 ? detail.session.related_notes.map((note, idx) => (
                        <li key={String(note.file_path ?? idx)}>{String(note.title ?? note.file_path ?? 'Related note')}</li>
                      )) : <li>No related notes yet</li>}
                    </ul>
                  </div>
                  <div>
                    <h4>Contradictions</h4>
                    <ul>
                      {detail.session.contradictions.length > 0 ? detail.session.contradictions.map((warning, idx) => (
                        <li key={String(warning.file_path ?? idx)}>{String(warning.summary ?? 'Potential contradiction')}</li>
                      )) : <li>No contradictions detected</li>}
                    </ul>
                  </div>
                </div>

                <div>
                  <h4>Draft Proposed Actions</h4>
                  <ul className="ingest-inbox__actions">
                    {detail.session.proposed_actions.length > 0 ? detail.session.proposed_actions.map((action, idx) => (
                      <li key={String(action.action_id ?? idx)}>
                        <strong>{String(action.action_type ?? 'action')}</strong>
                        {' '}
                        {String(action.target_file_path ?? action.target_note_type ?? 'draft target')}
                        <p>{String(action.rationale ?? 'Prepared for later review.')}</p>
                      </li>
                    )) : <li>No draft actions yet</li>}
                  </ul>
                </div>
              </div>
            )}
          </section>
        </div>
      </aside>
    </>
  )
}