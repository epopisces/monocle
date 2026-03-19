import { apiGet, apiPatch, apiPost } from './client'

/** Settings response shape (mirrors SettingsResponse model in Python). */
export interface SettingsResponse {
  ai: {
    provider: string
    model: string
    embed_model: string
    transcribe_backend: string
    transcribe_url: string | null
    transcribe_model: string
    embed_dimensions: number
    base_url: string | null
  }
  vault: {
    path: string
    inbox_path: string
    templates_path: string
    watch: boolean
    debounce_ms: number
  }
  index: {
    chroma_persist_path: string
    collection_name: string
  }
  agents: {
    weekly_summary_cron: string
    reindex_cron: string
  }
  review: {
    queue_threshold: number
    auto_approve_threshold_pct: number
    confidence_weights: Record<string, number>
  }
  server: {
    host: string
    port: number
    dev_mode: boolean
  }
  telemetry: {
    enabled: boolean
    otlp_endpoint: string
    log_level: string
    log_format: string
  }
  ui: Record<string, unknown>
  mcp_key_last4: string | null
}

export interface AIPatch {
  provider?: string
  model?: string
  embed_model?: string
  transcribe_backend?: string
  transcribe_url?: string | null
  transcribe_model?: string
  embed_dimensions?: number
  base_url?: string | null
}

export interface ReviewPatch {
  queue_threshold?: number
  auto_approve_threshold_pct?: number
}

export interface SettingsPatch {
  ai?: AIPatch
  review?: ReviewPatch
}

export interface RotateMcpKeyResponse {
  mcp_key_last4: string
}

export function getSettings(): Promise<SettingsResponse> {
  return apiGet<SettingsResponse>('/api/settings')
}

export function patchSettings(patch: SettingsPatch): Promise<SettingsResponse> {
  return apiPatch<SettingsResponse>('/api/settings', patch)
}

export function rotateMcpKey(): Promise<RotateMcpKeyResponse> {
  return apiPost<RotateMcpKeyResponse>('/api/settings/rotate-mcp-key')
}
