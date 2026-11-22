import type { components } from './schema.d.ts'
import { apiGet } from './client'

export type CaptureWorkbenchResponse = components['schemas']['CaptureWorkbenchResponse']
export type CaptureWorkbenchSection = components['schemas']['CaptureWorkbenchSection']
export type CaptureWorkbenchItem = components['schemas']['CaptureWorkbenchItem']

export type CaptureWorkbenchSectionKind = 'prepared' | 'pending_review' | 'failures'

export function getCaptureWorkbench(params?: {
  limit_per_section?: number
}): Promise<CaptureWorkbenchResponse> {
  return apiGet<CaptureWorkbenchResponse>(
    '/api/capture-workbench',
    params as Record<string, string | number | boolean | null | undefined>,
  )
}