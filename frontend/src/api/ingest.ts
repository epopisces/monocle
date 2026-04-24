import type { components } from './schema.d.ts'
import { apiDelete, apiGet, apiPatch, apiPost } from './client'

export type IngestRequest = components['schemas']['IngestRequest']
export type IngestResponse = components['schemas']['IngestResponse']
export type NoteType =
  | 'person_note'
  | 'decision'
  | 'idea'
  | 'observation'
  | 'reference'
  | 'meeting_note'
  | 'project'
  | 'action_item'
  | 'weekly_summary'
  | 'organization'
  | 'other'

export interface CountResponse {
  count: number
}

export interface OpenQuestion {
  id?: string
  question?: string
  reason?: string
  answer?: string
  answered_at?: string
}

export interface RelatedNote {
  file_path?: string
  title?: string
  score?: number
  excerpt?: string
}

export interface ContradictionWarning {
  file_path?: string
  title?: string
  summary?: string
  severity?: string
  excerpt?: string
}

export interface DiffPreviewHunk {
  section?: string | null
  before?: string | null
  after?: string | null
}

export interface DiffPreview {
  kind: string
  before_excerpt?: string | null
  after_excerpt?: string | null
  hunks: DiffPreviewHunk[]
}

export interface IngestExecutionValidation {
  title_match: boolean
  body_match: boolean
  sources_attached: boolean
}

export interface ProposedActionExecutionResult {
  status: 'succeeded' | 'failed' | 'skipped'
  message?: string | null
  file_path?: string | null
  executed_at?: string | null
  validation?: IngestExecutionValidation | null
}

export interface IngestExecutionSummary {
  total_actions: number
  succeeded: number
  failed: number
  skipped: number
  affected_file_paths: string[]
  completed_at?: string | null
}

export interface SourceLink {
  source_id: string
  session_id?: string | null
  source_name: string
  archive_path: string
  kind: string
  mime_type?: string | null
  captured_at?: string | null
  author?: string | null
}

export interface ProposedAction {
  action_id: string
  action_type: 'create_note' | 'update_note'
  approval_state: 'draft' | 'edited' | 'approved' | 'rejected' | 'executed' | 'failed'
  target_file_path: string | null
  target_note_type: NoteType | null
  rationale: string
  diff_preview?: DiffPreview | null
  proposed_content: Record<string, unknown>
  execution_result?: ProposedActionExecutionResult | null
}

export interface ProposedActionPatchRequest {
  target_file_path?: string | null
  target_note_type?: NoteType | null
  rationale?: string | null
  proposed_content?: Record<string, unknown>
}

export interface IngestOpenQuestionAnswerRequest {
  answer: string
}

export interface IngestSession {
  session_id: string
  origin: 'api' | 'chat' | 'inbox'
  state: string
  source_ids: string[]
  title: string | null
  digest: string | null
  open_questions: OpenQuestion[]
  related_notes: RelatedNote[]
  contradictions: ContradictionWarning[]
  proposed_actions: ProposedAction[]
  created_at: string
  updated_at: string
  prepared_at: string | null
  last_true_up_at: string | null
  execution_summary?: IngestExecutionSummary | null
}

export interface SourceRecord {
  source_id: string
  session_id: string
  kind: string
  status: string
  source_name: string
  mime_type: string | null
  archive_path: string
  checksum_sha256: string
  captured_at: string
  byte_size: number
  provenance: Record<string, unknown>
}

export interface IngestSessionDetailResponse {
  session: IngestSession
  sources: SourceRecord[]
}

export interface ArchivedSourceContentResponse {
  source: SourceRecord
  text: string
  truncated: boolean
}

export interface IngestTrueUpResponse {
  session_id: string
  job_id: string
  state: string
  last_true_up_at: string
}

export interface IngestNotificationSummary {
  notification_id: string
  session_id: string
  kind: string
  status: 'unread' | 'read' | 'dismissed'
  created_at: string
  session_state: string
  session_title: string | null
  session_digest: string | null
  source_names: string[]
  open_questions_count: number
  contradictions_count: number
  proposed_actions_count: number
}

/** List of failed-ingest records as returned by the API. */
export interface FailedIngestRecord {
  id: string
  content_preview: string
  content_truncated: boolean
  error_message: string
  failed_at: string
  source: string
  retried: boolean
}

export interface RetryRequest {
  id: string
}

export function ingest(body: IngestRequest): Promise<IngestResponse> {
  return apiPost<IngestResponse>('/api/ingest', body)
}

export function listIngestSessions(params?: {
  state?: string
  origin?: string
  ready_only?: boolean
  limit?: number
  offset?: number
}): Promise<IngestSession[]> {
  return apiGet<IngestSession[]>('/api/ingest/sessions', params)
}

export function getIngestSession(sessionId: string): Promise<IngestSessionDetailResponse> {
  return apiGet<IngestSessionDetailResponse>(`/api/ingest/sessions/${encodeURIComponent(sessionId)}`)
}

export function startIngestReview(sessionId: string): Promise<IngestSessionDetailResponse> {
  return apiPost<IngestSessionDetailResponse>(`/api/ingest/sessions/${encodeURIComponent(sessionId)}/start-review`)
}

export function answerIngestQuestion(
  sessionId: string,
  questionId: string,
  body: IngestOpenQuestionAnswerRequest,
): Promise<IngestSessionDetailResponse> {
  return apiPatch<IngestSessionDetailResponse>(
    `/api/ingest/sessions/${encodeURIComponent(sessionId)}/questions/${encodeURIComponent(questionId)}`,
    body,
  )
}

export function patchIngestAction(
  sessionId: string,
  actionId: string,
  body: ProposedActionPatchRequest,
): Promise<IngestSessionDetailResponse> {
  return apiPatch<IngestSessionDetailResponse>(
    `/api/ingest/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}`,
    body,
  )
}

export function approveIngestAction(sessionId: string, actionId: string): Promise<IngestSessionDetailResponse> {
  return apiPost<IngestSessionDetailResponse>(
    `/api/ingest/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/approve`,
  )
}

export function rejectIngestAction(sessionId: string, actionId: string): Promise<IngestSessionDetailResponse> {
  return apiPost<IngestSessionDetailResponse>(
    `/api/ingest/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/reject`,
  )
}

export function approveAllIngestActions(sessionId: string): Promise<IngestSessionDetailResponse> {
  return apiPost<IngestSessionDetailResponse>(`/api/ingest/sessions/${encodeURIComponent(sessionId)}/approve-all`)
}

export function executeIngestSession(sessionId: string): Promise<IngestSessionDetailResponse> {
  return apiPost<IngestSessionDetailResponse>(`/api/ingest/sessions/${encodeURIComponent(sessionId)}/execute`)
}

export function trueUpIngestSession(sessionId: string): Promise<IngestTrueUpResponse> {
  return apiPost<IngestTrueUpResponse>(`/api/ingest/sessions/${encodeURIComponent(sessionId)}/true-up`)
}

export function listIngestNotifications(params?: {
  status?: 'unread' | 'read' | 'dismissed'
  kind?: string
  limit?: number
  offset?: number
}): Promise<IngestNotificationSummary[]> {
  return apiGet<IngestNotificationSummary[]>('/api/ingest/notifications', params)
}

export function countIngestNotifications(params?: {
  status?: 'unread' | 'read' | 'dismissed'
  kind?: string
}): Promise<CountResponse> {
  return apiGet<CountResponse>('/api/ingest/notifications/count', params)
}

export function markIngestNotificationRead(notificationId: string): Promise<void> {
  return apiPost<void>(`/api/ingest/notifications/${encodeURIComponent(notificationId)}/read`)
}

export function dismissIngestNotification(notificationId: string): Promise<void> {
  return apiPost<void>(`/api/ingest/notifications/${encodeURIComponent(notificationId)}/dismiss`)
}

export function listIngestFailures(): Promise<FailedIngestRecord[]> {
  return apiGet<FailedIngestRecord[]>('/api/ingest/failures')
}

export function retryIngestFailure(id: string): Promise<IngestResponse> {
  return apiPost<IngestResponse>('/api/ingest/failures/retry', { id } satisfies RetryRequest)
}

export function deleteIngestFailure(id: string): Promise<void> {
  return apiDelete<void>(`/api/ingest/failures/${encodeURIComponent(id)}`)
}

export function listArchivedSources(params?: { limit?: number; offset?: number }): Promise<SourceRecord[]> {
  return apiGet<SourceRecord[]>('/api/ingest/sources', params)
}

export function getArchivedSource(sourceId: string): Promise<SourceRecord> {
  return apiGet<SourceRecord>(`/api/ingest/sources/${encodeURIComponent(sourceId)}`)
}

export function getArchivedSourceContent(sourceId: string): Promise<ArchivedSourceContentResponse> {
  return apiGet<ArchivedSourceContentResponse>(`/api/ingest/sources/${encodeURIComponent(sourceId)}/content`)
}

export function getArchivedSourceDownloadUrl(sourceId: string): string {
  return `/api/ingest/sources/${encodeURIComponent(sourceId)}/download`
}

export function isTextSourceRecord(source: { kind: string; mime_type?: string | null }): boolean {
  if (['text', 'url', 'chat_text'].includes(source.kind)) {
    return true
  }
  const mime = (source.mime_type ?? '').toLowerCase()
  return mime.startsWith('text/') || mime === 'application/json' || mime === 'application/xml'
}
