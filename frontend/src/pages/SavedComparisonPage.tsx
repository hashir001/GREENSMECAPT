import { ArrowLeft, Check, GitCompareArrows, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type { AssessmentRunRecord, AssessmentRunSummary, RankedSME, SME } from '../types/api'

function percent(value: number | undefined) {
  return value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function humanize(value: string) {
  return value.replace(/^normalized:/, '').replaceAll('_', ' ')
}

function rankedItem(items: RankedSME[], smeId: string) {
  return items.find((item) => item.sme_id === smeId)
}

export function SavedComparisonPage() {
  const [companies, setCompanies] = useState<SME[]>([])
  const [runs, setRuns] = useState<AssessmentRunSummary[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [run, setRun] = useState<AssessmentRunRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [resultLoading, setResultLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([api.listSMEs(), api.listAssessmentRuns()])
      .then(([nextCompanies, nextRuns]) => {
        setCompanies(nextCompanies)
        setRuns(nextRuns)
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Saved assessments could not be loaded.'))
      .finally(() => setLoading(false))
  }, [])

  const assessedIds = useMemo(() => new Set(runs.flatMap((item) => item.sme_ids)), [runs])
  const availableCompanies = useMemo(
    () => companies.filter((company) => assessedIds.has(company.sme_id)),
    [assessedIds, companies],
  )
  const matchingRuns = useMemo(() => {
    if (selected.length !== 2) return []
    return runs.filter((item) => selected.every((smeId) => item.sme_ids.includes(smeId)))
  }, [runs, selected])

  function toggleCompany(smeId: string) {
    setRun(null)
    setSelectedRunId('')
    setError('')
    setSelected((current) => {
      if (current.includes(smeId)) return current.filter((item) => item !== smeId)
      if (current.length === 2) return [current[1], smeId]
      return [...current, smeId]
    })
  }

  async function viewSavedResult() {
    const runId = selectedRunId || matchingRuns[0]?.run_id
    if (!runId) {
      setError('These companies do not share a saved assessment run yet.')
      return
    }
    setResultLoading(true)
    setError('')
    try {
      setRun(await api.getAssessmentRun(runId))
      setSelectedRunId(runId)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The saved result could not be loaded.')
    } finally {
      setResultLoading(false)
    }
  }

  const names = useMemo(() => new Map(companies.map((company) => [company.sme_id, company.legal_name])), [companies])

  if (loading) return <div className="skeleton assessment-builder-skeleton" />

  return (
    <>
      <div className="breadcrumbs"><Link to="/assessments"><ArrowLeft size={14} /> Assessment runs</Link><span>/</span><span>Saved comparison</span></div>
      <section className="page-heading"><div><span className="eyebrow">Read-only comparison</span><h1>Compare saved SME results</h1><p>Select two companies and view an existing assessment snapshot. Nothing is recalculated or edited.</p></div></section>

      <div className="comparison-assurance"><ShieldCheck size={18} /><span>This view uses immutable results already stored in the platform.</span></div>
      {error && <div className="error-banner">{error}</div>}

      <section className="panel builder-panel">
        <div className="builder-panel__intro"><span className="builder-panel__icon"><GitCompareArrows size={21} /></span><div><h2>Select two assessed companies</h2><p>Only companies present in at least one saved assessment are shown.</p></div></div>
        <div className="company-selector">
          {availableCompanies.map((company) => <button type="button" key={company.sme_id} className={selected.includes(company.sme_id) ? 'selected' : ''} onClick={() => toggleCompany(company.sme_id)}><span className="company-selector__check">{selected.includes(company.sme_id) && <Check size={14} />}</span><strong>{company.legal_name}</strong><small>{company.sector}</small></button>)}
        </div>
        {!availableCompanies.length && <div className="empty-state"><strong>No saved company results</strong><p>Complete an assessment run first.</p></div>}
        {selected.length === 2 && matchingRuns.length > 0 && <label className="builder-field saved-run-selector">Saved assessment snapshot<select value={selectedRunId || matchingRuns[0].run_id} onChange={(event) => { setSelectedRunId(event.target.value); setRun(null) }}>{matchingRuns.map((item) => <option value={item.run_id} key={item.run_id}>{item.cohort_id.replaceAll('_', ' ')} · {new Date(item.created_at).toLocaleDateString()}</option>)}</select></label>}
        {selected.length === 2 && matchingRuns.length === 0 && <p className="saved-comparison-note">No stored run contains both selected companies.</p>}
      </section>

      <div className="builder-footer"><Link className="secondary-button" to="/assessments"><ArrowLeft size={16} /> Back</Link><button className="primary-button" type="button" disabled={selected.length !== 2 || matchingRuns.length === 0 || resultLoading} onClick={() => void viewSavedResult()}>{resultLoading ? 'Loading saved result…' : 'View saved comparison'}</button></div>

      {run && <SavedResult run={run} selected={selected} names={names} />}
    </>
  )
}

function SavedResult({ run, selected, names }: { run: AssessmentRunRecord; selected: string[]; names: Map<string, string> }) {
  const crisp = run.result.comparable_topsis.topsis_result.ranking
  const fuzzy = run.result.fuzzy_topsis.ranking
  const preparations = run.result.preparations ?? []
  const weights = run.result.comparable_topsis.topsis_result.normalized_weights ?? {}
  const coverage = run.result.comparable_topsis.coverage ?? []
  const pair = run.result.electre_iii.pair_relations?.find((item) => selected.includes(item.left_sme_id) && selected.includes(item.right_sme_id))

  return <section className="saved-comparison-results">
    <div className="panel__header"><div><span className="eyebrow">Stored snapshot</span><h2>{run.cohort_id.replaceAll('_', ' ')}</h2></div><StatusPill label={run.comparison_status.replaceAll('_', ' ')} tone="positive" /></div>
    <div className="saved-company-grid">
      {selected.map((smeId) => {
        const preparation = preparations.find((item) => item.profile.sme_id === smeId)
        const greenScore = preparation?.green_score
        const crispItem = rankedItem(crisp, smeId)
        const fuzzyItem = rankedItem(fuzzy, smeId)
        const financial = preparation?.financial_assessment
        const readiness = preparation?.readiness_profile
        const context = preparation?.performance_context
        const evidenceStrength = preparation?.evidence_strength
        const constraints = readiness?.factors.filter((item) => item.state === 'constraining_evidence' || item.state === 'mixed_evidence') ?? []
        const companyCoverage = coverage.find((item) => item.sme_id === smeId)
        return <article className="panel saved-company-card" key={smeId}>
          <header><div><span className="eyebrow">Saved result</span><h2>{names.get(smeId) ?? smeId}</h2></div><strong className="saved-rank">#{crispItem?.rank ?? '—'}</strong></header>
          <div className="saved-score-grid"><span><b>{greenScore?.score === null || greenScore?.score === undefined ? '—' : `${greenScore.score.toFixed(1)}/100`}</b>Green Score · {greenScore?.status ?? 'legacy'}</span><span><b>{percent(crispItem?.score)}</b>TOPSIS</span><span><b>{percent(fuzzyItem?.score)}</b>Fuzzy TOPSIS</span><span><b>{percent(preparation?.observations.coverage.coverage_ratio)}</b>Assessment coverage</span><span><b>{percent(financial?.core_coverage_ratio)}</b>Financial coverage</span></div>
          <div className="dimension-result-detail"><strong>Environmental measures</strong>{context?.metrics.filter((item) => item.measurement_value !== null).map((item) => <span key={item.indicator_id}>{item.metric_name}: {item.measurement_value?.toLocaleString()} {item.measurement_unit ?? ''} · {humanize(item.state)}</span>)}{!context?.metrics.some((item) => item.measurement_value !== null) && <span>No accepted quantitative measurements stored.</span>}</div>
          <div className="dimension-result-detail"><strong>Financial values</strong>{financial?.metrics.filter((item) => item.state === 'reported').map((item) => <span key={item.metric_id}>{item.title}: {item.value?.toLocaleString()} {item.unit?.replaceAll('_', ' ')}</span>)}{!financial?.metrics.some((item) => item.state === 'reported') && <span>No reviewed financial values stored.</span>}</div>
          <div className="dimension-result-detail"><strong>Calculated indicators</strong>{financial?.derived_indicators.map((item) => <span key={item.indicator_id}>{humanize(item.indicator_id)}: {item.value.toLocaleString(undefined, { maximumFractionDigits: 2 })} {item.unit.replaceAll('_', ' ')}<small>{item.formula}</small></span>)}{!financial?.derived_indicators.length && <span>Required source inputs were incomplete.</span>}</div>
          <div className="dimension-result-detail"><strong>Evidence strength</strong>{evidenceStrength?.dimensions.map((item) => <span key={item.dimension_id}>{humanize(item.dimension_id)} · <b>{humanize(item.band)}</b><small>{item.rationale}</small></span>)}{!evidenceStrength && <span>No evidence-strength snapshot stored for this legacy run.</span>}</div>
          <div className="dimension-result-detail"><strong>Context and evidence</strong><span>{preparation?.observations.coverage.document_supported_count ?? 0} document-supported observations</span><span>{constraints.length} readiness constraints recorded</span><span>{companyCoverage?.excluded_criterion_ids.length ?? 0} criteria excluded from this comparison</span></div>
        </article>
      })}
    </div>
    <section className="panel saved-explanation">
      <div className="panel__header"><div><span className="eyebrow">Explainability</span><h2>Why the saved result looks this way</h2></div></div>
      <div className="saved-explanation-grid">
        <div><strong>ELECTRE III relationship</strong><p>{pair ? humanize(pair.relation) : 'No stored pairwise relation was returned for this snapshot.'}</p></div>
        <div><strong>Method agreement</strong><p>{selected.every((smeId) => rankedItem(crisp, smeId)?.rank === rankedItem(fuzzy, smeId)?.rank) ? 'TOPSIS and fuzzy TOPSIS preserve the same order.' : 'TOPSIS and fuzzy TOPSIS produce different ordering; inspect uncertainty.'}</p></div>
        <div><strong>Calibration</strong><p>{run.result.calibration?.statement ?? 'No calibration statement stored.'}</p></div>
        <div><strong>Robustness</strong><p>{run.result.robustness?.warnings.length ? run.result.robustness.warnings.join(' ') : `${run.result.robustness?.completed_scenarios ?? 0} sensitivity scenarios completed without a stored warning.`}</p></div>
      </div>
      <div className="weight-list">{Object.entries(weights).sort(([, left], [, right]) => right - left).map(([criterion, weight]) => <div key={criterion}><span>{humanize(criterion)}</span><div><i style={{ width: `${weight * 100}%` }} /></div><strong>{percent(weight)}</strong></div>)}</div>
      <small className="saved-comparison-disclaimer">TOPSIS values are relative to this saved cohort. Financial coverage is completeness—not financial performance. Readiness is contextual; development causal results are placeholders until expert calibration replaces them.</small>
    </section>
  </section>
}
