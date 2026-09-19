import { AlertTriangle, Check, FileSearch, ShieldCheck, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { EvidenceItem } from '../types/api'
import { StatusPill } from './StatusPill'

type Filter = 'all' | EvidenceItem['validation_status']

type EvidenceReviewPanelProps = {
  evidenceItems: EvidenceItem[]
  canValidate: boolean
  conflictEvidenceIds?: Set<string>
  companyNames?: Record<string, string>
  onValidate: (evidenceId: string, status: 'accepted' | 'rejected', reason?: string) => Promise<void>
}

function humanize(value: string) {
  return value.replaceAll('_', ' ')
}

function valueLabel(item: EvidenceItem) {
  if (typeof item.normalized_value === 'boolean') return item.normalized_value ? 'Yes' : 'No'
  return `${item.normalized_value}${item.unit === 'percent' ? '%' : item.unit ? ` ${item.unit}` : ''}`
}

export function EvidenceReviewPanel({ evidenceItems, canValidate, conflictEvidenceIds = new Set(), companyNames = {}, onValidate }: EvidenceReviewPanelProps) {
  const [filter, setFilter] = useState<Filter>('all')
  const [rejectingId, setRejectingId] = useState('')
  const [reason, setReason] = useState('')
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  const filtered = useMemo(
    () => evidenceItems.filter((item) => filter === 'all' || item.validation_status === filter),
    [evidenceItems, filter],
  )

  async function validate(evidenceId: string, status: 'accepted' | 'rejected', rejectionReason?: string) {
    setBusyId(evidenceId)
    setError('')
    try {
      await onValidate(evidenceId, status, rejectionReason)
      setRejectingId('')
      setReason('')
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The review decision could not be saved.')
    } finally {
      setBusyId('')
    }
  }

  return (
    <section className="panel evidence-panel">
      <div className="panel__header evidence-panel__header">
        <div>
          <span className="eyebrow">Traceable extraction</span>
          <h2>Evidence review</h2>
        </div>
        <div className="evidence-filters" aria-label="Filter evidence">
          {(['all', 'unvalidated', 'accepted', 'rejected'] as Filter[]).map((status) => (
            <button type="button" className={filter === status ? 'active' : ''} key={status} onClick={() => setFilter(status)}>
              {humanize(status)}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {!filtered.length && (
        <div className="empty-state empty-state--compact">
          <span className="empty-state__icon"><FileSearch size={20} /></span>
          <strong>No evidence in this view</strong>
          <p>Process a document or select a different validation filter.</p>
        </div>
      )}

      <div className="evidence-grid">
        {filtered.map((item) => {
          const conflict = conflictEvidenceIds.has(item.evidence_id)
          const companyName = companyNames[item.sme_id]
          return (
            <article className={`evidence-card ${conflict ? 'evidence-card--conflict' : ''}`} key={item.evidence_id}>
              <div className="evidence-card__header">
                <div>
                  {companyName && <span className="evidence-card__company">{companyName}</span>}
                  <strong>{humanize(item.indicator_id)}</strong>
                  <span>{item.reporting_period || 'Period not stated'} · {item.scope || 'Scope not stated'}</span>
                </div>
                <StatusPill
                  label={conflict ? 'conflict' : item.validation_status}
                  tone={conflict ? 'warning' : item.validation_status === 'accepted' ? 'positive' : item.validation_status === 'rejected' ? 'danger' : 'neutral'}
                />
              </div>

              {conflict && (
                <div className="evidence-alert"><AlertTriangle size={15} /> This value conflicts with another source in the same context.</div>
              )}

              <div className="evidence-value">
                <div><span>Source said</span><strong>{item.raw_value}</strong></div>
                <span className="evidence-value__arrow">→</span>
                <div><span>Normalized</span><strong>{valueLabel(item)}</strong></div>
              </div>

              <blockquote>{item.source_excerpt || 'No source excerpt was returned.'}</blockquote>
              <div className="evidence-provenance">
                <span><FileSearch size={14} /> {item.source_locator}</span>
                <span><ShieldCheck size={14} /> {humanize(item.extraction_method)}</span>
                {item.confidence !== null && <span>{Math.round(item.confidence * 100)}% extraction confidence</span>}
              </div>

              {canValidate && item.validation_status === 'unvalidated' && rejectingId !== item.evidence_id && (
                <div className="review-actions">
                  <button className="review-button review-button--accept" type="button" disabled={busyId === item.evidence_id} onClick={() => void validate(item.evidence_id, 'accepted')}>
                    <Check size={16} /> Accept evidence
                  </button>
                  <button className="review-button review-button--reject" type="button" disabled={busyId === item.evidence_id} onClick={() => setRejectingId(item.evidence_id)}>
                    <X size={16} /> Reject
                  </button>
                </div>
              )}

              {rejectingId === item.evidence_id && (
                <div className="reject-form">
                  <label>Why is this evidence unusable?</label>
                  <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="For example: wrong reporting period or OCR misread…" />
                  <div>
                    <button className="secondary-button secondary-button--small" type="button" onClick={() => setRejectingId('')}>Cancel</button>
                    <button className="review-button review-button--reject" type="button" disabled={!reason.trim() || busyId === item.evidence_id} onClick={() => void validate(item.evidence_id, 'rejected', reason.trim())}>Confirm rejection</button>
                  </div>
                </div>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
