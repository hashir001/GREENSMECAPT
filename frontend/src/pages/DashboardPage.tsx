import {
  ArrowUpRight,
  BarChart3,
  Building2,
  CircleCheck,
  Layers3,
  RefreshCw,
  ShieldCheck,
  Landmark,
  FileCheck2,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { MetricCard } from '../components/MetricCard'
import { RankingChart } from '../components/RankingChart'
import { StatusPill } from '../components/StatusPill'
import { ApiError, api } from '../lib/api'
import { usePermissions } from '../auth/usePermissions'
import type {
  AssessmentRunRecord,
  AssessmentRunSummary,
  SME,
  SMEApplication,
  FinancialSubmission,
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
  const { role } = usePermissions()

  if (role === 'sme_user') return <SMEDashboard />
  if (role === 'expert') return <ExpertDashboard />
  return <PortfolioDashboard role={role} />
}

function PortfolioDashboard({ role }: { role: string | null }) {
  const [state, setState] = useState(initialState)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError('')
    setNotice('')

    try {
      const [smes, runs] = await Promise.all([
        api.listSMEs(),
        api.listAssessmentRuns(),
      ])
      let latestRun: AssessmentRunRecord | null = null

      let incompatibleRunCount = 0
      for (const run of runs) {
        try {
          latestRun = await api.getAssessmentRun(run.run_id)
          break
        } catch (caught: unknown) {
          if (caught instanceof ApiError && caught.status === 409) {
            incompatibleRunCount += 1
          } else {
            throw caught
          }
        }
      }

      if (incompatibleRunCount > 0) {
        setNotice(
          `${incompatibleRunCount} saved comparison${incompatibleRunCount === 1 ? '' : 's'} use an older assessment model. Delete and recreate ${incompatibleRunCount === 1 ? 'it' : 'them'} from published profiles.`,
        )
      }

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
          <span className="eyebrow">{role === 'investor' ? 'Investor workspace' : role === 'reviewer' ? 'Reviewer workspace' : 'Platform administration'}</span>
          <h1>{role === 'investor' ? 'Published opportunities' : role === 'reviewer' ? 'Review & assessment overview' : 'Platform overview'}</h1>
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

      {notice && (
        <div className="comparison-assurance">
          <FileCheck2 size={18} />
          <span>{notice}</span>
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

function SMEDashboard() {
  const [company, setCompany] = useState<SME | null>(null)
  const [application, setApplication] = useState<SMEApplication | null>(null)
  const [financial, setFinancial] = useState<FinancialSubmission | null>(null)
  const [documentCount, setDocumentCount] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    void api.listSMEs().then(async (companies) => {
      const owned = companies[0] ?? null
      setCompany(owned)
      if (!owned) return
      const [record, app, finance] = await Promise.all([
        api.getSMERecord(owned.sme_id),
        api.getSMEApplication(owned.sme_id),
        api.getFinancialSubmission(owned.sme_id),
      ])
      setDocumentCount(record.documents.length)
      setApplication(app)
      setFinancial(finance)
    }).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : 'Your workspace could not be loaded.')
    })
  }, [])

  return <>
    <section className="page-heading"><div><span className="eyebrow">SME workspace</span><h1>{company?.legal_name ?? 'Your company'}</h1><p>Complete your evidence, financial information and application for review.</p></div></section>
    {error && <div className="error-banner">{error}</div>}
    <section className="metric-grid">
      <MetricCard icon={Building2} label="Application" value={application?.status.replaceAll('_', ' ') ?? 'Loading'} detail="Current review stage" />
      <MetricCard icon={FileCheck2} label="Source documents" value={String(documentCount)} detail="Uploaded evidence files" tone="blue" />
      <MetricCard icon={Landmark} label="Financial review" value={financial?.status.replaceAll('_', ' ') ?? 'Not started'} detail="Separate from environmental scoring" tone="gold" />
      <MetricCard icon={ShieldCheck} label="Evidence control" value="Human reviewed" detail="No automatic approval" tone="plum" />
    </section>
    <section className="dashboard-grid">
      <article className="panel"><div className="panel__header"><div><span className="eyebrow">Company record</span><h2>Documents and evidence</h2></div></div><p className="dashboard-guidance">Upload source documents, inspect extracted facts and submit the application when the record is ready.</p>{company && <Link className="primary-button" to={`/companies/${company.sme_id}`}>Open company workspace <ArrowUpRight size={15} /></Link>}</article>
      <article className="panel"><div className="panel__header"><div><span className="eyebrow">Investment information</span><h2>Financial submission</h2></div></div><p className="dashboard-guidance">Enter business-health and funding-request facts with a source for every reported value.</p><Link className="secondary-button" to="/financial">Open financial workspace <ArrowUpRight size={15} /></Link></article>
    </section>
  </>
}

function ExpertDashboard() {
  return <>
    <section className="page-heading"><div><span className="eyebrow">Expert workspace</span><h1>DEMATEL calibration</h1><p>Your expert interface is isolated from SME, reviewer and investor data.</p></div></section>
    <section className="panel empty-state"><span className="empty-state__icon"><Layers3 size={21} /></span><strong>Expert study awaiting activation</strong><p>The confirmed four driver domains and seven operational subdrivers are ready. Pairwise judgments stay unavailable until the expert study is approved—no values are fabricated.</p></section>
  </>
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
