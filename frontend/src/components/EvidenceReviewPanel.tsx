import {
  AlertTriangle,
  Ban,
  Check,
  ChevronDown,
  FileSearch,
  PencilLine,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useMemo, useState, type Dispatch, type SetStateAction } from 'react'

import type {
  DocumentProcessingStatus,
  EvidenceItem,
  SMEVerificationSubmission,
  SourceDocument,
} from '../types/api'
import { StatusPill } from './StatusPill'

type EvidenceView = 'all' | 'attention' | 'ready' | 'unusable'

type EvidenceReviewPanelProps = {
  evidenceItems: EvidenceItem[]
  canValidate: boolean
  canVerify?: boolean
  conflictEvidenceIds?: Set<string>
  companyNames?: Record<string, string>
  documents?: SourceDocument[]
  processingStatuses?: Record<string, DocumentProcessingStatus>
  onValidate: (
    evidenceId: string,
    status: 'accepted' | 'rejected',
    reason?: string,
  ) => Promise<void>
  onValidateMany?: (
    evidenceIds: string[],
    status: 'accepted' | 'rejected',
    reason?: string,
  ) => Promise<void>
  onVerify?: (
    evidenceId: string,
    submission: SMEVerificationSubmission,
  ) => Promise<void>
}

function humanize(value: string) {
  return value.replaceAll('_', ' ')
}

function valueLabel(item: EvidenceItem) {
  if (typeof item.normalized_value === 'boolean') {
    return item.normalized_value ? 'Yes' : 'No'
  }
  return `${item.normalized_value}${item.unit === 'percent' ? '%' : item.unit ? ` ${item.unit}` : ''}`
}

function evidenceView(
  item: EvidenceItem,
  conflictEvidenceIds: Set<string>,
): Exclude<EvidenceView, 'all'> {
  if (item.validation_status === 'rejected') return 'unusable'
  if (
    item.validation_status === 'unvalidated'
    || conflictEvidenceIds.has(item.evidence_id)
    || item.sme_verification.status === 'correction_proposed'
    || item.sme_verification.status === 'not_applicable'
  ) return 'attention'
  return 'ready'
}

function evidenceStatusLabel(
  item: EvidenceItem,
  conflictEvidenceIds: Set<string>,
) {
  const state = evidenceView(item, conflictEvidenceIds)
  if (state === 'ready') return 'evidence ready'
  if (state === 'unusable') return 'excluded'
  if (conflictEvidenceIds.has(item.evidence_id)) return 'conflict'
  if (item.sme_verification.status === 'correction_proposed') {
    return 'correction proposed'
  }
  if (item.sme_verification.status === 'not_applicable') {
    return 'not applicable disputed'
  }
  return 'review required'
}

export function EvidenceReviewPanel({
  evidenceItems,
  canValidate,
  canVerify = false,
  conflictEvidenceIds = new Set(),
  companyNames = {},
  documents = [],
  processingStatuses = {},
  onValidate,
  onValidateMany,
  onVerify,
}: EvidenceReviewPanelProps) {
  const [view, setView] = useState<EvidenceView>(canValidate ? 'attention' : 'all')
  const [openDocumentIds, setOpenDocumentIds] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [rejectingId, setRejectingId] = useState('')
  const [bulkRejectDocumentId, setBulkRejectDocumentId] = useState('')
  const [reason, setReason] = useState('')
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [verifyingId, setVerifyingId] = useState('')
  const [verificationMode, setVerificationMode] = useState<
    'correction_proposed' | 'not_applicable'
  >('correction_proposed')
  const [verificationDraft, setVerificationDraft] = useState({
    value: '',
    unit: '',
    period: '',
    scope: '',
    comment: '',
  })

  const documentGroups = useMemo(() => {
    const documentById = new Map(
      documents.map((document) => [document.document_id, document]),
    )
    const grouped = new Map<string, EvidenceItem[]>()
    for (const document of documents) grouped.set(document.document_id, [])
    for (const item of evidenceItems) {
      grouped.set(
        item.document_id,
        [...(grouped.get(item.document_id) ?? []), item],
      )
    }
    return [...grouped.entries()].map(([documentId, items]) => ({
      documentId,
      document: documentById.get(documentId),
      items,
      visibleItems: items.filter((item) => (
        view === 'all' || evidenceView(item, conflictEvidenceIds) === view
      )),
    }))
  }, [conflictEvidenceIds, documents, evidenceItems, view])

  function toggleSet(
    setter: Dispatch<SetStateAction<Set<string>>>,
    id: string,
  ) {
    setter((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function validate(
    evidenceId: string,
    status: 'accepted' | 'rejected',
    rejectionReason?: string,
  ) {
    setBusyId(evidenceId)
    setError('')
    try {
      await onValidate(evidenceId, status, rejectionReason)
      setSelectedIds((current) => {
        const next = new Set(current)
        next.delete(evidenceId)
        return next
      })
      setRejectingId('')
      setReason('')
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The review decision could not be saved.',
      )
    } finally {
      setBusyId('')
    }
  }

  async function validateMany(
    evidenceIds: string[],
    status: 'accepted' | 'rejected',
    rejectionReason?: string,
  ) {
    if (!evidenceIds.length) return
    setBusyId(`bulk:${evidenceIds[0]}`)
    setError('')
    try {
      if (onValidateMany) {
        await onValidateMany(evidenceIds, status, rejectionReason)
      } else {
        await Promise.all(
          evidenceIds.map((evidenceId) => (
            onValidate(evidenceId, status, rejectionReason)
          )),
        )
      }
      setSelectedIds((current) => new Set(
        [...current].filter((id) => !evidenceIds.includes(id)),
      ))
      setBulkRejectDocumentId('')
      setReason('')
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The selected decisions could not be saved.',
      )
    } finally {
      setBusyId('')
    }
  }

  async function confirmEvidence(item: EvidenceItem) {
    if (!onVerify) return
    setBusyId(item.evidence_id)
    setError('')
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
      setError(
        caught instanceof Error
          ? caught.message
          : 'The SME confirmation could not be saved.',
      )
    } finally {
      setBusyId('')
    }
  }

  async function confirmDocument(items: EvidenceItem[], documentId: string) {
    if (!onVerify) return
    const confirmable = items.filter((item) => (
      evidenceView(item, conflictEvidenceIds) === 'ready'
      && item.sme_verification.status === 'unreviewed'
    ))
    if (!confirmable.length) return
    setBusyId(`confirm:${documentId}`)
    setError('')
    try {
      await Promise.all(confirmable.map((item) => onVerify(item.evidence_id, {
        status: 'confirmed',
        proposed_value: null,
        proposed_unit: null,
        proposed_reporting_period: null,
        proposed_scope: null,
        comment: null,
      })))
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The document confirmation could not be saved.',
      )
    } finally {
      setBusyId('')
    }
  }

  function beginVerification(
    evidenceId: string,
    mode: 'correction_proposed' | 'not_applicable',
  ) {
    setVerifyingId(evidenceId)
    setVerificationMode(mode)
    setVerificationDraft({
      value: '',
      unit: '',
      period: '',
      scope: '',
      comment: '',
    })
  }

  async function submitVerification(item: EvidenceItem) {
    if (!onVerify) return
    setBusyId(item.evidence_id)
    setError('')
    try {
      const rawValue = verificationDraft.value.trim()
      let proposedValue: string | number | boolean | null = rawValue || null
      if (rawValue && typeof item.normalized_value === 'number') {
        proposedValue = Number(rawValue)
      }
      if (rawValue && typeof item.normalized_value === 'boolean') {
        proposedValue = rawValue.toLowerCase() === 'true'
      }
      await onVerify(item.evidence_id, {
        status: verificationMode,
        proposed_value: verificationMode === 'correction_proposed'
          ? proposedValue
          : null,
        proposed_unit: verificationMode === 'correction_proposed'
          ? verificationDraft.unit.trim() || null
          : null,
        proposed_reporting_period: verificationMode === 'correction_proposed'
          ? verificationDraft.period.trim() || null
          : null,
        proposed_scope: verificationMode === 'correction_proposed'
          ? verificationDraft.scope.trim() || null
          : null,
        comment: verificationDraft.comment.trim() || null,
      })
      setVerifyingId('')
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The SME response could not be saved.',
      )
    } finally {
      setBusyId('')
    }
  }

  const displayedGroups = documentGroups.filter((group) => (
    view === 'all' || group.visibleItems.length > 0
  ))
  const viewLabels: Record<EvidenceView, string> = {
    all: 'All data',
    attention: 'Needs attention',
    ready: 'Evidence ready',
    unusable: 'Excluded',
  }

  return (
    <section className="panel evidence-panel dossier-evidence">
      <div className="panel__header evidence-panel__header">
        <div>
          <span className="eyebrow">
            {canVerify ? 'SME dossier check' : 'Exception-based review'}
          </span>
          <h2>
            {canVerify
              ? 'Extracted data, grouped by document'
              : 'Review only evidence needing a decision'}
          </h2>
          <p>
            {canVerify
              ? 'Evidence-ready data has passed source and consistency checks. Confirm it or propose a correction.'
              : 'Clean source-grounded evidence is admitted automatically. Resolve only conflicts, missing grounding and SME disputes.'}
          </p>
        </div>
        <div className="evidence-filters" aria-label="Filter evidence">
          {(Object.keys(viewLabels) as EvidenceView[]).map((itemView) => (
            <button
              type="button"
              className={view === itemView ? 'active' : ''}
              key={itemView}
              onClick={() => setView(itemView)}
            >
              {viewLabels[itemView]}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {!displayedGroups.length && (
        <div className="empty-state empty-state--compact">
          <span className="empty-state__icon"><FileSearch size={20} /></span>
          <strong>No evidence in this view</strong>
          <p>
            {view === 'attention'
              ? 'There are currently no unresolved evidence exceptions.'
              : 'Process a document or select another view.'}
          </p>
        </div>
      )}

      <div className="evidence-document-stack">
        {displayedGroups.map((group) => {
          const ready = group.items.filter((item) => (
            evidenceView(item, conflictEvidenceIds) === 'ready'
          ))
          const attention = group.items.filter((item) => (
            evidenceView(item, conflictEvidenceIds) === 'attention'
          ))
          const unusable = group.items.filter((item) => (
            evidenceView(item, conflictEvidenceIds) === 'unusable'
          ))
          const selectable = attention.filter((item) => (
            item.validation_status === 'unvalidated'
            && !conflictEvidenceIds.has(item.evidence_id)
          ))
          const selected = selectable.filter((item) => (
            selectedIds.has(item.evidence_id)
          ))
          const confirmable = ready.filter((item) => (
            item.sme_verification.status === 'unreviewed'
          ))
          const open = openDocumentIds.has(group.documentId)
          const companyName = group.items[0]
            ? companyNames[group.items[0].sme_id]
            : undefined
          const processingStatus = processingStatuses[group.documentId]
            ?? (group.items.length ? 'completed' : 'stored')

          return (
            <section className="evidence-document dossier-document" key={group.documentId}>
              <button
                className="evidence-document__header"
                type="button"
                onClick={() => toggleSet(setOpenDocumentIds, group.documentId)}
              >
                <span className={`evidence-document__chevron ${open ? 'open' : ''}`}>
                  <ChevronDown size={17} />
                </span>
                <span className="evidence-document__identity">
                  {companyName && <small>{companyName}</small>}
                  <strong>{group.document?.file_name ?? group.documentId}</strong>
                  <small>
                    {humanize(group.document?.document_type ?? 'supporting document')}
                    {' · '}
                    {humanize(processingStatus)}
                  </small>
                </span>
                <span className="evidence-document__counts evidence-document__counts--simplified">
                  <b>{ready.length}<small>ready</small></b>
                  <b className={attention.length ? 'warning' : ''}>
                    {attention.length}<small>attention</small>
                  </b>
                  <b>{unusable.length}<small>excluded</small></b>
                </span>
              </button>

              {open && (
                <>
                  {canVerify && confirmable.length > 0 && (
                    <div className="dossier-document__action">
                      <span>
                        {confirmable.length} evidence-ready item
                        {confirmable.length === 1 ? '' : 's'} awaiting SME confirmation.
                      </span>
                      <button
                        className="review-button review-button--accept"
                        type="button"
                        disabled={Boolean(busyId)}
                        onClick={() => void confirmDocument(group.items, group.documentId)}
                      >
                        <Check size={14} /> Confirm ready data
                      </button>
                    </div>
                  )}

                  {canValidate && selectable.length > 0 && (
                    <div className="evidence-bulk-bar">
                      <span>
                        {selected.length
                          ? `${selected.length} exception${selected.length === 1 ? '' : 's'} selected`
                          : 'Select compatible exceptions for a deliberate bulk decision.'}
                      </span>
                      <button
                        className="secondary-button secondary-button--small"
                        type="button"
                        disabled={!selected.length || Boolean(busyId)}
                        onClick={() => void validateMany(
                          selected.map((item) => item.evidence_id),
                          'accepted',
                        )}
                      >
                        <Check size={14} /> Admit selected
                      </button>
                      <button
                        className="secondary-button secondary-button--small"
                        type="button"
                        disabled={!selected.length || Boolean(busyId)}
                        onClick={() => setBulkRejectDocumentId(group.documentId)}
                      >
                        <X size={14} /> Exclude selected
                      </button>
                    </div>
                  )}

                  {bulkRejectDocumentId === group.documentId && (
                    <div className="reject-form evidence-bulk-reject">
                      <label>Why is the selected evidence unusable?</label>
                      <textarea
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                        placeholder="For example: OCR misread or wrong reporting context."
                      />
                      <div>
                        <button
                          className="secondary-button secondary-button--small"
                          type="button"
                          onClick={() => setBulkRejectDocumentId('')}
                        >
                          Cancel
                        </button>
                        <button
                          className="review-button review-button--reject"
                          type="button"
                          disabled={!reason.trim() || !selected.length || Boolean(busyId)}
                          onClick={() => void validateMany(
                            selected.map((item) => item.evidence_id),
                            'rejected',
                            reason.trim(),
                          )}
                        >
                          Confirm exclusion
                        </button>
                      </div>
                    </div>
                  )}

                  {!group.visibleItems.length && (
                    <div className="empty-state empty-state--compact">
                      <strong>No items in this view</strong>
                      <p>This document has no evidence matching the selected state.</p>
                    </div>
                  )}

                  <div className="evidence-grid">
                    {group.visibleItems.map((item) => {
                      const itemView = evidenceView(item, conflictEvidenceIds)
                      const conflict = conflictEvidenceIds.has(item.evidence_id)
                      const canSelect = canValidate
                        && item.validation_status === 'unvalidated'
                        && !conflict
                      const canExclude = canValidate
                        && item.validation_status !== 'rejected'
                        && itemView === 'attention'

                      return (
                        <article
                          className={`evidence-card evidence-card--${itemView}`}
                          key={item.evidence_id}
                        >
                          {canSelect && (
                            <label className="evidence-card__select">
                              <input
                                type="checkbox"
                                checked={selectedIds.has(item.evidence_id)}
                                onChange={() => toggleSet(
                                  setSelectedIds,
                                  item.evidence_id,
                                )}
                              />
                              Select
                            </label>
                          )}

                          <div className="evidence-card__header">
                            <div>
                              <strong>{humanize(item.indicator_id)}</strong>
                              <span>
                                {humanize(item.claim_nature)}
                                {' · '}
                                {item.reporting_period || 'Period not stated'}
                                {' · '}
                                {item.scope || 'Scope not stated'}
                              </span>
                            </div>
                            <StatusPill
                              label={evidenceStatusLabel(item, conflictEvidenceIds)}
                              tone={
                                itemView === 'ready'
                                  ? 'positive'
                                  : itemView === 'unusable'
                                    ? 'danger'
                                    : 'warning'
                              }
                            />
                          </div>

                          {(item.entity_name || item.facility_or_site || item.project_name) && (
                            <div className="evidence-alert">
                              <ShieldCheck size={15} />
                              {[item.entity_name, item.facility_or_site, item.project_name]
                                .filter(Boolean)
                                .join(' · ')}
                            </div>
                          )}
                          {itemView === 'attention' && (
                            <div className="evidence-alert">
                              <AlertTriangle size={15} />
                              {conflict
                                ? 'Conflicting or incomplete context requires a reviewer decision.'
                                : item.sme_verification.status === 'correction_proposed'
                                  ? 'The SME proposed a correction to this extracted claim.'
                                  : item.sme_verification.status === 'not_applicable'
                                    ? 'The SME disputes the applicability of this claim.'
                                    : 'This claim did not pass automatic admission checks.'}
                            </div>
                          )}

                          <div className="evidence-value">
                            <div>
                              <span>Source said</span>
                              <strong>{item.raw_value}</strong>
                            </div>
                            <span className="evidence-value__arrow">→</span>
                            <div>
                              <span>Normalized</span>
                              <strong>{valueLabel(item)}</strong>
                            </div>
                          </div>

                          <blockquote>
                            {item.source_excerpt || 'No grounded source excerpt was returned.'}
                          </blockquote>
                          <div className="evidence-provenance">
                            <span><FileSearch size={14} /> {item.source_locator}</span>
                            <span><ShieldCheck size={14} /> {humanize(item.extraction_method)}</span>
                            {item.confidence !== null && (
                              <span>{Math.round(item.confidence * 100)}% extraction confidence</span>
                            )}
                          </div>

                          <div className="sme-verification-summary">
                            <StatusPill
                              label={`SME ${humanize(item.sme_verification.status)}`}
                              tone={
                                item.sme_verification.status === 'confirmed'
                                  ? 'positive'
                                  : item.sme_verification.status === 'unreviewed'
                                    ? 'neutral'
                                    : 'warning'
                              }
                            />
                            {item.sme_verification.comment && (
                              <span>{item.sme_verification.comment}</span>
                            )}
                            {item.sme_verification.status === 'correction_proposed' && (
                              <small>
                                Proposed: {item.sme_verification.proposed_value ?? valueLabel(item)}
                                {' · '}
                                {item.sme_verification.proposed_unit ?? item.unit ?? 'unit unchanged'}
                                {' · '}
                                {item.sme_verification.proposed_reporting_period
                                  ?? item.reporting_period
                                  ?? 'period unchanged'}
                                {' · '}
                                {item.sme_verification.proposed_scope
                                  ?? item.scope
                                  ?? 'scope unchanged'}
                              </small>
                            )}
                          </div>

                          {canVerify
                            && item.validation_status !== 'rejected'
                            && verifyingId !== item.evidence_id
                            && (
                              <div className="review-actions">
                                {item.sme_verification.status !== 'confirmed' && (
                                  <button
                                    className="review-button review-button--accept"
                                    type="button"
                                    disabled={busyId === item.evidence_id}
                                    onClick={() => void confirmEvidence(item)}
                                  >
                                    <Check size={16} /> Confirm
                                  </button>
                                )}
                                <button
                                  className="secondary-button secondary-button--small"
                                  type="button"
                                  disabled={busyId === item.evidence_id}
                                  onClick={() => beginVerification(
                                    item.evidence_id,
                                    'correction_proposed',
                                  )}
                                >
                                  <PencilLine size={14} /> Propose correction
                                </button>
                                <button
                                  className="secondary-button secondary-button--small"
                                  type="button"
                                  disabled={busyId === item.evidence_id}
                                  onClick={() => beginVerification(
                                    item.evidence_id,
                                    'not_applicable',
                                  )}
                                >
                                  <Ban size={14} /> Not applicable
                                </button>
                              </div>
                            )}

                          {canVerify && verifyingId === item.evidence_id && (
                            <div className="reject-form sme-verification-form">
                              <label>
                                {verificationMode === 'correction_proposed'
                                  ? 'Propose corrected data'
                                  : 'Explain why this does not apply'}
                              </label>
                              {verificationMode === 'correction_proposed' && (
                                <div className="verification-field-grid">
                                  <input
                                    value={verificationDraft.value}
                                    onChange={(event) => setVerificationDraft(
                                      (current) => ({ ...current, value: event.target.value }),
                                    )}
                                    placeholder={`Value: ${valueLabel(item)}`}
                                  />
                                  <input
                                    value={verificationDraft.unit}
                                    onChange={(event) => setVerificationDraft(
                                      (current) => ({ ...current, unit: event.target.value }),
                                    )}
                                    placeholder={`Unit: ${item.unit ?? 'not stated'}`}
                                  />
                                  <input
                                    value={verificationDraft.period}
                                    onChange={(event) => setVerificationDraft(
                                      (current) => ({ ...current, period: event.target.value }),
                                    )}
                                    placeholder={`Period: ${item.reporting_period ?? 'not stated'}`}
                                  />
                                  <input
                                    value={verificationDraft.scope}
                                    onChange={(event) => setVerificationDraft(
                                      (current) => ({ ...current, scope: event.target.value }),
                                    )}
                                    placeholder={`Scope: ${item.scope ?? 'not stated'}`}
                                  />
                                </div>
                              )}
                              <textarea
                                value={verificationDraft.comment}
                                onChange={(event) => setVerificationDraft(
                                  (current) => ({ ...current, comment: event.target.value }),
                                )}
                                placeholder={
                                  verificationMode === 'correction_proposed'
                                    ? 'Explain the correction and upload support if needed.'
                                    : 'Why is this metric not applicable?'
                                }
                              />
                              <div>
                                <button
                                  className="secondary-button secondary-button--small"
                                  type="button"
                                  onClick={() => setVerifyingId('')}
                                >
                                  Cancel
                                </button>
                                <button
                                  className="review-button review-button--accept"
                                  type="button"
                                  disabled={
                                    Boolean(busyId)
                                    || (
                                      verificationMode === 'not_applicable'
                                        ? !verificationDraft.comment.trim()
                                        : ![
                                            verificationDraft.value,
                                            verificationDraft.unit,
                                            verificationDraft.period,
                                            verificationDraft.scope,
                                          ].some((value) => value.trim())
                                    )
                                  }
                                  onClick={() => void submitVerification(item)}
                                >
                                  Save response
                                </button>
                              </div>
                            </div>
                          )}

                          {canValidate
                            && item.validation_status === 'unvalidated'
                            && rejectingId !== item.evidence_id
                            && (
                              <div className="review-actions">
                                <button
                                  className="review-button review-button--accept"
                                  type="button"
                                  disabled={busyId === item.evidence_id}
                                  onClick={() => void validate(item.evidence_id, 'accepted')}
                                >
                                  <Check size={16} /> Admit evidence
                                </button>
                                <button
                                  className="review-button review-button--reject"
                                  type="button"
                                  disabled={busyId === item.evidence_id}
                                  onClick={() => {
                                    setReason('')
                                    setRejectingId(item.evidence_id)
                                  }}
                                >
                                  <X size={16} /> Exclude
                                </button>
                              </div>
                            )}

                          {canExclude
                            && item.validation_status === 'accepted'
                            && rejectingId !== item.evidence_id
                            && (
                              <div className="review-actions">
                                <button
                                  className="review-button review-button--reject"
                                  type="button"
                                  disabled={busyId === item.evidence_id}
                                  onClick={() => {
                                    setReason('')
                                    setRejectingId(item.evidence_id)
                                  }}
                                >
                                  <X size={16} /> Exclude original evidence
                                </button>
                              </div>
                            )}

                          {rejectingId === item.evidence_id && (
                            <div className="reject-form">
                              <label>Why is this evidence unusable?</label>
                              <textarea
                                value={reason}
                                onChange={(event) => setReason(event.target.value)}
                                placeholder="For example: OCR misread, wrong entity or incompatible reporting context."
                              />
                              <div>
                                <button
                                  className="secondary-button secondary-button--small"
                                  type="button"
                                  onClick={() => setRejectingId('')}
                                >
                                  Cancel
                                </button>
                                <button
                                  className="review-button review-button--reject"
                                  type="button"
                                  disabled={!reason.trim() || busyId === item.evidence_id}
                                  onClick={() => void validate(
                                    item.evidence_id,
                                    'rejected',
                                    reason.trim(),
                                  )}
                                >
                                  Confirm exclusion
                                </button>
                              </div>
                            </div>
                          )}
                        </article>
                      )
                    })}
                  </div>
                </>
              )}
            </section>
          )
        })}
      </div>
    </section>
  )
}
