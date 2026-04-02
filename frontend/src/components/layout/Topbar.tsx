import { useEffect, useState } from 'react'
import { getHealth, type HealthResponse } from '../../api/health'
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

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const h = await getHealth()
        if (!cancelled) {
          setHealth(h)
          setStatus(healthToStatus(h))
        }
      } catch {
        if (!cancelled) setStatus('error')
      }
    }

    poll()
    const id = setInterval(poll, 10_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

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
        {/* Health dot — compact, no label */}
        <span
          className="topbar-health-dot"
          data-testid="health-indicator"
          title={health ? `${health.status} — index: ${health.index_status}` : 'Checking…'}
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

