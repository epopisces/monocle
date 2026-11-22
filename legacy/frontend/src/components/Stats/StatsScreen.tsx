/**
 * M20 — Stats Screen
 *
 * Renders:
 *  - 4 summary stat cards (total notes, people notes, pending review, failed ingests)
 *  - Horizontal bar chart: Notes by type (Recharts)
 *  - Horizontal bar chart: Notes by domain (Recharts)
 *  - Latency table (p50/p95 per operation, when available)
 *  - Source quality index (star ratings derived from notes_by_type share of total)
 */

import { useEffect, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { getStats, type BrainStats } from '../../api/stats'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import './StatsScreen.css'

// ── Colour palette cycles through accent shades ──────────────────────────────
const CHART_COLORS = [
  '#7c8af7',
  '#3dbf84',
  '#f5a623',
  '#e96b67',
  '#a78bfa',
  '#38bdf8',
  '#fb923c',
  '#34d399',
  '#f472b6',
  '#a3e635',
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function toChartData(record: Record<string, number>): { name: string; value: number }[] {
  return Object.entries(record)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }))
}

function prettyLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

/** Star rating from 0–5 based on how "rich" a type is represented */
function qualityStars(count: number, total: number): number {
  if (total === 0) return 0
  const pct = count / total
  return Math.round(Math.min(pct * 20, 5)) // scale: 5% = 1 star, 25%+ = 5 stars
}

// ── Stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: number | string
  accent?: string
}

function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <div className="stats-card" style={accent ? { borderTopColor: accent } : undefined}>
      <span className="stats-card__value">{value}</span>
      <span className="stats-card__label">{label}</span>
    </div>
  )
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

interface TooltipPayload {
  name: string
  value: number
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: TooltipPayload[]
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="stats-tooltip">
      <span className="stats-tooltip__name">{prettyLabel(payload[0].name)}</span>
      <span className="stats-tooltip__value">{payload[0].value}</span>
    </div>
  )
}

// ── Source quality row ────────────────────────────────────────────────────────

function QualityRow({ name, count, total }: { name: string; count: number; total: number }) {
  const stars = qualityStars(count, total)
  return (
    <div className="stats-quality-row">
      <span className="stats-quality-row__name">{prettyLabel(name)}</span>
      <span className="stats-quality-row__stars" aria-label={`${stars} out of 5 stars`}>
        {'★'.repeat(stars)}{'☆'.repeat(5 - stars)}
      </span>
      <span className="stats-quality-row__count">{count}</span>
    </div>
  )
}

// ── Latency table ─────────────────────────────────────────────────────────────

function LatencyTable({ p50, p95 }: { p50: Record<string, number>; p95: Record<string, number> }) {
  const ops = Object.keys(p50).length > 0 ? Object.keys(p50) : Object.keys(p95)
  if (ops.length === 0) return null
  return (
    <section className="stats-section">
      <h2 className="stats-section__title">Latency (ms)</h2>
      <table className="stats-latency-table">
        <thead>
          <tr>
            <th>Operation</th>
            <th>p50</th>
            <th>p95</th>
          </tr>
        </thead>
        <tbody>
          {ops.map(op => (
            <tr key={op}>
              <td>{prettyLabel(op)}</td>
              <td>{p50[op] != null ? p50[op].toFixed(1) : '—'}</td>
              <td>{p95[op] != null ? p95[op].toFixed(1) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

type LoadState = 'loading' | 'loaded' | 'error'

export default function StatsScreen() {
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [stats, setStats] = useState<BrainStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoadState('loading')
    getStats()
      .then(s => {
        if (!cancelled) {
          setStats(s)
          setLoadState('loaded')
        }
      })
      .catch(e => {
        if (!cancelled) {
          setError(mapErrorToUserMessage(e))
          setLoadState('error')
        }
      })
    return () => { cancelled = true }
  }, [])

  if (loadState === 'loading') {
    return (
      <div className="stats-screen" data-testid="stats-loading">
        <p className="stats-loading">Loading stats…</p>
      </div>
    )
  }

  if (loadState === 'error' || !stats) {
    return (
      <div className="stats-screen" data-testid="stats-error">
        <p className="stats-error" role="alert">{error ?? 'Failed to load stats.'}</p>
      </div>
    )
  }

  const typeData = toChartData(stats.notes_by_type ?? {})
  const domainData = toChartData(stats.notes_by_domain ?? {})
  const personCount = stats.notes_by_type?.['person_note'] ?? 0
  const total = stats.total_notes

  return (
    <div className="stats-screen" data-testid="stats-screen">
      <h1 className="stats-header">Knowledge Base Overview</h1>

      {/* ── Stat cards ── */}
      <div className="stats-cards" data-testid="stats-cards">
        <StatCard label="Total Notes" value={total} accent="var(--accent)" />
        <StatCard label="People Notes" value={personCount} accent="var(--graph-person)" />
        <StatCard label="Pending Review" value={stats.pending_review} accent="var(--review-pending)" />
        <StatCard label="Failed Ingests" value={stats.failed_ingests} accent="var(--error)" />
      </div>

      {/* ── Charts row ── */}
      <div className="stats-charts-row">
        {/* Notes by Type */}
        {typeData.length > 0 && (
          <section className="stats-section stats-section--chart">
            <h2 className="stats-section__title">Notes by Type</h2>
            <ResponsiveContainer width="100%" height={Math.max(120, typeData.length * 32)}>
              <BarChart
                data={typeData}
                layout="vertical"
                margin={{ top: 0, right: 24, bottom: 0, left: 120 }}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={120}
                  tickFormatter={prettyLabel}
                  tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--bg-elevated)' }} />
                <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                  {typeData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </section>
        )}

        {/* Notes by Domain */}
        {domainData.length > 0 && (
          <section className="stats-section stats-section--chart">
            <h2 className="stats-section__title">Notes by Domain</h2>
            <ResponsiveContainer width="100%" height={Math.max(120, domainData.length * 32)}>
              <BarChart
                data={domainData}
                layout="vertical"
                margin={{ top: 0, right: 24, bottom: 0, left: 120 }}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={120}
                  tickFormatter={prettyLabel}
                  tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--bg-elevated)' }} />
                <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                  {domainData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[(i + 3) % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </section>
        )}
      </div>

      {/* ── Source quality index ── */}
      {typeData.length > 0 && (
        <section className="stats-section">
          <h2 className="stats-section__title">
            Source Quality Index{' '}
            <span
              className="stats-info-icon"
              title="Computed from note-type share of total. Higher share = more notes from this source."
              aria-label="Source quality index is computed from note type share of total"
            >ⓘ</span>
          </h2>
          <div className="stats-quality-grid">
            {typeData.map(({ name, value }) => (
              <QualityRow key={name} name={name} count={value} total={total} />
            ))}
          </div>
        </section>
      )}

      {/* ── Latency table ── */}
      <LatencyTable
        p50={stats.latency_p50_ms ?? {}}
        p95={stats.latency_p95_ms ?? {}}
      />

      {/* ── Index info ── */}
      {stats.index && (
        <section className="stats-section">
          <h2 className="stats-section__title">Index</h2>
          <p className="stats-index-info">
            <span>{stats.total_chunks} chunks</span>
            <span className="stats-index-backend">backend: {stats.index.backend}</span>
          </p>
        </section>
      )}
    </div>
  )
}
