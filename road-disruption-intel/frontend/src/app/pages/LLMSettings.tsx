import { Fragment, useEffect, useState } from 'react'
import { Bot, Cpu, Download, KeyRound, Plug, RefreshCw, Save, Trash2 } from 'lucide-react'
import { api, fmtDate, useApi } from '../api'
import { Badge, Card, Confirm, ErrorBox, JobProgress, Loading, Notice, useToast } from '../components/ui'

const PROVIDER_INFO: Record<string, { title: string; secret?: string; text: string }> = {
  ollama: { title: 'Local Ollama', text: 'Runs on this computer. No data leaves the machine and there are no API charges. Speed depends on the GPU/CPU.' },
  openai_compatible: { title: 'OpenAI / OpenAI-compatible', secret: 'OPENAI_API_KEY', text: 'OpenAI or any server exposing /v1/chat/completions (e.g. Azure-compatible gateways, Groq, Together, LM Studio, vLLM). Set the base URL accordingly. Usage is billed by the provider.' },
  anthropic: { title: 'Anthropic', secret: 'ANTHROPIC_API_KEY', text: 'Anthropic Messages API with tool-based structured output. Usage is billed by Anthropic.' },
}

function SecretField({ name, status, onChanged }: { name: string; status: any; onChanged: () => void }) {
  const toast = useToast()
  const [v, setV] = useState('')
  const [confirm, setConfirm] = useState(false)
  const save = async () => {
    try { await api(`/api/secrets/${name}`, { method: 'PUT', body: { value: v } }); setV(''); toast('ok', `${name} saved on the server`); onChanged() }
    catch (e: any) { toast('error', e.message) }
  }
  const remove = async () => {
    try { await api(`/api/secrets/${name}`, { method: 'DELETE' }); toast('ok', `${name} removed`); onChanged() } catch (e: any) { toast('error', e.message) } finally { setConfirm(false) }
  }
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row small"><KeyRound size={14} /><code>{name}</code>
        {status?.configured ? <Badge tone="ok">set ({status.source === 'environment' ? 'environment variable' : 'stored on server'})</Badge> : <Badge tone="warn">not set</Badge>}</div>
      <div className="row">
        <input className="input" type="password" autoComplete="off" placeholder={status?.configured ? 'Enter a new key to replace' : 'Paste API key'} value={v} onChange={e => setV(e.target.value)} style={{ flex: 1, minWidth: 220 }} aria-label={`${name} value`} />
        <button className="btn" onClick={save} disabled={!v.trim() || status?.source === 'environment'}><Save size={14} />Save key</button>
        {status?.removable && <button className="btn danger" onClick={() => setConfirm(true)}><Trash2 size={14} />Remove</button>}
      </div>
      {status?.source === 'environment' && <span className="xs muted">Set via environment/.env – change it there.</span>}
      {confirm && <Confirm title={`Remove ${name}?`} danger confirmLabel="Remove key" message="The key is deleted from runtime/secrets.json. Classification with this provider will stop working until a new key is set." onCancel={() => setConfirm(false)} onConfirm={remove} />}
    </div>
  )
}

const pct = (v?: number) => (v === undefined || v === null ? '—' : `${(v * 100).toFixed(1)}%`)

function MetricRow({ label, m }: { label: string; m: any }) {
  if (!m) return null
  if (!m.evaluated) return <tr><td>{label}</td><td colSpan={4} className="muted small">Not evaluated – {m.reason}</td></tr>
  return (
    <tr>
      <td>{label}</td><td>{m.n?.toLocaleString('en-IN')}</td><td>{pct(m.accuracy)}</td><td>{pct(m.macro_f1)}</td>
      <td>{pct(m.majority_baseline)}{m.labelled_only && <div className="xs muted">labelled rows only: {pct(m.labelled_only.accuracy)} acc · {pct(m.labelled_only.macro_f1)} F1</div>}
        {m.not_learned?.length > 0 && <div className="xs muted">too few examples: {m.not_learned.join(', ')}</div>}</td>
    </tr>
  )
}

function EnginePanel() {
  const toast = useToast()
  const st = useApi<any>('/api/ml/status')
  const [form, setForm] = useState<any>(null)
  const [trainJob, setTrainJob] = useState<string | null>(null)
  const [sample, setSample] = useState('Landslide blocks Mumbai-Goa highway near Ratnagiri, traffic halted')
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (st.data && !form) setForm({ engine: st.data.engine, ml_fallback: st.data.ml_fallback, ml_relevance_threshold: st.data.ml_relevance_threshold }) }, [st.data, form])
  if (st.error) return <ErrorBox error={st.error} onRetry={st.reload} />
  if (!st.data || !form) return <Loading />
  const d = st.data
  const meta = d.model
  const save = async () => {
    try {
      await api('/api/settings/classification', { method: 'PUT', body: { ...form, ml_relevance_threshold: Number(form.ml_relevance_threshold) } })
      toast('ok', `Classification engine saved: ${form.engine === 'ml' ? 'ML model' : 'LLM'}`); st.reload()
    } catch (e: any) { toast('error', e.message) }
  }
  const train = async () => {
    try { const r = await api<any>('/api/ml/train', { method: 'POST' }); setTrainJob(r.job_id) } catch (e: any) { toast('error', e.message) }
  }
  const test = async () => {
    setBusy(true); setRes(null)
    try { setRes(await api('/api/ml/test', { body: { title: sample } })); st.reload() } catch (e: any) { setRes({ ok: false, error: { message: e.message } }) } finally { setBusy(false) }
  }
  return (
    <Card title={<div style={{ flex: 1 }}><h2>Classification engine</h2><div className="small muted">Choose what classifies records. The LLM reads the full text and extracts every field; the ML model is a fast local text classifier (TF-IDF features + logistic regression) that needs no LLM.</div></div>}
          actions={<button className="btn primary" onClick={save}><Save size={14} />Save engine</button>}>
      <div className="stack">
        <div className="row" role="radiogroup" aria-label="Classification engine">
          {[{ id: 'llm', label: 'LLM (active provider below)' }, { id: 'ml', label: 'ML model (local)' }].map(o => (
            <button key={o.id} type="button" role="radio" aria-checked={form.engine === o.id} className={`btn ${form.engine === o.id ? 'primary' : ''}`}
                    onClick={() => setForm({ ...form, engine: o.id })}>{o.id === 'llm' ? <Bot size={14} /> : <Cpu size={14} />}{o.label}</button>
          ))}
          {d.engine !== form.engine && <Badge tone="warn">unsaved</Badge>}
        </div>
        <div className="form-grid">
          <label className="check"><input type="checkbox" checked={!!form.ml_fallback} disabled={form.engine === 'ml'} onChange={e => setForm({ ...form, ml_fallback: e.target.checked })} />
            Fall back to the ML model when the LLM is unavailable</label>
          <label className="field">ML relevance threshold
            <input className="input" type="number" min={0.3} max={0.95} step={0.05} value={form.ml_relevance_threshold} onChange={e => setForm({ ...form, ml_relevance_threshold: e.target.value })} />
            <span className="hint">Probability needed to mark a record relevant. Records within 0.2 below it are marked “needs review”.</span></label>
        </div>
        <Notice kind="info">
          With the LLM engine and fallback on, a record whose LLM call fails (Ollama not running, timeout, invalid key, no credits…) keeps the failed attempt in its history and is then
          classified by the ML model; a classification job switches to ML for the remaining records as soon as the LLM is found unavailable. The fallback only fills gaps: a record that already has an LLM or human classification keeps it. ML results show provider <code>ml</code> and
          the model version. The ML model sets relevance, category and time status, and copies highway, road and city names only when they appear in the text. It never guesses severity or event times – those stay unknown.
        </Notice>
        <div className="section-title">ML model</div>
        {!d.sklearn_installed ? <Notice kind="error">scikit-learn is not installed. Run <code>setup_and_start.bat</code> again to install the updated requirements.</Notice> : !meta ? (
          <Notice kind="warn">No ML model has been trained yet. It is trained automatically the first time it is needed, or press <strong>Train now</strong>.</Notice>
        ) : (
          <div className="stack" style={{ gap: 8 }}>
            <div className="small">Model <span className="mono">{meta.version}</span> · trained {fmtDate(meta.trained_at)} by {meta.trained_by} · {meta.training_rows.toLocaleString('en-IN')} training records
              ({Object.entries(meta.by_origin).map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')}) · {d.records_classified_by_ml.toLocaleString('en-IN')} current record(s) classified by ML</div>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Model</th><th>Examples</th><th>Accuracy</th><th>Macro F1</th><th>Majority baseline</th></tr></thead>
                <tbody>
                  <MetricRow label="Relevance" m={meta.metrics.relevance} />
                  <MetricRow label="Category" m={meta.metrics.category} />
                  <MetricRow label="Time status" m={meta.metrics.time_status} />
                </tbody>
              </table>
            </div>
            <div className="xs muted">{meta.metric_note} Training data: current LLM and human classifications (approved and corrected records weigh 3×; rejected records and ML outputs are excluded),
              the bundled seed set, and weak negatives (unclassified records the keyword pre-filter rates as unlikely). Retrain after reviewing or correcting records to use your decisions.</div>
          </div>
        )}
        <div className="row">
          <button className="btn" onClick={train} disabled={!!trainJob || !d.sklearn_installed}><RefreshCw size={14} />{meta ? 'Retrain now' : 'Train now'}</button>
        </div>
        {trainJob && <JobProgress jobId={trainJob} compact onDone={j => { setTrainJob(null); toast(j.status === 'COMPLETED' ? 'ok' : 'error', j.message || j.status); st.reload() }} />}
        <div className="section-title">Try the ML model (test only – nothing is saved)</div>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <input className="input" style={{ flex: 1 }} value={sample} onChange={e => setSample(e.target.value)} aria-label="Test headline for the ML model" />
          <button className="btn" onClick={test} disabled={busy || sample.trim().length < 3}>{busy ? 'Classifying…' : 'Classify with ML'}</button>
        </div>
        {res && (res.ok ? (
          <div className="stack" style={{ gap: 6 }}>
            <div className="row small">
              <Badge tone={res.fields.relevance === 'RELEVANT' ? 'ok' : res.fields.relevance === 'NEEDS_REVIEW' ? 'warn' : 'neutral'}>{res.fields.relevance}</Badge>
              {res.fields.relevance !== 'IRRELEVANT' && <><Badge>{res.fields.category}</Badge><Badge>{res.fields.time_status}</Badge></>}
              <Badge tone="neutral">confidence {res.fields.model_confidence}</Badge>
              <span className="muted">P(relevant) = {pct(res.probabilities.relevance?.RELEVANT)} · {res.latency_ms} ms</span>
            </div>
            <dl className="kv">{['city', 'state', 'highway_number', 'road_name'].filter(k => res.fields[k]).map(k => <Fragment key={k}><dt>{k}</dt><dd>{res.fields[k]}</dd></Fragment>)}</dl>
            {res.probabilities.category && <div className="xs muted">Category probabilities: {Object.entries(res.probabilities.category).sort((a: any, b: any) => b[1] - a[1]).slice(0, 4).map(([k, v]: any) => `${k} ${pct(v)}`).join(' · ')}</div>}
          </div>
        ) : <Notice kind="error">{res.error?.message || 'Failed'}</Notice>)}
      </div>
    </Card>
  )
}

export default function LLMSettings() {
  const toast = useToast()
  const cfg = useApi<any>('/api/llm/config')
  const oll = useApi<any>('/api/llm/ollama/status')
  const [form, setForm] = useState<any>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [testRes, setTestRes] = useState<Record<string, any>>({})
  const [pull, setPull] = useState<{ model: string; job?: string; confirm?: boolean } | null>(null)
  const [sample, setSample] = useState({ title: 'TEST RECORD: NH-48 closed near Vasai after container truck overturns; traffic diverted', text: 'Mumbai-bound traffic on the Mumbai–Ahmedabad highway (NH-48) was halted for four hours on Tuesday morning after a container truck overturned near Vasai Phata, police said. Vehicles were diverted via Bhiwandi.' })
  const [sampleRes, setSampleRes] = useState<any>(null)
  const [sampling, setSampling] = useState(false)

  useEffect(() => { if (cfg.data && !form) setForm({ active_provider: cfg.data.active_provider, fallback_provider: cfg.data.fallback_provider, providers: JSON.parse(JSON.stringify(cfg.data.providers)) }) }, [cfg.data, form])
  if (cfg.error) return <ErrorBox error={cfg.error} onRetry={cfg.reload} />
  if (!cfg.data || !form) return <Loading />
  const secrets: Record<string, any> = Object.fromEntries(cfg.data.secrets.map((x: any) => [x.name, x]))
  const setP = (p: string, k: string, v: any) => setForm({ ...form, providers: { ...form.providers, [p]: { ...form.providers[p], [k]: v } } })

  const save = async () => {
    const providers: any = {}
    Object.entries(form.providers).forEach(([p, c]: any) => {
      providers[p] = { base_url: c.base_url, model: c.model, temperature: Number(c.temperature), max_tokens: Number(c.max_tokens), timeout_seconds: Number(c.timeout_seconds), ...(c.structured_output ? { structured_output: c.structured_output } : {}) }
    })
    try { await api('/api/llm/config', { method: 'PUT', body: { active_provider: form.active_provider, fallback_provider: form.fallback_provider || '', providers } }); toast('ok', 'LLM configuration saved'); cfg.reload() }
    catch (e: any) { toast('error', e.message) }
  }
  const test = async (p: string) => {
    setTesting(p)
    try { const r = await api<any>('/api/llm/test', { body: { provider: p } }); setTestRes(t => ({ ...t, [p]: r })); cfg.reload() }
    catch (e: any) { setTestRes(t => ({ ...t, [p]: { ok: false, error: { message: e.message } } })) } finally { setTesting(null) }
  }
  const runSample = async () => {
    setSampling(true); setSampleRes(null)
    try { setSampleRes(await api('/api/llm/test-classification', { body: { ...sample, provider: form.active_provider } })) }
    catch (e: any) { setSampleRes({ ok: false, error: { message: e.message } }) } finally { setSampling(false) }
  }
  const startPull = async (model: string) => {
    try { const r = await api<any>('/api/llm/ollama/pull', { body: { model, confirm: true } }); setPull({ model, job: r.job_id }) }
    catch (e: any) { toast('error', e.message); setPull(null) }
  }
  const o = oll.data
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Classification engine</h1>
          <div className="sub">Choose what classifies records – an LLM (local Ollama or your own cloud provider) or the local ML model – and configure both. Keys stay on the server and are never sent to the browser. LLM providers are never switched automatically; only the ML fallback (if enabled) steps in when the LLM is unavailable, and each classification records the provider and model used.</div></div>
        <div className="actions"><button className="btn primary" onClick={save}><Save size={14} />Save LLM configuration</button></div>
      </div>
      <EnginePanel />
      <Notice kind="info">{cfg.data.secret_storage}</Notice>

      <Card title="Active provider">
        <div className="form-grid">
          <label className="field">Provider used for classification
            <select className="input" value={form.active_provider} onChange={e => setForm({ ...form, active_provider: e.target.value })}>
              {cfg.data.available_providers.map((p: string) => <option key={p} value={p}>{PROVIDER_INFO[p]?.title || p}</option>)}
            </select></label>
          <label className="field">Fallback provider (manual switch only)
            <select className="input" value={form.fallback_provider} onChange={e => setForm({ ...form, fallback_provider: e.target.value })}>
              <option value="">None</option>{cfg.data.available_providers.filter((p: string) => p !== form.active_provider).map((p: string) => <option key={p} value={p}>{PROVIDER_INFO[p]?.title || p}</option>)}
            </select><span className="hint">If the active provider fails, the failure is shown and you can retry records with this provider from the record panel.</span></label>
          <div className="field">Prompt version<span className="mono">{cfg.data.prompt_version}</span></div>
        </div>
      </Card>

      {Object.keys(PROVIDER_INFO).map(p => {
        const c = form.providers[p] || {}
        const last = cfg.data.last_tests?.[p]
        const r = testRes[p]
        return (
          <Card key={p} title={<div style={{ flex: 1 }}><h2>{PROVIDER_INFO[p].title} {form.active_provider === p && <Badge tone="blue">active</Badge>}</h2><div className="small muted">{PROVIDER_INFO[p].text}</div></div>}
                actions={<button className="btn" onClick={() => test(p)} disabled={testing === p}><Plug size={14} />{testing === p ? 'Testing…' : 'Test connection'}</button>}>
            <div className="form-grid">
              <label className="field">{p === 'ollama' ? 'Ollama URL' : 'API base URL'}<input className="input" value={c.base_url || ''} onChange={e => setP(p, 'base_url', e.target.value)} /></label>
              <label className="field">Model
                <input className="input" list={`models-${p}`} value={c.model || ''} onChange={e => setP(p, 'model', e.target.value)} />
                <datalist id={`models-${p}`}>{(r?.models || (p === 'ollama' ? o?.ollama?.models?.map((m: any) => m.name) : []) || []).map((m: string) => <option key={m} value={m} />)}</datalist>
              </label>
              <label className="field">Temperature<input className="input" type="number" step="0.1" min={0} max={2} value={c.temperature ?? 0} onChange={e => setP(p, 'temperature', e.target.value)} /></label>
              <label className="field">Max output tokens<input className="input" type="number" min={128} max={8192} value={c.max_tokens ?? 900} onChange={e => setP(p, 'max_tokens', e.target.value)} /></label>
              <label className="field">Timeout (s)<input className="input" type="number" min={5} max={600} value={c.timeout_seconds ?? 60} onChange={e => setP(p, 'timeout_seconds', e.target.value)} /></label>
              {p === 'openai_compatible' && <label className="field">Structured output
                <select className="input" value={c.structured_output || 'json_schema'} onChange={e => setP(p, 'structured_output', e.target.value)}>
                  <option value="json_schema">JSON schema (OpenAI, recent compatible servers)</option><option value="json_object">JSON object mode</option><option value="none">None (prompt only)</option>
                </select></label>}
            </div>
            {PROVIDER_INFO[p].secret && <div style={{ marginTop: 12 }}><SecretField name={PROVIDER_INFO[p].secret!} status={secrets[PROVIDER_INFO[p].secret!]} onChanged={cfg.reload} /></div>}
            <div style={{ marginTop: 12 }}>
              {r ? (
                <Notice kind={r.ok ? 'ok' : 'error'}>
                  {r.ok ? <>Connected. Model <strong>{r.model}</strong> answered in {(r.latency_ms / 1000).toFixed(1)} s{r.models ? ` · ${r.models.length} model(s) listed` : ''}.</>
                    : <>Failed at <strong>{r.stage}</strong>: {r.error?.message}</>}
                </Notice>
              ) : last ? (
                <div className="small muted">Last test {fmtDate(last.tested_at)}: {last.ok ? <Badge tone="ok">OK</Badge> : <Badge tone="danger">FAILED</Badge>} {last.model} {last.error?.message && `– ${last.error.message}`}</div>
              ) : <div className="small muted">Not tested yet. Remember to save changes before testing.</div>}
            </div>
          </Card>
        )
      })}

      <Card title="Local LLM setup (Ollama)" actions={<button className="btn sm" onClick={oll.reload}>Re-check</button>}>
        {!o ? <Loading label="Checking Ollama and hardware…" /> : (
          <div className="stack">
            <div className="grid grid-3">
              <div><div className="xs muted">Ollama</div>{o.ollama.installed ? <Badge tone="ok">Installed</Badge> : <Badge tone="warn">Not found</Badge>} {o.ollama.reachable ? <Badge tone="ok">Service running v{o.ollama.version}</Badge> : <Badge tone="danger">Service not reachable</Badge>}</div>
              <div><div className="xs muted">Hardware</div><span className="small">{o.hardware.ram_gb ?? '?'} GB RAM · {o.hardware.gpus.length ? o.hardware.gpus.map((g: any) => `${g.name} (${g.vram_gb} GB)`).join(', ') : 'no NVIDIA GPU detected'} · {o.hardware.disk_free_gb ?? '?'} GB free disk</span></div>
              <div><div className="xs muted">Recommendation</div><span className="small"><strong>{o.recommendation.recommended || 'cloud provider'}</strong> – {o.recommendation.reason}</span></div>
            </div>
            {!o.ollama.installed && <Notice kind="warn">Ollama is not installed. Download the official Windows installer from <a href={o.ollama.download_url} target="_blank" rel="noopener noreferrer">ollama.com/download/windows</a> (internet required), install it, then press Re-check. You can also run <code>setup_llm.bat</code>.</Notice>}
            {o.ollama.installed && !o.ollama.reachable && <Notice kind="warn">Ollama is installed but its service is not running. Start “Ollama” from the Start menu, then press Re-check.</Notice>}
            {o.ollama.models.length > 0 && <div className="small">Installed models: {o.ollama.models.map((m: any) => <Badge key={m.name} tone={m.embedding_only ? 'neutral' : 'blue'} title={m.embedding_only ? 'Embedding model – cannot classify' : ''}>{m.name} {m.size_gb} GB</Badge>)}</div>}
            <table className="table">
              <thead><tr><th>Model</th><th>Download</th><th>Suggested RAM</th><th>Fits this PC</th><th>Notes</th><th /></tr></thead>
              <tbody>{o.recommendation.catalog.map((m: any) => {
                const installed = o.ollama.models.some((x: any) => x.name === m.name)
                return (
                  <tr key={m.name}><td className="mono">{m.name}</td><td>{m.download_gb} GB</td><td>{m.min_ram_gb} GB+</td>
                    <td>{m.suitable ? (m.gpu_accelerated ? <Badge tone="ok">Yes (GPU)</Badge> : <Badge tone="warn">CPU only – slow</Badge>) : <Badge tone="danger">Not recommended</Badge>}</td>
                    <td className="small">{m.notes}</td>
                    <td>{installed ? <Badge tone="ok">Installed</Badge> : <button className="btn sm" disabled={!o.ollama.reachable || !!pull?.job} onClick={() => setPull({ model: m.name, confirm: true })}><Download size={12} />Download</button>}</td></tr>
                )
              })}</tbody>
            </table>
            {pull?.job && <JobProgress jobId={pull.job} onDone={j => { toast(j.status === 'COMPLETED' ? 'ok' : 'error', j.message || j.status); setPull(null); oll.reload() }} />}
            {o.notes.map((n: string) => <div key={n} className="xs muted">{n}</div>)}
          </div>
        )}
      </Card>

      <Card title="Test classification (clearly labelled test record – nothing is saved)">
        <div className="stack">
          <label className="field">Test headline<input className="input" value={sample.title} onChange={e => setSample({ ...sample, title: e.target.value })} /></label>
          <label className="field">Test text<textarea className="input" rows={3} value={sample.text} onChange={e => setSample({ ...sample, text: e.target.value })} /></label>
          <div><button className="btn primary" onClick={runSample} disabled={sampling}>{sampling ? 'Classifying…' : `Classify with ${form.active_provider}`}</button> <span className="xs muted">Uses the saved configuration of the active provider.</span></div>
          {sampleRes && (sampleRes.ok ? (
            <div className="stack" style={{ gap: 8 }}>
              <Notice kind="ok">Valid structured output from {sampleRes.provider}/{sampleRes.model} in {(sampleRes.latency_ms / 1000).toFixed(1)} s.</Notice>
              <dl className="kv">{Object.entries(sampleRes.fields).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length)).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{Array.isArray(v) ? v.join(', ') : String(v)}</dd></Fragment>)}</dl>
              {sampleRes.validation_issues.length > 0 && <Notice kind="warn">Validation: {sampleRes.validation_issues.join('; ')}</Notice>}
              <details><summary className="small">Raw model output</summary><pre className="raw">{sampleRes.raw_output}</pre></details>
            </div>
          ) : <Notice kind="error">{sampleRes.error?.message || 'Failed'}{sampleRes.raw_output && <pre className="raw">{sampleRes.raw_output}</pre>}</Notice>)}
        </div>
      </Card>
      {pull?.confirm && !pull.job && (
        <Confirm title={`Download ${pull.model}?`} confirmLabel="Download model"
          message={<>This downloads the model through Ollama from the internet ({o?.recommendation.catalog.find((m: any) => m.name === pull.model)?.download_gb} GB approx.). It can take a long time on slow connections. Disk space free: {o?.hardware.disk_free_gb} GB.</>}
          onCancel={() => setPull(null)} onConfirm={() => startPull(pull.model)} />
      )}
    </div>
  )
}
