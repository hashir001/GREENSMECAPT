import { ArrowLeft, CheckCircle2, Eye, RefreshCw, Send } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { usePermissions } from '../auth/usePermissions'
import { api } from '../lib/api'
import type {
  AssessmentAutofill,
  AssessmentConfiguration,
  AssessmentProfileStatus,
  AssessmentSubmission,
  PreparedAssessment,
  StructuredInvestmentRecord,
} from '../types/api'

const readyStatuses = new Set(['ready_numeric', 'ready_range', 'ready_linguistic'])

export function AssessmentProfilePage() {
  const { smeId = '' } = useParams()
  const { canApproveProfiles, canPublishProfiles } = usePermissions()
  const [configuration, setConfiguration] = useState<AssessmentConfiguration | null>(null)
  const [autofill, setAutofill] = useState<AssessmentAutofill | null>(null)
  const [record, setRecord] = useState<StructuredInvestmentRecord | null>(null)
  const [status, setStatus] = useState<AssessmentProfileStatus | null>(null)
  const [prepared, setPrepared] = useState<PreparedAssessment | null>(null)
  const [facts, setFacts] = useState<Record<string, boolean | null>>({})
  const [ratings, setRatings] = useState<Record<string, string>>({})
  const [activity, setActivity] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([
      api.getAssessmentConfiguration(),
      api.getAssessmentAutofill(smeId),
      api.getSMERecord(smeId),
      api.getAssessmentProfileStatus(smeId),
    ]).then(([nextConfiguration, nextAutofill, nextRecord, nextStatus]) => {
      setConfiguration(nextConfiguration)
      setAutofill(nextAutofill)
      setRecord(nextRecord)
      setStatus(nextStatus)
      setFacts(nextAutofill.facts)
      setActivity(nextAutofill.activity_description)
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Profile could not be loaded.'))
  }, [smeId])

  const submission = useMemo<AssessmentSubmission | null>(() => {
    if (!autofill || !record || !configuration) return null
    const accepted = record.evidence_items.filter((item) => item.validation_status === 'accepted')
    return {
      context: {
        sme_id: smeId,
        activity_description: activity || 'Activity description requires reviewer confirmation.',
        sector: record.sme.sector,
        facts,
      },
      responses: Object.entries(ratings).map(([criterionId, linguisticValue]) => ({
        response_id: `review_${smeId}_${criterionId}`,
        sme_id: smeId,
        criterion_id: criterionId,
        kind: 'linguistic' as const,
        linguistic_value: linguisticValue,
        narrative: 'Reviewer rating based on accepted SME evidence.',
        supporting_evidence_ids: accepted.filter((item) => item.criterion_id === criterionId).map((item) => item.evidence_id),
        submitted_by: 'assessment_reviewer',
      })),
      financial_observations: autofill.financial_observations,
      readiness_observations: autofill.readiness_observations,
      metric_contexts: autofill.metric_contexts,
    }
  }, [activity, autofill, configuration, facts, ratings, record, smeId])

  async function refreshStatus() {
    setStatus(await api.getAssessmentProfileStatus(smeId))
  }

  async function prepare() {
    if (!submission) return
    setBusy(true); setError('')
    try { setPrepared(await api.prepareAssessment(submission)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Profile could not be prepared.') }
    finally { setBusy(false) }
  }

  async function approve() {
    if (!submission) return
    setBusy(true); setError('')
    try { await api.approveAssessmentProfile(smeId, submission); await refreshStatus() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Profile could not be approved.') }
    finally { setBusy(false) }
  }

  async function publish() {
    if (!status?.latest_revision_id) return
    setBusy(true); setError('')
    try { await api.publishAssessmentProfile(smeId, status.latest_revision_id, status.application_revision); await refreshStatus() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Profile could not be published.') }
    finally { setBusy(false) }
  }

  async function unpublish() {
    if (!status || status.application_status !== 'published') return
    if (!window.confirm('Withdraw this profile from investor comparison?')) return
    setBusy(true); setError('')
    try { await api.transitionSMEApplication(smeId, status.application_revision, 'approved', 'Profile withdrawn for reassessment.'); await refreshStatus() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Profile could not be withdrawn.') }
    finally { setBusy(false) }
  }

  const unresolvedFacts = prepared
    ? [...new Set(prepared.profile.decisions.flatMap((item) => item.status === 'uncertain' ? item.missing_facts : []))]
    : []
  const observations = new Map(prepared?.observations.observations.map((item) => [item.criterion_id, item]))
  const unresolvedScores = prepared?.profile.decisions.filter((item) => (
    item.output === 'green' && item.scoring_role === 'performance_criterion' && item.status === 'applicable'
    && !readyStatuses.has(observations.get(item.criterion_id)?.status ?? '')
  )) ?? []
  const scale = configuration ? Object.keys(configuration.normalization_policy.default_linguistic_scale) : []
  const finalScore = prepared?.green_score?.status === 'final'

  if (!configuration || !autofill || !record || !status) return <div className="skeleton assessment-builder-skeleton" />

  return (
    <>
      <div className="breadcrumbs"><Link to="/assessments/profiles"><ArrowLeft size={14} /> Profiles</Link><span>/</span><span>{status.legal_name}</span></div>
      <section className="page-heading"><div><span className="eyebrow">Assessment profile</span><h1>{status.legal_name}</h1><p>Resolve only missing applicability and environmental scoring inputs, then approve and publish.</p></div></section>
      {error && <div className="error-banner">{error}</div>}

      <section className="panel builder-panel">
        <h2>1. Source-grounded context</h2>
        <label className="builder-field">Activity description<textarea value={activity} onChange={(event) => setActivity(event.target.value)} rows={3} /></label>
        <p>{record.documents.length} documents · {record.evidence_items.filter((item) => item.validation_status === 'accepted').length} accepted evidence items · {autofill.readiness_observations.length} readiness observations</p>
      </section>

      {prepared && unresolvedFacts.length > 0 && <section className="panel builder-panel">
        <h2>2. Resolve applicability</h2>
        <p>These are the only unanswered facts currently affecting criterion applicability.</p>
        {unresolvedFacts.map((factId) => <div className="builder-field" key={factId}>
          <strong>{configuration.assessment_policy.fact_questions[factId] ?? factId}</strong>
          <div className="segmented-control">
            <button type="button" className={facts[factId] === true ? 'active' : ''} onClick={() => setFacts((current) => ({ ...current, [factId]: true }))}>Yes</button>
            <button type="button" className={facts[factId] === false ? 'active' : ''} onClick={() => setFacts((current) => ({ ...current, [factId]: false }))}>No</button>
          </div>
        </div>)}
      </section>}

      {prepared && unresolvedScores.length > 0 && <section className="panel builder-panel">
        <h2>3. Resolve environmental performance</h2>
        {unresolvedScores.map((criterion) => <label className="builder-field" key={criterion.criterion_id}>
          {criterion.title}
          <select value={ratings[criterion.criterion_id] ?? ''} onChange={(event) => setRatings((current) => ({ ...current, [criterion.criterion_id]: event.target.value }))}>
            <option value="">Select reviewed rating</option>
            {scale.map((value) => <option value={value} key={value}>{value.replaceAll('_', ' ')}</option>)}
          </select>
        </label>)}
      </section>}

      {prepared && <section className="panel builder-panel">
        <h2>4. Governed output</h2>
        <div className="comparison-assurance"><Eye size={18} /><span>Green Score: {prepared.green_score?.score ?? 'withheld'} / 100 · {prepared.green_score?.status ?? 'blocked'} · coverage {Math.round((prepared.green_score?.coverage_ratio ?? 0) * 100)}%</span></div>
        <p>Financial assessment: {prepared.financial_assessment.status} · Readiness factors: {prepared.readiness_profile.factors.length} · Evidence strength remains separate from performance.</p>
      </section>}

      <div className="builder-footer">
        <button className="secondary-button" type="button" disabled={busy} onClick={() => void prepare()}><RefreshCw size={16} />{prepared ? 'Refresh preview' : 'Prepare profile'}</button>
        {canApproveProfiles && <button className="secondary-button" type="button" disabled={busy || !finalScore || status.application_status !== 'approved'} onClick={() => void approve()}><CheckCircle2 size={16} />Approve revision</button>}
        {canPublishProfiles && status.application_status === 'approved' && status.latest_revision_id && <button className="primary-button" type="button" disabled={busy || !status.latest_policy_current} onClick={() => void publish()}><Send size={16} />Publish latest</button>}
        {canPublishProfiles && status.application_status === 'published' && <button className="secondary-button" type="button" disabled={busy} onClick={() => void unpublish()}>Withdraw publication</button>}
      </div>
    </>
  )
}
