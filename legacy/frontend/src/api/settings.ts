import { apiGet, apiPatch, apiPost } from './client'

/** A model entry in the ai.models registry. */
export interface ModelEntry {
  key: string
  name: string
  role: 'chat' | 'embed' | 'stt'
  provider: 'ollama' | 'foundry_local' | 'azure' | 'openai'
  base_url: string | null
}

/** Settings response shape (mirrors SettingsResponse model in Python). */
export interface SettingsResponse {
  ai: {
    chat_model_key: string
    embed_model_key: string
    stt_key: string | null
    embed_dimensions: number | null
    transcribe_backend: string
    transcribe_url: string
    ollama_base_url: string
    foundry_local_base_url: string
    models: ModelEntry[]
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
  history: {
    retention_versions: number
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
    trace_filters: string[]
  }
  ui: {
    chat_session_history_limit: number
    voice_input_backend: 'whisper' | 'web_speech'
  }
  mcp_key_last4: string | null
}

export interface ModelEntryInput {
  key: string
  name?: string
  role?: 'chat' | 'embed' | 'stt'
  provider?: 'ollama' | 'foundry_local' | 'azure' | 'openai'
  base_url?: string | null
}

export interface AIPatch {
  chat_model_key?: string
  embed_model_key?: string
  stt_key?: string | null
  transcribe_backend?: string
  transcribe_url?: string
  ollama_base_url?: string
  models?: ModelEntryInput[]
}

export interface ReviewPatch {
  queue_threshold?: number
  auto_approve_threshold_pct?: number
}

export interface HistoryPatch {
  retention_versions?: number
}

export interface UIPatch {
  voice_input_backend?: 'whisper' | 'web_speech'
}

export interface TelemetryPatch {
  trace_filters?: string[]
}

export interface SettingsPatch {
  ai?: AIPatch
  review?: ReviewPatch
  history?: HistoryPatch
  ui?: UIPatch
  telemetry?: TelemetryPatch
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
