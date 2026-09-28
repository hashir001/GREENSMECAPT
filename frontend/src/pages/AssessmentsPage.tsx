import { BarChart3, CalendarDays, ChevronRight, Eye, Plus, Trash2, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { usePermissions } from '../auth/usePermissions'
import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type { AssessmentRunSummary } from '../types/api'

function formattedDate(value: string): string {
  return new Intl.DateTimeFormat('en', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

export function AssessmentsPage() {
  const {
    canCompareApprovedProfiles,
    canDeleteAssessmentRuns,
    canRunAssessments,
  } = usePermissions()
  const [runs, setRuns] = useState<AssessmentRunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function deleteRun(runId: string) {
    if (!window.confirm('Permanently delete this assessment run?')) return
    const reason = window.prompt('Deletion reason (required):')?.trim()
    if (!reason) return
    setError('')
    try {
      await api.deleteAssessmentRun(runId, reason)
      setRuns((current) => current.filter((run) => run.run_id !== runId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Assessment run could not be deleted.')
    }
  }

  useEffect(() => {
    void api.listAssessmentRuns()
      .then(setRuns)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Assessments failed to load.')
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Decision history</span>
          <h1>Assessment runs</h1>
          <p>Every completed comparison remains reproducible and available for review.</p>
        </div>
        <div className="page-heading__actions">
          <Link
            className="secondary-button"
            to="/assessments/saved-comparison"
          >
            <Eye size={17} />
            View saved comparison
          </Link>
          {canRunAssessments && (
            <Link
              className="secondary-button"
              to="/assessments/new"
            >
              <Plus size={17} />
              Manage approved profiles
            </Link>
          )}
          {canCompareApprovedProfiles && (
            <Link
              className="primary-button"
              to="/assessments/compare"
            >
              <Users size={17} />
              Compare companies
            </Link>
          )}
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      <section className="assessment-list">
        {loading
          ? Array.from({ length: 4 }, (_, index) => (
              <div className="skeleton skeleton--assessment" key={index} />
            ))
          : runs.map((run) => (
              <article className="assessment-card" key={run.run_id}>
                <span className="assessment-card__icon"><BarChart3 size={22} /></span>
                <div className="assessment-card__main">
                  <div className="assessment-card__title">
                    <div><h2>{run.cohort_id}</h2><span>{run.run_id}</span></div>
                    <StatusPill
                      label={run.comparison_status.replaceAll('_', ' ')}
                      tone="positive"
                    />
                  </div>
                  <div className="assessment-card__meta">
                    <span><Users size={15} /> {run.sme_ids.length} companies compared</span>
                    <span><CalendarDays size={15} /> {formattedDate(run.created_at)}</span>
                    <span>Version {run.cohort_version}</span>
                  </div>
                </div>
                <div className="assessment-card__actions">
                  {canDeleteAssessmentRuns && (
                    <button className="icon-button icon-button--danger" type="button" aria-label={`Delete ${run.run_id}`} onClick={() => void deleteRun(run.run_id)}>
                      <Trash2 size={18} />
                    </button>
                  )}
                  <Link className="icon-button" to={`/assessments/${run.run_id}`} aria-label={`Open ${run.run_id}`}>
                    <ChevronRight size={20} />
                  </Link>
                </div>
              </article>
            ))}
      </section>

      {!loading && !runs.length && (
        <section className="panel empty-state">
          <span className="empty-state__icon"><BarChart3 size={21} /></span>
          <strong>No completed assessments</strong>
          <p>An approved-profile comparison will appear here as an immutable run.</p>
        </section>
      )}
    </>
  )
}
