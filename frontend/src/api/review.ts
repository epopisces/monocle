import type { components } from './schema.d.ts'
import { apiPatch } from './client'

export type NoteRef = components['schemas']['NoteRef']

export interface ApproveResponse {
  file_path: string
  review_status: string
  approved_by: string
  approved_at: string
  approval_mode: string
}

export type RejectResponse = ApproveResponse

export function approveNote(path: string): Promise<ApproveResponse> {
  return apiPatch<ApproveResponse>(`/api/review/${encodeURIComponent(path)}/approve`, {})
}

export function rejectNote(path: string): Promise<RejectResponse> {
  return apiPatch<RejectResponse>(`/api/review/${encodeURIComponent(path)}/reject`, {})
}
