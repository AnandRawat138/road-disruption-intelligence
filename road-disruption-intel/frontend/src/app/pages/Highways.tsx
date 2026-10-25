import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import maplibregl, { Map as MLMap } from 'maplibre-gl'
import { ExternalLink, Search, X } from 'lucide-react'
import { fmtDate, qs, useApi } from '../api'
import { usePublicSettings } from '../App'
import { SEVERITY_RAMP, catLabel } from '../meta'
import { Ago, Badge, Card, CategoryBadge, Empty, ErrorBox, Loading, MultiSelect, Notice, PrecisionBadge, Severity, Stat,
  StatusBadge } from '../components/ui'
import IncidentDrawer from '../components/IncidentDrawer'
import RecordDrawer from '../components/RecordDrawer'

const TYPE_LABEL: Record<string, string> = {
  NATIONAL_HIGHWAY: 'National highway', STATE_HIGHWAY: 'State highway', EXPRESSWAY: 'Expressway', NAMED_HIGHWAY: 'Named highway',
}
const WINDOWS = [{ v: 1, l: '24 hours' }, { v: 3, l: '3 days' }, { v: 7, l: '7 days' }, { v: 30, l: '30 days' }, { v: 90, l: '90 days' }, { v: 365, l: '1 year' }]

function topCategories(c: Record<string, number>) {
  return Object.entries(c || {}).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k]) => k)
}

function HighwayMap({ fc }: { fc: any }) {
  const { s } = usePublicSettings()
  const el = useRef<HTMLDivElement>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    if (!el.current || !fc?.features?.length) return
    let map: MLMap
    try {
      map = new maplibregl.Map({ container: el.current, style: s.map.style_url, attributionControl: false,
        center: [s.map.default_center[1], s.map.default_center[0]], zoom: 4 })
    } catch (e: any) { setErr(`Map unavailable (${e?.message || 'WebGL'})`); return }
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: s.map.attribution_note }), 'bottom-right')
    map.on('error', () => setErr('Map tiles could not be loaded (internet required for the basemap).'))
    map.on('load', () => {
      map.addSource('hw', { type: 'geojson', data: fc })
      map.addLayer({ id: 'hw-pts', type: 'circle', source: 'hw', paint: {
        'circle-radius': 8, 'circle-stroke-color': '#fff', 'circle-stroke-width': 2,
        'circle-color': ['match', ['get', 'severity'], ...Object.entries(SEVERITY_RAMP).flat(), SEVERITY_RAMP.UNKNOWN] as any } })
      const b = new maplibregl.LngLatBounds()
      fc.features.forEach((f: any) => b.extend(f.geometry.coordinates))
      map.fitBounds(b, { padding: 40, maxZoom: 9, duration: 0 })
    })
    return () => map.remove()
  }, [fc, s.map.style_url, s.map.attribution_note, s.map.default_center])
  if (!fc?.features?.length) return <div className="xs muted">No incident on this highway has a city-level or better location to map.</div>
  return (
    <div>
      <div ref={el} className="hw-map" role="img" aria-label="Approximate locations of incidents on this highway" />
      {err && <div className="xs muted">{err}</div>}
    </div>
  )
}

function Detail({ id, params, onIncident, onRecord }: { id: string; params: Record<string, any>; onIncident: (id: string) => void; onRecord: (id: string) => void }) {
  const { data, error, loading, reload } = useApi<any>(`/api/highways/detail${qs({ id, ...params })}`)
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (loading && !data) return <Loading />
  if (!data) return null
  const h = data.highway
  return (
    <div className="stack">
      <div>
        <div className="row"><h2 style={{ margin: 0 }}>{h.name}</h2><Badge tone="neutral">{TYPE_LABEL[h.type]}</Badge></div>
        <div className="small muted" style={{ marginTop: 4 }}>
          {h.states.length ? h.states.join(', ') : 'State not stated'}{h.cities.length ? ` · ${h.cities.slice(0, 6).join(', ')}` : ''} · last report <Ago iso={h.last_reported_at} />
        </div>
      </div>
      <div className="row">
        <Badge tone={h.running_incidents ? 'danger' : 'neutral'}>{h.running_incidents} running</Badge>
        <Badge tone={h.stale_incidents ? 'warn' : 'neutral'}>{h.stale_incidents} stale</Badge>
        <Badge tone={h.unverified_reports ? 'blue' : 'neutral'}>{h.unverified_reports} unverified report{h.unverified_reports === 1 ? '' : 's'}</Badge>
        <span className="small">Highest severity: <Severity value={h.max_severity} /></span>
      </div>
      <HighwayMap fc={data.map} />
      <div className="xs muted">{data.location_note}</div>
      <div className="section-title">Incidents naming this highway ({data.incidents.length})</div>
      {data.incidents.length === 0 ? <div className="small muted">No classified incident – only unverified reports below.</div> : (
        <div>
          {data.incidents.map((i: any) => (
            <button key={i.id} type="button" className="map-item" onClick={() => onIncident(i.id)}>
              <div className="row" style={{ gap: 6, marginBottom: 4 }}>
                <CategoryBadge code={i.category} /><StatusBadge status={i.status} stale={i.is_stale} /><Severity value={i.severity} />
              </div>
              <div style={{ fontWeight: 500 }}>{i.title}</div>
              <div className="xs muted" style={{ marginTop: 2 }}>
                {[i.city, i.state].filter(Boolean).join(', ') || 'Location not resolved'} · {i.article_count} report{i.article_count === 1 ? '' : 's'} · last {fmtDate(i.last_reported_at)} <PrecisionBadge precision={i.geo_precision} />
              </div>
            </button>
          ))}
        </div>
      )}
      {data.reports.length > 0 && <>
        <div className="section-title">Unverified recent reports ({data.reports.length})</div>
        <div className="xs muted">Not yet classified (or classified as needing review). Open a report to classify or review it; it then joins an incident if relevant.</div>
        <ul className="timeline-list">
          {data.reports.map((r: any) => (
            <li key={r.id}>
              <button type="button" className="btn ghost sm" style={{ textAlign: 'left', whiteSpace: 'normal' }} onClick={() => onRecord(r.id)}>{r.title}</button>
              <div className="xs muted">{r.source_name} · {fmtDate(r.published_at)}{r.source_url && <> · <a href={r.source_url} target="_blank" rel="noopener noreferrer">source <ExternalLink size={10} /></a></>}</div>
            </li>
          ))}
        </ul>
      </>}
    </div>
  )
}

export default function Highways() {
  const [sp, setSp] = useSearchParams()
  const set = (patch: Record<string, string | number | boolean | null>) => {
    const n = new URLSearchParams(sp)
    Object.entries(patch).forEach(([k, v]) => (v === null || v === '' ? n.delete(k) : n.set(k, String(v))))
    setSp(n, { replace: true })
  }
  const params = useMemo(() => ({
    report_days: Number(sp.get('days') || 7),
    include_stale: sp.get('stale') !== 'false',
    include_reports: sp.get('reports') !== 'false',
  }), [sp])
  const types = (sp.get('type') || '').split(',').filter(Boolean)
  const sort = sp.get('sort') || 'activity'
  const query = sp.get('q') || ''
  const { data, error, loading, reload } = useApi<any>(`/api/highways${qs({ ...params, q: query, type: types, sort })}`, 120000)
  const [q, setQ] = useState(query)
  const [incident, setIncident] = useState<string | null>(null)
  const [record, setRecord] = useState<string | null>(null)
  const items: any[] = data?.items || []
  const selected = sp.get('hw') || ''
  const m = data?.meta
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Highways with possible running events</h1>
          <div className="sub">Every national highway, state highway, expressway and named highway that a report names in connection with an open
            disruption. Highways are listed only where a report names them – positions on the map are approximate city/locality centroids, never points on the road.</div>
        </div>
      </div>
      {m && (
        <div className="grid grid-4">
          <Stat label="Highways listed" value={data.total} tip="Highways named by at least one open incident or recent unverified report under the current filters" />
          <Stat label="With running incidents" value={m.with_running_incidents} tone={m.with_running_incidents ? '#b42318' : undefined}
                tip={`Open incident reported within the last ${m.stale_after_hours} h`} />
          <Stat label="Expressways" value={m.by_type.EXPRESSWAY} foot={`${m.by_type.NATIONAL_HIGHWAY} national · ${m.by_type.STATE_HIGHWAY} state highways`} />
          <Stat label="Named highways" value={m.by_type.NAMED_HIGHWAY} foot="e.g. Mumbai-Goa Highway" />
        </div>
      )}
      <div className="hw-layout">
        <Card bodyClass="">
          <form className="filters" role="search" onSubmit={e => { e.preventDefault(); set({ q }) }}>
            <label className="field" style={{ flex: '1 1 200px' }}>Search highway
              <span className="row" style={{ flexWrap: 'nowrap' }}>
                <input className="input" style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)} placeholder="NH-48, Yamuna, Mumbai-Pune, Kerala…" />
                <button className="btn" aria-label="Search"><Search size={14} /></button>
              </span>
            </label>
            <MultiSelect label="Type" options={Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))} value={types} onChange={v => set({ type: v.join(',') })} />
            <label className="field">Unverified reports from
              <select className="input" value={params.report_days} onChange={e => set({ days: e.target.value })}>
                {WINDOWS.map(w => <option key={w.v} value={w.v}>last {w.l}</option>)}
              </select>
            </label>
            <label className="field">Sort
              <select className="input" value={sort} onChange={e => set({ sort: e.target.value })}>
                <option value="activity">Running first</option><option value="severity">Severity</option>
                <option value="recent">Latest report</option><option value="name">Name</option>
              </select>
            </label>
            <label className="check"><input type="checkbox" checked={params.include_stale} onChange={e => set({ stale: e.target.checked ? null : 'false' })} />Include stale incidents</label>
            <label className="check"><input type="checkbox" checked={params.include_reports} onChange={e => set({ reports: e.target.checked ? null : 'false' })} />Include unverified reports</label>
            {(query || types.length) ? <button type="button" className="btn ghost" onClick={() => { setQ(''); set({ q: null, type: null }) }}><X size={14} />Clear</button> : null}
          </form>
          {error && <div style={{ padding: 12 }}><ErrorBox error={error} onRetry={reload} /></div>}
          {m && m.with_running_incidents === 0 && items.length > 0 && (
            <div style={{ padding: '10px 12px 0' }}><Notice kind="info">No highway has an incident reported within the last {m.stale_after_hours} hours. Stale incidents and unverified reports are shown so you can verify them; fetch current news under Sources &amp; acquisition for live coverage.</Notice></div>
          )}
          {loading && !data ? <Loading /> : items.length === 0 ? (
            <Empty title="No highway matches">Widen the report window, include stale incidents, or fetch and classify recent news.</Empty>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Highway</th><th title="Open incidents reported within the staleness window">Running</th><th title="Open incidents without a recent report">Stale</th>
                  <th title="Recent unclassified reports flagged by the keyword pre-filter">Unverified</th><th>Main categories</th><th>Severity</th><th>Last report</th></tr></thead>
                <tbody style={{ opacity: loading ? 0.6 : 1 }}>
                  {items.map(h => (
                    <tr key={h.id} className={`clickable ${selected === h.id ? 'selected' : ''}`} tabIndex={0} aria-selected={selected === h.id}
                        onClick={() => set({ hw: h.id })} onKeyDown={e => { if (e.key === 'Enter') set({ hw: h.id }) }}>
                      <td className="title-cell"><span className="t">{h.name}</span>
                        <div className="xs muted">{TYPE_LABEL[h.type]}{h.states.length ? ` · ${h.states.slice(0, 2).join(', ')}` : ''}</div></td>
                      <td>{h.running_incidents ? <Badge tone="danger">{h.running_incidents}</Badge> : <span className="muted">0</span>}</td>
                      <td>{h.stale_incidents ? <Badge tone="warn">{h.stale_incidents}</Badge> : <span className="muted">0</span>}</td>
                      <td>{h.unverified_reports ? <Badge tone="blue">{h.unverified_reports}</Badge> : <span className="muted">0</span>}</td>
                      <td className="small">{topCategories(h.categories).map(catLabel).join(', ') || <span className="muted">—</span>}</td>
                      <td><Severity value={h.max_severity} /></td>
                      <td className="small nowrap">{fmtDate(h.last_reported_at, false)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {m && <div className="xs muted" style={{ padding: '8px 12px' }}>{m.note}</div>}
        </Card>
        <Card bodyClass="card-body">
          {selected ? <Detail id={selected} params={params} onIncident={setIncident} onRecord={setRecord} />
            : <Empty title="Select a highway">Choose a highway on the left to see its incidents, unverified reports and an approximate map.</Empty>}
        </Card>
      </div>
      {incident && <IncidentDrawer id={incident} onClose={() => setIncident(null)} onChanged={reload} />}
      {record && <RecordDrawer id={record} onClose={() => setRecord(null)} onChanged={reload} />}
    </div>
  )
}
