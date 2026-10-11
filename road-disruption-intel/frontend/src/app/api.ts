// Thin API client. All data comes from the backend; nothing is mocked in the browser.
import { useCallback, useEffect, useRef, useState } from 'react'

const TOKEN_KEY = 'rdi.accessToken'
const OPERATOR_KEY = 'rdi.operator'

export function getToken(): string {
  try { return sessionStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}
export function setToken(t: string) {
  try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
}
export function getOperator(): string {
  try { return localStorage.getItem(OPERATOR_KEY) || '' } catch { return '' }
}
export function setOperator(name: string) {
  try { localStorage.setItem(OPERATOR_KEY, name) } catch { /* ignore */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function headers(json: boolean): Record<string, string> {
  const h: Record<string, string> = {}
  if (json) h['Content-Type'] = 'application/json'
  const t = getToken()
  if (t) h['Authorization'] = `Bearer ${t}`
  const op = getOperator()
  if (op) h['X-Operator'] = op
  return h
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method || (opts.body !== undefined || opts.form ? 'POST' : 'GET'), headers: headers(!opts.form) }
  if (opts.form) init.body = opts.form
  else if (opts.body !== undefined) init.body = JSON.stringify(opts.body)
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Cannot reach the application server. Is the backend running?')
  }
  const text = await res.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const msg = data?.error?.message || (typeof data?.detail === 'string' ? data.detail : null) || `Request failed (HTTP ${res.status})`
    if (res.status === 401) window.dispatchEvent(new CustomEvent('rdi:auth-required'))
    throw new ApiError(res.status, msg)
  }
  return data as T
}

export function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)) return
    sp.set(k, Array.isArray(v) ? v.join(',') : String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
}

/** Download a file from an API endpoint while sending auth headers. */
export async function download(path: string, fallbackName: string) {
  const res = await fetch(path, { headers: headers(false) })
  if (!res.ok) {
    let msg = `Download failed (HTTP ${res.status})`
    try { const j = await res.json(); msg = j?.error?.message || msg } catch { /* ignore */ }
    throw new ApiError(res.status, msg)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const m = /filename="([^"]+)"/.exec(cd)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = m ? m[1] : fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export interface Loadable<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Fetch `path` whenever it changes; optional polling interval in ms. */
export function useApi<T = any>(path: string | null, pollMs?: number): Loadable<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(!!path)
  const [tick, setTick] = useState(0)
  const seq = useRef(0)
  const reload = useCallback(() => setTick(t => t + 1), [])

  useEffect(() => {
    if (!path) { setLoading(false); return }
    const my = ++seq.current
    setLoading(true)
    api<T>(path)
      .then(d => { if (my === seq.current) { setData(d); setError(null) } })
      .catch(e => { if (my === seq.current) setError(e.message || String(e)) })
      .finally(() => { if (my === seq.current) setLoading(false) })
  }, [path, tick])

  useEffect(() => {
    if (!pollMs || !path) return
    const id = window.setInterval(() => setTick(t => t + 1), pollMs)
    return () => window.clearInterval(id)
  }, [pollMs, path])

  return { data, error, loading, reload }
}

export function fmtDate(iso?: string | null, withTime = true): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-IN', withTime
    ? { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }
    : { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })
}

export function fmtAgo(iso?: string | null): string {
  if (!iso) return 'never'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 0) return 'in ' + fmtDuration(-s)
  return fmtDuration(s) + ' ago'
}

function fmtDuration(s: number): string {
  if (s < 90) return `${Math.round(s)}s`
  if (s < 5400) return `${Math.round(s / 60)} min`
  if (s < 172800) return `${Math.round(s / 3600)} h`
  return `${Math.round(s / 86400)} days`
}

export const fmtNum = (n?: number | null) => (n === null || n === undefined ? '—' : n.toLocaleString('en-IN'))
