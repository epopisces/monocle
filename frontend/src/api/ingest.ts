import type { components } from './schema.d.ts'
import { apiGet, apiPost, apiDelete } from './client'

export type IngestRequest = components['schemas']['IngestRequest']
export type IngestResponse = components['schemas']['IngestResponse']

export interface CountResponse {
  count: number
}

export interface IngestSession {
  session_id: string
  origin: 'api' | 'chat' | 'inbox'
  state: string
  source_ids: string[]
  title: string | null
  digest: string | null
  open_questions: Array<Record<string, unknown>>
  related_notes: Array<Record<string, unknown>>
  contradictions: Array<Record<string, unknown>>
  proposed_actions: Array<Record<string, unknown>>
  created_at: string
  updated_at: string
  prepared_at: string | null
  last_true_up_at: string | null
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

export function getIngestSession(sessionId: string): Promise<IngestSessionDetailResponse> {
  return apiGet<IngestSessionDetailResponse>(`/api/ingest/sessions/${encodeURIComponent(sessionId)}`)
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
