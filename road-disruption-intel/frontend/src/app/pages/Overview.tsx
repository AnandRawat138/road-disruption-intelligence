import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { fmtDate, fmtNum, qs, useApi } from '../api'
import { Ago, Badge, Card, Empty, ErrorBox, Loading, Notice, Stat } from '../components/ui'
import { BarList, DailyColumns } from '../components/charts'
import { catLabel, SEVERITY_META } from '../meta'
import { usePublicSettings } from '../App'
import SetupChecklist from './SetupChecklist'

export default function Overview() {
  const nav = useNavigate()
  const { s } = usePublicSettings()
  const [f, setF] = useState({ date_from: '', date_to: '', state: '', category: '' })
  const { data, error, loading, reload } = useApi<any>(`/api/dashboard/summary${qs(f)}`, 30000)
  const set = (k: string, v: string) => setF(p => ({ ...p, [k]: v }))
  const toRecords = (extra: Record<string, string>) => nav(`/records${qs({ ...extra, date_from: f.date_from, date_to: f.date_to, state: f.state, category: extra.category || f.category })}`)

  if (error && !data) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const m = data.metrics
  const d = data.definitions
  const nothingImported = m.unique_articles === 0
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Operational overview</h1>
          <div className="sub">{s.branding.company_name} · live figures from the local database, refreshed every 30 seconds.
            Data covers articles published {fmtDate(data.coverage.earliest_published, false)} – {fmtDate(data.coverage.latest_published, false)}.</div>
        </div>
        <div className="actions">
          <button className="btn" onClick={reload} disabled={loading}><RefreshCw size={14} />Refresh</button>
        </div>
      </div>

      <SetupChecklist summary={data} />

      <div className="card filters" style={{ borderRadius: 8 }} role="group" aria-label="Dashboard filters">
        <label className="field">Published from<input type="date" className="input" value={f.date_from} onChange={e => set('date_from', e.target.value)} /></label>
        <label className="field">Published to<input type="date" className="input" value={f.date_to} onChange={e => set('date_to', e.target.value)} /></label>
        <label className="field">State
          <select className="input" value={f.state} onChange={e => set('state', e.target.value)}>
            <option value="">All states</option>
            {data.by_state.map((x: any) => <option key={x.key} value={x.key}>{x.key}</option>)}
            {f.state && !data.by_state.some((x: any) => x.key === f.state) && <option value={f.state}>{f.state}</option>}
          </select>
        </label>
        <label className="field">Category
          <select className="input" value={f.category} onChange={e => set('category', e.target.value)}>
            <option value="">All categories</option>
            {s.categories.map(c => <option key={c.code} value={c.code}>{c.label}</option>)}
          </select>
        </label>
        {(f.date_from || f.date_to || f.state || f.category) && <button className="btn ghost" onClick={() => setF({ date_from: '', date_to: '', state: '', category: '' })}>Clear filters</button>}
        <span className="right small muted">Filters apply to relevance counts, distributions and incident counts.</span>
      </div>

      {data.last_successful_refresh === null && !nothingImported && (
        <Notice kind="info">No live source has been fetched successfully yet – figures reflect imported historical data only. Use <strong>Sources &amp; acquisition → Fetch now</strong> to retrieve current news.</Notice>
      )}

      <div className="kpi-row">
        <Stat label="Source records" value={fmtNum(m.total_source_records)} tip={d.total_source_records} foot="incl. repeats across files/queries" />
        <Stat label="Unique articles" value={fmtNum(m.unique_articles)} tip={d.unique_articles} onClick={() => nav('/records')} />
        <Stat label="Relevant reports" value={fmtNum(m.relevant_reports)} tip={d.relevant_reports} onClick={() => toRecords({ relevance: 'RELEVANT' })}
              foot={`${fmtNum(m.classified)} classified so far`} />
        <Stat label="Unclassified" value={fmtNum(m.unclassified)} tip={d.unclassified} onClick={() => nav('/records?classification_status=UNCLASSIFIED')}
              foot={m.failed_classifications ? `${fmtNum(m.failed_classifications)} failed` : undefined} />
        <Stat label="Awaiting review" value={fmtNum(m.awaiting_review)} tip={d.awaiting_review} onClick={() => nav('/review')} />
        <Stat label="Active incidents" value={fmtNum(m.active_incidents)} tip={d.active_incidents} onClick={() => nav('/disruptions?lifecycle=active')}
              foot={`reported within ${data.stale_after_hours} h`} />
        <Stat label="High-severity active" value={fmtNum(m.high_severity_active)} tip={d.high_severity_active}
              onClick={() => nav('/disruptions?lifecycle=active&severity=HIGH,CRITICAL')} />
        <Stat label="Open but stale" value={fmtNum(m.stale_open_incidents)} tip={d.stale_open_incidents} onClick={() => nav('/disruptions?lifecycle=stale')} />
        <Stat label="Resolved (7 days)" value={fmtNum(m.recently_resolved)} tip={d.recently_resolved} onClick={() => nav('/disruptions?lifecycle=resolved')} />
        <Stat label="Last live refresh" value={<span style={{ fontSize: 16 }}><Ago iso={data.last_successful_refresh} /></span>} tip={d.last_successful_refresh}
              onClick={() => nav('/sources')} />
      </div>

      {nothingImported ? (
        <Card><Empty title="No records yet">Import the historical data or fetch from a source to populate the dashboard.</Empty></Card>
      ) : (
        <>
          <div className="grid grid-2">
            <Card title="Relevant reports by category" actions={<span className="small muted">click a bar to open records</span>}>
              <BarList data={data.by_category} labelOf={catLabel} onSelect={k => toRecords({ relevance: 'RELEVANT', category: k })} />
            </Card>
            <Card title="Relevant reports by state">
              <BarList data={data.by_state} onSelect={k => toRecords({ relevance: 'RELEVANT', state: k })} />
            </Card>
          </div>
          <div className="grid grid-2">
            <Card title="Articles published per day" actions={<span className="small muted">{data.timeline.length} days</span>}>
              <DailyColumns data={data.timeline} field="articles" label="Articles" />
            </Card>
            <Card title="Relevant reports per day" actions={<span className="small muted">classified records only</span>}>
              <DailyColumns data={data.timeline} field="relevant" label="Relevant reports" color="#1d4ed8" />
            </Card>
          </div>
          <div className="grid grid-3">
            <Card title="Top cities (relevant)"><BarList data={data.by_city} onSelect={k => toRecords({ relevance: 'RELEVANT', city: k })} /></Card>
            <Card title="Severity (relevant)"><BarList data={data.by_severity} labelOf={k => SEVERITY_META[k]?.label || k} onSelect={k => toRecords({ relevance: 'RELEVANT', severity: k })} /></Card>
            <Card title="Unclassified queue by keyword pre-filter" actions={<span className="small muted">not a classification</span>}>
              <BarList data={data.unclassified_by_prefilter} onSelect={k => nav(`/records?classification_status=UNCLASSIFIED&prefilter=${k}`)} />
            </Card>
          </div>
        </>
      )}

      <div className="grid grid-2">
        <Card title="Source health" actions={<button className="btn sm" onClick={() => nav('/sources')}>Manage</button>} bodyClass="table-wrap">
          <table className="table">
            <thead><tr><th>Source</th><th>Status</th><th>Last success</th><th>New total</th></tr></thead>
            <tbody>
              {data.sources.map((x: any) => (
                <tr key={x.id}>
                  <td>{x.name}{!x.enabled && <span className="muted small"> (disabled)</span>}</td>
                  <td>{x.last_status ? <Badge tone={x.last_status === 'OK' ? 'ok' : x.last_status === 'PARTIAL' ? 'warn' : 'danger'}>{x.last_status}</Badge> : <Badge>Not run</Badge>}</td>
                  <td className="small"><Ago iso={x.last_success_at} /></td>
                  <td>{fmtNum(x.total_new)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Recent activity" bodyClass="card-body">
          <div className="section-title" style={{ marginTop: 0 }}>Classification (last 24 h)</div>
          <div className="row small">
            {Object.keys(data.classifications_24h).length === 0 ? <span className="muted">No classifications in the last 24 hours.</span> :
              Object.entries(data.classifications_24h).map(([k, v]) => <Badge key={k} tone={k === 'VALID' ? 'ok' : 'danger'}>{k}: {String(v)}</Badge>)}
          </div>
          <ul className="timeline-list" style={{ marginTop: 6 }}>
            {data.recent_classifications.slice(0, 5).map((r: any, i: number) => (
              <li key={i}><span className="muted">{fmtDate(r.at)}</span> · {r.status === 'VALID' ? (r.relevance || '') : <Badge tone="danger">{r.status}</Badge>} {r.category && `· ${catLabel(r.category)}`} — <span className="clip">{r.title}</span></li>
            ))}
          </ul>
          <div className="section-title">Ingestion</div>
          <ul className="timeline-list">
            {data.recent_fetch_runs.slice(0, 3).map((r: any) => (
              <li key={`f${r.id}`}><span className="muted">{fmtDate(r.started_at)}</span> · fetch {r.source_id}: <Badge tone={r.status === 'OK' ? 'ok' : r.status === 'PARTIAL' ? 'warn' : 'danger'}>{r.status}</Badge> {r.new} new / {r.duplicates} dup</li>
            ))}
            {data.recent_imports.slice(0, 4).map((b: any) => (
              <li key={b.id}><span className="muted">{fmtDate(b.finished_at)}</span> · import {b.file_name}: {fmtNum(b.imported)} new, {fmtNum(b.duplicate)} dup, {b.invalid + b.failed} rejected</li>
            ))}
            {!data.recent_fetch_runs.length && !data.recent_imports.length && <li className="muted">No ingestion yet.</li>}
          </ul>
        </Card>
      </div>
      <div className="footer-note">Generated {fmtDate(data.generated_at)} IST. Counts are computed from the database at request time; locations are approximate.</div>
    </div>
  )
}
