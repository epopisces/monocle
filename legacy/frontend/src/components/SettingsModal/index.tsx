import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import {
  getSettings,
  patchSettings,
  rotateMcpKey,
  type SettingsResponse,
  type SettingsPatch,
} from '../../api/settings'
import { getModelStatus, type ProviderModelsResponse } from '../../api/health'
import { useTheme, type Theme } from '../../hooks/useTheme'
import './SettingsModal.css'


interface Props {
  open: boolean
  onClose: () => void
}

type Status = 'idle' | 'loading' | 'saving' | 'error'

interface State {
  settings: SettingsResponse | null
  status: Status
  error: string | null
  keyRotating: boolean
  lastKeyHint: string | null
}

type Action =
  | { type: 'LOADED'; payload: SettingsResponse }
  | { type: 'LOAD_ERROR'; payload: string }
  | { type: 'SAVING' }
  | { type: 'SAVED'; payload: SettingsResponse }
  | { type: 'SAVE_ERROR'; payload: string }
  | { type: 'KEY_ROTATING' }
  | { type: 'KEY_ROTATED'; payload: string }
  | { type: 'KEY_ERROR'; payload: string }
  | { type: 'RESET' }

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'LOADED': return { ...state, settings: action.payload, status: 'idle', error: null }
    case 'LOAD_ERROR': return { ...state, status: 'error', error: action.payload }
    case 'SAVING': return { ...state, status: 'saving', error: null }
    case 'SAVED': return { ...state, settings: action.payload, status: 'idle', error: null }
    case 'SAVE_ERROR': return { ...state, status: 'error', error: action.payload }
    case 'KEY_ROTATING': return { ...state, keyRotating: true, error: null }
    case 'KEY_ROTATED': return { ...state, keyRotating: false, lastKeyHint: action.payload }
    case 'KEY_ERROR': return { ...state, keyRotating: false, error: action.payload }
    case 'RESET': return INITIAL
    default: return state
  }
}

const INITIAL: State = {
  settings: null,
  status: 'loading',
  error: null,
  keyRotating: false,
  lastKeyHint: null,
}

const TRANSCRIBE_BACKENDS = ['subprocess', 'whisper_cpp', 'native']

/** Well-known noisy routes surfaced as checkboxes in the Tracing Filters panel. */
const KNOWN_FILTERS = [
  { route: '/api/health', label: 'Health checks (/api/health)' },
  { route: '/api/capture-workbench', label: 'Capture workbench polling (/api/capture-workbench)' },
]

function modelStateBadge(available: boolean, loaded: boolean): { cls: string; label: string } {
  if (loaded) return { cls: 'loaded', label: 'loaded' }
  if (available) return { cls: 'available', label: 'available' }
  return { cls: 'unavailable', label: 'not found' }
}

export default function SettingsModal({ open, onClose }: Props) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const overlayRef = useRef<HTMLDivElement>(null)
  const thresholdTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [draftQT, setDraftQT] = useState<number | null>(null)
  const [draftAAT, setDraftAAT] = useState<number | null>(null)
  const [draftHistoryRetention, setDraftHistoryRetention] = useState<string | null>(null)
  const [modelStatus, setModelStatus] = useState<ProviderModelsResponse | null>(null)
  const { theme, setTheme } = useTheme()

  // Load settings when opened; cancel any pending debounce when closed
  useEffect(() => {
    if (!open) {
      if (thresholdTimer.current) {
        clearTimeout(thresholdTimer.current)
        thresholdTimer.current = null
      }
      return
    }
    dispatch({ type: 'RESET' })
    setModelStatus(null)
    getSettings()
      .then(s => dispatch({ type: 'LOADED', payload: s }))
      .catch(e => dispatch({ type: 'LOAD_ERROR', payload: String(e) }))
    getModelStatus()
      .then(ms => setModelStatus(ms))
      .catch(() => setModelStatus(null))
  }, [open])

  // Clear draft values when server data refreshes; cancel debounce timer on unmount
  useEffect(() => {
    if (state.settings) { setDraftQT(null); setDraftAAT(null); setDraftHistoryRetention(null) }
  }, [state.settings])
  useEffect(() => () => { if (thresholdTimer.current) clearTimeout(thresholdTimer.current) }, [])

  // Close on backdrop click
  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }, [onClose])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleChatModelChange = async (key: string) => {
    const patch: SettingsPatch = { ai: { chat_model_key: key } }
    dispatch({ type: 'SAVING' })
    try {
      const s = await patchSettings(patch)
      dispatch({ type: 'SAVED', payload: s })
      setModelStatus(null)
      getModelStatus().then(ms => setModelStatus(ms)).catch(() => setModelStatus(null))
    } catch (e) {
      dispatch({ type: 'SAVE_ERROR', payload: String(e) })
    }
  }

  const handleEmbedModelChange = async (key: string) => {
    const patch: SettingsPatch = { ai: { embed_model_key: key } }
    dispatch({ type: 'SAVING' })
    try {
      const s = await patchSettings(patch)
      dispatch({ type: 'SAVED', payload: s })
    } catch (e) {
      dispatch({ type: 'SAVE_ERROR', payload: String(e) })
    }
  }

  const handleThresholdChange = (field: 'queue_threshold' | 'auto_approve_threshold_pct', value: number) => {
    if (field === 'queue_threshold') setDraftQT(value)
    else setDraftAAT(value)
    if (thresholdTimer.current) clearTimeout(thresholdTimer.current)
    thresholdTimer.current = setTimeout(() => {
      const patch: SettingsPatch = { review: { [field]: value } }
      dispatch({ type: 'SAVING' })
      patchSettings(patch)
        .then(s => dispatch({ type: 'SAVED', payload: s }))
        .catch(e => dispatch({ type: 'SAVE_ERROR', payload: String(e) }))
    }, 400)
  }

  const handleRotateKey = async () => {
    dispatch({ type: 'KEY_ROTATING' })
    try {
      const r = await rotateMcpKey()
      dispatch({ type: 'KEY_ROTATED', payload: r.mcp_key_last4 })
    } catch (e) {
      dispatch({ type: 'KEY_ERROR', payload: String(e) })
    }
  }

  const handleHistoryRetentionBlur = async () => {
    if (!settings || draftHistoryRetention === null) return
    if (draftHistoryRetention.trim() === '') {
      setDraftHistoryRetention(null)
      return
    }

    const parsedRetention = parseInt(draftHistoryRetention, 10)
    if (Number.isNaN(parsedRetention)) {
      setDraftHistoryRetention(null)
      return
    }
    if (parsedRetention === settings.history.retention_versions) {
      setDraftHistoryRetention(null)
      return
    }

    dispatch({ type: 'SAVING' })
    try {
      const saved = await patchSettings({ history: { retention_versions: parsedRetention } })
      dispatch({ type: 'SAVED', payload: saved })
    } catch (e) {
      dispatch({ type: 'SAVE_ERROR', payload: String(e) })
    }
  }

  const handleTraceFilterToggle = async (route: string, checked: boolean) => {
    if (!settings) return
    const current = settings.telemetry.trace_filters ?? []
    const next = checked
      ? [...new Set([...current, route])]
      : current.filter(f => f !== route)
    const patch: SettingsPatch = { telemetry: { trace_filters: next } }
    dispatch({ type: 'SAVING' })
    patchSettings(patch)
      .then(s => dispatch({ type: 'SAVED', payload: s }))
      .catch(e => dispatch({ type: 'SAVE_ERROR', payload: String(e) }))
  }

  if (!open) return null

  const { settings, status, error, keyRotating, lastKeyHint } = state
  const keyHint = lastKeyHint ?? settings?.mcp_key_last4

  return (
    <div
      className="settings-overlay"
      ref={overlayRef}
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
      data-testid="settings-modal"
    >
      <div className="settings-modal">
        <div className="settings-modal__header">
          <h2>Settings</h2>
          <button className="settings-modal__close" onClick={onClose} aria-label="Close settings">✕</button>
        </div>

        {status === 'loading' ? (
          <div className="settings-modal__body settings-modal__loading">Loading settings…</div>
        ) : !settings ? (
          <div data-testid="settings-error" className="settings-modal__body settings-modal__error">{error ?? 'Failed to load settings'}</div>
        ) : (
          <div className="settings-modal__body">
            {error && <div data-testid="settings-error" className="settings-modal__error">{error}</div>}

            {/* AI Models */}
            <section className="settings-section">
              <h3 className="settings-section__title">AI Models</h3>

              <label className="settings-field">
                <span className="settings-field__label">Chat model</span>
                <select
                  value={settings.ai.chat_model_key}
                  onChange={e => handleChatModelChange(e.target.value)}
                  disabled={status === 'saving'}
                  className="settings-select"
                  data-testid="chat-model-select"
                >
                  {settings.ai.models
                    .filter(m => m.role === 'chat')
                    .map(m => (
                      <option key={m.key} value={m.key}>
                        {m.name} ({m.provider})
                      </option>
                    ))}
                </select>
              </label>

              <label className="settings-field">
                <span className="settings-field__label">Embed model</span>
                <select
                  value={settings.ai.embed_model_key}
                  onChange={e => handleEmbedModelChange(e.target.value)}
                  disabled={status === 'saving'}
                  className="settings-select"
                  data-testid="embed-model-select"
                >
                  {settings.ai.models
                    .filter(m => m.role === 'embed')
                    .map(m => (
                      <option key={m.key} value={m.key}>
                        {m.name} ({m.provider})
                      </option>
                    ))}
                </select>
              </label>

              <label className="settings-field">
                <span className="settings-field__label">Transcribe backend</span>
                <select
                  value={settings.ai.transcribe_backend}
                  onChange={e => {
                    const patch: SettingsPatch = { ai: { transcribe_backend: e.target.value } }
                    dispatch({ type: 'SAVING' })
                    patchSettings(patch)
                      .then(s => dispatch({ type: 'SAVED', payload: s }))
                      .catch(err => dispatch({ type: 'SAVE_ERROR', payload: String(err) }))
                  }}
                  disabled={status === 'saving'}
                  className="settings-select"
                >
                  {TRANSCRIBE_BACKENDS.map(b => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </label>

              {/* Model status panel */}
              <div className="model-status-list" data-testid="model-status-panel">
                {modelStatus === null ? (
                  <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                    Checking models…
                  </span>
                ) : !modelStatus.provider_reachable ? (
                  <span className="model-status-unreachable" data-testid="provider-unreachable">
                    <span className="provider-status-dot provider-status-dot--down" />
                    {modelStatus.provider} not reachable
                  </span>
                ) : (
                  <>
                    <div className="provider-status-row">
                      <span className="provider-status-dot provider-status-dot--up" />
                      <span className="provider-status-name">{modelStatus.provider}</span>
                      <span className="provider-status-label">running</span>
                    </div>
                    {modelStatus.models.map(m => {
                      const { cls, label } = modelStateBadge(m.available, m.loaded)
                      return (
                        <div key={m.role} className="model-status-row" data-testid={`model-status-${m.role}`}>
                          <span className={`model-status-dot model-status-dot--${cls}`} />
                          <span className="model-status-name" title={m.name}>{m.name}</span>
                          <span className="model-status-role">{m.role}</span>
                          <span className={`model-status-badge model-status-badge--${cls}`}>{label}</span>
                        </div>
                      )
                    })}
                  </>
                )}
              </div>
            </section>

            {/* Review thresholds */}
            <section className="settings-section">
              <h3 className="settings-section__title">Review Queue</h3>

              <label className="settings-field">
                <span className="settings-field__label">
                  Queue threshold: <strong>{draftQT ?? settings.review.queue_threshold}%</strong>
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={draftQT ?? settings.review.queue_threshold}
                  onChange={e => handleThresholdChange('queue_threshold', parseInt(e.target.value, 10))}
                  disabled={status === 'saving'}
                  className="settings-range"
                  data-testid="queue-threshold-slider"
                />
              </label>

              <label className="settings-field">
                <span className="settings-field__label">
                  Auto-approve threshold: <strong>{draftAAT ?? settings.review.auto_approve_threshold_pct}%</strong>
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={draftAAT ?? settings.review.auto_approve_threshold_pct}
                  onChange={e => handleThresholdChange('auto_approve_threshold_pct', parseInt(e.target.value, 10))}
                  disabled={status === 'saving'}
                  className="settings-range"
                />
              </label>
            </section>

            <section className="settings-section">
              <h3 className="settings-section__title">History</h3>
              <label className="settings-field">
                <span className="settings-field__label">Stored note versions per document</span>
                <input
                  type="number"
                  min={1}
                  max={500}
                  step={1}
                  value={draftHistoryRetention ?? String(settings.history.retention_versions)}
                  onChange={e => setDraftHistoryRetention(e.target.value)}
                  onBlur={handleHistoryRetentionBlur}
                  disabled={status === 'saving'}
                  className="settings-input"
                  data-testid="history-retention-input"
                />
                <span className="settings-field__hint">Older snapshots are pruned automatically when this limit is exceeded.</span>
              </label>
            </section>

            {/* Tracing Filters */}
            <section className="settings-section">
              <h3 className="settings-section__title">Tracing Filters</h3>
              <p className="settings-section__description">
                Routes checked below are suppressed from OTel traces. Uncheck to debug those paths.
              </p>
              {KNOWN_FILTERS.map(({ route, label }) => {
                const active = (settings.telemetry.trace_filters ?? []).includes(route)
                return (
                  <label key={route} className="settings-field settings-field--checkbox" data-testid={`trace-filter-${route.replace(/\//g, '-').replace(/^-/, '')}`}>
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={e => handleTraceFilterToggle(route, e.target.checked)}
                      disabled={status === 'saving'}
                    />
                    <span className="settings-field__label">{label}</span>
                  </label>
                )
              })}
            </section>

            {/* MCP Key */}
            <section className="settings-section">
              <h3 className="settings-section__title">MCP Access</h3>
              <div className="settings-field settings-field--row">
                <span className="settings-field__label">MCP Key</span>
                <span className="settings-key-hint" data-testid="mcp-key-hint">
                  {keyHint ? `••••${keyHint}` : 'None configured'}
                </span>
                <button
                  className="settings-btn"
                  onClick={handleRotateKey}
                  disabled={keyRotating || status === 'saving'}
                  data-testid="rotate-key-btn"
                >
                  {keyRotating ? 'Rotating…' : 'Rotate'}
                </button>
              </div>
            </section>

            {/* Theme */}
            <section className="settings-section">
              <h3 className="settings-section__title">Theme</h3>
              <div className="settings-field settings-field--theme">
                {(['dark', 'light', 'system'] as Theme[]).map(t => (
                  <label key={t} className="settings-theme-option">
                    <input
                      type="radio"
                      name="theme"
                      value={t}
                      checked={theme === t}
                      onChange={() => setTheme(t)}
                      data-testid={`theme-radio-${t}`}
                    />
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </label>
                ))}
              </div>
            </section>

            {/* Vault info (read-only) */}
            <section className="settings-section">
              <h3 className="settings-section__title">Vault</h3>
              <div className="settings-field">
                <span className="settings-field__label">Path</span>
                <span className="settings-value">{settings.vault.path}</span>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
