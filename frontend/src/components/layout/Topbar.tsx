import { useEffect, useState } from 'react'
import { getHealth, type HealthResponse } from '../../api/health'
import './Topbar.css'

interface TopbarProps {
  onMenuToggle: () => void
  onSettingsOpen?: () => void
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

export default function Topbar({ onMenuToggle, onSettingsOpen }: TopbarProps) {
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
        <span
          className="topbar-health"
          data-testid="health-indicator"
          title={health ? `${health.status} — index: ${health.index_status}` : 'Checking…'}
        >
          <span
            className="health-dot"
            style={{ backgroundColor: statusColor(status) }}
          />
          <span className="health-label">
            {health ? `Backend: ${health.status}` : 'Connecting…'}
          </span>
        </span>
      </div>

      <div className="topbar-right">
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
