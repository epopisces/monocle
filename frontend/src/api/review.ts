import type { components } from './schema.d.ts'
import { apiGet, apiPatch, apiPost } from './client'

export type NoteRef = components['schemas']['NoteRef']

export interface ReviewListResponse {
  items: NoteRef[]
  total: number
  offset: number
  limit: number
}

export interface ReviewCountResponse {
  count: number
}

export interface ApproveResponse {
  file_path: string
  review_status: string
  approved_by: string
  approved_at: string
  approval_mode: string
}

export interface ApproveAllResponse {
  approved: number
  skipped: number
  errors: number
}

export function listReview(params?: { limit?: number; offset?: number }): Promise<ReviewListResponse> {
  return apiGet<ReviewListResponse>('/api/review', params as Record<string, string | number | boolean | null | undefined>)
}

export function getReviewCount(): Promise<ReviewCountResponse> {
  return apiGet<ReviewCountResponse>('/api/review/count')
}

export function approveNote(path: string): Promise<ApproveResponse> {
  return apiPatch<ApproveResponse>(`/api/review/${encodeURIComponent(path)}/approve`, {})
}

export function approveAll(): Promise<ApproveAllResponse> {
  return apiPost<ApproveAllResponse>('/api/review/approve-all')
}
