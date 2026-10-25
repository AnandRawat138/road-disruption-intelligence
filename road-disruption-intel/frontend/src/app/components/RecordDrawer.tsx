import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ExternalLink, Pencil, RotateCcw, X } from 'lucide-react'
import { api, fmtDate, useApi } from '../api'
import { usePublicSettings } from '../App'
import { CATEGORY_META, RELEVANCE_LABEL, SEVERITIES, TIME_STATUS } from '../meta'
import { Badge, CategoryBadge, ClassBadge, Drawer, ErrorBox, JobProgress, Loading, Notice, PrecisionBadge, ReviewBadge,
  Severity, useToast } from './ui'

const EDIT_FIELDS: { key: string; label: string; type?: 'select' | 'datetime' | 'number' | 'textarea'; options?: string[] }[] = [
  { key: 'relevance', label: 'Relevance', type: 'select', options: Object.keys(RELEVANCE_LABEL) },
  { key: 'category', label: 'Category', type: 'select', options: Object.keys(CATEGORY_META) },
  { key: 'severity', label: 'Severity', type: 'select', options: SEVERITIES },
  { key: 'time_status', label: 'Event status', type: 'select', options: TIME_STATUS },
  { key: 'state', label: 'State' }, { key: 'city', label: 'City' }, { key: 'locality', label: 'Locality' },
  { key: 'road_name', label: 'Road name' }, { key: 'highway_number', label: 'Highway number' },
  { key: 'direction', label: 'Direction' }, { key: 'event_start', label: 'Event start (IST)', type: 'datetime' },
  { key: 'event_end', label: 'Event end (IST)', type: 'datetime' }, { key: 'reported_delay', label: 'Reported delay' },
  { key: 'latitude', label: 'Latitude (manual)', type: 'number' }, { key: 'longitude', label: 'Longitude (manual)', type: 'number' },
  { key: 'summary', label: 'Summary', type: 'textarea' }, { key: 'advisory_action', label: 'Advisory action', type: 'textarea' },
]

function toLocalInput(iso?: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const ist = new Date(d.getTime() + 330 * 60000)
  return ist.toISOString().slice(0, 16)
}

export default function RecordDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged?: () => void }) {
  const { data, error, loading, reload } = useApi<any>(`/api/records/${id}`)
  const llm = useApi<any>('/api/llm/config')
  const toast = useToast()
  const { s } = usePublicSettings()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Record<string, any>>({})
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [provider, setProvider] = useState<string>('')
  const [raw, setRaw] = useState<{ id: string; text: string } | null>(null)

  const changed = () => { reload(); onChanged?.() }
  const review = async (decision: string) => {
    setBusy(true)
    try { await api(`/api/records/${id}/review`, { body: { decision, note: note || undefined } }); toast('ok', `Record ${decision.toLowerCase().replace('_', ' ')}`); changed() }
    catch (e: any) { toast('error', e.message) } finally { setBusy(false) }
  }
  const reclassify = async () => {
    try {
      const choice = provider === '__ml' ? { engine: 'ml' } : provider ? { engine: 'llm', provider } : {}
      const r = await api<any>('/api/classification/run', { body: { article_ids: [id], reclassify: true, ...choice } })
      setJobId(r.job_id)
    } catch (e: any) { toast('error', e.message) }
  }
  const startEdit = () => {
    const c = data.classification || {}
    const f: Record<string, any> = {}
    EDIT_FIELDS.forEach(x => { f[x.key] = x.type === 'datetime' ? toLocalInput(c[x.key]) : (c[x.key] ?? '') })
    setForm(f)
    setEditing(true)
  }
  const saveEdit = async () => {
    const c = data.classification || {}
    const changes: Record<string, any> = {}
    EDIT_FIELDS.forEach(x => {
      let v = form[x.key]
      const orig = x.type === 'datetime' ? toLocalInput(c[x.key]) : (c[x.key] ?? '')
      if (String(v) === String(orig)) return
      if (x.type === 'datetime') v = v ? `${v}:00+05:30` : null
      else if (x.type === 'number') v = v === '' ? null : Number(v)
      else v = v === '' ? null : v
      changes[x.key] = v
    })
    if (!Object.keys(changes).length) { setEditing(false); return }
    setBusy(true)
    try {
      await api(`/api/records/${id}/classification`, { method: 'PATCH', body: { changes, note: note || undefined } })
      toast('ok', 'Correction saved as a new human-reviewed version')
      setEditing(false)
      changed()
    } catch (e: any) { toast('error', e.message) } finally { setBusy(false) }
  }
  const showRaw = async (clsId: string) => {
    try { const r = await api<any>(`/api/records/${id}/classifications/${clsId}/raw`); setRaw({ id: clsId, text: r.raw_output || r.error || '(empty)' }) }
    catch (e: any) { toast('error', e.message) }
  }

  const a = data?.article
  const c = data?.classification
  const title = a ? a.title : 'Record'
  return (
    <Drawer title={<div><div className="small muted">News record · {id}</div><h2 style={{ marginTop: 2 }}>{title}</h2></div>} onClose={onClose}>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {a && (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            <ClassBadge status={a.classification_status} /><ReviewBadge status={a.review_status} />
            {c && <CategoryBadge code={c.category} />}{c && <Severity value={c.severity} />}
            {a.source_url && <a className="btn sm right" href={a.source_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={13} />Open source</a>}
          </div>

          <dl className="kv">
            <dt>Source</dt><dd>{a.source_name || '—'} <span className="muted small">({a.connector}, {a.source_type})</span></dd>
            <dt>Published</dt><dd>{fmtDate(a.published_at)} IST</dd>
            <dt>Retrieved</dt><dd>{fmtDate(a.retrieved_at)} IST · ingested {fmtDate(a.ingested_at)}</dd>
            {a.query_used && <><dt>Found by query</dt><dd>“{a.query_used}”{a.query_city && <span className="muted small"> (search context only, not the event location)</span>}</dd></>}
            <dt>Keyword pre-filter</dt><dd>{a.prefilter_label || '—'} <span className="muted small">{a.prefilter_reason}</span></dd>
            {data.incident && <><dt>Incident</dt><dd><Link to={`/disruptions?incident=${data.incident.id}`}>{data.incident.title}</Link> <Badge>{data.incident.status}</Badge></dd></>}
          </dl>

          <div className="section-title">Original text</div>
          {a.headline_only && <div style={{ marginBottom: 6 }}><Notice kind="warn">Only the headline/RSS snippet is available for this record; the article body was not provided by the source.</Notice></div>}
          <div className="source-text">{[a.title, a.summary_text !== a.title ? a.summary_text : null, a.body_text].filter(Boolean).join('\n\n')}</div>

          <div className="section-title">Classification</div>
          {!c ? (
            <Notice kind="info">This record has not been classified yet.</Notice>
          ) : editing ? (
            <div className="stack">
              <Notice kind="info">Saving creates a new <strong>human</strong> version. The model output is kept in the history.</Notice>
              <div className="form-grid">
                {EDIT_FIELDS.map(x => (
                  <label key={x.key} className="field" style={x.type === 'textarea' ? { gridColumn: '1 / -1' } : undefined}>{x.label}
                    {x.type === 'select' ? (
                      <select className="input" value={form[x.key] || ''} onChange={e => setForm({ ...form, [x.key]: e.target.value })}>
                        {x.options!.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : x.type === 'textarea' ? (
                      <textarea className="input" value={form[x.key] || ''} onChange={e => setForm({ ...form, [x.key]: e.target.value })} />
                    ) : (
                      <input className="input" type={x.type === 'datetime' ? 'datetime-local' : x.type === 'number' ? 'number' : 'text'} step="any"
                             value={form[x.key] ?? ''} onChange={e => setForm({ ...form, [x.key]: e.target.value })} />
                    )}
                  </label>
                ))}
              </div>
              <span className="xs muted">Manual latitude/longitude mark the location as operator-placed. Leave blank to keep the geocoded approximation.</span>
              <label className="field">Correction note (optional)<input className="input" value={note} onChange={e => setNote(e.target.value)} maxLength={500} /></label>
              <div className="row"><button className="btn primary" onClick={saveEdit} disabled={busy}>Save correction</button><button className="btn" onClick={() => setEditing(false)}>Cancel</button></div>
            </div>
          ) : (
            <>
              <dl className="kv">
                <dt>Relevance</dt><dd>{RELEVANCE_LABEL[c.relevance] || c.relevance}</dd>
                <dt>Summary</dt><dd>{c.summary || '—'}</dd>
                <dt>Location</dt><dd>{[c.locality, c.city, c.state, c.country].filter(Boolean).join(', ') || <span className="muted">unknown</span>}</dd>
                <dt>Road / highway</dt><dd>{[c.road_name, c.highway_number].filter(Boolean).join(' · ') || <span className="muted">not stated</span>}{c.direction && ` (${c.direction})`}</dd>
                {c.affected_segment && <><dt>Affected segment</dt><dd>{c.affected_segment}</dd></>}
                <dt>Event time</dt><dd>{c.event_start ? fmtDate(c.event_start) : 'start not stated'} → {c.event_end ? fmtDate(c.event_end) : 'end not stated'} · <Badge>{c.time_status || 'UNKNOWN'}</Badge> <span className="muted small">(as reported at publication)</span></dd>
                {c.reported_delay && <><dt>Reported delay</dt><dd>{c.reported_delay}</dd></>}
                <dt>Map position</dt><dd><PrecisionBadge precision={c.geo_precision} /> {c.latitude != null && <span className="mono small">{c.latitude.toFixed(4)}, {c.longitude.toFixed(4)}</span>} <span className="muted small">{c.geo_method} {c.geo_display_name ? `· ${c.geo_display_name}` : ''}</span></dd>
                <dt>Model confidence</dt><dd>{c.model_confidence || '—'} <span className="muted small">{c.provider === 'ml' ? "(from the ML classifier's probabilities – not verified accuracy)" : '(model self-assessment, not a calibrated probability)'}</span></dd>
                <dt>Validation</dt><dd><Badge tone={c.validation_status === 'PASSED' ? 'ok' : 'warn'}>{c.validation_status}</Badge> · evidence {c.evidence_verified ? <Badge tone="ok">found in source</Badge> : <Badge tone="warn">not verified</Badge>}</dd>
                <dt>Produced by</dt><dd>{c.origin === 'HUMAN' ? `Human correction by ${c.created_by}` : `${c.provider} / ${c.model}`} · prompt {c.prompt_version || '—'} · {fmtDate(c.created_at)}</dd>
              </dl>
              {c.evidence_excerpt && <><div className="section-title">Supporting excerpt</div><div className="evidence">“{c.evidence_excerpt}”</div></>}
              {c.advisory_action && <><div className="section-title">Suggested operational action (advisory)</div><div className="small">{c.advisory_action}</div></>}
              {(c.validation_issues?.length > 0 || c.review_reasons?.length > 0 || c.missing_fields?.length > 0) && (
                <div className="stack" style={{ marginTop: 12, gap: 6 }}>
                  {c.review_reasons?.length > 0 && <Notice kind="warn"><strong>Flagged for review:</strong> {c.review_reasons.join('; ')}</Notice>}
                  {c.validation_issues?.length > 0 && <Notice kind="info"><strong>Validation notes:</strong> {c.validation_issues.join('; ')}</Notice>}
                  {c.missing_fields?.length > 0 && <div className="small muted">Missing in source: {c.missing_fields.join(', ')}</div>}
                </div>
              )}
            </>
          )}

          {!editing && (
            <>
              <div className="section-title">Actions</div>
              <div className="stack" style={{ gap: 8 }}>
                <label className="field">Review note (optional)<input className="input" value={note} onChange={e => setNote(e.target.value)} maxLength={500} /></label>
                <div className="row">
                  <button className="btn ok" onClick={() => review('APPROVED')} disabled={busy || !c}><Check size={14} />Approve</button>
                  <button className="btn danger" onClick={() => review('REJECTED')} disabled={busy || !c}><X size={14} />Reject</button>
                  {c && <button className="btn" onClick={startEdit}><Pencil size={14} />Edit fields</button>}
                </div>
                <div className="row">
                  <select className="input" value={provider} onChange={e => setProvider(e.target.value)} aria-label="Classifier to use">
                    <option value="">Configured engine</option>
                    {(llm.data?.available_providers || []).map((p: string) => <option key={p} value={p}>LLM: {p}</option>)}
                    <option value="__ml">ML model (local, no LLM)</option>
                  </select>
                  <button className="btn" onClick={reclassify} disabled={!!jobId}><RotateCcw size={14} />{c ? 'Reclassify' : 'Classify now'}</button>
                </div>
                {jobId && <JobProgress jobId={jobId} compact onDone={j => { setJobId(null); toast(j.status === 'COMPLETED' ? 'ok' : 'error', j.message || j.status); changed() }} />}
              </div>
            </>
          )}

          <div className="section-title">Classification history ({data.classification_history.length})</div>
          <ul className="timeline-list">
            {data.classification_history.map((h: any) => (
              <li key={h.id} className="row">
                <span>v{h.version}</span>
                <Badge tone={h.status === 'VALID' ? 'ok' : 'danger'}>{h.status}</Badge>
                {h.is_current && <Badge tone="blue">current</Badge>}
                <span>{h.origin === 'HUMAN' ? `human (${h.created_by})` : `${h.provider}/${h.model}`}</span>
                <span className="muted">{fmtDate(h.created_at)}{h.latency_ms ? ` · ${(h.latency_ms / 1000).toFixed(1)} s` : ''}</span>
                {h.error && <span className="small" style={{ color: 'var(--danger)' }}>{h.error.slice(0, 160)}</span>}
                {h.has_raw_output && <button className="btn sm ghost right" onClick={() => showRaw(h.id)}>Raw output</button>}
              </li>
            ))}
            {!data.classification_history.length && <li className="muted">No attempts yet.</li>}
          </ul>
          {raw && <pre className="raw" aria-label="Raw model output">{raw.text}</pre>}

          <div className="section-title">Provenance ({data.sightings.length} sighting{data.sightings.length === 1 ? '' : 's'})</div>
          <ul className="timeline-list">
            {data.sightings.slice(0, 15).map((sg: any) => (
              <li key={sg.id}><span className="muted">{fmtDate(sg.seen_at)}</span> · {sg.origin} {sg.external_id && <span className="mono xs">[{sg.external_id}]</span>} {sg.query_used && <span className="muted">q: “{sg.query_used}”</span>} {sg.match_method && sg.match_method !== 'new' && <Badge>matched by {sg.match_method}</Badge>}</li>
            ))}
          </ul>
          {Object.keys(a.dataset_flags || {}).length > 0 && <div className="small muted" style={{ marginTop: 6 }}>Historical dataset flags: <span className="mono xs">{JSON.stringify(a.dataset_flags)}</span></div>}

          {data.audit.length > 0 && <>
            <div className="section-title">Audit trail</div>
            <ul className="timeline-list">
              {data.audit.map((e: any) => <li key={e.id}><span className="muted">{fmtDate(e.at)}</span> · <strong>{e.actor}</strong> {e.action.replace('_', ' ')} {e.details?.new && typeof e.details.new === 'string' ? `→ ${e.details.new}` : ''} {e.details?.note ? `(“${e.details.note}”)` : ''}</li>)}
            </ul>
          </>}
          <div className="footer-note">{s.branding.product_name} · model output is advisory; verify with the source before operational use.</div>
        </>
      )}
    </Drawer>
  )
}
