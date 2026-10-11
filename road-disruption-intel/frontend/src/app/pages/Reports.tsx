import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { fmtDate, fmtNum, qs, useApi } from '../api'
import { usePublicSettings } from '../App'
import { BarList } from '../components/charts'
import { Card, CategoryBadge, ErrorBox, Loading, Notice, Severity, StatusBadge, Tabs } from '../components/ui'
import { catLabel, SEVERITY_META } from '../meta'

function isoDay(d: Date) { return d.toISOString().slice(0, 10) }

function SummaryReport() {
  const { s } = usePublicSettings()
  const [range, setRange] = useState({ date_from: isoDay(new Date(Date.now() - 30 * 86400000)), date_to: isoDay(new Date()), state: '' })
  const [applied, setApplied] = useState(range)
  const { data, error, loading, reload } = useApi<any>(`/api/reports/summary${qs(applied)}`)
  return (
    <div className="stack">
      <div className="card filters no-print" style={{ borderRadius: 8 }}>
        <label className="field">From<input type="date" className="input" value={range.date_from} onChange={e => setRange({ ...range, date_from: e.target.value })} /></label>
        <label className="field">To<input type="date" className="input" value={range.date_to} onChange={e => setRange({ ...range, date_to: e.target.value })} /></label>
        <label className="field">State (optional)<input className="input" value={range.state} onChange={e => setRange({ ...range, state: e.target.value })} /></label>
        <button className="btn primary" onClick={() => setApplied(range)}>Generate</button>
        <button className="btn" onClick={() => window.print()} disabled={!data}><Printer size={14} />Print / save as PDF</button>
      </div>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && (
        <div className="card card-body stack">
          <div>
            <div className="small muted">{s.branding.company_name} · {s.branding.company_location}</div>
            <h1 style={{ marginTop: 4 }}>Road disruption summary: {fmtDate(data.period.from, false)} – {fmtDate(data.period.to, false)}{data.state ? ` · ${data.state}` : ''}</h1>
            <div className="small muted">Generated {fmtDate(data.generated_at)} IST by {s.branding.product_name}</div>
          </div>
          <div className="kpi-row">
            <div className="card stat"><div className="label">Articles published</div><div className="value">{fmtNum(data.articles_in_period)}</div></div>
            <div className="card stat"><div className="label">Classified relevant</div><div className="value">{fmtNum(data.relevant_in_period)}</div></div>
            <div className="card stat"><div className="label">Operator-approved</div><div className="value">{fmtNum(data.approved_in_period)}</div></div>
            <div className="card stat"><div className="label">Not yet classified</div><div className="value">{fmtNum(data.unclassified_in_period)}</div></div>
            <div className="card stat"><div className="label">Incidents</div><div className="value">{fmtNum(data.incident_count)}</div></div>
          </div>
          {data.unclassified_in_period > 0 && <Notice kind="warn">{fmtNum(data.unclassified_in_period)} articles in this period have not been classified and are not reflected in the incident figures.</Notice>}
          <div className="grid grid-3">
            <Card title="By category"><BarList data={data.by_category} labelOf={catLabel} /></Card>
            <Card title="By state"><BarList data={data.by_state} /></Card>
            <Card title="By severity"><BarList data={data.by_severity} labelOf={k => SEVERITY_META[k]?.label || k} /></Card>
          </div>
          <Card title="Top incidents (by severity, then number of reports)" bodyClass="">
            <table className="table">
              <thead><tr><th>Category</th><th>Incident</th><th>Location</th><th>Severity</th><th>Status</th><th>Reports</th><th>Last report</th></tr></thead>
              <tbody>{data.top_incidents.map((i: any) => (
                <tr key={i.id}><td><CategoryBadge code={i.category} /></td><td>{i.title}</td><td className="small">{[i.city, i.state].filter(Boolean).join(', ')}</td>
                  <td><Severity value={i.severity} /></td><td><StatusBadge status={i.status} /></td><td>{i.article_count}</td><td className="small">{fmtDate(i.last_reported_at)}</td></tr>
              ))}{!data.top_incidents.length && <tr><td colSpan={7} className="muted">No incidents in this period.</td></tr>}</tbody>
            </table>
          </Card>
          <div className="small muted"><strong>Provenance:</strong> {data.provenance}</div>
        </div>
      )}
    </div>
  )
}

function Quality() {
  const { data, error, loading, reload } = useApi<any>('/api/quality')
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (loading && !data) return <Loading />
  const pct = (n: number) => (data.relevant_records ? ` (${Math.round((n / data.relevant_records) * 100)}%)` : '')
  return (
    <div className="stack">
      <div className="grid grid-2">
        <Card title={`Missing fields in ${fmtNum(data.relevant_records)} relevant records`}>
          <table className="table"><tbody>
            {Object.entries(data.missing_fields).map(([k, v]: any) => <tr key={k}><td>{k.replace(/_/g, ' ')}</td><td>{fmtNum(v)}{pct(v)}</td></tr>)}
            <tr><td>end before start (date conflict)</td><td>{fmtNum(data.date_conflicts)}</td></tr>
          </tbody></table>
        </Card>
        <Card title="Geocoding precision">
          <table className="table"><tbody>
            {Object.entries(data.geocoding).map(([k, v]: any) => <tr key={k}><td>{k.replace(/_/g, ' ')}</td><td>{fmtNum(v)}{pct(v)}</td></tr>)}
          </tbody></table>
          <div className="xs muted" style={{ marginTop: 6 }}>Locality/city positions are centroids. Only operator-placed positions are exact.</div>
        </Card>
      </div>
      <Card title="Source reliability (measured)" bodyClass="">
        <div className="small muted" style={{ padding: '8px 14px' }}>Computed from classifications and operator decisions in this database – not assumed. Sources with fewer than 3 classified records are omitted.</div>
        <table className="table">
          <thead><tr><th>Source</th><th>Classified</th><th>Relevant</th><th>Relevant rate</th><th>Approved</th><th>Rejected</th><th>Approval rate</th></tr></thead>
          <tbody>{data.source_reliability.map((r: any) => (
            <tr key={r.source}><td>{r.source}</td><td>{r.classified}</td><td>{r.relevant}</td><td>{r.relevant_rate != null ? `${Math.round(r.relevant_rate * 100)}%` : '—'}</td><td>{r.approved}</td><td>{r.rejected}</td><td>{r.approval_rate != null ? `${Math.round(r.approval_rate * 100)}%` : 'no reviews'}</td></tr>
          ))}{!data.source_reliability.length && <tr><td colSpan={7} className="muted">Not enough classified records yet.</td></tr>}</tbody>
        </table>
      </Card>
      <div className="grid grid-2">
        <Card title={`Failed classifications (${fmtNum(data.failed_total)})`}>
          {data.failed_classifications.length ? <ul className="timeline-list">{data.failed_classifications.map((f: any) => <li key={f.id}>{f.title} <span className="muted">({f.attempts} attempt(s))</span></li>)}</ul> : <span className="muted small">None.</span>}
          {data.failed_total > 0 && <Link className="btn sm" style={{ marginTop: 8 }} to="/records?classification_status=FAILED">Open failed records to retry</Link>}
        </Card>
        <Card title="Possible duplicate incidents">
          {data.duplicate_suggestions.length ? <ul className="timeline-list">{data.duplicate_suggestions.map((d: any) => (
            <li key={`${d.a_id}${d.b_id}`}><strong>{catLabel(d.category)} · {d.city}</strong><br />
              <Link to={`/disruptions?incident=${d.a_id}`}>{d.a_title}</Link> <span className="mono xs">{d.a_id}</span><br />
              <Link to={`/disruptions?incident=${d.b_id}`}>{d.b_title}</Link> <span className="mono xs">{d.b_id}</span></li>
          ))}</ul> : <span className="muted small">No suggestions.</span>}
          <div className="xs muted" style={{ marginTop: 6 }}>Same category and city, reported within 48 h. Open one and use “Merge into another incident” after checking they describe the same event.</div>
        </Card>
      </div>
      <div className="grid grid-2">
        <Card title="Stale open incidents">
          {data.stale_open_incidents.length ? <ul className="timeline-list">{data.stale_open_incidents.map((i: any) => <li key={i.id}><Link to={`/disruptions?incident=${i.id}`}>{i.title}</Link> <span className="muted small">last report {fmtDate(i.last_reported_at)}</span></li>)}</ul> : <span className="muted small">None.</span>}
        </Card>
        <Card title="Incidents with conflicting reports">
          {data.conflicting_incidents.length ? <ul className="timeline-list">{data.conflicting_incidents.map((i: any) => <li key={i.id}><Link to={`/disruptions?incident=${i.id}`}>{i.title}</Link><div className="xs muted">{i.notes?.slice(-1)[0]}</div></li>)}</ul> : <span className="muted small">None.</span>}
        </Card>
      </div>
    </div>
  )
}

export default function Reports() {
  const [tab, setTab] = useState('summary')
  return (
    <div>
      <div className="page-head no-print"><div><h1>Analytics & reports</h1><div className="sub">Period summaries for distribution and data-quality checks for the operations team. Use the Records and Disruptions pages to export filtered CSV/JSON.</div></div></div>
      <div className="no-print"><Tabs tabs={[{ id: 'summary', label: 'Summary report' }, { id: 'quality', label: 'Data quality' }]} value={tab} onChange={setTab} /></div>
      {tab === 'summary' ? <SummaryReport /> : <Quality />}
    </div>
  )
}
