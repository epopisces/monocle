import { useEffect, useRef, useState } from 'react'
import { getHealth, getModelStatus, type HealthResponse, type ProviderModelsResponse } from '../../api/health'
import { getSettings, patchSettings, type ModelEntry } from '../../api/settings'
import OmniSearch from './OmniSearch'
import './Topbar.css'

interface TopbarProps {
  onMenuToggle: () => void
  onSettingsOpen?: () => void
  onVoiceOpen?: () => void
  onReviewOpen?: () => void
  onFailedOpen?: () => void
  reviewCount?: number
  failedCount?: number
}

type HealthStatus = 'unknown' | 'ready' | 'degraded' | 'error'

function statusColor(s: HealthStatus): string {
  switch (s) {
    case 'ready': return 'var(--success)'
    case 'degraded': return 'var(--warning)'
    case 'error': return 'var(--error)'
    default: return 'var(--text-secondary)'
  }
}

function healthToStatus(h: HealthResponse): HealthStatus {
  if (!h.ai_reachable) return 'degraded'
  if (h.status === 'indexing') return 'degraded'
  if (h.status === 'ready') return 'ready'
  return 'degraded'
}

export default function Topbar({
  onMenuToggle,
  onSettingsOpen,
  onVoiceOpen,
  onReviewOpen,
  onFailedOpen,
  reviewCount = 0,
  failedCount = 0,
}: TopbarProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [status, setStatus] = useState<HealthStatus>('unknown')
  const [modelStatus, setModelStatus] = useState<ProviderModelsResponse | null>(null)

  // Model selector state
  const [activeSelector, setActiveSelector] = useState<'chat' | 'embed' | null>(null)
  const [selectorModels, setSelectorModels] = useState<ModelEntry[]>([])
  const [selectorLoading, setSelectorLoading] = useState(false)
  const [activeChatKey, setActiveChatKey] = useState<string | null>(null)
  const [activeEmbedKey, setActiveEmbedKey] = useState<string | null>(null)
  const selectorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const [h, ms] = await Promise.allSettled([getHealth(), getModelStatus()])
        if (cancelled) return
        if (h.status === 'fulfilled') {
          setHealth(h.value)
          setStatus(healthToStatus(h.value))
        } else {
          setStatus('error')
        }
        if (ms.status === 'fulfilled') {
          setModelStatus(ms.value)
        }
      } catch {
        if (!cancelled) setStatus('error')
      }
    }

    poll()
    const id = setInterval(poll, 15_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    if (!activeSelector) return
    function handleClickOutside(e: MouseEvent) {
      if (selectorRef.current && !selectorRef.current.contains(e.target as Node)) {
        setActiveSelector(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [activeSelector])

  async function openModelSelector(role: 'chat' | 'embed') {
    if (activeSelector === role) {
      setActiveSelector(null)
      return
    }
    setActiveSelector(role)
    setSelectorLoading(true)
    try {
      const settings = await getSettings()
      setSelectorModels(settings.ai.models.filter(m => m.role === role))
      setActiveChatKey(settings.ai.chat_model_key)
      setActiveEmbedKey(settings.ai.embed_model_key)
    } catch {
      setActiveSelector(null)
    } finally {
      setSelectorLoading(false)
    }
  }

  async function handleModelSelect(role: 'chat' | 'embed', key: string) {
    setActiveSelector(null)
    try {
      await patchSettings({
        ai: role === 'chat' ? { chat_model_key: key } : { embed_model_key: key },
      })
      const ms = await getModelStatus()
      setModelStatus(ms)
    } catch {
      // silent; next poll will correct state
    }
  }

  // Build detailed tooltip text for the health indicator
  const chatModel = modelStatus?.models.find(m => m.role === 'chat')
  const embedModel = modelStatus?.models.find(m => m.role === 'embed')
  const modelTooltip = modelStatus
    ? modelStatus.provider_reachable
      ? modelStatus.models
          .map(m => `${m.role}: ${m.name} (${m.loaded ? 'loaded' : m.available ? 'available' : 'not found'})`)
          .join('\n')
      : `${modelStatus.provider}: not reachable`
    : ''
  const healthTitle = [
    health ? `${health.status} — index: ${health.index_status}` : 'Checking…',
    modelTooltip,
  ].filter(Boolean).join('\n')

  return (
    <header className="topbar" data-testid="topbar">
      <div className="topbar-left">
        <button
          className="topbar-menu-btn"
          onClick={onMenuToggle}
          aria-label="Toggle navigation"
        >
          ☰
        </button>
        <span className="topbar-logo">◉ Monocle</span>
      </div>

      <div className="topbar-center">
        <OmniSearch />
      </div>

      <div className="topbar-right">
        {/* Model status badges — clickable to switch active model */}
        {modelStatus?.provider_reachable && modelStatus.models.some(m => m.available) && (
          <div className="topbar-models-status" ref={selectorRef} data-testid="models-status-badges">
            {chatModel?.available && (
              <div className="topbar-model-selector-wrap">
                <button
                  className={`topbar-model-badge topbar-model-badge--clickable ${chatModel.loaded ? 'topbar-model-badge--loaded' : 'topbar-model-badge--cold'}`}
                  onClick={() => openModelSelector('chat')}
                  title={
                    chatModel.loaded
                      ? `${chatModel.name} is loaded and ready\nClick to change chat model`
                      : `${chatModel.name} is not loaded — first chat response will be slower\nClick to change chat model`
                  }
                  data-testid={`model-badge-chat-${chatModel.loaded ? 'loaded' : 'cold'}`}
                  aria-haspopup="listbox"
                  aria-expanded={activeSelector === 'chat'}
                >
                  {chatModel.loaded ? '✓' : '⏳'} chat: {chatModel.name}
                </button>
                {activeSelector === 'chat' && (
                  <div className="topbar-model-dropdown" role="listbox" aria-label="Select chat model">
                    {selectorLoading ? (
                      <div className="topbar-model-dropdown__status">Loading…</div>
                    ) : selectorModels.length === 0 ? (
                      <div className="topbar-model-dropdown__status">No models configured</div>
                    ) : (
                      selectorModels.map(m => (
                        <button
                          key={m.key}
                          className={`topbar-model-dropdown__item${m.key === activeChatKey ? ' topbar-model-dropdown__item--active' : ''}`}
                          onClick={() => handleModelSelect('chat', m.key)}
                          role="option"
                          aria-selected={m.key === activeChatKey}
                        >
                          <span className="topbar-model-dropdown__name">{m.name}</span>
                          <span className="topbar-model-dropdown__provider">{m.provider}</span>
                          {m.key === activeChatKey && <span className="topbar-model-dropdown__check">✓</span>}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
            {embedModel?.available && (
              <div className="topbar-model-selector-wrap">
                <button
                  className={`topbar-model-badge topbar-model-badge--clickable ${embedModel.loaded ? 'topbar-model-badge--loaded' : 'topbar-model-badge--cold'}`}
                  onClick={() => openModelSelector('embed')}
                  title={
                    embedModel.loaded
                      ? `${embedModel.name} is loaded and ready\nClick to change embed model`
                      : `${embedModel.name} is not loaded — search/embedding operations will be slower\nClick to change embed model`
                  }
                  data-testid={`model-badge-embed-${embedModel.loaded ? 'loaded' : 'cold'}`}
                  aria-haspopup="listbox"
                  aria-expanded={activeSelector === 'embed'}
                >
                  {embedModel.loaded ? '✓' : '⏳'} embed: {embedModel.name}
                </button>
                {activeSelector === 'embed' && (
                  <div className="topbar-model-dropdown" role="listbox" aria-label="Select embed model">
                    {selectorLoading ? (
                      <div className="topbar-model-dropdown__status">Loading…</div>
                    ) : selectorModels.length === 0 ? (
                      <div className="topbar-model-dropdown__status">No models configured</div>
                    ) : (
                      selectorModels.map(m => (
                        <button
                          key={m.key}
                          className={`topbar-model-dropdown__item${m.key === activeEmbedKey ? ' topbar-model-dropdown__item--active' : ''}`}
                          onClick={() => handleModelSelect('embed', m.key)}
                          role="option"
                          aria-selected={m.key === activeEmbedKey}
                        >
                          <span className="topbar-model-dropdown__name">{m.name}</span>
                          <span className="topbar-model-dropdown__provider">{m.provider}</span>
                          {m.key === activeEmbedKey && <span className="topbar-model-dropdown__check">✓</span>}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Health dot — compact, tooltip shows provider + model detail */}
        <span
          className="topbar-health-dot"
          data-testid="health-indicator"
          title={healthTitle}
        >
          <span
            className="health-dot"
            style={{ backgroundColor: statusColor(status) }}
          />
        </span>

        {/* Voice capture button */}
        <button
          className="topbar-menu-btn"
          onClick={onVoiceOpen}
          aria-label="Voice capture"
          title="Voice capture"
          data-testid="voice-capture-btn"
        >
          🎤
        </button>

        {/* Review queue badge button — always visible when count > 0 */}
        {reviewCount > 0 && (
          <button
            className="topbar-menu-btn topbar-badge-btn"
            onClick={onReviewOpen}
            aria-label={`Review queue: ${reviewCount} pending`}
            title={`${reviewCount} notes pending review`}
            data-testid="review-queue-btn"
          >
            🔔
            <span className="topbar-badge" data-testid="review-badge">{reviewCount}</span>
          </button>
        )}

        {/* Failed captures warning button — only when failures exist */}
        {failedCount > 0 && (
          <button
            className="topbar-menu-btn topbar-badge-btn topbar-badge-btn--warning"
            onClick={onFailedOpen}
            aria-label={`Failed captures: ${failedCount}`}
            title={`${failedCount} failed capture(s)`}
            data-testid="failed-captures-btn"
          >
            ⚠
            <span className="topbar-badge topbar-badge--warning" data-testid="failed-badge">
              {failedCount}
            </span>
          </button>
        )}

        <button
          className="topbar-menu-btn"
          onClick={onSettingsOpen}
          aria-label="Open settings"
          data-testid="settings-btn"
        >
          ⚙
        </button>
      </div>
    </header>
  )
}

