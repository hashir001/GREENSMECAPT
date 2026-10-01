import { CheckCircle2, FileCheck2, LoaderCircle, RefreshCw, Save, Send, XCircle } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { usePermissions } from '../auth/usePermissions'
import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type {
  FinancialObservation,
  FinancialPolicy,
  FinancialSubmission,
  SME,
  SourceDocument,
} from '../types/api'

type FieldDraft = {
  state: FinancialObservation['state']
  value: string
  unit: string
  period: string
  basis: string
  sourceId: string
  narrative: string
}

const unresolvedStates: Array<{ value: FinancialObservation['state']; label: string }> = [
  { value: 'reported', label: 'Reported value' },
  { value: 'unknown', label: 'Unknown' },
  { value: 'not_measured', label: 'Not measured' },
  { value: 'not_applicable', label: 'Not applicable' },
  { value: 'needs_review', label: 'Needs review' },
]

function blankDraft(unit = ''): FieldDraft {
  return { state: 'unknown', value: '', unit, period: '', basis: '', sourceId: '', narrative: '' }
}

function statusTone(status: FinancialSubmission['status']) {
  if (status === 'approved') return 'positive' as const
  if (status === 'changes_requested') return 'danger' as const
  if (status === 'submitted' || status === 'under_review') return 'warning' as const
  return 'neutral' as const
}

export function FinancialPage() {
  const { role } = usePermissions()
  const reviewMode = role === 'admin' || role === 'reviewer'
  return reviewMode ? <FinancialReviewQueue /> : <SMEFinancialWorkspace />
}

function SMEFinancialWorkspace() {
  const [policy, setPolicy] = useState<FinancialPolicy | null>(null)
  const [company, setCompany] = useState<SME | null>(null)
  const [documents, setDocuments] = useState<SourceDocument[]>([])
  const [submission, setSubmission] = useState<FinancialSubmission | null>(null)
  const [drafts, setDrafts] = useState<Record<string, FieldDraft>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [configuration, companies] = await Promise.all([
        api.getFinancialConfiguration(),
        api.listSMEs(),
      ])
      const owned = companies[0] ?? null
      setPolicy(configuration)
      setCompany(owned)
      if (!owned) return
      const [record, saved] = await Promise.all([
        api.getSMERecord(owned.sme_id),
        api.getFinancialSubmission(owned.sme_id),
      ])
      setDocuments(record.documents)
      setSubmission(saved)
      const byMetric = new Map(saved?.observations.map((item) => [item.metric_id, item]))
      setDrafts(Object.fromEntries(configuration.metrics
        .filter((metric) => metric.role !== 'derived_indicator')
        .map((metric) => {
        const item = byMetric.get(metric.metric_id)
        return [metric.metric_id, item ? {
          state: item.state,
          value: item.value?.toString() ?? '',
          unit: item.unit ?? metric.allowed_units[0] ?? '',
          period: item.reporting_period ?? '',
          basis: item.comparison_basis ?? '',
          sourceId: item.source_ids[0] ?? '',
          narrative: item.narrative ?? '',
        } : blankDraft(metric.allowed_units[0])]
        })))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Financial workspace could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { queueMicrotask(() => void load()) }, [load])

  function update(metricId: string, patch: Partial<FieldDraft>) {
    setDrafts((current) => ({
      ...current,
      [metricId]: { ...current[metricId], ...patch },
    }))
  }

  function observations(): FinancialObservation[] {
    if (!policy || !company) return []
    const timestamp = Date.now()
    return policy.metrics
      .filter((metric) => metric.role !== 'derived_indicator')
      .map((metric) => {
      const field = drafts[metric.metric_id] ?? blankDraft(metric.allowed_units[0])
      const reported = field.state === 'reported'
      return {
        observation_id: `finance_${company.sme_id}_${metric.metric_id}_${timestamp}`,
        sme_id: company.sme_id,
        metric_id: metric.metric_id,
        state: field.state,
        ...(reported ? { value: Number(field.value), unit: field.unit } : {}),
        ...(field.period ? { reporting_period: field.period } : {}),
        ...(field.basis ? { comparison_basis: field.basis } : {}),
        source_ids: reported && field.sourceId ? [field.sourceId] : [],
        ...(field.narrative ? { narrative: field.narrative } : {}),
      }
      })
  }

  async function save(submitAfter: boolean) {
    if (!company) return
    const incomplete = policy?.metrics
      .filter((metric) => metric.role !== 'derived_indicator')
      .find((metric) => {
      const field = drafts[metric.metric_id]
      return field?.state === 'reported' && (
        field.value === ''
        || !field.unit
        || !field.sourceId
        || (metric.requires_reporting_period && !field.period.trim())
        || (metric.requires_comparison_basis && !field.basis.trim())
      )
      })
    if (incomplete) {
      setError(`Complete the value, unit, period and evidence source for ${incomplete.title}.`)
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await api.saveFinancialSubmission(
        company.sme_id,
        submission?.revision ?? null,
        observations(),
      )
      const next = submitAfter
        ? await api.submitFinancialSubmission(company.sme_id, saved.revision)
        : saved
      setSubmission(next)
      setNotice(submitAfter ? 'Financial information submitted for review.' : 'Financial draft saved.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Financial information could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  const editable = !submission || ['draft', 'changes_requested'].includes(submission.status)

  if (loading) return <div className="skeleton assessment-builder-skeleton" />
  if (!company) return <div className="error-banner">No SME workspace is assigned to this account.</div>

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">SME financial workspace</span>
          <h1>Financial & investment information</h1>
          <p>Provide traceable statement and funding-request inputs. The system calculates financial indicators transparently; none are folded into the Green Score.</p>
        </div>
        {submission && <StatusPill label={submission.status.replaceAll('_', ' ')} tone={statusTone(submission.status)} />}
      </section>

      {submission?.review_note && <div className="review-note"><strong>Reviewer note</strong><span>{submission.review_note}</span></div>}
      {error && <div className="error-banner">{error}</div>}
      {notice && <div className="form-success financial-notice">{notice}</div>}

      <section className="financial-grid">
        {policy?.metrics.filter((metric) => metric.role !== 'derived_indicator').map((metric) => {
          const field = drafts[metric.metric_id] ?? blankDraft(metric.allowed_units[0])
          const reported = field.state === 'reported'
          return (
            <article className="panel financial-metric" key={metric.metric_id}>
              <header><div><span className="eyebrow">{metric.group.replaceAll('_', ' ')} · {metric.role.replaceAll('_', ' ')}</span><h2>{metric.title}</h2></div><StatusPill label={metric.importance} tone={metric.importance === 'core' ? 'warning' : 'neutral'} /></header>
              <p>{metric.description}</p>
              <label className="builder-field">Availability<select disabled={!editable} value={field.state} onChange={(event) => update(metric.metric_id, { state: event.target.value as FinancialObservation['state'] })}>{unresolvedStates.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
              {reported && <div className="financial-value-grid">
                <label className="builder-field">Value<input disabled={!editable} required type="number" step="any" value={field.value} onChange={(event) => update(metric.metric_id, { value: event.target.value })} /></label>
                <label className="builder-field">Unit<select disabled={!editable} value={field.unit} onChange={(event) => update(metric.metric_id, { unit: event.target.value })}>{metric.allowed_units.map((unit) => <option value={unit} key={unit}>{unit.replaceAll('_', ' ')}</option>)}</select></label>
                <label className="builder-field">Reporting period<input disabled={!editable} required={metric.requires_reporting_period} placeholder="FY 2025" value={field.period} onChange={(event) => update(metric.metric_id, { period: event.target.value })} /></label>
                <label className="builder-field">Evidence source<select disabled={!editable} required value={field.sourceId} onChange={(event) => update(metric.metric_id, { sourceId: event.target.value })}><option value="">Select uploaded document</option>{documents.map((document) => <option value={document.document_id} key={document.document_id}>{document.file_name}</option>)}</select></label>
              </div>}
              {metric.requires_comparison_basis && <label className="builder-field">Comparison basis<input disabled={!editable} required={reported} placeholder="FY2025 compared with FY2024" value={field.basis} onChange={(event) => update(metric.metric_id, { basis: event.target.value })} /></label>}
              <label className="builder-field">Context or notes<textarea disabled={!editable} value={field.narrative} onChange={(event) => update(metric.metric_id, { narrative: event.target.value })} /></label>
            </article>
          )
        })}
      </section>

      {!documents.length && <div className="methodology-note"><FileCheck2 size={18} /><p>Upload a financial statement or other source in <Link className="text-link" to={`/companies/${company.sme_id}`}>your company record</Link> before reporting a value.</p></div>}
      {editable && <div className="builder-footer"><button className="secondary-button" disabled={busy} onClick={() => void save(false)}><Save size={16} /> Save draft</button><button className="primary-button" disabled={busy} onClick={() => void save(true)}>{busy ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />} Submit for review</button></div>}
    </>
  )
}

function FinancialReviewQueue() {
  const [policy, setPolicy] = useState<FinancialPolicy | null>(null)
  const [submissions, setSubmissions] = useState<FinancialSubmission[]>([])
  const [companies, setCompanies] = useState<SME[]>([])
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [configuration, queue, smes] = await Promise.all([
        api.getFinancialConfiguration(), api.listFinancialSubmissions(), api.listSMEs(),
      ])
      setPolicy(configuration)
      setSubmissions(queue)
      setCompanies(smes)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Financial review queue could not be loaded.')
    }
  }, [])

  useEffect(() => { queueMicrotask(() => void load()) }, [load])
  const names = useMemo(() => new Map(companies.map((item) => [item.sme_id, item.legal_name])), [companies])
  const titles = useMemo(() => new Map(policy?.metrics.map((item) => [item.metric_id, item.title]) ?? []), [policy])

  async function decide(item: FinancialSubmission, decision: 'approved' | 'changes_requested') {
    setBusy(item.sme_id)
    setError('')
    try {
      await api.reviewFinancialSubmission(item.sme_id, item.revision, decision, notes[item.sme_id])
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The financial review could not be saved.')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <section className="page-heading"><div><span className="eyebrow">Human-governed review</span><h1>Financial review queue</h1><p>Verify SME-reported facts and their source documents before approval.</p></div><button className="secondary-button" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></section>
      {error && <div className="error-banner">{error}</div>}
      <div className="financial-review-list">
        {submissions.map((item) => <article className="panel financial-review-card" key={item.submission_id}>
          <header><div><span className="eyebrow">{item.sme_id}</span><h2>{names.get(item.sme_id) ?? item.sme_id}</h2></div><StatusPill label={item.status.replaceAll('_', ' ')} tone={statusTone(item.status)} /></header>
          <div className="financial-review-values">{item.observations.map((observation) => <div key={observation.metric_id}><strong>{titles.get(observation.metric_id) ?? observation.metric_id}</strong><span>{observation.state === 'reported' ? `${observation.value?.toLocaleString()} ${observation.unit?.replaceAll('_', ' ')}` : observation.state.replaceAll('_', ' ')}</span><small>{observation.reporting_period ?? 'No period'} · {observation.source_ids.length} source(s)</small></div>)}</div>
          {['submitted', 'under_review'].includes(item.status) && <footer><textarea placeholder="Required when requesting changes" value={notes[item.sme_id] ?? ''} onChange={(event) => setNotes((current) => ({ ...current, [item.sme_id]: event.target.value }))} /><button className="danger-button" disabled={busy === item.sme_id || !notes[item.sme_id]?.trim()} onClick={() => void decide(item, 'changes_requested')}><XCircle size={16} /> Request changes</button><button className="primary-button" disabled={busy === item.sme_id} onClick={() => void decide(item, 'approved')}><CheckCircle2 size={16} /> Approve</button></footer>}
        </article>)}
        {!submissions.length && <div className="panel empty-state"><strong>No financial submissions yet</strong><p>Submitted SME financial information will appear here.</p></div>}
      </div>
    </>
  )
}
