import { AlertTriangle, Ban, Check, ChevronDown, FileSearch, PencilLine, ShieldCheck, X } from 'lucide-react'
import { useMemo, useState, type Dispatch, type SetStateAction } from 'react'

import type { DocumentProcessingStatus, EvidenceItem, SMEVerificationSubmission, SourceDocument } from '../types/api'
import { StatusPill } from './StatusPill'

type Filter = 'all' | EvidenceItem['validation_status']

type EvidenceReviewPanelProps = {
  evidenceItems: EvidenceItem[]
  canValidate: boolean
  canVerify?: boolean
  conflictEvidenceIds?: Set<string>
  companyNames?: Record<string, string>
  documents?: SourceDocument[]
  processingStatuses?: Record<string, DocumentProcessingStatus>
  onValidate: (evidenceId: string, status: 'accepted' | 'rejected', reason?: string) => Promise<void>
  onValidateMany?: (evidenceIds: string[], status: 'accepted' | 'rejected', reason?: string) => Promise<void>
  onVerify?: (evidenceId: string, submission: SMEVerificationSubmission) => Promise<void>
}

function humanize(value: string) { return value.replaceAll('_', ' ') }

function valueLabel(item: EvidenceItem) {
  if (typeof item.normalized_value === 'boolean') return item.normalized_value ? 'Yes' : 'No'
  return `${item.normalized_value}${item.unit === 'percent' ? '%' : item.unit ? ` ${item.unit}` : ''}`
}

export function EvidenceReviewPanel({ evidenceItems, canValidate, canVerify = false, conflictEvidenceIds = new Set(), companyNames = {}, documents = [], processingStatuses = {}, onValidate, onValidateMany, onVerify }: EvidenceReviewPanelProps) {
  const [filter, setFilter] = useState<Filter>('all')
  const [rejectingId, setRejectingId] = useState('')
  const [reason, setReason] = useState('')
  const [busyId, setBusyId] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set())
  const [bulkRejectDocumentId, setBulkRejectDocumentId] = useState('')
  const [bulkReason, setBulkReason] = useState('')
  const [error, setError] = useState('')
  const [verifyingId, setVerifyingId] = useState('')
  const [verificationMode, setVerificationMode] = useState<'correction_proposed' | 'not_applicable'>('correction_proposed')
  const [verificationDraft, setVerificationDraft] = useState({ value: '', unit: '', period: '', scope: '', comment: '' })

  const documentGroups = useMemo(() => {
    const documentById = new Map(documents.map((document) => [document.document_id, document]))
    const grouped = new Map<string, EvidenceItem[]>()
    for (const document of documents) grouped.set(document.document_id, [])
    for (const item of evidenceItems) grouped.set(item.document_id, [...(grouped.get(item.document_id) ?? []), item])
    return [...grouped.entries()].map(([documentId, items]) => ({
      documentId,
      document: documentById.get(documentId),
      items,
      visibleItems: items.filter((item) => filter === 'all' || item.validation_status === filter),
    }))
  }, [documents, evidenceItems, filter])

  async function validate(evidenceId: string, status: 'accepted' | 'rejected', rejectionReason?: string) {
    setBusyId(evidenceId); setError('')
    try {
      await onValidate(evidenceId, status, rejectionReason)
      setSelectedIds((current) => { const next = new Set(current); next.delete(evidenceId); return next })
      setRejectingId(''); setReason('')
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The review decision could not be saved.')
    } finally { setBusyId('') }
  }

  async function validateMany(evidenceIds: string[], status: 'accepted' | 'rejected', rejectionReason?: string) {
    if (!evidenceIds.length) return
    setBusyId(`bulk:${evidenceIds[0]}`); setError('')
    try {
      if (onValidateMany) await onValidateMany(evidenceIds, status, rejectionReason)
      else await Promise.all(evidenceIds.map((evidenceId) => onValidate(evidenceId, status, rejectionReason)))
      setSelectedIds((current) => new Set([...current].filter((id) => !evidenceIds.includes(id))))
      setBulkRejectDocumentId(''); setBulkReason('')
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The bulk review decision could not be saved.')
    } finally { setBusyId('') }
  }

  function toggleSet(setter: Dispatch<SetStateAction<Set<string>>>, id: string) {
    setter((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next })
  }

  function beginVerification(evidenceId: string, mode: 'correction_proposed' | 'not_applicable') {
    setVerifyingId(evidenceId)
    setVerificationMode(mode)
    setVerificationDraft({ value: '', unit: '', period: '', scope: '', comment: '' })
  }

  async function submitVerification(item: EvidenceItem) {
    if (!onVerify) return
    setBusyId(item.evidence_id); setError('')
    try {
      const rawValue = verificationDraft.value.trim()
      let proposedValue: string | number | boolean | null = rawValue || null
      if (rawValue && typeof item.normalized_value === 'number') proposedValue = Number(rawValue)
      if (rawValue && typeof item.normalized_value === 'boolean') proposedValue = rawValue.toLowerCase() === 'true'
      await onVerify(item.evidence_id, {
        status: verificationMode,
        proposed_value: verificationMode === 'correction_proposed' ? proposedValue : null,
        proposed_unit: verificationMode === 'correction_proposed' ? verificationDraft.unit.trim() || null : null,
        proposed_reporting_period: verificationMode === 'correction_proposed' ? verificationDraft.period.trim() || null : null,
        proposed_scope: verificationMode === 'correction_proposed' ? verificationDraft.scope.trim() || null : null,
        comment: verificationDraft.comment.trim() || null,
      })
      setVerifyingId('')
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The SME verification response could not be saved.')
    } finally { setBusyId('') }
  }

  async function confirmEvidence(item: EvidenceItem) {
    if (!onVerify) return
    setBusyId(item.evidence_id); setError('')
    try {
      await onVerify(item.evidence_id, {
        status: 'confirmed',
        proposed_value: null,
        proposed_unit: null,
        proposed_reporting_period: null,
        proposed_scope: null,
        comment: null,
      })
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The SME confirmation could not be saved.')
    } finally { setBusyId('') }
  }

  const displayedGroups = documentGroups.filter((group) => filter === 'all' || group.visibleItems.length > 0)
  const hasVisibleEvidence = displayedGroups.length > 0

  return (
    <section className="panel evidence-panel">
      <div className="panel__header evidence-panel__header">
        <div><span className="eyebrow">{canVerify ? 'SME verification' : 'Traceable extraction'}</span><h2>{canVerify ? 'Your extracted data by document' : 'Evidence review by document'}</h2></div>
        <div className="evidence-filters" aria-label="Filter evidence">{(['all', 'unvalidated', 'accepted', 'rejected'] as Filter[]).map((status) => <button type="button" className={filter === status ? 'active' : ''} key={status} onClick={() => setFilter(status)}>{humanize(status)}</button>)}</div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      {!hasVisibleEvidence && <div className="empty-state empty-state--compact"><span className="empty-state__icon"><FileSearch size={20} /></span><strong>No evidence in this view</strong><p>Process a document or select a different validation filter.</p></div>}

      <div className="evidence-document-stack">
        {displayedGroups.map((group) => {
          const counts = {
            accepted: group.items.filter((item) => item.validation_status === 'accepted').length,
            pending: group.items.filter((item) => item.validation_status === 'unvalidated').length,
            rejected: group.items.filter((item) => item.validation_status === 'rejected').length,
            conflicts: group.items.filter((item) => conflictEvidenceIds.has(item.evidence_id)).length,
          }
          const reviewReady = group.items.filter((item) => item.validation_status === 'unvalidated' && !conflictEvidenceIds.has(item.evidence_id))
          const selected = reviewReady.filter((item) => selectedIds.has(item.evidence_id))
          const collapsed = collapsedIds.has(group.documentId)
          const companyName = group.items[0] ? companyNames[group.items[0].sme_id] : undefined
          const processingStatus = processingStatuses[group.documentId] ?? (group.items.length ? 'completed' : 'stored')
          return <section className="evidence-document" key={group.documentId}>
            <button className="evidence-document__header" type="button" onClick={() => toggleSet(setCollapsedIds, group.documentId)}>
              <span className={`evidence-document__chevron ${collapsed ? '' : 'open'}`}><ChevronDown size={17} /></span>
              <span className="evidence-document__identity">{companyName && <small>{companyName}</small>}<strong>{group.document?.file_name ?? group.documentId}</strong><small>{humanize(group.document?.document_type ?? 'document')} · {humanize(processingStatus)}</small></span>
              <span className="evidence-document__counts"><b>{counts.pending}<small>pending</small></b><b>{counts.accepted}<small>accepted</small></b><b>{counts.rejected}<small>rejected</small></b><b className={counts.conflicts ? 'warning' : ''}>{counts.conflicts}<small>conflicts</small></b></span>
            </button>

            {!collapsed && <>
              {canValidate && reviewReady.length > 0 && <div className="evidence-bulk-bar"><span>{selected.length ? `${selected.length} selected` : `${reviewReady.length} review-ready`}</span><button className="secondary-button secondary-button--small" type="button" disabled={!selected.length || Boolean(busyId)} onClick={() => void validateMany(selected.map((item) => item.evidence_id), 'accepted')}><Check size={14} /> Accept selected</button><button className="secondary-button secondary-button--small" type="button" disabled={!selected.length || Boolean(busyId)} onClick={() => setBulkRejectDocumentId(group.documentId)}><X size={14} /> Reject selected</button><button className="review-button review-button--accept" type="button" disabled={Boolean(busyId)} onClick={() => void validateMany(reviewReady.map((item) => item.evidence_id), 'accepted')}><Check size={14} /> Accept all review-ready</button></div>}
              {bulkRejectDocumentId === group.documentId && <div className="reject-form evidence-bulk-reject"><label>Why should the selected evidence be rejected?</label><textarea value={bulkReason} onChange={(event) => setBulkReason(event.target.value)} placeholder="For example: OCR misread or wrong reporting period…" /><div><button className="secondary-button secondary-button--small" type="button" onClick={() => setBulkRejectDocumentId('')}>Cancel</button><button className="review-button review-button--reject" type="button" disabled={!bulkReason.trim() || !selected.length || Boolean(busyId)} onClick={() => void validateMany(selected.map((item) => item.evidence_id), 'rejected', bulkReason.trim())}>Confirm rejection</button></div></div>}

              {!group.visibleItems.length && <div className="empty-state empty-state--compact"><strong>No extracted evidence yet</strong><p>This document is {humanize(processingStatus)}.</p></div>}
              <div className="evidence-grid">{group.visibleItems.map((item) => {
                const conflict = conflictEvidenceIds.has(item.evidence_id)
                const selectable = canValidate && item.validation_status === 'unvalidated' && !conflict
                return <article className={`evidence-card ${conflict ? 'evidence-card--conflict' : ''}`} key={item.evidence_id}>
                  {selectable && <label className="evidence-card__select"><input type="checkbox" checked={selectedIds.has(item.evidence_id)} onChange={() => toggleSet(setSelectedIds, item.evidence_id)} /> Select</label>}
                  <div className="evidence-card__header"><div><strong>{humanize(item.indicator_id)}</strong><span>{humanize(item.claim_nature)} · {item.reporting_period || 'Period not stated'} · {item.scope || 'Scope not stated'}</span></div><StatusPill label={conflict ? 'conflict' : item.validation_status} tone={conflict ? 'warning' : item.validation_status === 'accepted' ? 'positive' : item.validation_status === 'rejected' ? 'danger' : 'neutral'} /></div>
                  {(item.entity_name || item.facility_or_site || item.project_name) && <div className="evidence-alert"><ShieldCheck size={15} /> {[item.entity_name, item.facility_or_site, item.project_name].filter(Boolean).join(' · ')}</div>}
                  {conflict && <div className="evidence-alert"><AlertTriangle size={15} /> Conflicting or incomplete context—review individually.</div>}
                  <div className="evidence-value"><div><span>Source said</span><strong>{item.raw_value}</strong></div><span className="evidence-value__arrow">→</span><div><span>Normalized</span><strong>{valueLabel(item)}</strong></div></div>
                  <blockquote>{item.source_excerpt || 'No source excerpt was returned.'}</blockquote>
                  <div className="evidence-provenance"><span><FileSearch size={14} /> {item.source_locator}</span><span><ShieldCheck size={14} /> {humanize(item.extraction_method)}</span>{item.confidence !== null && <span>{Math.round(item.confidence * 100)}% extraction confidence</span>}</div>
                  <div className="sme-verification-summary">
                    <StatusPill label={`SME ${humanize(item.sme_verification.status)}`} tone={item.sme_verification.status === 'confirmed' ? 'positive' : item.sme_verification.status === 'unreviewed' ? 'neutral' : 'warning'} />
                    {item.sme_verification.comment && <span>{item.sme_verification.comment}</span>}
                    {item.sme_verification.status === 'correction_proposed' && <small>Proposed: {item.sme_verification.proposed_value ?? valueLabel(item)} · {item.sme_verification.proposed_unit ?? item.unit ?? 'unit unchanged'} · {item.sme_verification.proposed_reporting_period ?? item.reporting_period ?? 'period unchanged'} · {item.sme_verification.proposed_scope ?? item.scope ?? 'scope unchanged'}</small>}
                  </div>
                  {canVerify && verifyingId !== item.evidence_id && <div className="review-actions"><button className="review-button review-button--accept" type="button" disabled={busyId === item.evidence_id} onClick={() => void confirmEvidence(item)}><Check size={16} /> Confirm</button><button className="secondary-button secondary-button--small" type="button" disabled={busyId === item.evidence_id} onClick={() => beginVerification(item.evidence_id, 'correction_proposed')}><PencilLine size={14} /> Propose correction</button><button className="secondary-button secondary-button--small" type="button" disabled={busyId === item.evidence_id} onClick={() => beginVerification(item.evidence_id, 'not_applicable')}><Ban size={14} /> Not applicable</button></div>}
                  {canVerify && verifyingId === item.evidence_id && <div className="reject-form sme-verification-form"><label>{verificationMode === 'correction_proposed' ? 'Propose corrected data' : 'Explain why this does not apply'}</label>{verificationMode === 'correction_proposed' && <div className="verification-field-grid"><input value={verificationDraft.value} onChange={(event) => setVerificationDraft((current) => ({ ...current, value: event.target.value }))} placeholder={`Value: ${valueLabel(item)}`} /><input value={verificationDraft.unit} onChange={(event) => setVerificationDraft((current) => ({ ...current, unit: event.target.value }))} placeholder={`Unit: ${item.unit ?? 'not stated'}`} /><input value={verificationDraft.period} onChange={(event) => setVerificationDraft((current) => ({ ...current, period: event.target.value }))} placeholder={`Period: ${item.reporting_period ?? 'not stated'}`} /><input value={verificationDraft.scope} onChange={(event) => setVerificationDraft((current) => ({ ...current, scope: event.target.value }))} placeholder={`Scope: ${item.scope ?? 'not stated'}`} /></div>}<textarea value={verificationDraft.comment} onChange={(event) => setVerificationDraft((current) => ({ ...current, comment: event.target.value }))} placeholder={verificationMode === 'correction_proposed' ? 'Explain the correction and upload support if needed.' : 'Why is this metric not applicable?'} /><div><button className="secondary-button secondary-button--small" type="button" onClick={() => setVerifyingId('')}>Cancel</button><button className="review-button review-button--accept" type="button" disabled={Boolean(busyId) || (verificationMode === 'not_applicable' ? !verificationDraft.comment.trim() : ![verificationDraft.value, verificationDraft.unit, verificationDraft.period, verificationDraft.scope].some((value) => value.trim()))} onClick={() => void submitVerification(item)}>Save response</button></div></div>}
                  {canValidate && item.validation_status === 'unvalidated' && rejectingId !== item.evidence_id && <div className="review-actions"><button className="review-button review-button--accept" type="button" disabled={busyId === item.evidence_id} onClick={() => void validate(item.evidence_id, 'accepted')}><Check size={16} /> Accept evidence</button><button className="review-button review-button--reject" type="button" disabled={busyId === item.evidence_id} onClick={() => setRejectingId(item.evidence_id)}><X size={16} /> Reject</button></div>}
                  {rejectingId === item.evidence_id && <div className="reject-form"><label>Why is this evidence unusable?</label><textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="For example: wrong reporting period or OCR misread…" /><div><button className="secondary-button secondary-button--small" type="button" onClick={() => setRejectingId('')}>Cancel</button><button className="review-button review-button--reject" type="button" disabled={!reason.trim() || busyId === item.evidence_id} onClick={() => void validate(item.evidence_id, 'rejected', reason.trim())}>Confirm rejection</button></div></div>}
                </article>
              })}</div>
            </>}
          </section>
        })}
      </div>
    </section>
  )
}
