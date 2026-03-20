import { apiPost } from './client'

/** Trigger the weekly summary agent (SSE streaming — returns EventSource URL) */
export function triggerWeeklySummaryUrl(): string {
  return '/api/agents/weekly-summary'
}

/** POST to trigger weekly summary (non-streaming variant — fires and forgets) */
export function triggerWeeklySummary(): Promise<unknown> {
  return apiPost<unknown>('/api/agents/weekly-summary', {})
}

/** POST to trigger a full vault reindex (returns 202 immediately) */
export function triggerReindex(): Promise<unknown> {
  return apiPost<unknown>('/api/agents/reindex', {})
}
