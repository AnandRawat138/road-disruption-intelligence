import { useRef, useState } from 'react'
import { Download, FileUp, Play } from 'lucide-react'
import { api, download, fmtDate, fmtNum, useApi } from '../api'
import { Badge, Card, ErrorBox, JobProgress, Loading, Notice, Pagination, useToast } from '../components/ui'

export default function DataImport() {
  const toast = useToast()
  const files = useApi<any>('/api/imports/files')
  const [page, setPage] = useState(1)
  const batches = useApi<any>(`/api/imports/batches?page=${page}&page_size=15`, 5000)
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [jobs, setJobs] = useState<{ job_id: string; file: string }[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const run = async (paths: string[]) => {
    try { const r = await api<any>('/api/imports/run', { body: { paths } }); setJobs(j => [...r.batches.map((b: any) => ({ job_id: b.job_id, file: b.file })), ...j]); setSel(new Set()) }
    catch (e: any) { toast('error', e.message) }
  }
  const upload = async () => {
    const f = fileRef.current?.files?.[0]
    if (!f) return
    const form = new FormData()
    form.append('file', f)
    setUploading(true)
    try { const r = await api<any>('/api/imports/upload', { form }); setJobs(j => [{ job_id: r.job_id, file: r.file }, ...j]); if (fileRef.current) fileRef.current.value = '' }
    catch (e: any) { toast('error', e.message) } finally { setUploading(false) }
  }
  const fmtSize = (b: number) => b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(0)} KB`
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Data import</h1>
          <div className="sub">Imports read source files without modifying them. Re-importing is safe: articles already in the database are matched by canonical URL, source id or content and counted as duplicates.</div></div>
      </div>

      <Card title="Historical data folder" actions={files.data && <span className="small muted mono">{files.data.data_dir}</span>} bodyClass="">
        {files.error && <div style={{ padding: 12 }}><ErrorBox error={files.error} onRetry={files.reload} /></div>}
        {!files.data ? <Loading label="Scanning files…" /> : !files.data.data_dir_exists ? (
          <div style={{ padding: 14 }}><Notice kind="warn">The historical data folder was not found. Set HISTORICAL_DATA_DIR in .env or place files in a <code>data</code> folder next to the project.</Notice></div>
        ) : (
          <>
            <div style={{ padding: '10px 14px' }}><Notice kind="info">Recommended order: raw → deduplicated → relevant → weak labels → evaluation splits. Later files add provenance flags to the same articles.
              Note: the earlier “weak label” file contains no event labels (only a constant 0.85 confidence), so it is imported as provenance only — it does not classify anything.</Notice></div>
            <table className="table">
              <thead><tr><th><span className="sr-only">Select</span></th><th>File</th><th>Role</th><th>Rows</th><th>Size</th><th>Last import</th></tr></thead>
              <tbody>
                {files.data.files.map((f: any) => (
                  <tr key={f.path}>
                    <td><input type="checkbox" aria-label={`Select ${f.name}`} checked={sel.has(f.path)} onChange={() => setSel(p => { const n = new Set(p); n.has(f.path) ? n.delete(f.path) : n.add(f.path); return n })} /></td>
                    <td><span className="mono small">{f.name}</span></td>
                    <td><Badge>{f.role}</Badge><div className="xs muted">{f.role_description}</div></td>
                    <td>{fmtNum(f.rows)}</td>
                    <td className="nowrap">{fmtSize(f.size_bytes)}</td>
                    <td className="small">{f.last_batch ? <><Badge tone={f.last_batch.status.startsWith('COMPLETED') ? 'ok' : f.last_batch.status === 'RUNNING' ? 'blue' : 'danger'}>{f.last_batch.status}</Badge> {fmtDate(f.last_batch.finished_at)}<div className="xs muted">{f.last_batch.message}</div></> : <span className="muted">never imported</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="filters" style={{ borderTop: '1px solid var(--border)', borderBottom: 0 }}>
              <button className="btn primary" disabled={!sel.size} onClick={() => run([...sel])}><Play size={14} />Import selected ({sel.size})</button>
              <button className="btn" onClick={() => run(files.data.files.filter((f: any) => f.role !== 'LEGACY_DB').map((f: any) => f.path))}>Import all data files</button>
            </div>
          </>
        )}
      </Card>

      <Card title="Upload a file">
        <div className="row">
          <input ref={fileRef} type="file" accept=".jsonl,.ndjson,.json,.csv" className="input" aria-label="File to import" />
          <button className="btn" onClick={upload} disabled={uploading}><FileUp size={14} />{uploading ? 'Uploading…' : 'Upload & import'}</button>
        </div>
        <div className="small muted" style={{ marginTop: 6 }}>Accepted: JSONL, JSON array, CSV (UTF-8). Recognised columns: title/headline, url/source_url/link, description/summary, article_text/content, source/publisher, publication_time/published_at/date, language, query, article_id. Rows without a title, or without any URL/id/date, are rejected and listed in the error report.</div>
      </Card>

      {jobs.length > 0 && <Card title="Running imports">{jobs.map(j => <div key={j.job_id} style={{ marginBottom: 10 }}><div className="small mono">{j.file}</div><JobProgress jobId={j.job_id} compact onDone={() => { files.reload(); batches.reload() }} /></div>)}</Card>}

      <Card title="Import history" bodyClass="">
        {!batches.data ? <Loading /> : (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>File</th><th>Status</th><th>Finished</th><th>Discovered</th><th>Imported</th><th>Duplicate</th><th>Invalid</th><th>Failed</th><th>Skipped</th><th>Errors</th></tr></thead>
                <tbody>
                  {batches.data.items.map((b: any) => (
                    <tr key={b.id}>
                      <td className="small"><span className="mono">{b.file_name}</span><div className="xs muted">{b.file_role} · sha256 {b.file_sha256?.slice(0, 12)}…</div></td>
                      <td><Badge tone={b.status === 'COMPLETED' ? 'ok' : b.status === 'COMPLETED_WITH_ERRORS' ? 'warn' : ['RUNNING', 'QUEUED'].includes(b.status) ? 'blue' : 'danger'}>{b.status}</Badge></td>
                      <td className="small nowrap">{fmtDate(b.finished_at)}</td>
                      <td>{fmtNum(b.discovered)}</td><td>{fmtNum(b.imported)}</td><td>{fmtNum(b.duplicate)}</td>
                      <td>{fmtNum(b.invalid)}</td><td>{fmtNum(b.failed)}</td><td>{fmtNum(b.skipped)}</td>
                      <td>{b.error_rows > 0 ? <button className="btn sm" onClick={() => download(`/api/imports/batches/${b.id}/errors.csv`, `${b.id}_errors.csv`).catch(e => toast('error', e.message))}><Download size={12} />{b.error_rows} rows</button> : <span className="muted">none</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pages={batches.data.pages} total={batches.data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
