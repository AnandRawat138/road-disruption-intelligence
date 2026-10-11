import React, { createContext, useContext, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Activity, Bell, BarChart3, Bot, FileInput, Gauge, ListChecks, Map as MapIcon, Menu, Newspaper,
  Radio, Settings, type LucideIcon } from 'lucide-react'
import { api, getOperator, getToken, setOperator, setToken, useApi } from './api'
import { Notice, ToastProvider } from './components/ui'
import Overview from './pages/Overview'
import Disruptions from './pages/Disruptions'
import MapPage from './pages/MapPage'
import Records from './pages/Records'
import ReviewQueue from './pages/ReviewQueue'
import Sources from './pages/Sources'
import DataImport from './pages/DataImport'
import Reports from './pages/Reports'
import LLMSettings from './pages/LLMSettings'
import SystemSettings from './pages/SystemSettings'
import AlertsPage from './pages/AlertsPage'

export interface PublicSettings {
  branding: { company_name: string; company_location: string; product_name: string; product_short_name: string; logo_url: string; support_email: string; website: string }
  map: { style_url: string; attribution_note: string; default_center: [number, number]; default_zoom: number; focus_regions: Record<string, [number, number, number]> }
  version: string
  categories: { code: string; label: string }[]
  auth_required: boolean
}

const SettingsCtx = createContext<{ s: PublicSettings; reload: () => void } | null>(null)
export const usePublicSettings = () => useContext(SettingsCtx)!

const NAV: { to: string; label: string; icon: LucideIcon; section?: string }[] = [
  { to: '/', label: 'Overview', icon: Gauge, section: 'Monitor' },
  { to: '/disruptions', label: 'Disruptions', icon: Activity },
  { to: '/map', label: 'Interactive map', icon: MapIcon },
  { to: '/records', label: 'News & records', icon: Newspaper, section: 'Work' },
  { to: '/review', label: 'Classification queue', icon: ListChecks },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/reports', label: 'Analytics & reports', icon: BarChart3 },
  { to: '/sources', label: 'Sources & acquisition', icon: Radio, section: 'Configure' },
  { to: '/import', label: 'Data import', icon: FileInput },
  { to: '/llm', label: 'LLM configuration', icon: Bot },
  { to: '/system', label: 'Settings & health', icon: Settings },
]

function initials(name: string) {
  return name.split(/\s+/).filter(w => /^[A-Za-z]/.test(w)).slice(0, 2).map(w => w[0]).join('').toUpperCase() || 'RD'
}

function Shell({ s }: { s: PublicSettings }) {
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const alerts = useApi<{ unread: number }>('/api/alerts?unread_only=true', 60000)
  const review = useApi<{ by_review_status: Record<string, number> }>('/api/classification/stats', 60000)
  const [op, setOp] = useState(getOperator())
  useEffect(() => setOpen(false), [loc.pathname])
  const current = NAV.find(n => (n.to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(n.to)))
  const pending = review.data?.by_review_status?.PENDING_REVIEW || 0
  const unread = alerts.data?.unread || 0
  const b = s.branding
  return (
    <div className="shell">
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
        <div className="brand">
          <div className="brand-mark">
            <div className="logo-box" aria-hidden>{b.logo_url ? <img src={b.logo_url} alt="" /> : initials(b.company_name)}</div>
            <div>
              <div className="brand-name">{b.product_name}</div>
              <div className="brand-company">{b.company_name}</div>
            </div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map(n => (
            <React.Fragment key={n.to}>
              {n.section && <div className="nav-section">{n.section}</div>}
              <NavLink to={n.to} end={n.to === '/'}>
                <n.icon size={16} />{n.label}
                {n.to === '/review' && pending > 0 && <span className="count" aria-label={`${pending} awaiting review`}>{pending}</span>}
                {n.to === '/alerts' && unread > 0 && <span className="count" aria-label={`${unread} unread`}>{unread}</span>}
              </NavLink>
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-foot">
          {b.product_short_name} v{s.version}<br />© {new Date().getFullYear()} {b.company_name}<br />{b.company_location}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="btn ghost icon-btn menu-toggle" onClick={() => setOpen(o => !o)} aria-label="Toggle navigation"><Menu size={18} /></button>
          <span className="title">{current?.label || ''}</span>
          <span className="spacer" />
          <NavLink to="/alerts" className="btn ghost icon-btn" aria-label={`Alerts (${unread} unread)`} title="Alerts">
            <Bell size={17} />{unread > 0 && <span className="badge danger" style={{ marginLeft: 2 }}>{unread}</span>}
          </NavLink>
          <label className="row small muted" title="Your name is recorded in the audit trail for changes you make. It is not a login.">
            <span className="op-label">Operator</span>
            <input className="input" style={{ width: 140 }} value={op} placeholder="Your name"
                   onChange={e => { setOp(e.target.value); setOperator(e.target.value) }} aria-label="Operator name for audit trail" />
          </label>
        </header>
        <main className={`content ${loc.pathname.startsWith('/map') ? 'flush' : ''}`} id="main">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/disruptions" element={<Disruptions />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/records" element={<Records />} />
            <Route path="/review" element={<ReviewQueue />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/import" element={<DataImport />} />
            <Route path="/llm" element={<LLMSettings />} />
            <Route path="/system" element={<SystemSettings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function Login({ onDone }: { onDone: () => void }) {
  const [t, setT] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setToken(t.trim())
    try { await api('/api/ready'); onDone() } catch (x: any) { setErr(x.message); setToken('') }
  }
  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
      <form className="card" style={{ width: 380, padding: 24 }} onSubmit={submit}>
        <h1 style={{ marginBottom: 6 }}>Sign in</h1>
        <p className="muted small" style={{ marginBottom: 14 }}>This deployment requires the access token configured by your administrator (APP_ACCESS_TOKEN).</p>
        <label className="field">Access token<input className="input" type="password" value={t} onChange={e => setT(e.target.value)} autoFocus required /></label>
        {err && <div style={{ marginTop: 10 }}><Notice kind="error">{err}</Notice></div>}
        <button className="btn primary" style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>Continue</button>
      </form>
    </div>
  )
}

export default function App() {
  const [s, setS] = useState<PublicSettings | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [needAuth, setNeedAuth] = useState(false)
  const load = () => api<PublicSettings>('/api/settings/public').then(d => {
    setS(d)
    document.title = `${d.branding.product_name} – ${d.branding.company_name}`
    if (d.auth_required && !getToken()) setNeedAuth(true)
  }).catch(e => setErr(e.message))
  useEffect(() => {
    load()
    const h = () => setNeedAuth(true)
    window.addEventListener('rdi:auth-required', h)
    return () => window.removeEventListener('rdi:auth-required', h)
  }, [])
  if (err) return <div style={{ padding: 40 }}><Notice kind="error">{err}</Notice></div>
  if (!s) return <div className="loading-block"><span className="spinner" />Loading…</div>
  if (needAuth) return <Login onDone={() => setNeedAuth(false)} />
  return (
    <SettingsCtx.Provider value={{ s, reload: load }}>
      <ToastProvider>
        <BrowserRouter><Shell s={s} /></BrowserRouter>
      </ToastProvider>
    </SettingsCtx.Provider>
  )
}
