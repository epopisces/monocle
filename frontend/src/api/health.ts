import type { components } from './schema.d.ts'
import { apiGet } from './client'

export type HealthResponse = components['schemas']['HealthResponse']

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/api/health')
}
