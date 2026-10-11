import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Play, Plug, Save } from 'lucide-react'
import { api, fmtDate, useApi } from '../api'
import { Ago, Badge, Card, ErrorBox, JobProgress, Loading, Notice, useToast } from '../components/ui'

function statusTone(s?: string | null) {
  return s === 'OK' ? 'ok' : s === 'PARTIAL' ? 'warn' : s ? 'danger' : 'neutral'
}

function listToText(v: any) { return Array.isArray(v) ? v.join('\n') : (v ?? '') }

function SourceCard({ src, onChanged }: { src: any; onChanged: () => void }) {
  const toast = useToast()
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState<any>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [test, setTest] = useState<any>(null)
  const [testing, setTesting] = useState(false)
  const runs = useApi<any>(edit ? `/api/sources/${src.id}/runs?page_size=8` : null)

  const start = () => {
    setForm({
      enabled: src.enabled, poll_interval_minutes: src.poll_interval_minutes, max_records: src.max_records,
      timeout_seconds: src.timeout_seconds, max_retries: src.max_retries,
      config: Object.fromEntries(Object.entries(src.config).map(([k, v]) => [k, Array.isArray(v) ? listToText(v) : v])),
    })
    setEdit(true)
  }
  const save = async () => {
    const cfg: any = {}
    Object.entries(form.config).forEach(([k, v]) => {
      const orig = src.config[k]
      cfg[k] = Array.isArray(orig) ? String(v).split('\n').map(x => x.trim()).filter(Boolean)
        : typeof orig === 'number' ? Number(v) : typeof orig === 'boolean' ? !!v : v
    })
    try {
      await api(`/api/sources/${src.id}`, { method: 'PATCH', body: { ...form, poll_interval_minutes: Number(form.poll_interval_minutes),
        max_records: Number(form.max_records), timeout_seconds: Number(form.timeout_seconds), max_retries: Number(form.max_retries), config: cfg } })
      toast('ok', 'Source saved'); setEdit(false); onChanged()
    } catch (e: any) { toast('error', e.message) }
  }
  const toggle = async () => {
    try { await api(`/api/sources/${src.id}`, { method: 'PATCH', body: { enabled: !src.enabled } }); onChanged() } catch (e: any) { toast('error', e.message) }
  }
  const fetchNow = async () => {
    try { const r = await api<any>(`/api/sources/${src.id}/fetch`, { method: 'POST' }); setJobId(r.job_id) } catch (e: any) { toast('error', e.message) }
  }
  const runTest = async () => {
    setTesting(true); setTest(null)
    try { setTest(await api(`/api/sources/${src.id}/test`, { method: 'POST' })) } catch (e: any) { setTest({ ok: false, message: e.message }) }
    finally { setTesting(false) }
  }
  const notConfigured = src.configuration_status !== 'CONFIGURED'
  return (
    <Card title={<div style={{ flex: 1 }}><h2>{src.name}</h2><div className="small muted">{src.connector_name} · {src.description}</div></div>}
          actions={<label className="check"><input type="checkbox" checked={src.enabled} onChange={toggle} />Scheduled polling</label>}>
      <div className="grid grid-4" style={{ gap: 10 }}>
        <div><div className="xs muted">Configuration</div>{notConfigured ? <Badge tone="warn">NOT CONFIGURED</Badge> : <Badge tone="ok">Configured</Badge>}
          <div className="xs muted">{src.configuration_message}</div></div>
        <div><div className="xs muted">Verification</div>
          <Badge tone={src.verification === 'VERIFIED' ? 'ok' : src.verification === 'FAILING' ? 'danger' : 'neutral'}>{src.verification}</Badge>
          {src.last_status && <> <Badge tone={statusTone(src.last_status)}>{src.last_status}</Badge></>}</div>
        <div><div className="xs muted">Last success / attempt</div><div className="small"><Ago iso={src.last_success_at} /> / <Ago iso={src.last_attempt_at} /></div></div>
        <div><div className="xs muted">Next scheduled run</div><div className="small">{src.enabled ? (src.next_run_at ? fmtDate(src.next_run_at) : 'within a minute') : 'polling disabled'}</div></div>
        <div><div className="xs muted">Fetched (all runs)</div><strong>{src.total_fetched.toLocaleString('en-IN')}</strong></div>
        <div><div className="xs muted">New articles</div><strong>{src.total_new.toLocaleString('en-IN')}</strong></div>
        <div><div className="xs muted">Duplicates</div><strong>{src.total_duplicates.toLocaleString('en-IN')}</strong></div>
        <div><div className="xs muted">Likely relevant (pre-filter)</div><strong>{src.total_relevant.toLocaleString('en-IN')}</strong></div>
      </div>
      {src.last_error && <div style={{ marginTop: 10 }}><Notice kind={src.last_status === 'PARTIAL' ? 'warn' : 'error'}><strong>Last error:</strong> {src.last_error}</Notice></div>}
      <div className="small muted" style={{ marginTop: 10 }}>{src.access_notes}</div>
      {src.required_secrets.length > 0 && <div className="small" style={{ marginTop: 4 }}>Credentials: {src.required_secrets.map((x: string) => <code key={x} style={{ marginRight: 6 }}>{x}</code>)}
        – set them under <Link to="/system">Settings &amp; health → API keys</Link>.</div>}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn primary" onClick={fetchNow} disabled={!!jobId || notConfigured}><Play size={14} />Fetch now</button>
        <button className="btn" onClick={runTest} disabled={testing || notConfigured}><Plug size={14} />{testing ? 'Testing…' : 'Connection test'}</button>
        <button className="btn" onClick={() => (edit ? setEdit(false) : start())}>{edit ? 'Close settings' : 'Settings & history'}</button>
      </div>
      {jobId && <div style={{ marginTop: 10 }}><JobProgress jobId={jobId} onDone={j => { setJobId(null); toast(j.status === 'COMPLETED' ? 'ok' : 'error', j.message || j.status); onChanged() }} /></div>}
      {test && (
        <div style={{ marginTop: 10 }}>
          <Notice kind={test.ok ? 'ok' : 'error'}>{test.message}{test.sample?.length > 0 && <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{test.sample.map((x: any, i: number) => <li key={i}>{x.title} <span className="muted">({x.source || 'unknown'})</span></li>)}</ul>}
            {test.ok && <div className="xs" style={{ marginTop: 4 }}>Test items are not stored.</div>}</Notice>
        </div>
      )}
      {edit && form && (
        <div className="stack" style={{ marginTop: 14 }}>
          <div className="divider" />
          <div className="form-grid">
            <label className="field">Polling interval (minutes)<input className="input" type="number" min={30} value={form.poll_interval_minutes} onChange={e => setForm({ ...form, poll_interval_minutes: e.target.value })} /><span className="hint">Minimum 30 min to respect provider limits.</span></label>
            <label className="field">Max records per run<input className="input" type="number" min={1} max={1000} value={form.max_records} onChange={e => setForm({ ...form, max_records: e.target.value })} /></label>
            <label className="field">Request timeout (s)<input className="input" type="number" min={3} max={120} value={form.timeout_seconds} onChange={e => setForm({ ...form, timeout_seconds: e.target.value })} /></label>
            <label className="field">Retries (exponential backoff)<input className="input" type="number" min={0} max={6} value={form.max_retries} onChange={e => setForm({ ...form, max_retries: e.target.value })} /></label>
          </div>
          <div className="form-grid">
            {Object.entries(src.config).map(([k, v]) => (
              <label key={k} className="field" style={Array.isArray(v) ? { gridColumn: 'span 2' } : undefined}>{k.replace(/_/g, ' ')}
                {Array.isArray(v) ? <textarea className="input" rows={6} value={form.config[k]} onChange={e => setForm({ ...form, config: { ...form.config, [k]: e.target.value } })} />
                  : typeof v === 'boolean' ? <input type="checkbox" checked={!!form.config[k]} onChange={e => setForm({ ...form, config: { ...form.config, [k]: e.target.checked } })} />
                  : <input className="input" value={form.config[k]} onChange={e => setForm({ ...form, config: { ...form.config, [k]: e.target.value } })} />}
                {Array.isArray(v) && <span className="hint">One per line.</span>}
              </label>
            ))}
          </div>
          <div><button className="btn primary" onClick={save}><Save size={14} />Save source settings</button></div>
          <div className="section-title">Recent runs</div>
          {runs.data ? (
            <table className="table">
              <thead><tr><th>Started</th><th>Trigger</th><th>Status</th><th>Fetched</th><th>New</th><th>Dup</th><th>Error</th></tr></thead>
              <tbody>{runs.data.items.map((r: any) => (
                <tr key={r.id}><td className="small nowrap">{fmtDate(r.started_at)}</td><td>{r.trigger}</td><td><Badge tone={statusTone(r.status)}>{r.status}</Badge></td>
                  <td>{r.fetched}</td><td>{r.new}</td><td>{r.duplicates}</td><td className="small">{r.error?.slice(0, 160)}</td></tr>
              ))}{!runs.data.items.length && <tr><td colSpan={7} className="muted">No runs yet.</td></tr>}</tbody>
            </table>
          ) : <Loading />}
        </div>
      )}
    </Card>
  )
}

export default function Sources() {
  const { data, error, loading, reload } = useApi<any>('/api/sources', 20000)
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />
  if (loading && !data) return <Loading />
  const sch = data.scheduler
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Sources & acquisition</h1>
          <div className="sub">Each source is fetched independently – one failing connector never stops the others. A source is marked VERIFIED only after a real successful fetch on this machine.</div></div>
      </div>
      <Notice kind={sch.running ? 'info' : 'warn'}>
        Scheduler: {sch.running ? <>running (last check <Ago iso={sch.last_tick} />). Enabled sources are polled at their interval.</> : <>not running – {sch.reason || 'unknown reason'}. Use “Fetch now” for manual retrieval.</>}
        {' '}No source provides complete coverage of all news; results are samples of what each provider indexes.
      </Notice>
      {data.sources.map((s: any) => <SourceCard key={s.id} src={s} onChanged={reload} />)}
    </div>
  )
}
