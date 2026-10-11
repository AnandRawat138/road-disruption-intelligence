import { Link } from 'react-router-dom'
import { api, useApi } from '../api'
import { Card } from '../components/ui'

/** First-run guide. Every step's completion is derived from real backend state. */
export default function SetupChecklist({ summary }: { summary: any }) {
  const setup = useApi<any>('/api/settings/setup')
  const llm = useApi<any>('/api/llm/config')
  const stats = useApi<any>('/api/classification/stats')
  if (!setup.data || setup.data.dismissed || !llm.data || !stats.data) return null
  const m = summary.metrics
  const llmOk = !!llm.data.last_tests?.[llm.data.active_provider]?.ok
  const steps = [
    { done: m.unique_articles > 0, label: 'Import historical data', to: '/import', hint: 'Load the files in the data folder into the database.' },
    { done: llmOk, label: 'Configure and test the LLM', to: '/llm', hint: 'Use a local Ollama model or your own API key.' },
    { done: m.classified > 0, label: 'Classify records', to: '/records?prefilter=LIKELY_RELEVANT&classification_status=UNCLASSIFIED', hint: 'Start with records the keyword pre-filter marks as likely relevant.' },
    { done: !!summary.last_successful_refresh, label: 'Fetch current news from a source', to: '/sources', hint: 'Google News RSS works without a key.' },
    { done: (stats.data.by_review_status?.APPROVED || 0) > 0, label: 'Review and approve records', to: '/review', hint: 'Approval confirms the incident.' },
  ]
  if (steps.every(s => s.done)) return null
  const dismiss = async () => { await api('/api/settings/setup', { method: 'PUT', body: { dismissed: true } }); setup.reload() }
  return (
    <Card title="Getting started" actions={<button className="btn sm ghost" onClick={dismiss}>Hide</button>}>
      <ol className="steps">
        {steps.map((s, i) => (
          <li key={s.label}>
            <span className={`step-num ${s.done ? 'done' : ''}`} aria-label={s.done ? 'completed' : 'not completed'}>{s.done ? '✓' : i + 1}</span>
            <div style={{ flex: 1 }}><Link to={s.to}><strong>{s.label}</strong></Link><div className="small muted">{s.hint}</div></div>
          </li>
        ))}
      </ol>
    </Card>
  )
}
