import { ArrowLeft, ArrowRight, Check, Info, Play, SlidersHorizontal, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { api } from '../lib/api'
import { isPreviewMode } from '../lib/supabase'
import type { AssessmentAutofill, AssessmentConfiguration, CohortAssessmentRequest, SME, StructuredInvestmentRecord } from '../types/api'

type FinancialDraft = { state: string; value: string; unit: string; period: string; basis: string; sourceId: string }
type ReadinessDraft = { state: string; sourceId: string; narrative: string }
type MetricContextDraft = { period: string; scope: string; denominator: string; denominatorUnit: string; baseline: string; benchmark: string; target: string; referenceUnit: string; sourceId: string; narrative: string }

type Draft = {
  activityDescription: string
  facts: Record<string, boolean | null>
  ratings: Record<string, string>
  financial: Record<string, FinancialDraft>
  readiness: Record<string, ReadinessDraft>
  metricContexts: Record<string, MetricContextDraft>
}

const ratingLabels: Record<string, string> = {
  very_low: 'Very low', low: 'Low', medium: 'Medium', high: 'High', very_high: 'Very high',
}

function slug(value: string) {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
}

function suggestedFacts(
  _company: SME | undefined,
  factIds: string[],
): Record<string, boolean | null> {
  return Object.fromEntries(
    factIds.map((factId) => [factId, null]),
  ) as Record<string, boolean | null>
}

export function AssessmentBuilderPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [companies, setCompanies] = useState<SME[]>([])
  const [configuration, setConfiguration] = useState<AssessmentConfiguration | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [records, setRecords] = useState<Record<string, StructuredInvestmentRecord>>({})
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [autofill, setAutofill] = useState<Record<string, AssessmentAutofill>>({})
  const [cohortName, setCohortName] = useState('Green SME comparison')
  const [minimumSharedCriteria, setMinimumSharedCriteria] = useState(2)
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([api.listSMEs(), api.getAssessmentConfiguration()])
      .then(([nextCompanies, nextConfiguration]) => {
        setCompanies(nextCompanies)
        setConfiguration(nextConfiguration)
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Assessment setup could not be loaded.'))
      .finally(() => setLoading(false))
  }, [])

  const scoredCriteria = useMemo(() => {
    if (!configuration) return []
    const ruleIds = new Set(configuration.normalization_policy.rules.map((rule) => rule.criterion_id))
    return configuration.assessment_policy.criteria.filter((criterion) => ruleIds.has(criterion.criterion_id))
  }, [configuration])

  const scale = configuration ? Object.keys(configuration.normalization_policy.default_linguistic_scale) : []

  function draftFor(smeId: string): Draft {
    return drafts[smeId] ?? {
      activityDescription: companies.find((company) => company.sme_id === smeId)?.sector ?? '',
      facts: suggestedFacts(
        companies.find((company) => company.sme_id === smeId),
        Object.keys(
          configuration?.assessment_policy.fact_questions ?? {},
        ),
      ),
      ratings: {},
      financial: {},
      readiness: {},
      metricContexts: {},
    }
  }

  function updateDraft(smeId: string, update: (current: Draft) => Draft) {
    setDrafts((current) => ({ ...current, [smeId]: update(current[smeId] ?? draftFor(smeId)) }))
  }

  function updateFinancial(smeId: string, metricId: string, patch: Partial<FinancialDraft>) {
    updateDraft(smeId, (current) => {
      const existing = current.financial[metricId] ?? { state: 'unknown', value: '', unit: '', period: '', basis: '', sourceId: '' }
      return { ...current, financial: { ...current.financial, [metricId]: { ...existing, ...patch } } }
    })
  }

  function updateReadiness(smeId: string, factorId: string, patch: Partial<ReadinessDraft>) {
    updateDraft(smeId, (current) => {
      const existing = current.readiness[factorId] ?? { state: 'unknown', sourceId: '', narrative: '' }
      return { ...current, readiness: { ...current.readiness, [factorId]: { ...existing, ...patch } } }
    })
  }

  function updateMetricContext(smeId: string, indicatorId: string, patch: Partial<MetricContextDraft>) {
    updateDraft(smeId, (current) => {
      const existing = current.metricContexts[indicatorId] ?? {
        period: '', scope: '', denominator: '', denominatorUnit: '', baseline: '', benchmark: '', target: '', referenceUnit: '', sourceId: '', narrative: '',
      }
      return { ...current, metricContexts: { ...current.metricContexts, [indicatorId]: { ...existing, ...patch } } }
    })
  }

  function toggleCompany(smeId: string) {
    setSelected((current) => current.includes(smeId) ? current.filter((id) => id !== smeId) : [...current, smeId])
    if (!drafts[smeId]) updateDraft(smeId, (current) => current)
    if (!records[smeId]) {
      void api.getSMERecord(smeId).then((record) => setRecords((current) => ({ ...current, [smeId]: record }))).catch(() => undefined)
    }
    if (!autofill[smeId]) {
      void api.getAssessmentAutofill(smeId).then((result) => {
        setAutofill((current) => ({ ...current, [smeId]: result }))
        updateDraft(smeId, (current) => ({
          ...current,
          activityDescription: result.activity_description || current.activityDescription,
          facts: { ...current.facts, ...result.facts },
          financial: {
            ...current.financial,
            ...Object.fromEntries(result.financial_observations.map((item) => [item.metric_id, {
              state: item.state,
              value: item.value === undefined ? '' : String(item.value),
              unit: item.unit ?? '',
              period: item.reporting_period ?? '',
              basis: item.comparison_basis ?? '',
              sourceId: item.source_ids[0] ?? '',
            }])),
          },
          readiness: {
            ...current.readiness,
            ...Object.fromEntries(result.readiness_observations.map((item) => [item.factor_id, {
              state: item.state,
              sourceId: item.source_ids[0] ?? '',
              narrative: item.narrative ?? '',
            }])),
          },
          metricContexts: {
            ...current.metricContexts,
            ...Object.fromEntries(result.metric_contexts.map((item) => [item.indicator_id, {
              period: item.reporting_period ?? '',
              scope: item.operational_scope ?? '',
              denominator: item.denominator_value === undefined ? '' : String(item.denominator_value),
              denominatorUnit: item.denominator_unit ?? '',
              baseline: item.baseline_value === undefined ? '' : String(item.baseline_value),
              benchmark: item.benchmark_value === undefined ? '' : String(item.benchmark_value),
              target: item.target_value === undefined ? '' : String(item.target_value),
              referenceUnit: item.reference_unit ?? '',
              sourceId: item.source_ids[0] ?? '',
              narrative: item.narrative ?? '',
            }])),
          },
        }))
      }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Accepted evidence could not be loaded.'))
    }
  }

  function loadPresentationExample() {
    const exampleIds = companies.slice(0, 3).map((company) => company.sme_id)
    setSelected(exampleIds)
    setCohortName('UAE Green SME opportunity review')
    setDrafts(Object.fromEntries(exampleIds.map((smeId, companyIndex) => {
      const company = companies.find((item) => item.sme_id === smeId)!
      const facts = Object.fromEntries(Object.keys(configuration?.assessment_policy.fact_questions ?? {}).map((key) => [key, false]))
      facts.offers_environmental_solution = true
      facts.operates_facility = true
      if (smeId.includes('solar')) facts.provides_clean_energy = true
      if (smeId.includes('ecopack')) facts.handles_materials_or_waste = true
      if (smeId.includes('greenforge')) facts.manufactures_or_processes = true
      const ratingIndex = Math.max(1, 4 - companyIndex)
      const ratings = Object.fromEntries(scoredCriteria.map((criterion, criterionIndex) => [
        criterion.criterion_id,
        scale[Math.max(0, Math.min(scale.length - 1, ratingIndex - (criterionIndex % 2)))] ?? 'medium',
      ]))
      const sourceId = records[smeId]?.documents[0]?.document_id ?? ''
      const financial = Object.fromEntries((configuration?.financial_policy.metrics ?? []).map((metric) => [metric.metric_id, {
        state: 'unknown', value: '', unit: metric.allowed_units[0] ?? '', period: '', basis: '', sourceId: '',
      }]))
      const readiness = Object.fromEntries((configuration?.readiness_specification.factors ?? []).map((factor) => [factor.factor_id, {
        state: sourceId ? 'enabling_evidence' : 'unknown', sourceId, narrative: sourceId ? 'Reviewed source indicates an enabling condition.' : '',
      }]))
      return [smeId, { activityDescription: `${company.legal_name} provides ${company.sector.toLowerCase()} solutions with documented environmental outcomes.`, facts, ratings, financial, readiness, metricContexts: {} }]
    })))
  }

  function stepError() {
    if (step === 1 && selected.length < 2) return 'Select at least two companies for a fair comparison.'
    if (step === 1 && !cohortName.trim()) return 'Give this comparison a clear name.'
    if (step === 2 && selected.some((smeId) => !draftFor(smeId).activityDescription.trim())) return 'Every company needs an activity description.'
    if (step === 3 && selected.some((smeId) => scoredCriteria.some((criterion) => !draftFor(smeId).ratings[criterion.criterion_id]))) return 'Complete every reviewer rating. The backend will ignore ratings for criteria it determines are not applicable.'
    if (step === 4) {
      for (const smeId of selected) {
        const draft = draftFor(smeId)
        for (const metric of configuration?.financial_policy.metrics.filter((item) => item.role !== 'derived_indicator') ?? []) {
          const item = draft.financial[metric.metric_id]
          if (item?.state === 'reported' && (!Number.isFinite(Number(item.value)) || !item.sourceId || (metric.requires_reporting_period && !item.period))) return `Complete the value, source and required period for ${metric.title}.`
        }
        for (const factor of configuration?.readiness_specification.factors ?? []) {
          const item = draft.readiness[factor.factor_id]
          if (['enabling_evidence', 'constraining_evidence', 'mixed_evidence'].includes(item?.state) && !item.sourceId) return `Choose a source for ${factor.title}.`
        }
      }
    }
    return ''
  }

  function continueStep() {
    const issue = stepError()
    if (issue) { setError(issue); return }
    setError('')
    setStep((current) => Math.min(4, current + 1))
  }

  async function runAssessment() {
    const issue = stepError()
    if (issue || !configuration) { setError(issue || 'Assessment configuration is unavailable.'); return }
    setSubmitting(true)
    setError('')
    const timestamp = Date.now()
    const request: CohortAssessmentRequest = {
      run_id: `run_${slug(cohortName)}_${timestamp}`,
      cohort_id: slug(cohortName),
      version: '1.0',
      minimum_shared_criteria: minimumSharedCriteria,
      minimum_shared_weight_ratio: configuration.normalization_policy.minimum_coverage_ratio,
      submissions: selected.map((smeId) => {
        const company = companies.find((item) => item.sme_id === smeId)!
        const draft = draftFor(smeId)
        return {
          context: {
            sme_id: smeId,
            activity_description: draft.activityDescription,
            sector: company.sector,
            facts: draft.facts,
          },
          responses: scoredCriteria.map((criterion) => ({
            response_id: `response_${smeId}_${criterion.criterion_id}_${timestamp}`,
            sme_id: smeId,
            criterion_id: criterion.criterion_id,
            kind: 'linguistic' as const,
            linguistic_value: draft.ratings[criterion.criterion_id],
            submitted_by: user?.id ?? 'reviewer_preview',
          })),
          financial_observations: configuration.financial_policy.metrics.filter((metric) => metric.role !== 'derived_indicator').map((metric) => {
            const item = draft.financial[metric.metric_id] ?? { state: 'unknown', value: '', unit: metric.allowed_units[0] ?? '', period: '', basis: '', sourceId: '' }
            return {
              observation_id: `financial_${smeId}_${metric.metric_id}_${timestamp}`,
              sme_id: smeId, metric_id: metric.metric_id,
              state: item.state as 'reported' | 'unknown' | 'not_measured' | 'not_applicable' | 'needs_review',
              ...(item.state === 'reported' ? { value: Number(item.value), unit: item.unit, reporting_period: item.period || undefined, comparison_basis: item.basis || undefined } : {}),
              source_ids: item.sourceId ? [item.sourceId] : [],
            }
          }),
          readiness_observations: configuration.readiness_specification.factors.map((factor) => {
            const item = draft.readiness[factor.factor_id] ?? { state: 'unknown', sourceId: '', narrative: '' }
            return {
              observation_id: `readiness_${smeId}_${factor.factor_id}_${timestamp}`,
              sme_id: smeId, factor_id: factor.factor_id,
              state: item.state as 'enabling_evidence' | 'constraining_evidence' | 'mixed_evidence' | 'unknown' | 'not_applicable' | 'needs_review',
              source_ids: item.sourceId ? [item.sourceId] : [], narrative: item.narrative || undefined,
            }
          }),
          metric_contexts: Object.entries(draft.metricContexts).filter(([, item]) => Object.values(item).some(Boolean)).map(([indicatorId, item]) => ({
            context_id: `context_${smeId}_${indicatorId}_${timestamp}`, sme_id: smeId, indicator_id: indicatorId,
            reporting_period: item.period || undefined, operational_scope: item.scope || undefined,
            denominator_value: item.denominator ? Number(item.denominator) : undefined, denominator_unit: item.denominatorUnit || undefined,
            baseline_value: item.baseline ? Number(item.baseline) : undefined, benchmark_value: item.benchmark ? Number(item.benchmark) : undefined,
            target_value: item.target ? Number(item.target) : undefined, reference_unit: item.referenceUnit || undefined,
            source_ids: item.sourceId ? [item.sourceId] : [], narrative: item.narrative || undefined,
          })),
        }
      }),
    }
    try {
      const result = await api.createAssessment(request)
      navigate(`/assessments/${result.run_id}`)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The comparison could not be completed.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="skeleton assessment-builder-skeleton" />

  return (
    <>
      <div className="breadcrumbs"><Link to="/assessments"><ArrowLeft size={14} /> Assessment runs</Link><span>/</span><span>New comparison</span></div>
      <section className="page-heading assessment-builder-heading">
        <div><span className="eyebrow">Governed decision workflow</span><h1>Create a comparison</h1><p>Build the cohort, describe actual activities, then provide traceable reviewer judgements.</p></div>
        {isPreviewMode && <button className="secondary-button" type="button" onClick={loadPresentationExample}><Play size={16} /> Load presentation example</button>}
      </section>

      <nav className="builder-steps" aria-label="Assessment progress">
        {[[1, 'Cohort'], [2, 'Applicability'], [3, 'Environmental review'], [4, 'Finance & readiness']].map(([number, label]) => (
          <button type="button" key={number} className={step === number ? 'active' : step > Number(number) ? 'complete' : ''} onClick={() => Number(number) < step && setStep(Number(number))}>
            <span>{step > Number(number) ? <Check size={14} /> : number}</span>{label}
          </button>
        ))}
      </nav>

      {error && <div className="error-banner">{error}</div>}

      {step === 1 && (
        <section className="panel builder-panel">
          <div className="builder-panel__intro"><span className="builder-panel__icon"><Users size={21} /></span><div><h2>Choose the comparison cohort</h2><p>Only companies inside this run are compared. The completed result becomes an immutable snapshot.</p></div></div>
          <label className="builder-field">Comparison name<input value={cohortName} onChange={(event) => setCohortName(event.target.value)} /></label>
          <div className="company-selector">
            {companies.map((company) => (
              <button type="button" key={company.sme_id} className={selected.includes(company.sme_id) ? 'selected' : ''} onClick={() => toggleCompany(company.sme_id)}>
                <span className="company-selector__check">{selected.includes(company.sme_id) && <Check size={14} />}</span>
                <strong>{company.legal_name}</strong><small>{company.sector}</small>
              </button>
            ))}
          </div>
          <div className="advanced-control"><SlidersHorizontal size={16} /><label>Minimum shared scored criteria<input type="number" min="1" max={Math.max(1, scoredCriteria.length)} value={minimumSharedCriteria} onChange={(event) => setMinimumSharedCriteria(Number(event.target.value))} /></label><p>Comparisons stop if companies do not share enough legitimate criteria.</p></div>
        </section>
      )}

      {step === 2 && (
        <div className="profile-stack">
          <div className="methodology-note">
            <Info size={18} />
            <p>
              Accepted document evidence prefills activity answers. Anything
              not supported remains unclear for the reviewer; sector labels
              never create yes/no answers by themselves.
            </p>
          </div>
          {selected.map((smeId) => {
            const company = companies.find((item) => item.sme_id === smeId)!
            const draft = draftFor(smeId)
            const prefill = autofill[smeId]
            return (
              <section className="panel profile-card" key={smeId}>
                <div className="profile-card__header"><div><span className="eyebrow">Activity profile</span><h2>{company.legal_name}</h2></div><span>{company.sector}</span></div>
                {prefill && <div className="methodology-note"><Info size={16} /><p>Accepted evidence prefilled {Object.keys(prefill.facts).length} activity answers and {prefill.activity_description_source_ids.length ? 'the activity description' : 'the registered-sector fallback'}. Review before continuing.</p></div>}
                {prefill?.sector_proposals.length ? <div className="methodology-note"><Info size={16} /><p>Document evidence suggests: {prefill.sector_proposals.map((item) => item.sector_id.replaceAll('_', ' ')).join(', ')}. This remains a proposal and does not silently replace the registered sector.</p></div> : null}
                <label className="builder-field">What does this company actually do?<textarea value={draft.activityDescription} onChange={(event) => updateDraft(smeId, (current) => ({ ...current, activityDescription: event.target.value }))} /></label>
                <div className="fact-grid">
                  {Object.entries(configuration?.assessment_policy.fact_questions ?? {}).map(([factId, question]) => (
                    <article key={factId}><p>{question}</p><div className="tri-state">
                      {[[true, 'Yes'], [false, 'No'], [null, 'Unclear']] .map(([value, label]) => (
                        <button type="button" key={label as string} className={draft.facts[factId] === value ? 'active' : ''} onClick={() => updateDraft(smeId, (current) => ({ ...current, facts: { ...current.facts, [factId]: value as boolean | null } }))}>{label as string}</button>
                      ))}
                    </div></article>
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {step === 3 && (
        <div className="rating-stack">
          <div className="methodology-note"><Info size={18} /><p>The activity answers determine applicability. Ratings are reviewer judgements—not invented company metrics—and unused conditional ratings are discarded by the backend.</p></div>
          {selected.map((smeId) => {
            const company = companies.find((item) => item.sme_id === smeId)!
            const draft = draftFor(smeId)
            return (
              <section className="panel rating-card" key={smeId}>
                <div className="profile-card__header"><div><span className="eyebrow">Evidence-informed judgement</span><h2>{company.legal_name}</h2></div></div>
                <div className="rating-list">
                  {scoredCriteria.map((criterion) => {
                    const weight = configuration?.normalization_policy.rules.find((rule) => rule.criterion_id === criterion.criterion_id)?.base_weight ?? 0
                    return (
                      <article key={criterion.criterion_id}>
                        <div><strong>{criterion.title}</strong><p>{criterion.question}</p><span>{criterion.requirement} · development weight {Math.round(weight * 100)}%</span></div>
                        <select value={draft.ratings[criterion.criterion_id] ?? ''} onChange={(event) => updateDraft(smeId, (current) => ({ ...current, ratings: { ...current.ratings, [criterion.criterion_id]: event.target.value } }))}>
                          <option value="">Select rating</option>
                          {scale.map((value) => <option value={value} key={value}>{ratingLabels[value] ?? value}</option>)}
                        </select>
                      </article>
                    )
                  })}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {step === 4 && (
        <div className="profile-stack">
          <div className="methodology-note"><Info size={18} /><p>These are separate profiles. Financial health is not part of the Green Score; readiness is contextual and receives no scalar score; raw utility totals remain non-comparable until their context is complete.</p></div>
          {selected.map((smeId) => {
            const company = companies.find((item) => item.sme_id === smeId)!
            const draft = draftFor(smeId)
            const record = records[smeId]
            const prefill = autofill[smeId]
            const sources = [
              ...(record?.documents.map((document) => ({ id: document.document_id, label: `Document · ${document.file_name}` })) ?? []),
              ...(record?.evidence_items.filter((item) => item.validation_status === 'accepted').map((item) => ({ id: item.evidence_id, label: `Evidence · ${item.indicator_id}` })) ?? []),
            ]
            const observedIndicators = new Set(record?.evidence_items.filter((item) => item.validation_status === 'accepted').map((item) => item.indicator_id) ?? [])
            const contextMetrics = configuration?.metric_catalog.metrics.filter(
              (metric) => metric.dimension === 'environmental_performance'
                && metric.value_nature !== 'activity_denominator'
                && observedIndicators.has(metric.indicator_id),
            ) ?? []
            return (
              <section className="panel dimension-card" key={smeId}>
                <div className="profile-card__header"><div><span className="eyebrow">Distinct assessment dimensions</span><h2>{company.legal_name}</h2></div></div>
                {prefill && <div className="methodology-note"><Info size={16} /><p>Accepted evidence prefilled {prefill.financial_observations.length} financial values, {prefill.readiness_observations.length} readiness factors and {prefill.metric_contexts.length} environmental contexts. {prefill.gaps.length ? `${prefill.gaps.length} conflict(s) still require review.` : 'No accepted-evidence conflicts were found.'}</p></div>}

                <div className="dimension-section">
                  <div><h3>Financial & investment assessment</h3><p>Core ratios establish coverage. Supporting transaction values remain visible without fabricated pass/fail thresholds.</p></div>
                  <div className="dimension-list">
                    {configuration?.financial_policy.metrics.filter((metric) => metric.role !== 'derived_indicator').map((metric) => {
                      const item = draft.financial[metric.metric_id] ?? { state: 'unknown', value: '', unit: metric.allowed_units[0] ?? '', period: '', basis: '', sourceId: '' }
                      return <article key={metric.metric_id}>
                        <div><strong>{metric.title}</strong><span>{metric.importance} · {metric.group.replaceAll('_', ' ')}</span><small>{metric.description}</small></div>
                        <div className="dimension-inputs">
                          <select value={item.state} onChange={(event) => updateFinancial(smeId, metric.metric_id, { state: event.target.value })}>
                            <option value="unknown">Unknown</option><option value="reported">Reported</option><option value="not_measured">Not measured</option><option value="not_applicable">Not applicable</option><option value="needs_review">Needs review</option>
                          </select>
                          {item.state === 'reported' && <>
                            <input type="number" step="any" value={item.value} placeholder="Value" onChange={(event) => updateFinancial(smeId, metric.metric_id, { value: event.target.value })} />
                            <select value={item.unit || metric.allowed_units[0]} onChange={(event) => updateFinancial(smeId, metric.metric_id, { unit: event.target.value })}>{metric.allowed_units.map((unit) => <option key={unit} value={unit}>{unit.replaceAll('_', ' ')}</option>)}</select>
                            {metric.requires_reporting_period && <input value={item.period} placeholder="Reporting period" onChange={(event) => updateFinancial(smeId, metric.metric_id, { period: event.target.value })} />}
                            {metric.requires_comparison_basis && <input value={item.basis} placeholder="Comparison basis, e.g. FY2025 vs FY2024" onChange={(event) => updateFinancial(smeId, metric.metric_id, { basis: event.target.value })} />}
                            <select value={item.sourceId} onChange={(event) => updateFinancial(smeId, metric.metric_id, { sourceId: event.target.value })}><option value="">Select source</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</select>
                          </>}
                        </div>
                      </article>
                    })}
                  </div>
                </div>

                <div className="dimension-section">
                  <div><h3>SME readiness observations</h3><p>Seven research-grounded subdrivers. These states later receive causal interpretation from calibrated DEMATEL, never automatic Green Score weights.</p></div>
                  <div className="dimension-list">
                    {configuration?.readiness_specification.factors.map((factor) => {
                      const item = draft.readiness[factor.factor_id] ?? { state: 'unknown', sourceId: '', narrative: '' }
                      const evidenceState = ['enabling_evidence', 'constraining_evidence', 'mixed_evidence'].includes(item.state)
                      return <article key={factor.factor_id}>
                        <div><strong>{factor.title}</strong><span>{factor.domain_id.replaceAll('_', ' ')}</span></div>
                        <div className="dimension-inputs">
                          <select value={item.state} onChange={(event) => updateReadiness(smeId, factor.factor_id, { state: event.target.value })}>
                            <option value="unknown">Unknown</option><option value="enabling_evidence">Enabling evidence</option><option value="constraining_evidence">Constraining evidence</option><option value="mixed_evidence">Mixed evidence</option><option value="needs_review">Needs review</option><option value="not_applicable">Not applicable</option>
                          </select>
                          {evidenceState && <select value={item.sourceId} onChange={(event) => updateReadiness(smeId, factor.factor_id, { sourceId: event.target.value })}><option value="">Select source</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</select>}
                          <input value={item.narrative} placeholder="Reviewer interpretation (optional)" onChange={(event) => updateReadiness(smeId, factor.factor_id, { narrative: event.target.value })} />
                        </div>
                      </article>
                    })}
                  </div>
                </div>

                <div className="dimension-section">
                  <div><h3>Environmental measurement context</h3><p>Only accepted extracted measurements appear. Add denominators, boundaries and references when the source supports them.</p></div>
                  {!contextMetrics.length && <p className="muted-copy">No accepted environmental measurement currently requires added comparison context.</p>}
                  <div className="dimension-list">
                    {contextMetrics.map((metric) => {
                      const item = draft.metricContexts[metric.indicator_id] ?? { period: '', scope: '', denominator: '', denominatorUnit: '', baseline: '', benchmark: '', target: '', referenceUnit: '', sourceId: '', narrative: '' }
                      return <article key={metric.indicator_id}>
                        <div><strong>{metric.name}</strong><span>{metric.comparison_requirements.map((value) => value.replaceAll('_', ' ')).join(' · ')}</span></div>
                        <div className="dimension-inputs dimension-inputs--context">
                          <input value={item.period} placeholder="Reporting period" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { period: event.target.value })} />
                          <input value={item.scope} placeholder="Operational boundary / scope" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { scope: event.target.value })} />
                          <input type="number" step="any" value={item.denominator} placeholder="Denominator value" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { denominator: event.target.value })} />
                          <input value={item.denominatorUnit} placeholder="Denominator unit" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { denominatorUnit: event.target.value })} />
                          <input type="number" step="any" value={item.baseline} placeholder="Baseline (optional)" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { baseline: event.target.value })} />
                          <input type="number" step="any" value={item.benchmark} placeholder="Benchmark (optional)" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { benchmark: event.target.value })} />
                          <input type="number" step="any" value={item.target} placeholder="Target (optional)" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { target: event.target.value })} />
                          <input value={item.referenceUnit} placeholder="Reference unit" onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { referenceUnit: event.target.value })} />
                          <select value={item.sourceId} onChange={(event) => updateMetricContext(smeId, metric.indicator_id, { sourceId: event.target.value })}><option value="">Select context source</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</select>
                        </div>
                      </article>
                    })}
                  </div>
                </div>
              </section>
            )
          })}
        </div>
      )}

      <div className="builder-footer">
        <button className="secondary-button" type="button" onClick={() => step === 1 ? navigate('/assessments') : setStep((current) => current - 1)}><ArrowLeft size={16} /> {step === 1 ? 'Cancel' : 'Back'}</button>
        {step < 4 ? <button className="primary-button" type="button" onClick={continueStep}>Continue <ArrowRight size={16} /></button> : <button className="primary-button" type="button" disabled={submitting} onClick={() => void runAssessment()}><Play size={16} /> {submitting ? 'Running all methods…' : 'Run comparison'}</button>}
      </div>
    </>
  )
}
