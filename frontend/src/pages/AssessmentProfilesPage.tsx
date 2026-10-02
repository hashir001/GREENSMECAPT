import { ArrowRight, ClipboardCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../lib/api'
import type { AssessmentProfileStatus } from '../types/api'

const labels: Record<AssessmentProfileStatus['lifecycle_status'], string> = {
  not_prepared: 'Not approved',
  approved: 'Approved — ready to publish',
  published: 'Published',
  approved_changes: 'Approved changes — publish latest',
  reapproval_required: 'Policy changed — reapprove',
  published_outdated: 'Published profile requires reapproval',
}

export function AssessmentProfilesPage() {
  const [profiles, setProfiles] = useState<AssessmentProfileStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void api.listAssessmentProfileStatuses()
      .then(setProfiles)
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Profiles could not be loaded.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Governed assessment profiles</span>
          <h1>Prepare, approve and publish</h1>
          <p>One controlled profile per SME. Only current published revisions can enter investor comparisons.</p>
        </div>
      </section>
      {error && <div className="error-banner">{error}</div>}
      <section className="assessment-list">
        {loading ? <div className="skeleton assessment-builder-skeleton" /> : profiles.map((profile) => (
          <article className="assessment-card" key={profile.sme_id}>
            <span className="assessment-card__icon"><ClipboardCheck size={21} /></span>
            <div className="assessment-card__main">
              <div className="assessment-card__title">
                <div><h2>{profile.legal_name}</h2><span>{profile.sector}</span></div>
                <span className={`status-pill ${profile.comparison_eligible ? 'status-pill--positive' : ''}`}>
                  {labels[profile.lifecycle_status]}
                </span>
              </div>
              <div className="assessment-card__meta">
                <span>Application: {profile.application_status.replaceAll('_', ' ')}</span>
                <span>{profile.latest_profile_version ? `Profile v${profile.latest_profile_version}` : 'No approved profile'}</span>
                <span>{profile.comparison_eligible ? 'Comparison eligible' : 'Not comparison eligible'}</span>
              </div>
            </div>
            <Link className="icon-button" to={`/assessments/profiles/${profile.sme_id}`} aria-label={`Open ${profile.legal_name}`}>
              <ArrowRight size={19} />
            </Link>
          </article>
        ))}
      </section>
      {!loading && !profiles.length && <section className="panel empty-state"><strong>No SMEs available</strong></section>}
    </>
  )
}
