import { ArrowLeft, Check, GitCompareArrows, Play, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../lib/api'
import { usePermissions } from '../auth/usePermissions'
import type {
  AutomaticCohortAssessmentRequest,
  SME,
} from '../types/api'

function slug(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}

export function ApprovedComparisonPage() {
  const navigate = useNavigate()
  const { role } = usePermissions()
  const [companies, setCompanies] = useState<SME[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [comparisonName, setComparisonName] = useState(
    'Green SME portfolio comparison',
  )
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([
      api.listSMEs(),
      role === 'investor'
        ? Promise.resolve(null)
        : api.listAssessmentProfileStatuses(),
    ])
      .then(([smes, statuses]) => {
        if (statuses === null) {
          setCompanies(smes)
          return
        }
        const eligible = new Set(
          statuses.filter((item) => item.comparison_eligible).map((item) => item.sme_id),
        )
        setCompanies(smes.filter((item) => eligible.has(item.sme_id)))
      })
      .catch((caught: unknown) => {
        setError(
          caught instanceof Error
            ? caught.message
            : 'Companies could not be loaded.',
        )
      })
      .finally(() => setLoading(false))
  }, [role])

  function toggleCompany(smeId: string) {
    setSelected((current) => (
      current.includes(smeId)
        ? current.filter((item) => item !== smeId)
        : [...current, smeId]
    ))
  }

  async function compare() {
    if (selected.length < 2) {
      setError('Select at least two companies.')
      return
    }

    if (!comparisonName.trim()) {
      setError('Give the comparison a name.')
      return
    }

    setSubmitting(true)
    setError('')

    const timestamp = Date.now()
    const request: AutomaticCohortAssessmentRequest = {
      run_id: `run_${slug(comparisonName)}_${timestamp}`,
      cohort_id: slug(comparisonName),
      version: '1.0',
      sme_ids: selected,
      minimum_shared_criteria: 2,
      minimum_shared_weight_ratio: 0.6,
    }

    try {
      const result = await api.createAutomaticAssessment(request)
      navigate(`/assessments/${result.run_id}`)
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The companies could not be compared.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="skeleton assessment-builder-skeleton" />
  }

  return (
    <>
      <div className="breadcrumbs">
        <Link to="/assessments">
          <ArrowLeft size={14} />
          Assessment runs
        </Link>
        <span>/</span>
        <span>Compare companies</span>
      </div>

      <section className="page-heading">
        <div>
          <span className="eyebrow">Investor comparison</span>
          <h1>Compare approved SME profiles</h1>
          <p>
            Select companies and run the governed assessment. Evidence,
            applicability and approved inputs are resolved automatically.
          </p>
        </div>
      </section>

      <div className="comparison-assurance">
        <ShieldCheck size={18} />
        <span>
          Investors cannot alter criterion ratings, evidence or model
          weights. Every comparison uses the centrally approved profiles.
        </span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <section className="panel builder-panel">
        <div className="builder-panel__intro">
          <span className="builder-panel__icon">
            <GitCompareArrows size={21} />
          </span>
          <div>
            <h2>Select the comparison cohort</h2>
            <p>
              Choose at least two SMEs. The completed result is stored as
              a reproducible assessment run.
            </p>
          </div>
        </div>

        <label className="builder-field">
          Comparison name
          <input
            value={comparisonName}
            onChange={(event) => setComparisonName(event.target.value)}
          />
        </label>

        <div className="company-selector">
          {companies.map((company) => (
            <button
              type="button"
              key={company.sme_id}
              className={
                selected.includes(company.sme_id)
                  ? 'selected'
                  : ''
              }
              onClick={() => toggleCompany(company.sme_id)}
            >
              <span className="company-selector__check">
                {selected.includes(company.sme_id) && (
                  <Check size={14} />
                )}
              </span>
              <strong>{company.legal_name}</strong>
              <small>{company.sector}</small>
            </button>
          ))}
        </div>

        {!companies.length && (
          <div className="empty-state">
            <strong>No companies are available</strong>
            <p>
              {role === 'investor'
                ? 'Published SME assessment profiles will appear here.'
                : 'No SME currently has an approved and published assessment profile. Prepare and publish at least two profiles before comparing them.'}
            </p>
            {role !== 'investor' && (
              <Link className="secondary-button" to="/assessments/profiles">
                Prepare assessment profiles
              </Link>
            )}
          </div>
        )}
      </section>

      <div className="builder-footer">
        <Link className="secondary-button" to="/assessments">
          <ArrowLeft size={16} />
          Cancel
        </Link>
        <button
          className="primary-button"
          type="button"
          disabled={submitting || selected.length < 2}
          onClick={() => void compare()}
        >
          <Play size={16} />
          {submitting ? 'Running assessment…' : 'Compare companies'}
        </button>
      </div>
    </>
  )
}
