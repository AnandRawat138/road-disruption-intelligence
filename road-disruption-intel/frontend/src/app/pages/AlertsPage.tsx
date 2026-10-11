import { Link } from 'react-router-dom'
import { api, fmtDate, useApi } from '../api'
import { Badge, Card, Empty, ErrorBox, Loading, Severity, useToast } from '../components/ui'

export default function AlertsPage() {
  const { data, error, loading, reload } = useApi<any>('/api/alerts', 30000)
  const rules = useApi<any>('/api/settings/alerts')
  const toast = useToast()
  const readAll = async () => { try { await api('/api/alerts/read-all', { method: 'POST' }); reload() } catch (e: any) { toast('error', e.message) } }
  const read = async (id: number) => { try { await api(`/api/alerts/${id}/read`, { method: 'POST' }); reload() } catch (e: any) { toast('error', e.message) } }
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Alerts</h1><div className="sub">In-app alerts only (no email/SMS is configured). Each incident raises at most one alert per rule.
          {rules.data && <> Current rule: {rules.data.enabled ? <>severity ≥ <strong>{rules.data.min_severity}</strong> when status becomes <strong>{rules.data.on_status.join(', ')}</strong>{rules.data.categories.length ? ` for ${rules.data.categories.join(', ')}` : ''}.</> : 'alerts disabled.'} <Link to="/system">Change</Link></>}</div></div>
        <div className="actions"><button className="btn" onClick={readAll} disabled={!data?.unread}>Mark all read</button></div>
      </div>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data ? <Loading /> : (
        <Card bodyClass="">
          {!data.items.length ? <Empty title="No alerts">Alerts appear when an incident matching the rule is confirmed (for example by approving a high-severity record).</Empty> : (
            <table className="table">
              <thead><tr><th>Raised</th><th>Severity</th><th>Message</th><th>Rule</th><th /></tr></thead>
              <tbody>{data.items.map((a: any) => (
                <tr key={a.id} style={{ fontWeight: a.read_at ? 400 : 600 }}>
                  <td className="small nowrap">{fmtDate(a.created_at)}</td><td><Severity value={a.severity} /></td>
                  <td><Link to={`/disruptions?incident=${a.incident_id}`}>{a.message}</Link></td><td className="xs muted">{a.rule}</td>
                  <td>{a.read_at ? <Badge>read</Badge> : <button className="btn sm" onClick={() => read(a.id)}>Mark read</button>}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  )
}
