import { useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { api, fmtDate, useApi } from '../api'
import { Badge, CategoryBadge, Confirm, Drawer, ErrorBox, Loading, Notice, PrecisionBadge, ReviewBadge, Severity,
  StatusBadge, useToast } from './ui'
import RecordDrawer from './RecordDrawer'

export default function IncidentDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged?: () => void }) {
  const { data, error, loading, reload } = useApi<any>(`/api/incidents/${id}`)
  const toast = useToast()
  const [note, setNote] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [mergeTarget, setMergeTarget] = useState('')
  const [confirmMerge, setConfirmMerge] = useState(false)
  const [record, setRecord] = useState<string | null>(null)
  const changed = () => { reload(); onChanged?.() }

  const setStatus = async (status: string) => {
    try { await api(`/api/incidents/${id}/status`, { body: { status, note: note || undefined } }); toast('ok', `Incident marked ${status.toLowerCase()}`); setNote(''); changed() }
    catch (e: any) { toast('error', e.message) } finally { setPending(null) }
  }
  const merge = async () => {
    try { const r = await api<any>(`/api/incidents/${id}/merge`, { body: { target_id: mergeTarget.trim(), confirm: true, note: note || undefined } }); toast('ok', `${r.articles_moved} article(s) moved`); changed() }
    catch (e: any) { toast('error', e.message) } finally { setConfirmMerge(false) }
  }
  const detach = async (articleId: string) => {
    try { await api(`/api/incidents/${id}/detach`, { body: { article_id: articleId } }); toast('ok', 'Article detached (kept as a record)'); changed() }
    catch (e: any) { toast('error', e.message) }
  }
  const i = data?.incident
  return (
    <Drawer title={<div><div className="small muted">Incident · {id}</div><h2 style={{ marginTop: 2 }}>{i?.title || 'Incident'}</h2></div>} onClose={onClose}>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {i && (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            <CategoryBadge code={i.category} /><Severity value={i.severity} /><StatusBadge status={i.status} stale={i.is_stale} />
            {i.has_conflict && <Badge tone="warn">Conflicting reports</Badge>}
          </div>
          {i.is_stale && <div style={{ marginBottom: 10 }}><Notice kind="warn">No new report since {fmtDate(i.last_reported_at)}. This incident is not verified as current – do not treat it as a live closure without checking.</Notice></div>}
          <dl className="kv">
            <dt>Location</dt><dd>{[i.locality, i.city, i.state].filter(Boolean).join(', ') || '—'} <PrecisionBadge precision={i.geo_precision} /></dd>
            <dt>Road / highway</dt><dd>{[i.road_name, i.highway_number].filter(Boolean).join(' · ') || <span className="muted">not stated</span>}</dd>
            <dt>Event window</dt><dd>{i.event_start ? fmtDate(i.event_start) : 'start not stated'} → {i.event_end ? fmtDate(i.event_end) : 'end not stated'} · reported as <Badge>{i.time_status || 'UNKNOWN'}</Badge></dd>
            <dt>First / last report</dt><dd>{fmtDate(i.first_reported_at)} → {fmtDate(i.last_reported_at)}</dd>
            <dt>Last verified</dt><dd>{i.last_verified_at ? `${fmtDate(i.last_verified_at)} (operator)` : <span className="muted">never verified by an operator</span>}</dd>
            <dt>Evidence</dt><dd>{i.article_count} linked article(s)</dd>
          </dl>
          {i.conflict_notes?.length > 0 && <div style={{ marginTop: 10 }}><Notice kind="warn"><strong>Conflicts for review:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{i.conflict_notes.map((n: string, k: number) => <li key={k}>{n}</li>)}</ul></Notice></div>}

          <div className="section-title">Status</div>
          <div className="stack" style={{ gap: 8 }}>
            <label className="field">Note (recorded in history)<input className="input" value={note} onChange={e => setNote(e.target.value)} maxLength={500} /></label>
            <div className="row">
              {data.allowed_transitions.map((t: string) => (
                <button key={t} className={`btn ${t === 'DISMISSED' ? 'danger' : t === 'CONFIRMED' ? 'ok' : ''}`}
                        onClick={() => (t === 'DISMISSED' || t === 'RESOLVED' ? setPending(t) : setStatus(t))}>Mark {t.toLowerCase()}</button>
              ))}
            </div>
          </div>

          <div className="section-title">Linked articles</div>
          <ul className="timeline-list">
            {data.articles.map((a: any) => (
              <li key={a.id}>
                <div className="row">
                  <button className="btn ghost sm" style={{ textAlign: 'left', whiteSpace: 'normal', fontWeight: 600 }} onClick={() => setRecord(a.id)}>{a.title}</button>
                  {a.source_url && <a href={a.source_url} target="_blank" rel="noopener noreferrer" className="btn sm right" aria-label="Open source article"><ExternalLink size={12} /></a>}
                  <button className="btn sm" onClick={() => detach(a.id)} title="Remove this article from the incident (the record is kept)">Detach</button>
                </div>
                <div className="small muted">{a.source_name} · {fmtDate(a.published_at)} · {a.classified_by} · confidence {a.model_confidence || '—'} <ReviewBadge status={a.review_status} /></div>
                {a.evidence_excerpt && <div className="evidence" style={{ marginTop: 4 }}>“{a.evidence_excerpt}” {!a.evidence_verified && <Badge tone="warn">not verified in source</Badge>}</div>}
              </li>
            ))}
          </ul>

          <div className="section-title">Merge into another incident</div>
          <div className="row">
            <input className="input" placeholder="Target incident id (INC_…)" value={mergeTarget} onChange={e => setMergeTarget(e.target.value)} style={{ flex: 1 }} />
            <button className="btn" disabled={!mergeTarget.trim()} onClick={() => setConfirmMerge(true)}>Merge…</button>
          </div>
          <div className="xs muted" style={{ marginTop: 4 }}>Duplicate suggestions are listed under Analytics &amp; reports → Data quality.</div>

          <div className="section-title">History</div>
          <ul className="timeline-list">
            {data.history.map((h: any) => <li key={h.id}><span className="muted">{fmtDate(h.changed_at)}</span> · <strong>{h.actor}</strong>: {h.from_status || '—'} → {h.to_status} {h.note && <span className="muted">({h.note})</span>}</li>)}
          </ul>
        </>
      )}
      {pending && <Confirm title={`Mark incident ${pending.toLowerCase()}?`} danger={pending === 'DISMISSED'} confirmLabel={`Mark ${pending.toLowerCase()}`}
        message={pending === 'DISMISSED' ? 'Dismissed incidents are hidden from active views but kept with their history and articles. This can be reversed.' : 'The incident and its history are preserved; new conflicting reports will re-open it for review.'}
        onCancel={() => setPending(null)} onConfirm={() => setStatus(pending)} />}
      {confirmMerge && <Confirm title="Merge incidents?" confirmLabel="Merge"
        message={`All articles of this incident move to ${mergeTarget}. This incident is then dismissed with a note. Source articles are never deleted.`}
        onCancel={() => setConfirmMerge(false)} onConfirm={merge} />}
      {record && <RecordDrawer id={record} onClose={() => setRecord(null)} onChanged={changed} />}
    </Drawer>
  )
}
