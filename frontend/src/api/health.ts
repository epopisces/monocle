import type { components } from './schema.d.ts'
import { apiGet } from './client'

export type HealthResponse = components['schemas']['HealthResponse']

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/api/health')
}

// Model status types (mirrors monocle/models.py ModelStatus / ProviderModelsResponse)
export interface ModelStatus {
  name: string
  role: 'chat' | 'embed' | 'transcribe'
  available: boolean
  loaded: boolean
}

export interface ProviderModelsResponse {
  provider: string
  provider_reachable: boolean
  models: ModelStatus[]
}

export function getModelStatus(): Promise<ProviderModelsResponse> {
  return apiGet<ProviderModelsResponse>('/api/health/models')
}
