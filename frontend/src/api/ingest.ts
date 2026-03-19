import type { components } from './schema.d.ts'
import { apiGet, apiPost, apiDelete } from './client'

export type IngestRequest = components['schemas']['IngestRequest']
export type IngestResponse = components['schemas']['IngestResponse']
export type IngestConfidence = components['schemas']['IngestConfidence']

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

export function listIngestFailures(): Promise<FailedIngestRecord[]> {
  return apiGet<FailedIngestRecord[]>('/api/ingest/failures')
}

export function retryIngestFailure(id: string): Promise<IngestResponse> {
  return apiPost<IngestResponse>('/api/ingest/failures/retry', { id } satisfies RetryRequest)
}

export function deleteIngestFailure(id: string): Promise<void> {
  return apiDelete<void>(`/api/ingest/failures/${encodeURIComponent(id)}`)
}
