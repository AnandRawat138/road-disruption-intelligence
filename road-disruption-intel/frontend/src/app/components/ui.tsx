import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Info, X, XCircle } from 'lucide-react'
import { api, fmtAgo } from '../api'
import { CATEGORY_META, CLASS_STATUS_LABEL, PRECISION_LABEL, REVIEW_LABEL, SEVERITY_META, STATUS_TONE } from '../meta'

export function Card({ title, actions, children, className = '', bodyClass = 'card-body' }: {
  title?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string; bodyClass?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && <div className="card-head">{typeof title === 'string' ? <h2>{title}</h2> : title}{actions}</div>}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

export function Tip({ text }: { text: string }) {
  return (
    <span className="tip" tabIndex={0} aria-label={text}>
      <Info size={13} aria-hidden />
      <span className="tip-text" role="tooltip">{text}</span>
    </span>
  )
}

export function Stat({ label, value, foot, tip, onClick, tone }: {
  label: string; value: React.ReactNode; foot?: React.ReactNode; tip?: string; onClick?: () => void; tone?: string
}) {
  const content = (
    <>
      <div className="label">{label}{tip && <Tip text={tip} />}</div>
      <div className="value" style={tone ? { color: tone } : undefined}>{value}</div>
      {foot && <div className="foot">{foot}</div>}
    </>
  )
  return onClick
    ? <button type="button" className="card stat link" onClick={onClick} style={{ textAlign: 'left', font: 'inherit' }}>{content}</button>
    : <div className="card stat">{content}</div>
}

export function Badge({ tone = 'neutral', children, title }: { tone?: string; children: React.ReactNode; title?: string }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>
}

export function CategoryBadge({ code }: { code?: string | null }) {
  if (!code) return <span className="muted">—</span>
  const m = CATEGORY_META[code] || CATEGORY_META.UNKNOWN
  return (
    <span className="badge neutral">
      <span aria-hidden className="mono" style={{ fontSize: 10, color: 'var(--text-3)' }}>{m.glyph}</span>{m.label}
    </span>
  )
}

export function Severity({ value }: { value?: string | null }) {
  const m = SEVERITY_META[value || 'UNKNOWN'] || SEVERITY_META.UNKNOWN
  return (
    <span className="sev" style={{ color: m.color }} title={`Severity: ${m.label}`}>
      <span className="sev-bars" aria-hidden>
        {[1, 2, 3, 4].map(i => <i key={i} className={i <= m.level ? 'on' : ''} style={{ height: 4 + i * 2.5 }} />)}
      </span>
      {m.label}
    </span>
  )
}

export function StatusBadge({ status, stale }: { status?: string | null; stale?: boolean }) {
  if (!status) return <span className="muted">—</span>
  return (
    <span className="row" style={{ gap: 4 }}>
      <Badge tone={STATUS_TONE[status] || 'neutral'}>{status.charAt(0) + status.slice(1).toLowerCase()}</Badge>
      {stale && <Badge tone="warn" title="No new report within the staleness window – not verified as current">Stale</Badge>}
    </span>
  )
}

export function ClassBadge({ status }: { status?: string | null }) {
  const tone = status === 'CLASSIFIED' ? 'ok' : status === 'FAILED' ? 'danger' : status === 'PROCESSING' || status === 'QUEUED' ? 'blue' : 'neutral'
  return <Badge tone={tone}>{CLASS_STATUS_LABEL[status || ''] || status || '—'}</Badge>
}

export function ReviewBadge({ status }: { status?: string | null }) {
  const tone = status === 'APPROVED' ? 'ok' : status === 'REJECTED' ? 'danger' : status === 'PENDING_REVIEW' ? 'warn' : 'neutral'
  return <Badge tone={tone}>{REVIEW_LABEL[status || ''] || status || '—'}</Badge>
}

export function PrecisionBadge({ precision }: { precision?: string | null }) {
  if (!precision) return <Badge tone="neutral" title="No usable location">Not mapped</Badge>
  return <Badge tone={precision === 'MANUAL' ? 'ok' : 'neutral'} title="Coordinates are approximate unless operator-placed">{PRECISION_LABEL[precision] || precision}</Badge>
}

export function Notice({ kind = 'info', children }: { kind?: 'info' | 'warn' | 'error' | 'ok'; children: React.ReactNode }) {
  const Icon = kind === 'error' ? XCircle : kind === 'warn' ? AlertTriangle : kind === 'ok' ? CheckCircle2 : Info
  return <div className={`notice ${kind}`} role={kind === 'error' ? 'alert' : 'status'}><Icon size={16} aria-hidden /><div>{children}</div></div>
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="loading-block" role="status"><span className="spinner" aria-hidden />{label}</div>
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return <div className="empty"><h3>{title}</h3>{children && <div className="small" style={{ marginTop: 6 }}>{children}</div>}</div>
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Notice kind="error">
      <div className="row"><span>{error}</span>{onRetry && <button className="btn sm" onClick={onRetry}>Retry</button>}</div>
    </Notice>
  )
}

export function Pagination({ page, pages, total, onPage, pageSize, onPageSize }: {
  page: number; pages: number; total: number; onPage: (p: number) => void; pageSize?: number; onPageSize?: (n: number) => void
}) {
  return (
    <div className="pagination">
      <span>{total.toLocaleString('en-IN')} result{total === 1 ? '' : 's'}</span>
      {onPageSize && (
        <label className="row" style={{ gap: 4 }}>Rows
          <select className="input" value={pageSize} onChange={e => onPageSize(Number(e.target.value))} aria-label="Rows per page">
            {[25, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      )}
      <span className="right">Page {pages ? page : 0} of {pages}</span>
      <button className="btn sm" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page"><ChevronLeft size={14} /></button>
      <button className="btn sm" onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Next page"><ChevronRight size={14} /></button>
    </div>
  )
}

export function MultiSelect({ label, options, value, onChange }: {
  label: string; options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter(x => x !== v) : [...value, v])
  return (
    <div className="chip-select" ref={ref} onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}>
      <button type="button" className="btn chip-btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span>{label}{value.length ? `: ${value.length}` : ''}</span><ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className="menu" role="listbox" aria-label={label} aria-multiselectable>
          {options.map(o => (
            <label key={o.value}><input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} />{o.label}</label>
          ))}
          {value.length > 0 && <button className="btn sm ghost" style={{ marginTop: 4 }} onClick={() => onChange([])}>Clear</button>}
        </div>
      )}
    </div>
  )
}

export function Drawer({ title, onClose, children, actions }: { title: React.ReactNode; onClose: () => void; children: React.ReactNode; actions?: React.ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Details'}>
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>{title}</div>
          {actions}
          <button className="btn ghost icon-btn" onClick={onClose} aria-label="Close" autoFocus><X size={18} /></button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  )
}

export function Confirm({ title, message, confirmLabel = 'Confirm', danger, onConfirm, onCancel, busy }: {
  title: string; message: React.ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void; busy?: boolean
}) {
  return (
    <>
      <div className="overlay top" onClick={onCancel} />
      <div className="modal" role="alertdialog" aria-modal="true" aria-label={title}>
        <div className="modal-body"><h2 style={{ marginBottom: 8 }}>{title}</h2><div className="muted">{message}</div></div>
        <div className="modal-foot">
          <button className="btn" onClick={onCancel} autoFocus>Cancel</button>
          <button className={`btn ${danger ? 'danger solid' : 'primary'}`} onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- toasts
type Toast = { id: number; kind: 'ok' | 'error' | 'info'; text: string }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, kind, text }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === 'error' ? 8000 : 4500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap" aria-live="polite">
        {toasts.map(t => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

// ---------------------------------------------------------------- job progress
export interface Job { id: string; job_type: string; status: string; total: number; processed: number; succeeded: number; failed: number; message?: string; created_at?: string; finished_at?: string }

export function JobProgress({ jobId, onDone, compact }: { jobId: string; onDone?: (job: Job) => void; compact?: boolean }) {
  const [job, setJob] = useState<Job | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const doneRef = useRef(false)
  useEffect(() => {
    let alive = true
    doneRef.current = false
    const poll = async () => {
      try {
        const j = await api<Job>(`/api/jobs/${jobId}`)
        if (!alive) return
        setJob(j)
        if (!['QUEUED', 'RUNNING'].includes(j.status)) {
          if (!doneRef.current) { doneRef.current = true; onDone?.(j) }
          return
        }
      } catch (e: any) { if (alive) setErr(e.message) }
      if (alive) setTimeout(poll, 1500)
    }
    poll()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])
  if (err) return <Notice kind="error">{err}</Notice>
  if (!job) return <div className="row small muted"><span className="spinner" /> Starting…</div>
  const pct = job.total ? Math.min(100, Math.round((job.processed / job.total) * 100)) : (job.status === 'RUNNING' ? 5 : 100)
  const running = ['QUEUED', 'RUNNING'].includes(job.status)
  const tone = job.status === 'COMPLETED' ? 'ok' : job.status === 'FAILED' || job.status === 'INTERRUPTED' ? 'danger' : running ? 'blue' : 'neutral'
  const cancel = async () => { try { await api(`/api/jobs/${job.id}/cancel`, { method: 'POST' }) } catch (e: any) { setErr(e.message) } }
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row small">
        <Badge tone={tone}>{job.status}</Badge>
        {!compact && <span className="muted">{job.job_type}</span>}
        <span className="clip" style={{ flex: 1, minWidth: 0 }}>{job.message}</span>
        {running && <button className="btn sm" onClick={cancel}>Cancel</button>}
      </div>
      {running && <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${pct}%` }} /></div>}
    </div>
  )
}

export function Ago({ iso }: { iso?: string | null }) {
  return <span title={iso || ''}>{fmtAgo(iso)}</span>
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(t => <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}>{t.label}</button>)}
    </div>
  )
}
