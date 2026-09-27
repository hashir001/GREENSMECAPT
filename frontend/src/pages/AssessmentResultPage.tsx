import { AlertTriangle, ArrowLeft, Award, CheckCircle2, GitCompareArrows, Scale, ShieldCheck, Target } from 'lucide-react'
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { Link, useParams } from 'react-router-dom'

import { RankingChart } from '../components/RankingChart'
import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type { AssessmentRunRecord, RankedSME, SME } from '../types/api'

function humanize(value: string) {
  return value.replace(/^normalized:/, '').replaceAll('_', ' ')
}

function scorePercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function rankingMap(ranking: RankedSME[]) {
  return new Map(ranking.map((item) => [item.sme_id, item]))
}

export function AssessmentResultPage() {
  const { runId = '' } = useParams()
  const [run, setRun] = useState<AssessmentRunRecord | null>(null)
  const [companies, setCompanies] = useState<SME[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([api.getAssessmentRun(runId), api.listSMEs()])
      .then(([nextRun, nextCompanies]) => { setRun(nextRun); setCompanies(nextCompanies) })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Assessment result could not be loaded.'))
      .finally(() => setLoading(false))
  }, [runId])

  const names = useMemo(() => new Map(companies.map((company) => [company.sme_id, company.legal_name])), [companies])

  if (loading) return <div className="skeleton result-page-skeleton" />
  if (!run) return <section className="panel empty-state"><strong>Assessment unavailable</strong><p>{error}</p><Link className="secondary-button" to="/assessments"><ArrowLeft size={16} /> Return to runs</Link></section>

  const crisp = run.result.comparable_topsis.topsis_result.ranking
  const fuzzy = run.result.fuzzy_topsis.ranking
  const fuzzyBySme = rankingMap(fuzzy)
  const leader = crisp[0]
  const robustness = run.result.robustness
  const stability = robustness?.sme_stability ?? []
  const weights = run.result.comparable_topsis.topsis_result.normalized_weights ?? {}
  const coverage = run.result.comparable_topsis.coverage ?? []
  const chartData = crisp.map((item) => ({ name: names.get(item.sme_id) ?? item.sme_id, score: item.score, rank: item.rank }))

  return (
    <>
      <div className="breadcrumbs"><Link to="/assessments"><ArrowLeft size={14} /> Assessment runs</Link><span>/</span><span>{run.cohort_id}</span></div>

      <section className="result-hero">
        <div><span className="eyebrow eyebrow--light">Completed decision analysis</span><h1>{run.cohort_id.replaceAll('_', ' ')}</h1><p>{run.sme_ids.length} companies · {run.result.comparable_topsis.shared_criterion_ids.length} shared criteria · version {run.cohort_version}</p></div>
        <div className="result-hero__winner"><span><Award size={21} /></span><div><small>Leading company</small><strong>{names.get(leader?.sme_id ?? '') ?? leader?.sme_id}</strong><p>{scorePercent(leader?.score ?? 0)} TOPSIS closeness score</p></div></div>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {robustness?.warnings.length ? <div className="insight-banner"><span className="insight-banner__icon"><AlertTriangle size={20} /></span><div><strong>Sensitivity warning</strong><p>{robustness.warnings.join(' ')}</p></div></div> : (
        <div className="result-assurance"><ShieldCheck size={18} /><span><strong>Robustness checked.</strong> {robustness?.completed_scenarios ?? 0} controlled weight and threshold perturbations completed.</span></div>
      )}

      <section className="result-overview-grid">
        <article className="panel result-ranking-panel"><div className="panel__header"><div><span className="eyebrow">Primary ranking</span><h2>Relative portfolio position</h2></div><StatusPill label={run.comparison_status} tone={run.comparison_status === 'ready' ? 'positive' : 'warning'} /></div><RankingChart data={chartData} /></article>
        <article className="panel method-guide"><span className="eyebrow">How to read this</span><h2>Three methods, three questions</h2>
          <div><span><Target size={18} /></span><p><strong>TOPSIS</strong>Who is closest to the strongest overall profile and furthest from the weakest?</p></div>
          <div><span><Scale size={18} /></span><p><strong>Fuzzy TOPSIS</strong>Does that order survive when qualitative ratings are treated as ranges rather than false precision?</p></div>
          <div><span><GitCompareArrows size={18} /></span><p><strong>ELECTRE III</strong>Does one company credibly outrank another without hiding vetoes or genuine incomparability?</p></div>
        </article>
      </section>

      <section className="panel method-comparison">
        <div className="panel__header"><div><span className="eyebrow">Cross-method view</span><h2>Ranking agreement</h2></div><span className="result-count">No single method is treated as unquestionable</span></div>
        <div className="method-table-wrap"><table><thead><tr><th>Company</th><th>TOPSIS</th><th>Fuzzy TOPSIS</th><th>ELECTRE III</th><th>Interpretation</th></tr></thead><tbody>
          {crisp.map((item) => {
            const fuzzyItem = fuzzyBySme.get(item.sme_id)
            const electreLevel = run.result.electre_iii.rank_levels.find((level) => level.sme_ids.includes(item.sme_id))
            const stable = fuzzyItem?.rank === item.rank && electreLevel?.level === item.rank
            return <tr key={item.sme_id}><td><strong>{names.get(item.sme_id) ?? item.sme_id}</strong><small>{item.sme_id}</small></td><td><b>#{item.rank}</b><span>{scorePercent(item.score)}</span></td><td><b>#{fuzzyItem?.rank ?? '—'}</b><span>{fuzzyItem ? scorePercent(fuzzyItem.score) : 'Not returned'}</span></td><td><b>Level {electreLevel?.level ?? '—'}</b><span>{electreLevel?.contains_preference_cycle ? 'Preference cycle' : 'No cycle'}</span></td><td><StatusPill label={stable ? 'methods agree' : 'inspect difference'} tone={stable ? 'positive' : 'warning'} /></td></tr>
          })}
        </tbody></table></div>
        {run.result.electre_iii.incomparable_pairs.length > 0 && <div className="incomparability-note"><GitCompareArrows size={17} /><p><strong>{run.result.electre_iii.incomparable_pairs.length} incomparable pair{run.result.electre_iii.incomparable_pairs.length === 1 ? '' : 's'}.</strong> ELECTRE found cases where neither company can honestly be declared superior under the current evidence and thresholds.</p></div>}
      </section>

      <section className="decision-grid">
        <article className="panel"><div className="panel__header"><div><span className="eyebrow">Model influence</span><h2>Shared criterion weights</h2></div></div><div className="weight-list">
          {Object.entries(weights).sort(([, left], [, right]) => right - left).map(([criterion, weight]) => <div key={criterion}><span>{humanize(criterion)}</span><div><i style={{ width: `${weight * 100}%` }} /></div><strong>{scorePercent(weight)}</strong></div>)}
        </div></article>
        <article className="panel"><div className="panel__header"><div><span className="eyebrow">Comparability</span><h2>Cohort coverage</h2></div></div><div className="coverage-list">
          {coverage.map((item) => <div key={item.sme_id}><span><strong>{names.get(item.sme_id) ?? item.sme_id}</strong><small>{item.shared_criterion_ids.length} shared · {item.excluded_criterion_ids.length} excluded</small></span><div><i style={{ width: `${item.shared_weight_ratio * 100}%` }} /></div><b>{scorePercent(item.shared_weight_ratio)}</b></div>)}
          {!coverage.length && <p className="muted-copy">Coverage detail was not stored for this legacy preview run.</p>}
        </div></article>
      </section>

      {(run.result.preparations?.length ?? 0) > 0 && <section className="panel dimension-results">
        <div className="panel__header"><div><span className="eyebrow">Separate decision dimensions</span><h2>Financial, readiness and measurement context</h2></div><span className="result-count">Not collapsed into the Green Score</span></div>
        <div className="dimension-result-grid">
          {run.result.preparations?.map((preparation) => {
            const financial = preparation.financial_assessment
            const readiness = preparation.readiness_profile
            const constraints = readiness.factors.filter((factor) => factor.state === 'constraining_evidence' || factor.state === 'mixed_evidence')
            const contextual = preparation.performance_context.metrics
            const readyMetrics = contextual.filter((metric) => metric.state === 'ready').length
            return <article key={preparation.profile.sme_id}>
              <header><strong>{names.get(preparation.profile.sme_id) ?? preparation.profile.sme_id}</strong><StatusPill label={`finance ${financial.status}`} tone={financial.status === 'complete' ? 'positive' : 'warning'} /></header>
              <div className="dimension-result-stats"><span><b>{scorePercent(financial.core_coverage_ratio)}</b> core financial coverage</span><span><b>{constraints.length}</b> readiness constraint{constraints.length === 1 ? '' : 's'}</span><span><b>{readyMetrics}/{contextual.length}</b> metrics context-ready</span></div>
              <div className="dimension-result-detail">
                <strong>Financial evidence</strong>
                {financial.metrics.filter((metric) => metric.state === 'reported').map((metric) => <span key={metric.metric_id}>{humanize(metric.title)}: {metric.value?.toLocaleString()} {metric.unit?.replaceAll('_', ' ')}</span>)}
                {!financial.metrics.some((metric) => metric.state === 'reported') && <span>No reviewed financial values reported.</span>}
              </div>
              <div className="dimension-result-detail">
                <strong>Readiness interpretation</strong>
                {constraints.map((factor) => <span key={factor.factor_id}>{humanize(factor.factor_id)} · {humanize(factor.state)}</span>)}
                {!constraints.length && <span>No evidenced constraint recorded; unknowns remain unknown.</span>}
                {!readiness.causal_results_available && <small>DEMATEL causal interpretation awaits expert calibration.</small>}
              </div>
              <div className="dimension-result-detail">
                <strong>Environmental measures</strong>
                {contextual.filter((metric) => metric.measurement_value !== null).map((metric) => <span key={metric.indicator_id}>{metric.metric_name}: {metric.measurement_value?.toLocaleString()} {metric.measurement_unit} · {humanize(metric.state)}</span>)}
                {!contextual.some((metric) => metric.measurement_value !== null) && <span>No accepted quantitative measurements.</span>}
              </div>
            </article>
          })}
        </div>
      </section>}

      {stability.length > 0 && <section className="panel stability-panel"><div className="panel__header"><div><span className="eyebrow">Sensitivity analysis</span><h2>First-place stability</h2></div><span className="result-count">Across {robustness?.completed_scenarios} scenarios</span></div><div className="stability-grid">
        {stability.map((item) => {
          const average = Object.values(item.first_place_rates).reduce((total, value) => total + value, 0) / Math.max(1, Object.keys(item.first_place_rates).length)
          return <article key={item.sme_id}><div><strong>{names.get(item.sme_id) ?? item.sme_id}</strong><span>Average across methods</span></div><div className="stability-ring" style={{ '--stability': `${average * 360}deg` } as CSSProperties}><span>{scorePercent(average)}</span></div><small>Observed rank range {Math.min(...Object.values(item.best_ranks))}–{Math.max(...Object.values(item.worst_ranks))}</small></article>
        })}
      </div></section>}

      <footer className="calibration-note"><CheckCircle2 size={17} /><p><strong>{run.result.calibration?.status === 'development' ? 'Development calibration is visible—not disguised.' : 'Calibration recorded.'}</strong> {run.result.calibration?.statement ?? 'The run preserves the exact method configuration used.'}</p></footer>
    </>
  )
}
