import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Download, Search, X } from 'lucide-react'
import { download, fmtDate, qs, useApi } from '../api'
import { usePublicSettings } from '../App'
import { INCIDENT_STATUSES, SEVERITIES, SEVERITY_META } from '../meta'
import { Badge, Card, CategoryBadge, Empty, ErrorBox, Loading, MultiSelect, Notice, Pagination, PrecisionBadge, Severity,
  StatusBadge, useToast } from '../components/ui'
import IncidentDrawer from '../components/IncidentDrawer'

export const LIFECYCLES = [
  { id: '', label: 'All' }, { id: 'active', label: 'Active' }, { id: 'stale', label: 'Open but stale' },
  { id: 'open', label: 'All open' }, { id: 'resolved', label: 'Resolved' },
]

export function useIncidentFilters() {
  const [sp, setSp] = useSearchParams()
  const f = useMemo(() => {
    const o: Record<string, any> = {}
    for (const k of ['q', 'lifecycle', 'state', 'city', 'highway', 'date_from', 'date_to', 'has_conflict', 'source', 'classification'])
      if (sp.get(k)) o[k] = sp.get(k)
    for (const k of ['status', 'category', 'severity']) if (sp.get(k)) o[k] = sp.get(k)!.split(',')
    return o
  }, [sp])
  const update = (patch: Record<string, any>) => {
    const n = new URLSearchParams(sp)
    Object.entries(patch).forEach(([k, v]) => {
      if (v === undefined || v === '' || v === null || (Array.isArray(v) && !v.length)) n.delete(k)
      else n.set(k, Array.isArray(v) ? v.join(',') : String(v))
    })
    if (!('page' in patch)) n.delete('page')
    setSp(n, { replace: true })
  }
  return { sp, f, update }
}

export default function Disruptions() {
  const { s } = usePublicSettings()
  const toast = useToast()
  const { sp, f, update } = useIncidentFilters()
  const page = Number(sp.get('page') || 1)
  const sort = sp.get('sort') || 'last_reported_at'
  const { data, error, loading, reload } = useApi<any>(`/api/incidents${qs({ ...f, page, page_size: 25, sort })}`)
  const [q, setQ] = useState(f.q || '')
  const [open, setOpen] = useState<string | null>(sp.get('incident'))
  const items: any[] = data?.items || []
  const exp = async (format: string) => {
    try { await download(`/api/incidents/export${qs({ ...f, format })}`, `incidents.${format}`) } catch (e: any) { toast('error', e.message) }
  }
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Live & recent disruptions</h1>
          <div className="sub">Incidents group related reports about the same event. “Active” means an open incident with a report in the staleness window;
            older open incidents are shown as <em>stale</em> and are not presented as current.</div>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => exp('csv')}><Download size={14} />CSV</button>
          <button className="btn" onClick={() => exp('json')}><Download size={14} />JSON</button>
        </div>
      </div>
      <Card bodyClass="">
        <div className="filters">
          <div className="row" role="radiogroup" aria-label="Lifecycle">
            {LIFECYCLES.map(l => (
              <button key={l.id} className={`btn sm ${(f.lifecycle || '') === l.id ? 'primary' : ''}`} role="radio" aria-checked={(f.lifecycle || '') === l.id}
                      onClick={() => update({ lifecycle: l.id })}>{l.label}</button>
            ))}
          </div>
        </div>
        <form className="filters" onSubmit={e => { e.preventDefault(); update({ q }) }} role="search">
          <label className="field" style={{ flex: '1 1 220px' }}>Search
            <span className="row" style={{ flexWrap: 'nowrap' }}>
              <input className="input" style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)} placeholder="Title, city, road, highway…" />
              <button className="btn" aria-label="Search"><Search size={14} /></button>
            </span>
          </label>
          <MultiSelect label="Status" options={INCIDENT_STATUSES.map(x => ({ value: x, label: x }))} value={f.status || []} onChange={v => update({ status: v })} />
          <MultiSelect label="Category" options={s.categories.map(c => ({ value: c.code, label: c.label }))} value={f.category || []} onChange={v => update({ category: v })} />
          <MultiSelect label="Severity" options={SEVERITIES.map(x => ({ value: x, label: SEVERITY_META[x].label }))} value={f.severity || []} onChange={v => update({ severity: v })} />
          <label className="field">City<input className="input" value={f.city || ''} onChange={e => update({ city: e.target.value })} style={{ width: 120 }} /></label>
          <label className="field">State<input className="input" value={f.state || ''} onChange={e => update({ state: e.target.value })} style={{ width: 130 }} /></label>
          <label className="field">Reported from<input type="date" className="input" value={f.date_from || ''} onChange={e => update({ date_from: e.target.value })} /></label>
          <label className="field">to<input type="date" className="input" value={f.date_to || ''} onChange={e => update({ date_to: e.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={f.has_conflict === 'true'} onChange={e => update({ has_conflict: e.target.checked ? 'true' : '' })} />Conflicts only</label>
          <label className="field">Sort
            <select className="input" value={sort} onChange={e => update({ sort: e.target.value })}>
              <option value="last_reported_at">Latest report</option><option value="severity">Severity</option>
              <option value="article_count">Most reports</option><option value="first_reported_at">First report</option>
            </select>
          </label>
          {Object.keys(f).length > 0 && <button type="button" className="btn ghost" onClick={() => { setQ(''); update(Object.fromEntries(Object.keys(f).map(k => [k, '']))) }}><X size={14} />Clear</button>}
        </form>
        {error && <div style={{ padding: 12 }}><ErrorBox error={error} onRetry={reload} /></div>}
        {f.lifecycle === 'active' && data && data.total === 0 && (
          <div style={{ padding: 12 }}><Notice kind="info">No incident has a report within the staleness window. Historical data is older than this window; fetch current news from Sources &amp; acquisition and classify it to see active disruptions.</Notice></div>
        )}
        {loading && !data ? <Loading /> : items.length === 0 ? <Empty title="No incidents match">Incidents are created when records are classified as relevant.</Empty> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Category</th><th>Incident</th><th>Location</th><th>Road</th><th>Severity</th><th>Status</th><th>Reports</th><th>Last report</th></tr></thead>
              <tbody style={{ opacity: loading ? 0.6 : 1 }}>
                {items.map(i => (
                  <tr key={i.id} className="clickable" tabIndex={0} onClick={() => setOpen(i.id)} onKeyDown={e => { if (e.key === 'Enter') setOpen(i.id) }}>
                    <td><CategoryBadge code={i.category} /></td>
                    <td className="title-cell"><span className="t">{i.title}</span>{i.has_conflict && <Badge tone="warn">Conflict</Badge>}</td>
                    <td className="small">{[i.locality, i.city, i.state].filter(Boolean).join(', ') || '—'}<div><PrecisionBadge precision={i.geo_precision} /></div></td>
                    <td className="small">{[i.highway_number, i.road_name].filter(Boolean).join(' · ') || '—'}</td>
                    <td><Severity value={i.severity} /></td>
                    <td><StatusBadge status={i.status} stale={i.is_stale} /></td>
                    <td>{i.article_count}</td>
                    <td className="small nowrap">{fmtDate(i.last_reported_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={page} pages={data.pages} total={data.total} onPage={p => update({ page: p })} />}
      </Card>
      {open && <IncidentDrawer id={open} onClose={() => { setOpen(null); update({ incident: '' }) }} onChanged={reload} />}
    </div>
  )
}
