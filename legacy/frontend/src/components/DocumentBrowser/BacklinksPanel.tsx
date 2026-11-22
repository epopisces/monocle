import { useEffect, useState } from 'react'
import { getNoteBacklinks, type BacklinkRef } from '../../api/notes'
import './BacklinksPanel.css'

interface BacklinksPanelProps {
  path: string
  onNavigate: (sourcePath: string) => void
}

export default function BacklinksPanel({ path, onNavigate }: BacklinksPanelProps) {
  const [backlinks, setBacklinks] = useState<BacklinkRef[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!path) return
    let cancelled = false
    setLoading(true)
    setError(null)
    getNoteBacklinks(path)
      .then(data => {
        if (!cancelled) setBacklinks(data)
      })
      .catch(err => {
        if (!cancelled) setError(String(err?.message ?? 'Failed to load backlinks'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [path])

  return (
    <aside className="backlinks-panel" data-testid="backlinks-panel">
      <h3 className="backlinks-panel__heading">Backlinks</h3>
      {loading && <p className="backlinks-panel__loading">Loading…</p>}
      {error && <p className="backlinks-panel__error">{error}</p>}
      {!loading && !error && backlinks.length === 0 && (
        <p className="backlinks-panel__empty">No incoming links</p>
      )}
      {!loading && backlinks.length > 0 && (
        <ul className="backlinks-panel__list" data-testid="backlinks-list">
          {backlinks.map((bl) => (
            <li key={`${bl.source}|${bl.relation || ''}`} className="backlinks-panel__item">
              {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
              <div
                className="backlinks-panel__link"
                onDoubleClick={() => onNavigate(bl.source)}
                title={`Double-click to navigate to ${bl.source}`}
                data-testid="backlink-item"
              >
                <span className="backlinks-panel__source">{bl.source}</span>
                {bl.relation && (
                  <span className="backlinks-panel__relation">— {bl.relation}</span>
                )}
                {bl.context && (
                  <p className="backlinks-panel__context">{bl.context}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
