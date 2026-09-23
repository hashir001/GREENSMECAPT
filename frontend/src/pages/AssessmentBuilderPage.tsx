import { ArrowLeft, ArrowRight, Check, Info, Play, SlidersHorizontal, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { api } from '../lib/api'
import { isPreviewMode } from '../lib/supabase'
import type { AssessmentConfiguration, CohortAssessmentRequest, SME } from '../types/api'

type Draft = {
  activityDescription: string
  facts: Record<string, boolean | null>
  ratings: Record<string, string>
}

const ratingLabels: Record<string, string> = {
  very_low: 'Very low', low: 'Low', medium: 'Medium', high: 'High', very_high: 'Very high',
}

function slug(value: string) {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
}

function suggestedFacts(
  company: SME | undefined,
  factIds: string[],
): Record<string, boolean | null> {
  const facts = Object.fromEntries(
    factIds.map((factId) => [factId, false]),
  ) as Record<string, boolean | null>

  if (!company) return facts

  const description = `${company.legal_name} ${company.sector}`.toLowerCase()
  const includesAny = (...terms: string[]) => (
    terms.some((term) => description.includes(term))
  )

  facts.manufactures_or_processes = includesAny(
    'manufactur',
    'packag',
    'processing',
    'industrial',
    'production',
  )
  facts.operates_facility = includesAny(
    'manufactur',
    'packag',
    'solar',
    'energy',
    'industrial',
    'production',
    'retail',
    'hospitality',
  )
  facts.handles_materials_or_waste = includesAny(
    'manufactur',
    'packag',
    'recycl',
    'circular',
    'waste',
    'material',
    'production',
  )
  facts.provides_clean_energy = includesAny(
    'solar',
    'renewable',
    'clean energy',
  )
  facts.provides_circular_services = includesAny(
    'recycl',
    'circular',
    'reuse',
    'repair',
    'recovery',
  )
  facts.works_on_buildings = includesAny(
    'construction',
    'building',
    'retrofit',
    'rooftop',
  )
  facts.works_in_agriculture_food_land = includesAny(
    'agriculture',
    'farming',
    'food',
    'land',
  )
  facts.provides_digital_services = includesAny(
    'software',
    'digital',
    'technology',
    'consulting',
  )
  facts.offers_environmental_solution = includesAny(
    'sustainable',
    'green',
    'solar',
    'renewable',
    'clean energy',
    'environment',
    'recycl',
    'circular',
  )
  facts.operates_retail_or_hospitality = includesAny(
    'retail',
    'restaurant',
    'hospitality',
    'hotel',
  )

  return facts
}

export function AssessmentBuilderPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [companies, setCompanies] = useState<SME[]>([])
  const [configuration, setConfiguration] = useState<AssessmentConfiguration | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
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
    }
  }

  function updateDraft(smeId: string, update: (current: Draft) => Draft) {
    setDrafts((current) => ({ ...current, [smeId]: update(current[smeId] ?? draftFor(smeId)) }))
  }

  function toggleCompany(smeId: string) {
    setSelected((current) => current.includes(smeId) ? current.filter((id) => id !== smeId) : [...current, smeId])
    if (!drafts[smeId]) updateDraft(smeId, (current) => current)
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
      return [smeId, { activityDescription: `${company.legal_name} provides ${company.sector.toLowerCase()} solutions with documented environmental outcomes.`, facts, ratings }]
    })))
  }

  function stepError() {
    if (step === 1 && selected.length < 2) return 'Select at least two companies for a fair comparison.'
    if (step === 1 && !cohortName.trim()) return 'Give this comparison a clear name.'
    if (step === 2 && selected.some((smeId) => !draftFor(smeId).activityDescription.trim())) return 'Every company needs an activity description.'
    if (step === 3 && selected.some((smeId) => scoredCriteria.some((criterion) => !draftFor(smeId).ratings[criterion.criterion_id]))) return 'Complete every reviewer rating. The backend will ignore ratings for criteria it determines are not applicable.'
    return ''
  }

  function continueStep() {
    const issue = stepError()
    if (issue) { setError(issue); return }
    setError('')
    setStep((current) => Math.min(3, current + 1))
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
        {[[1, 'Cohort'], [2, 'Activity profile'], [3, 'Reviewer ratings']].map(([number, label]) => (
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
              Activity answers are prefilled from the registered company
              profile for internal review. Adjust any suggestion that does
              not describe the company accurately.
            </p>
          </div>
          {selected.map((smeId) => {
            const company = companies.find((item) => item.sme_id === smeId)!
            const draft = draftFor(smeId)
            return (
              <section className="panel profile-card" key={smeId}>
                <div className="profile-card__header"><div><span className="eyebrow">Activity profile</span><h2>{company.legal_name}</h2></div><span>{company.sector}</span></div>
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

      <div className="builder-footer">
        <button className="secondary-button" type="button" onClick={() => step === 1 ? navigate('/assessments') : setStep((current) => current - 1)}><ArrowLeft size={16} /> {step === 1 ? 'Cancel' : 'Back'}</button>
        {step < 3 ? <button className="primary-button" type="button" onClick={continueStep}>Continue <ArrowRight size={16} /></button> : <button className="primary-button" type="button" disabled={submitting} onClick={() => void runAssessment()}><Play size={16} /> {submitting ? 'Running all methods…' : 'Run comparison'}</button>}
      </div>
    </>
  )
}
