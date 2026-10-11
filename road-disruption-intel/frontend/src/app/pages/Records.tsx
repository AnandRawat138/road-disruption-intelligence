import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowDown, ArrowUp, Check, Download, Play, Search, X } from 'lucide-react'
import { api, download, fmtDate, qs, useApi } from '../api'
import { usePublicSettings } from '../App'
import { CLASS_STATUS_LABEL, PREFILTER_LABEL, RELEVANCE_LABEL, REVIEW_LABEL, SEVERITIES, SEVERITY_META } from '../meta'
import { Card, CategoryBadge, ClassBadge, Confirm, Empty, ErrorBox, JobProgress, Loading, MultiSelect, Pagination,
  PrecisionBadge, ReviewBadge, Severity, useToast } from '../components/ui'
import RecordDrawer from '../components/RecordDrawer'

const LIST_KEYS = ['category', 'severity', 'relevance', 'classification_status', 'review_status', 'prefilter']
const SCALAR_KEYS = ['q', 'source', 'state', 'city', 'highway', 'date_from', 'date_to', 'has_coords', 'needs_review', 'incident_id']

export function useFilterParams() {
  const [sp, setSp] = useSearchParams()
  const filters = useMemo(() => {
    const f: Record<string, any> = {}
    LIST_KEYS.forEach(k => { const v = sp.get(k); if (v) f[k] = v.split(',') })
    SCALAR_KEYS.forEach(k => { const v = sp.get(k); if (v) f[k] = v })
    return f
  }, [sp])
  const update = (patch: Record<string, any>) => {
    const next = new URLSearchParams(sp)
    Object.entries(patch).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) next.delete(k)
      else next.set(k, Array.isArray(v) ? v.join(',') : String(v))
    })
    if (!('page' in patch)) next.delete('page')
    setSp(next, { replace: true })
  }
  return { sp, filters, update }
}

const opts = (m: Record<string, string>) => Object.entries(m).map(([value, label]) => ({ value, label }))

export default function Records({ reviewMode = false }: { reviewMode?: boolean }) {
  const { s } = usePublicSettings()
  const toast = useToast()
  const { sp, filters, update } = useFilterParams()
  const page = Number(sp.get('page') || 1)
  const pageSize = Number(sp.get('page_size') || 25)
  const sort = sp.get('sort') || 'published_at'
  const order = sp.get('order') || 'desc'
  const effective = reviewMode && !filters.review_status ? { ...filters, review_status: ['PENDING_REVIEW'] } : filters
  const query = qs({ ...effective, page, page_size: pageSize, sort, order })
  const { data, error, loading, reload } = useApi<any>(`/api/records${query}`)
  const facets = useApi<any>('/api/records/facets')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [open, setOpen] = useState<string | null>(null)
  const [q, setQ] = useState(filters.q || '')
  const [jobId, setJobId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<null | { kind: string; n: number }>(null)
  const [bulkLimit, setBulkLimit] = useState(100)

  const items: any[] = data?.items || []
  const allSel = items.length > 0 && items.every(r => selected.has(r.id))
  const toggleAll = () => setSelected(allSel ? new Set() : new Set(items.map(r => r.id)))
  const toggle = (id: string) => setSelected(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })
  const sortBy = (k: string) => update({ sort: k, order: sort === k && order === 'desc' ? 'asc' : 'desc' })

  const classify = async (body: any) => {
    try { const r = await api<any>('/api/classification/run', { body }); setJobId(r.job_id); toast('info', `Classification started with ${r.provider}`) }
    catch (e: any) { toast('error', e.message) }
  }
  const bulkReview = async (decision: string) => {
    try {
      const r = await api<any>('/api/records/bulk-review', { body: { ids: [...selected], decision } })
      toast('ok', `${r.updated} record(s) ${decision.toLowerCase()}${r.skipped.length ? `, ${r.skipped.length} skipped (not classified)` : ''}`)
      setSelected(new Set()); reload()
    } catch (e: any) { toast('error', e.message) }
  }
  const doExport = async (format: string) => {
    try { await download(`/api/records/export${qs({ ...effective, format, sort })}`, `records.${format}`) }
    catch (e: any) { toast('error', e.message) }
  }
  const SortH = ({ k, label }: { k: string; label: string }) => (
    <th aria-sort={sort === k ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button className="sort" onClick={() => sortBy(k)}>{label}{sort === k && (order === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
    </th>
  )
  const activeCount = Object.keys(filters).length
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{reviewMode ? 'Classification queue' : 'News & records'}</h1>
          <div className="sub">{reviewMode
            ? 'Classified records waiting for operator approval. Approving confirms the linked incident; rejecting removes the record from incident evidence. Flagged records list the reasons.'
            : 'Every imported or fetched article with its current classification. Search and filters run on the server; click a row for full evidence and provenance.'}</div>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => doExport('csv')}><Download size={14} />Export CSV</button>
          <button className="btn" onClick={() => doExport('json')}><Download size={14} />Export JSON</button>
        </div>
      </div>

      {jobId && <Card><JobProgress jobId={jobId} onDone={j => { setJobId(null); toast(j.status === 'COMPLETED' ? 'ok' : 'error', j.message || j.status); reload() }} /></Card>}

      <Card bodyClass="">
        <form className="filters" onSubmit={e => { e.preventDefault(); update({ q }) }} role="search">
          <label className="field" style={{ flex: '1 1 260px' }}>Search
            <span className="row" style={{ flexWrap: 'nowrap' }}>
              <input className="input" style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)} placeholder="Keyword, city, road, NH-48, source…" />
              <button className="btn" type="submit" aria-label="Search"><Search size={14} /></button>
            </span>
          </label>
          <MultiSelect label="Category" options={s.categories.map(c => ({ value: c.code, label: c.label }))} value={filters.category || []} onChange={v => update({ category: v })} />
          <MultiSelect label="Severity" options={SEVERITIES.map(x => ({ value: x, label: SEVERITY_META[x].label }))} value={filters.severity || []} onChange={v => update({ severity: v })} />
          <MultiSelect label="Relevance" options={opts(RELEVANCE_LABEL)} value={filters.relevance || []} onChange={v => update({ relevance: v })} />
          <MultiSelect label="Classification" options={opts(CLASS_STATUS_LABEL)} value={filters.classification_status || []} onChange={v => update({ classification_status: v })} />
          <MultiSelect label="Review" options={opts(REVIEW_LABEL)} value={filters.review_status || (reviewMode ? ['PENDING_REVIEW'] : [])} onChange={v => update({ review_status: v })} />
          <MultiSelect label="Pre-filter" options={opts(PREFILTER_LABEL)} value={filters.prefilter || []} onChange={v => update({ prefilter: v })} />
          <label className="field">State
            <select className="input" value={filters.state || ''} onChange={e => update({ state: e.target.value })}>
              <option value="">Any</option>{facets.data?.states.map((x: any) => <option key={x.value} value={x.value}>{x.value} ({x.count})</option>)}
            </select>
          </label>
          <label className="field">City
            <select className="input" value={filters.city || ''} onChange={e => update({ city: e.target.value })}>
              <option value="">Any</option>{facets.data?.cities.map((x: any) => <option key={x.value} value={x.value}>{x.value} ({x.count})</option>)}
            </select>
          </label>
          <label className="field">Highway
            <select className="input" value={filters.highway || ''} onChange={e => update({ highway: e.target.value })}>
              <option value="">Any</option>{facets.data?.highways.map((x: any) => <option key={x.value} value={x.value}>{x.value} ({x.count})</option>)}
            </select>
          </label>
          <label className="field">Source
            <select className="input" value={filters.source || ''} onChange={e => update({ source: e.target.value })} style={{ maxWidth: 180 }}>
              <option value="">Any</option>{facets.data?.sources.map((x: any) => <option key={x.value} value={x.value}>{x.value} ({x.count})</option>)}
            </select>
          </label>
          <label className="field">Published from<input type="date" className="input" value={filters.date_from || ''} onChange={e => update({ date_from: e.target.value })} /></label>
          <label className="field">to<input type="date" className="input" value={filters.date_to || ''} onChange={e => update({ date_to: e.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={filters.needs_review === 'true'} onChange={e => update({ needs_review: e.target.checked ? 'true' : '' })} />Flagged only</label>
          {activeCount > 0 && <button type="button" className="btn ghost" onClick={() => { setQ(''); update(Object.fromEntries([...LIST_KEYS, ...SCALAR_KEYS].map(k => [k, '']))) }}><X size={14} />Clear ({activeCount})</button>}
        </form>

        <div className="filters" style={{ background: 'var(--surface-2)' }}>
          <span className="small muted">{selected.size} selected</span>
          <button className="btn sm" disabled={!selected.size || !!jobId} onClick={() => classify({ article_ids: [...selected], reclassify: true })}><Play size={13} />Classify selected</button>
          <button className="btn sm ok" disabled={!selected.size} onClick={() => bulkReview('APPROVED')}><Check size={13} />Approve</button>
          <button className="btn sm danger" disabled={!selected.size} onClick={() => setConfirm({ kind: 'reject', n: selected.size })}><X size={13} />Reject</button>
          <span className="right row small">
            Classify all matching (max
            <input className="input" type="number" min={1} max={5000} value={bulkLimit} onChange={e => setBulkLimit(Math.max(1, Math.min(5000, Number(e.target.value) || 1)))} style={{ width: 80 }} aria-label="Maximum records to classify" />)
            <button className="btn sm" disabled={!data?.total || !!jobId} onClick={() => setConfirm({ kind: 'classify-all', n: Math.min(bulkLimit, data?.total || 0) })}><Play size={13} />Start</button>
          </span>
        </div>

        {error && <div style={{ padding: 12 }}><ErrorBox error={error} onRetry={reload} /></div>}
        {loading && !data ? <Loading /> : items.length === 0 ? (
          <Empty title="No records match these filters">
            {activeCount ? 'Try removing a filter or widening the date range. Unclassified records have no category, severity or location yet.' : 'Import historical data or fetch from a source.'}
          </Empty>
        ) : (
          <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 360px)', minHeight: 300 }}>
            <table className="table">
              <thead>
                <tr>
                  <th><input type="checkbox" checked={allSel} onChange={toggleAll} aria-label="Select all on this page" /></th>
                  <SortH k="category" label="Category" />
                  <SortH k="title" label="Title" />
                  <SortH k="city" label="Location" />
                  <th>Road</th>
                  <SortH k="event_start" label="Event time" />
                  <SortH k="published_at" label="Published" />
                  <SortH k="source" label="Source" />
                  <SortH k="severity" label="Severity" />
                  <th>Status</th>
                  <SortH k="updated_at" label="Updated" />
                </tr>
              </thead>
              <tbody style={{ opacity: loading ? 0.6 : 1 }}>
                {items.map(r => (
                  <tr key={r.id} className={`clickable ${selected.has(r.id) ? 'selected' : ''}`} onClick={() => setOpen(r.id)}
                      onKeyDown={e => { if (e.key === 'Enter') setOpen(r.id) }} tabIndex={0} aria-label={`Open ${r.title}`}>
                    <td onClick={e => e.stopPropagation()}><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label="Select record" /></td>
                    <td>{r.category ? <CategoryBadge code={r.category} /> : <span className="muted small">{r.relevance === 'IRRELEVANT' ? 'Irrelevant' : '—'}</span>}</td>
                    <td className="title-cell"><span className="t">{r.title}</span>{r.needs_review && <span className="badge warn" style={{ marginTop: 3 }}>Flagged</span>}</td>
                    <td className="small">{[r.locality, r.city, r.state].filter(Boolean).join(', ') || <span className="muted">—</span>}{r.geo_precision && <div><PrecisionBadge precision={r.geo_precision} /></div>}</td>
                    <td className="small">{[r.highway_number, r.road_name].filter(Boolean).join(' · ') || <span className="muted">—</span>}</td>
                    <td className="small nowrap">{r.event_start ? fmtDate(r.event_start) : <span className="muted">—</span>}</td>
                    <td className="small nowrap">{fmtDate(r.published_at)}</td>
                    <td className="small">{r.source_name || '—'}</td>
                    <td>{r.severity ? <Severity value={r.severity} /> : <span className="muted">—</span>}</td>
                    <td><div className="stack" style={{ gap: 3 }}><ClassBadge status={r.classification_status} /><ReviewBadge status={r.review_status} /></div></td>
                    <td className="small nowrap">{fmtDate(r.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={page} pages={data.pages} total={data.total} onPage={p => update({ page: p })} pageSize={pageSize} onPageSize={n => update({ page_size: n })} />}
      </Card>

      {open && <RecordDrawer id={open} onClose={() => setOpen(null)} onChanged={reload} />}
      {confirm?.kind === 'reject' && (
        <Confirm title={`Reject ${confirm.n} record(s)?`} danger confirmLabel="Reject"
                 message="Rejected records are kept (with history) but removed from incident evidence. Incidents left without evidence are dismissed. You can change the decision later."
                 onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); bulkReview('REJECTED') }} />
      )}
      {confirm?.kind === 'classify-all' && (
        <Confirm title={`Classify up to ${confirm.n.toLocaleString('en-IN')} record(s)?`} confirmLabel="Start classification"
                 message={<>Records matching the current filters (newest first) are sent to the active LLM provider in the background.
                   Already-classified records with the same model and prompt are skipped. With a local model this takes roughly 5–15 seconds per record; cloud providers may incur API charges.</>}
                 onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); classify({ filters: effective, limit: confirm.n }) }} />
      )}
    </div>
  )
}
