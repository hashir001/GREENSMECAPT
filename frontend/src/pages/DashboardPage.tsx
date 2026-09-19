import {
  ArrowUpRight,
  BarChart3,
  Building2,
  CircleCheck,
  Layers3,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { MetricCard } from '../components/MetricCard'
import { RankingChart } from '../components/RankingChart'
import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type {
  AssessmentRunRecord,
  AssessmentRunSummary,
  SME,
} from '../types/api'

type DashboardState = {
  smes: SME[]
  runs: AssessmentRunSummary[]
  latestRun: AssessmentRunRecord | null
}

const initialState: DashboardState = { smes: [], runs: [], latestRun: null }

function shortDate(value: string): string {
  return new Intl.DateTimeFormat('en', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value))
}

export function DashboardPage() {
  const [state, setState] = useState(initialState)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const [smes, runs] = await Promise.all([
        api.listSMEs(),
        api.listAssessmentRuns(),
      ])
      const latestRun = runs[0]
        ? await api.getAssessmentRun(runs[0].run_id)
        : null

      setState({ smes, runs, latestRun })
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Dashboard data failed to load.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    queueMicrotask(() => void loadDashboard())
  }, [loadDashboard])

  const assessedSMEs = useMemo(
    () => new Set(state.runs.flatMap((run) => run.sme_ids)).size,
    [state.runs],
  )
  const portfolioCoverage = state.smes.length
    ? Math.round((assessedSMEs / state.smes.length) * 100)
    : 0
  const ranking =
    state.latestRun?.result.comparable_topsis.topsis_result.ranking ?? []
  const names = new Map(
    state.smes.map((sme) => [sme.sme_id, sme.legal_name]),
  )
  const chartData = ranking.map((item) => ({
    name: names.get(item.sme_id) ?? item.sme_id,
    score: item.score,
    rank: item.rank,
  }))
  const robustness = state.latestRun?.result.robustness
  const latestLeader = ranking[0]

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Portfolio command centre</span>
          <h1>Investment overview</h1>
          <p>
            Evidence quality, assessment coverage and ranked opportunities in one view.
          </p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => void loadDashboard()}
        >
          <RefreshCw size={17} className={loading ? 'spin' : ''} />
          Refresh data
        </button>
      </section>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button type="button" onClick={() => void loadDashboard()}>
            Try again
          </button>
        </div>
      )}

      <section className="metric-grid" aria-label="Portfolio metrics">
        <MetricCard
          icon={Building2}
          label="SMEs in portfolio"
          value={loading ? '—' : String(state.smes.length)}
          detail="Companies available to this account"
        />
        <MetricCard
          icon={Layers3}
          label="Completed comparisons"
          value={loading ? '—' : String(state.runs.length)}
          detail="Immutable assessment snapshots"
          tone="blue"
        />
        <MetricCard
          icon={CircleCheck}
          label="Portfolio assessed"
          value={loading ? '—' : `${portfolioCoverage}%`}
          detail={`${assessedSMEs} unique SMEs included in runs`}
          tone="gold"
        />
        <MetricCard
          icon={ShieldCheck}
          label="Sensitivity scenarios"
          value={loading ? '—' : String(robustness?.completed_scenarios ?? 0)}
          detail="Latest ranking robustness check"
          tone="plum"
        />
      </section>

      <section className="dashboard-grid">
        <article className="panel panel--ranking">
          <div className="panel__header">
            <div>
              <span className="eyebrow">Latest comparison</span>
              <h2>SME ranking</h2>
            </div>
            {state.latestRun && (
              <StatusPill
                label={state.latestRun.comparison_status.replaceAll('_', ' ')}
                tone="positive"
              />
            )}
          </div>

          {loading ? (
            <div className="skeleton skeleton--chart" />
          ) : chartData.length ? (
            <>
              <RankingChart data={chartData} />
              <div className="ranking-note">
                <BarChart3 size={18} />
                <p>
                  <strong>
                    {names.get(latestLeader?.sme_id ?? '') ?? 'Top SME'}
                  </strong>{' '}
                  currently leads with a score of{' '}
                  <strong>{Math.round((latestLeader?.score ?? 0) * 100)}</strong>.
                  Review the full run before making an investment decision.
                </p>
              </div>
            </>
          ) : (
            <EmptyState
              title="No completed ranking yet"
              detail="A reviewer must complete a cohort assessment before rankings appear here."
            />
          )}
        </article>

        <article className="panel panel--activity">
          <div className="panel__header">
            <div>
              <span className="eyebrow">Recent activity</span>
              <h2>Assessment runs</h2>
            </div>
            <Link className="text-link" to="/assessments">
              View all <ArrowUpRight size={15} />
            </Link>
          </div>

          <div className="run-list">
            {loading
              ? Array.from({ length: 3 }, (_, index) => (
                  <div className="skeleton skeleton--row" key={index} />
                ))
              : state.runs.slice(0, 4).map((run) => (
                  <Link className="run-row" to={`/assessments/${run.run_id}`} key={run.run_id}>
                    <span className="run-row__mark"><BarChart3 size={18} /></span>
                    <span className="run-row__copy">
                      <strong>{run.cohort_id}</strong>
                      <small>{run.sme_ids.length} SMEs · {shortDate(run.created_at)}</small>
                    </span>
                    <StatusPill label="Complete" tone="positive" />
                  </Link>
                ))}
            {!loading && !state.runs.length && (
              <EmptyState
                title="No assessment history"
                detail="Completed runs will appear here."
              />
            )}
          </div>
        </article>
      </section>

      <section className="panel portfolio-preview">
        <div className="panel__header">
          <div>
            <span className="eyebrow">Current universe</span>
            <h2>SME portfolio</h2>
          </div>
          <Link
            className="secondary-button secondary-button--small"
            to="/companies"
          >
            Explore portfolio <ArrowUpRight size={15} />
          </Link>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Company</th><th>Sector</th><th>Jurisdiction</th><th>Assessment</th>
              </tr>
            </thead>
            <tbody>
              {state.smes.slice(0, 5).map((sme) => {
                const assessed = state.runs.some((run) =>
                  run.sme_ids.includes(sme.sme_id),
                )

                return (
                  <tr key={sme.sme_id}>
                    <td><strong>{sme.legal_name}</strong><small>{sme.sme_id}</small></td>
                    <td>{sme.sector}</td>
                    <td>{sme.jurisdiction}</td>
                    <td>
                      <StatusPill
                        label={assessed ? 'Assessed' : 'Pending'}
                        tone={assessed ? 'positive' : 'warning'}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!loading && !state.smes.length && (
            <EmptyState
              title="No SMEs registered"
              detail="Add the first company through an administrator account."
            />
          )}
        </div>
      </section>
    </>
  )
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon"><Layers3 size={21} /></span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  )
}
