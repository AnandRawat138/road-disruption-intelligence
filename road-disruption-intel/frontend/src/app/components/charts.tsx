import { useState } from 'react'

const BAR = '#3b5b8c'

/** Horizontal single-series bar list. Each row is a button when `onSelect` is given (click to filter). */
export function BarList({ data, labelOf, onSelect, max = 12 }: {
  data: { key: string; count: number }[]; labelOf?: (k: string) => string; onSelect?: (k: string) => void; max?: number
}) {
  if (!data?.length) return <div className="chart-empty">No data for the current filters.</div>
  const rows = data.slice(0, max)
  const top = Math.max(...rows.map(r => r.count), 1)
  return (
    <div className="barlist" role="list">
      {rows.map(r => {
        const label = labelOf ? labelOf(r.key) : r.key
        const inner = (
          <>
            <span className="bl-label" title={label}>{label}</span>
            <span className="bl-bar" aria-hidden><span style={{ width: `${Math.max(2, (r.count / top) * 100)}%`, background: BAR }} /></span>
            <span className="bl-val">{r.count.toLocaleString('en-IN')}</span>
          </>
        )
        return onSelect
          ? <button key={r.key} type="button" className="bl-row" role="listitem" onClick={() => onSelect(r.key)}
                    title={`Filter by ${label}`} aria-label={`${label}: ${r.count}. Filter records`}>{inner}</button>
          : <div key={r.key} className="bl-row" role="listitem">{inner}</div>
      })}
    </div>
  )
}

/** Daily column chart for one series with a hover tooltip. */
export function DailyColumns({ data, field, label, color = BAR, height = 120 }: {
  data: { date: string; [k: string]: any }[]; field: string; label: string; color?: string; height?: number
}) {
  const [hover, setHover] = useState<number | null>(null)
  if (!data?.length) return <div className="chart-empty">No dated records in this range.</div>
  const W = 640, H = height, padL = 34, padB = 18, padT = 8
  const max = Math.max(...data.map(d => d[field] || 0), 1)
  const n = data.length
  const slot = (W - padL) / n
  const bw = Math.max(1, Math.min(14, slot - 2))
  const y = (v: number) => padT + (H - padB - padT) * (1 - v / max)
  const ticks = [0, Math.round(max / 2), max]
  const h = hover !== null ? data[hover] : null
  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${label} per day`} onMouseLeave={() => setHover(null)}>
        {ticks.map(t => (
          <g key={t}>
            <line x1={padL} x2={W} y1={y(t)} y2={y(t)} stroke="#e6e9ef" strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 4} fontSize={10} textAnchor="end" fill="#6b7689">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const v = d[field] || 0
          const x = padL + i * slot + (slot - bw) / 2
          const top = y(v)
          const hgt = Math.max(0, H - padB - top)
          return (
            <g key={d.date} onMouseEnter={() => setHover(i)}>
              <rect x={padL + i * slot} y={padT} width={slot} height={H - padB - padT} fill="transparent" />
              {hgt > 0 && <rect x={x} y={top} width={bw} height={hgt} rx={Math.min(2, bw / 2)} fill={color} opacity={hover === null || hover === i ? 1 : 0.55} />}
            </g>
          )
        })}
        <text x={padL} y={H - 4} fontSize={10} fill="#6b7689">{data[0].date}</text>
        <text x={W} y={H - 4} fontSize={10} fill="#6b7689" textAnchor="end">{data[n - 1].date}</text>
      </svg>
      {h && (
        <div style={{ position: 'absolute', top: 0, right: 0, background: '#101828', color: '#fff', fontSize: 12, padding: '4px 8px', borderRadius: 6, pointerEvents: 'none' }}>
          {h.date}: <strong>{(h[field] || 0).toLocaleString('en-IN')}</strong> {label.toLowerCase()}
        </div>
      )}
    </div>
  )
}
