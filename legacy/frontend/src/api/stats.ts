import type { components } from './schema.d.ts'
import { apiGet } from './client'

export type BrainStats = components['schemas']['BrainStats']

export function getStats(): Promise<BrainStats> {
  return apiGet<BrainStats>('/api/stats')
}
