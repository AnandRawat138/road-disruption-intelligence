import { useEffect, useState } from 'react'
import { Database, Save } from 'lucide-react'
import { api, fmtDate, useApi } from '../api'
import { usePublicSettings } from '../App'
import { SEVERITIES } from '../meta'
import { Badge, Card, ErrorBox, Loading, Notice, Pagination, Tabs, useToast } from '../components/ui'

function SettingsForm({ group, fields, title, note }: {
  group: string; title: string; note?: string
  fields: { key: string; label: string; type: 'text' | 'number' | 'bool' | 'select' | 'list'; options?: string[]; hint?: string }[]
}) {
  const toast = useToast()
  const { reload: reloadPublic } = usePublicSettings()
  const { data, error, reload } = useApi<any>(`/api/settings/${group}`)
  const [form, setForm] = useState<any>(null)
  useEffect(() => { if (data) setForm(data) }, [data])
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!form) return <Loading />
  const save = async () => {
    const body: any = {}
    fields.forEach(f => {
      let v = form[f.key]
      if (f.type === 'number') v = Number(v)
      if (f.type === 'list' && typeof v === 'string') v = v.split(',').map((x: string) => x.trim()).filter(Boolean)
      body[f.key] = v
    })
    try { await api(`/api/settings/${group}`, { method: 'PUT', body }); toast('ok', `${title} saved`); reload(); reloadPublic() }
    catch (e: any) { toast('error', e.message) }
  }
  return (
    <Card title={title} actions={<button className="btn primary sm" onClick={save}><Save size={13} />Save</button>}>
      {note && <div className="small muted" style={{ marginBottom: 10 }}>{note}</div>}
      <div className="form-grid">
        {fields.map(f => (
          <label key={f.key} className={f.type === 'bool' ? 'check' : 'field'}>
            {f.type === 'bool' ? <><input type="checkbox" checked={!!form[f.key]} onChange={e => setForm({ ...form, [f.key]: e.target.checked })} />{f.label}</> : <>
              {f.label}
              {f.type === 'select' ? <select className="input" value={form[f.key]} onChange={e => setForm({ ...form, [f.key]: e.target.value })}>{f.options!.map(o => <option key={o}>{o}</option>)}</select>
                : <input className="input" type={f.type === 'number' ? 'number' : 'text'} value={Array.isArray(form[f.key]) ? form[f.key].join(', ') : (form[f.key] ?? '')} onChange={e => setForm({ ...form, [f.key]: e.target.value })} />}
              {f.hint && <span className="hint">{f.hint}</span>}
            </>}
          </label>
        ))}
      </div>
    </Card>
  )
}

function NewsKeys() {
  const toast = useToast()
  const { data, reload } = useApi<any>('/api/secrets')
  const [vals, setVals] = useState<Record<string, string>>({})
  if (!data) return <Loading />
  const save = async (name: string) => {
    try { await api(`/api/secrets/${name}`, { method: 'PUT', body: { value: vals[name] } }); setVals({ ...vals, [name]: '' }); toast('ok', `${name} saved`); reload() }
    catch (e: any) { toast('error', e.message) }
  }
  const remove = async (name: string) => {
    if (!window.confirm(`Remove ${name} from the server?`)) return
    try { await api(`/api/secrets/${name}`, { method: 'DELETE' }); toast('ok', `${name} removed`); reload() } catch (e: any) { toast('error', e.message) }
  }
  return (
    <Card title="API keys">
      <Notice kind="info">Keys are stored on the server in <code>runtime/secrets.json</code> (plain JSON protected by Windows user permissions – not encrypted) or read from environment variables / <code>.env</code>, which take precedence. Keys are never returned to the browser, written to logs or included in exports.</Notice>
      <table className="table" style={{ marginTop: 10 }}>
        <thead><tr><th>Key</th><th>Purpose</th><th>Status</th><th>Set / replace</th></tr></thead>
        <tbody>{data.secrets.map((s: any) => (
          <tr key={s.name}>
            <td className="mono small">{s.name}</td><td className="small">{s.description}</td>
            <td>{s.configured ? <Badge tone="ok">{s.source === 'environment' ? 'environment' : 'stored'}</Badge> : <Badge tone="warn">not set</Badge>}</td>
            <td><div className="row">
              <input className="input" type="password" autoComplete="off" value={vals[s.name] || ''} onChange={e => setVals({ ...vals, [s.name]: e.target.value })} disabled={s.source === 'environment'} aria-label={`${s.name} value`} />
              <button className="btn sm" disabled={!vals[s.name]?.trim()} onClick={() => save(s.name)}>Save</button>
              {s.removable && <button className="btn sm danger" onClick={() => remove(s.name)}>Remove</button>}
            </div></td>
          </tr>
        ))}</tbody>
      </table>
    </Card>
  )
}

function Health() {
  const toast = useToast()
  const info = useApi<any>('/api/system/info')
  const ready = useApi<any>('/api/ready', 15000)
  const [busy, setBusy] = useState(false)
  const backup = async () => {
    setBusy(true)
    try { const r = await api<any>('/api/system/backup', { method: 'POST' }); toast('ok', `Backup created: ${r.file}`); info.reload() } catch (e: any) { toast('error', e.message) } finally { setBusy(false) }
  }
  if (info.error) return <ErrorBox error={info.error} onRetry={info.reload} />
  if (!info.data) return <Loading />
  const d = info.data
  return (
    <div className="stack">
      <Card title="System health">
        <div className="row" style={{ marginBottom: 10 }}>
          {ready.data && Object.entries(ready.data.checks).map(([k, v]: any) => <Badge key={k} tone={v.ok ? 'ok' : 'danger'}>{k.replace(/_/g, ' ')}: {v.ok ? 'OK' : 'problem'}</Badge>)}
        </div>
        <dl className="kv">
          <dt>Version</dt><dd>{d.version} · Python {d.python}</dd>
          <dt>Listening on</dt><dd>{d.bind} {d.auth_enabled ? <Badge tone="ok">access token required</Badge> : <Badge>local only, no login</Badge>}</dd>
          <dt>Database</dt><dd className="mono small">{d.database.path} ({d.database.size_mb} MB)</dd>
          <dt>Historical data</dt><dd className="mono small">{d.historical_data_dir}</dd>
          <dt>Runtime folder</dt><dd className="mono small">{d.runtime_dir}</dd>
          <dt>Scheduler</dt><dd>{d.scheduler.running ? 'running' : `not running (${d.scheduler.reason || 'unknown'})`} · {d.sources_enabled} source(s) enabled</dd>
          <dt>LLM</dt><dd>{d.llm.active_provider} / {d.llm.model} · last test {d.llm.last_test ? (d.llm.last_test.ok ? 'OK' : 'FAILED') + ' ' + fmtDate(d.llm.last_test.tested_at) : 'never'}</dd>
        </dl>
      </Card>
      <div className="grid grid-2">
        <Card title="Requires internet"><ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{d.internet_required_for.map((x: string) => <li key={x}>{x}</li>)}</ul></Card>
        <Card title="Works offline"><ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{d.works_offline.map((x: string) => <li key={x}>{x}</li>)}</ul></Card>
      </div>
      <Card title="Backups" actions={<button className="btn sm" onClick={backup} disabled={busy}><Database size={13} />Back up now</button>}>
        <div className="small muted" style={{ marginBottom: 8 }}>Backups are consistent SQLite copies in <code>runtime/backups</code>. A backup is made automatically before any schema migration. To restore, stop the application and run <code>backend\..\.venv\Scripts\python -m rdi.cli restore &lt;file&gt; --yes</code> (see TROUBLESHOOTING.md).</div>
        <table className="table"><thead><tr><th>File</th><th>Size</th><th>Created</th></tr></thead>
          <tbody>{d.backups.map((b: any) => <tr key={b.name}><td className="mono small">{b.name}</td><td>{b.size_mb} MB</td><td className="small">{fmtDate(b.created)}</td></tr>)}
            {!d.backups.length && <tr><td colSpan={3} className="muted">No backups yet.</td></tr>}</tbody></table>
      </Card>
    </div>
  )
}

function AuditLog() {
  const [page, setPage] = useState(1)
  const { data } = useApi<any>(`/api/audit?page=${page}&page_size=25`)
  if (!data) return <Loading />
  return (
    <Card title="Audit trail" bodyClass="">
      <table className="table"><thead><tr><th>When</th><th>Operator</th><th>Entity</th><th>Action</th><th>Details</th></tr></thead>
        <tbody>{data.items.map((e: any) => (
          <tr key={e.id}><td className="small nowrap">{fmtDate(e.at)}</td><td>{e.actor}</td><td className="small">{e.entity_type} <span className="mono xs">{e.entity_id}</span></td><td>{e.action}</td>
            <td className="mono xs" style={{ maxWidth: 420, overflowWrap: 'anywhere' }}>{JSON.stringify(e.details).slice(0, 300)}</td></tr>
        ))}</tbody></table>
      <Pagination page={page} pages={data.pages} total={data.total} onPage={setPage} />
      <div className="xs muted" style={{ padding: '0 14px 10px' }}>Operator names come from the “Operator” field in the header. They identify who made a change but are not authenticated logins.</div>
    </Card>
  )
}

export default function SystemSettings() {
  const [tab, setTab] = useState('general')
  return (
    <div>
      <div className="page-head"><div><h1>Settings & system health</h1><div className="sub">Branding, workflow rules, API keys, backups and the audit trail.</div></div></div>
      <Tabs tabs={[{ id: 'general', label: 'Branding & workflow' }, { id: 'keys', label: 'API keys' }, { id: 'health', label: 'Health & backups' }, { id: 'audit', label: 'Audit trail' }]} value={tab} onChange={setTab} />
      {tab === 'general' && (
        <div className="stack">
          <SettingsForm group="branding" title="Branding" note="Shown in the header, sidebar, reports and browser title. Optional fields can be left blank; nothing is invented on the client's behalf."
            fields={[{ key: 'company_name', label: 'Company name', type: 'text' }, { key: 'company_location', label: 'Location', type: 'text' },
              { key: 'product_name', label: 'Product name', type: 'text' }, { key: 'product_short_name', label: 'Short name', type: 'text' },
              { key: 'logo_url', label: 'Logo URL (optional)', type: 'text', hint: 'Path or https URL of a logo image. Leave blank for the text logo.' },
              { key: 'support_email', label: 'Support e-mail (optional)', type: 'text' }, { key: 'website', label: 'Website (optional)', type: 'text' }]} />
          <SettingsForm group="classification" title="Classification workflow"
            fields={[{ key: 'auto_classify_new', label: 'Automatically classify newly fetched records', type: 'bool' },
              { key: 'auto_classify_min_prefilter', label: 'Auto-classify only when pre-filter is', type: 'select', options: ['LIKELY_RELEVANT', 'POSSIBLY_RELEVANT'] },
              { key: 'max_input_chars', label: 'Max characters sent per record', type: 'number' }, { key: 'retries', label: 'Retries per record', type: 'number' },
              { key: 'concurrency', label: 'Parallel requests (cloud providers, max 4)', type: 'number' },
              { key: 'review_low_confidence', label: 'Flag low model confidence', type: 'bool' }, { key: 'review_unverified_evidence', label: 'Flag unverified evidence', type: 'bool' },
              { key: 'review_unresolved_location', label: 'Flag unresolved location', type: 'bool' }, { key: 'review_headline_only', label: 'Flag headline-only records', type: 'bool' }]} />
          <SettingsForm group="incidents" title="Incident lifecycle"
            fields={[{ key: 'stale_after_hours', label: 'Treat open incidents as stale after (hours)', type: 'number' },
              { key: 'link_window_hours', label: 'Link related reports within (hours)', type: 'number' },
              { key: 'auto_resolve_on_report', label: 'Mark resolved when a report says the road reopened', type: 'bool' }]} />
          <SettingsForm group="alerts" title="In-app alert rules"
            fields={[{ key: 'enabled', label: 'Alerts enabled', type: 'bool' }, { key: 'min_severity', label: 'Minimum severity', type: 'select', options: SEVERITIES.filter(s => s !== 'UNKNOWN') },
              { key: 'on_status', label: 'When status becomes (comma separated)', type: 'list' }, { key: 'categories', label: 'Only categories (comma separated, blank = all)', type: 'list' }]} />
          <SettingsForm group="map" title="Map" note="The default basemap is OpenFreeMap (free, OpenStreetMap data, attribution shown on the map). Any MapLibre style URL can be used."
            fields={[{ key: 'style_url', label: 'Map style URL', type: 'text' }, { key: 'attribution_note', label: 'Attribution text', type: 'text' }, { key: 'default_zoom', label: 'Default zoom', type: 'number' }]} />
        </div>
      )}
      {tab === 'keys' && <NewsKeys />}
      {tab === 'health' && <Health />}
      {tab === 'audit' && <AuditLog />}
    </div>
  )
}
