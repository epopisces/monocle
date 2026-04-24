import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  answerIngestQuestion,
  approveAllIngestActions,
  approveIngestAction,
  getIngestSession,
  listIngestSessions,
  patchIngestAction,
  rejectIngestAction,
  startIngestReview,
  trueUpIngestSession,
  type IngestSession,
  type IngestSessionDetailResponse,
  type ProposedAction,
} from '../../api/ingest'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import './IngestReviewScreen.css'

interface ActionDraft {
  rationale: string
  title: string
  body: string
}

function summarizeSession(session: IngestSession) {
  return session.title ?? session.digest ?? session.source_ids[0] ?? 'Prepared session'
}

function formatStateLabel(state: string) {
  return state.split('_').join(' ')
}

function buildActionDraft(action: ProposedAction): ActionDraft {
  return {
    rationale: action.rationale,
    title: String(action.proposed_content.title ?? ''),
    body: String(action.proposed_content.body ?? ''),
  }
}

export default function IngestReviewScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [sessions, setSessions] = useState<IngestSession[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get('session'))
  const [detail, setDetail] = useState<IngestSessionDetailResponse | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [questionDrafts, setQuestionDrafts] = useState<Record<string, string>>({})
  const [actionDrafts, setActionDrafts] = useState<Record<string, ActionDraft>>({})
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const detailRequestId = useRef(0)
  const selectedIdRef = useRef<string | null>(selectedId)
  const querySessionId = searchParams.get('session')
  const querySessionIdRef = useRef<string | null>(querySessionId)
  const setSearchParamsRef = useRef(setSearchParams)

  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])

  useEffect(() => {
    querySessionIdRef.current = querySessionId
    if (querySessionId !== selectedIdRef.current) {
      setSelectedId(querySessionId)
    }
  }, [querySessionId])

  useEffect(() => {
    setSearchParamsRef.current = setSearchParams
  }, [setSearchParams])

  const syncDrafts = useCallback((nextDetail: IngestSessionDetailResponse | null) => {
    if (!nextDetail) {
      setQuestionDrafts({})
      setActionDrafts({})
      return
    }

    const nextQuestions: Record<string, string> = {}
    for (const question of nextDetail.session.open_questions) {
      if (!question.id) continue
      nextQuestions[question.id] = question.answer ?? ''
    }
    setQuestionDrafts(nextQuestions)

    const nextActions: Record<string, ActionDraft> = {}
    for (const action of nextDetail.session.proposed_actions) {
      nextActions[action.action_id] = buildActionDraft(action)
    }
    setActionDrafts(nextActions)
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      setLoadingList(true)
      setError(null)
      const nextSessions = await listIngestSessions({ ready_only: true, limit: 50 })
      setSessions(nextSessions)
      if (nextSessions.length === 0) {
        selectedIdRef.current = null
        setSelectedId(null)
        setDetail(null)
        setSearchParamsRef.current({}, { replace: true })
        return
      }
      const preferred = querySessionIdRef.current
      const currentSelected = selectedIdRef.current
      const hasPreferred = preferred ? nextSessions.some(item => item.session_id === preferred) : false
      const nextSelected = hasPreferred
        ? preferred
        : (currentSelected && nextSessions.some(item => item.session_id === currentSelected)
          ? currentSelected
          : nextSessions[0].session_id)
      selectedIdRef.current = nextSelected
      setSelectedId(nextSelected)
      if (nextSelected) {
        setSearchParamsRef.current({ session: nextSelected }, { replace: true })
      } else {
        setSearchParamsRef.current({}, { replace: true })
      }
    } catch (e) {
      setError(mapErrorToUserMessage(e))
    } finally {
      setLoadingList(false)
    }
  }, [])

  const loadDetail = useCallback(async (sessionId: string) => {
    const requestId = ++detailRequestId.current
    try {
      setLoadingDetail(true)
      setError(null)
      const nextDetail = await getIngestSession(sessionId)
      if (detailRequestId.current !== requestId) {
        return
      }
      setDetail(nextDetail)
      syncDrafts(nextDetail)
    } catch (e) {
      if (detailRequestId.current !== requestId) {
        return
      }
      setError(mapErrorToUserMessage(e))
    } finally {
      if (detailRequestId.current !== requestId) {
        return
      }
      setLoadingDetail(false)
    }
  }, [syncDrafts])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  useEffect(() => {
    if (!selectedId) return
    loadDetail(selectedId)
  }, [selectedId, loadDetail])

  const selectedSession = useMemo(
    () => sessions.find(item => item.session_id === selectedId) ?? null,
    [sessions, selectedId],
  )

  const replaceDetail = useCallback((nextDetail: IngestSessionDetailResponse) => {
    setDetail(nextDetail)
    syncDrafts(nextDetail)
    setSessions(current => current.map(item => (
      item.session_id === nextDetail.session.session_id
        ? {
            ...item,
            state: nextDetail.session.state,
            title: nextDetail.session.title,
            digest: nextDetail.session.digest,
            open_questions: nextDetail.session.open_questions,
            contradictions: nextDetail.session.contradictions,
            proposed_actions: nextDetail.session.proposed_actions,
            updated_at: nextDetail.session.updated_at,
            prepared_at: nextDetail.session.prepared_at,
            last_true_up_at: nextDetail.session.last_true_up_at,
          }
        : item
    )))
  }, [syncDrafts])

  const runMutation = useCallback(async (key: string, action: () => Promise<IngestSessionDetailResponse>) => {
    try {
      setBusyKey(key)
      setError(null)
      const nextDetail = await action()
      replaceDetail(nextDetail)
    } catch (e) {
      setError(mapErrorToUserMessage(e))
    } finally {
      setBusyKey(null)
    }
  }, [replaceDetail])

  const handleSelect = useCallback((sessionId: string) => {
    selectedIdRef.current = sessionId
    setSelectedId(sessionId)
    setSearchParamsRef.current({ session: sessionId }, { replace: true })
  }, [])

  const handleTrueUp = useCallback(async () => {
    if (!detail) return
    try {
      setBusyKey('true-up')
      setError(null)
      await trueUpIngestSession(detail.session.session_id)
      await loadSessions()
    } catch (e) {
      setError(mapErrorToUserMessage(e))
    } finally {
      setBusyKey(null)
    }
  }, [detail, loadSessions])

  return (
    <div className="ingest-review" data-testid="ingest-review-screen">
      <aside className="ingest-review__rail">
        <div className="ingest-review__rail-header">
          <h1>Ingest Review</h1>
          <p>Prepared sessions ready for human review.</p>
        </div>

        {loadingList && <div className="ingest-review__panel">Loading sessions…</div>}
        {!loadingList && sessions.length === 0 && <div className="ingest-review__panel">No sessions are ready for review.</div>}
        {!loadingList && sessions.length > 0 && (
          <ul className="ingest-review__session-list">
            {sessions.map(session => (
              <li key={session.session_id}>
                <button
                  type="button"
                  className={`ingest-review__session${session.session_id === selectedId ? ' ingest-review__session--active' : ''}`}
                  onClick={() => handleSelect(session.session_id)}
                >
                  <span className="ingest-review__session-title">{summarizeSession(session)}</span>
                  <span className="ingest-review__session-state">{formatStateLabel(session.state)}</span>
                  <span className="ingest-review__session-digest">{session.digest ?? 'Prepared session ready for review.'}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="ingest-review__workspace">
        {error && <div className="ingest-review__error" role="alert">{error}</div>}
        {!selectedSession && !loadingList && <div className="ingest-review__panel">Select a prepared session to review.</div>}
        {selectedSession && loadingDetail && <div className="ingest-review__panel">Loading review workspace…</div>}
        {detail && !loadingDetail && (
          <div className="ingest-review__content" data-testid="ingest-review-detail">
            <header className="ingest-review__hero">
              <div>
                <p className="ingest-review__eyebrow">{formatStateLabel(detail.session.state)}</p>
                <h2>{detail.session.title ?? summarizeSession(detail.session)}</h2>
                <p className="ingest-review__digest">{detail.session.digest ?? 'Prepared session ready for review.'}</p>
              </div>
              <div className="ingest-review__hero-actions">
                <button
                  type="button"
                  onClick={() => runMutation('start-review', () => startIngestReview(detail.session.session_id))}
                  disabled={busyKey !== null || detail.session.state === 'in_review'}
                >
                  {detail.session.state === 'in_review' ? 'Review started' : 'Start review'}
                </button>
                <button type="button" onClick={handleTrueUp} disabled={busyKey !== null}>
                  {busyKey === 'true-up' ? 'Refreshing…' : 'True-up'}
                </button>
                <button
                  type="button"
                  onClick={() => runMutation('approve-all', () => approveAllIngestActions(detail.session.session_id))}
                  disabled={busyKey !== null || detail.session.proposed_actions.length === 0}
                >
                  Approve all
                </button>
              </div>
            </header>

            <div className="ingest-review__grid">
              <section className="ingest-review__panel">
                <h3>Sources</h3>
                <ul className="ingest-review__simple-list">
                  {detail.sources.map(source => (
                    <li key={source.source_id}>
                      <strong>{source.source_name}</strong>
                      <span>{source.kind}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="ingest-review__panel">
                <h3>Related notes</h3>
                <ul className="ingest-review__simple-list">
                  {detail.session.related_notes.length > 0 ? detail.session.related_notes.map(note => (
                    <li key={note.file_path ?? note.title}>
                      {note.file_path ? <Link to={`/docs?path=${encodeURIComponent(note.file_path)}`}>{note.title ?? note.file_path}</Link> : <span>{note.title ?? 'Related note'}</span>}
                      {note.excerpt && <span>{note.excerpt}</span>}
                    </li>
                  )) : <li>No related notes suggested yet.</li>}
                </ul>
              </section>
            </div>

            <section className="ingest-review__panel">
              <h3>Follow-up questions</h3>
              <div className="ingest-review__stack">
                {detail.session.open_questions.length > 0 ? detail.session.open_questions.map(question => (
                  <article key={question.id ?? question.question} className="ingest-review__question" data-testid="review-question">
                    <p><strong>{question.question ?? 'Question'}</strong></p>
                    {question.reason && <p className="ingest-review__muted">{question.reason}</p>}
                    <textarea
                      value={questionDrafts[question.id ?? ''] ?? ''}
                      onChange={event => setQuestionDrafts(current => ({ ...current, [question.id ?? '']: event.target.value }))}
                      placeholder="Add the missing context"
                    />
                    <div className="ingest-review__inline-actions">
                      <button
                        type="button"
                        onClick={() => runMutation(
                          `question:${question.id}`,
                          () => answerIngestQuestion(detail.session.session_id, question.id ?? '', { answer: questionDrafts[question.id ?? ''] ?? '' }),
                        )}
                        disabled={!question.id || busyKey !== null || !(questionDrafts[question.id] ?? '').trim()}
                      >
                        Save answer
                      </button>
                    </div>
                  </article>
                )) : <p>No follow-up questions.</p>}
              </div>
            </section>

            <section className="ingest-review__panel">
              <h3>Contradictions</h3>
              <div className="ingest-review__stack">
                {detail.session.contradictions.length > 0 ? detail.session.contradictions.map(item => (
                  <article key={`${item.file_path ?? 'warning'}:${item.summary ?? ''}`} className="ingest-review__warning">
                    <div>
                      <strong>{item.title ?? item.file_path ?? 'Potential contradiction'}</strong>
                      <p>{item.summary ?? 'Potential contradiction detected.'}</p>
                      {item.excerpt && <p className="ingest-review__muted">{item.excerpt}</p>}
                    </div>
                    {item.file_path && <Link to={`/docs?path=${encodeURIComponent(item.file_path)}`}>Open note</Link>}
                  </article>
                )) : <p>No contradictions detected.</p>}
              </div>
            </section>

            <section className="ingest-review__panel">
              <h3>Proposed changes</h3>
              <div className="ingest-review__stack">
                {detail.session.proposed_actions.length > 0 ? detail.session.proposed_actions.map(action => {
                  const draft = actionDrafts[action.action_id] ?? buildActionDraft(action)
                  return (
                    <article key={action.action_id} className="ingest-review__action" data-testid="review-action">
                      <header className="ingest-review__action-header">
                        <div>
                          <strong>{action.action_type}</strong>
                          <p>{action.target_file_path ?? action.target_note_type ?? 'Draft target'}</p>
                        </div>
                        <span className={`ingest-review__pill ingest-review__pill--${action.approval_state}`}>{action.approval_state}</span>
                      </header>

                      <label>
                        Rationale
                        <textarea
                          value={draft.rationale}
                          onChange={event => setActionDrafts(current => ({
                            ...current,
                            [action.action_id]: { ...draft, rationale: event.target.value },
                          }))}
                        />
                      </label>

                      <div className="ingest-review__action-grid">
                        <label>
                          Title
                          <input
                            value={draft.title}
                            onChange={event => setActionDrafts(current => ({
                              ...current,
                              [action.action_id]: { ...draft, title: event.target.value },
                            }))}
                          />
                        </label>
                        <label>
                          Body
                          <textarea
                            value={draft.body}
                            onChange={event => setActionDrafts(current => ({
                              ...current,
                              [action.action_id]: { ...draft, body: event.target.value },
                            }))}
                          />
                        </label>
                      </div>

                      {action.diff_preview && (
                        <div className="ingest-review__diff" data-testid="review-diff">
                          <p className="ingest-review__muted">{action.diff_preview.kind} preview</p>
                          {action.diff_preview.hunks.map((hunk, index) => (
                            <div key={`${action.action_id}:${hunk.section ?? index}`} className="ingest-review__diff-hunk">
                              <strong>{hunk.section ?? 'change'}</strong>
                              <div className="ingest-review__diff-columns">
                                <pre>{hunk.before ?? 'New content'}</pre>
                                <pre>{hunk.after ?? 'Removed'}</pre>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="ingest-review__inline-actions">
                        <button
                          type="button"
                          onClick={() => runMutation(
                            `save:${action.action_id}`,
                            () => patchIngestAction(detail.session.session_id, action.action_id, {
                              rationale: draft.rationale,
                              proposed_content: { title: draft.title, body: draft.body },
                            }),
                          )}
                          disabled={busyKey !== null}
                        >
                          Save draft
                        </button>
                        <button
                          type="button"
                          onClick={() => runMutation(
                            `approve:${action.action_id}`,
                            () => approveIngestAction(detail.session.session_id, action.action_id),
                          )}
                          disabled={busyKey !== null}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => runMutation(
                            `reject:${action.action_id}`,
                            () => rejectIngestAction(detail.session.session_id, action.action_id),
                          )}
                          disabled={busyKey !== null}
                        >
                          Reject
                        </button>
                      </div>
                    </article>
                  )
                }) : <p>No proposed actions yet.</p>}
              </div>
            </section>
          </div>
        )}
      </section>
    </div>
  )
}
