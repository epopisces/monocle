import { useEffect, useState } from 'react'
import { getHealth, getModelStatus, type HealthResponse, type ProviderModelsResponse } from '../../api/health'
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

  // Build detailed tooltip text for the health indicator
  const chatModel = modelStatus?.models.find(m => m.role === 'chat')
  const embedModel = modelStatus?.models.find(m => m.role === 'embed')
  const chatNotLoaded = modelStatus?.provider_reachable && chatModel && !chatModel.loaded
  const embedNotLoaded = modelStatus?.provider_reachable && embedModel && !embedModel.loaded
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
        {/* Model status badges — show when models are available (green if loaded, amber if not) */}
        {modelStatus?.provider_reachable && modelStatus.models.some(m => m.available) && (
          <div className="topbar-models-status" data-testid="models-status-badges">
            {chatModel?.available && (
              <span
                className={`topbar-model-badge ${chatModel.loaded ? 'topbar-model-badge--loaded' : 'topbar-model-badge--cold'}`}
                title={
                  chatModel.loaded
                    ? `${chatModel.name} is loaded and ready`
                    : `${chatModel.name} is not loaded — first chat response will be slower while the model initialises`
                }
                data-testid={`model-badge-chat-${chatModel.loaded ? 'loaded' : 'cold'}`}
              >
                {chatModel.loaded ? '✓' : '⏳'} chat
              </span>
            )}
            {embedModel?.available && (
              <span
                className={`topbar-model-badge ${embedModel.loaded ? 'topbar-model-badge--loaded' : 'topbar-model-badge--cold'}`}
                title={
                  embedModel.loaded
                    ? `${embedModel.name} is loaded and ready`
                    : `${embedModel.name} is not loaded — search/embedding operations will be slower on first use`
                }
                data-testid={`model-badge-embed-${embedModel.loaded ? 'loaded' : 'cold'}`}
              >
                {embedModel.loaded ? '✓' : '⏳'} embed
              </span>
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

