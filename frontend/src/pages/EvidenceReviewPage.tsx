import {
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { usePermissions } from '../auth/usePermissions'
import { EvidenceReviewPanel } from '../components/EvidenceReviewPanel'
import { api } from '../lib/api'
import type {
  DocumentProcessingStatus,
  EvidenceItem,
  SME,
  SourceDocument,
} from '../types/api'

export function EvidenceReviewPage() {
  const { canValidateEvidence } = usePermissions()
  const [companies, setCompanies] = useState<SME[]>([])
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [documents, setDocuments] = useState<SourceDocument[]>([])
  const [processingStatuses, setProcessingStatuses] = useState<
    Record<string, DocumentProcessingStatus>
  >({})
  const [conflictEvidenceIds, setConflictEvidenceIds] = useState<Set<string>>(
    new Set(),
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void api.listSMEs()
      .then(async (nextCompanies) => {
        setCompanies(nextCompanies)
        const records = await Promise.all(
          nextCompanies.map((company) => api.getSMERecord(company.sme_id)),
        )
        setEvidence(records.flatMap((record) => record.evidence_items))
        const nextDocuments = records.flatMap((record) => record.documents)
        setDocuments(nextDocuments)
        const snapshots = await Promise.all(nextDocuments.map(async (document) => (
          api.getDocumentProcessing(document.sme_id, document.document_id)
            .catch(() => null)
        )))
        setProcessingStatuses(Object.fromEntries(
          snapshots
            .filter((item) => item !== null)
            .map((item) => [item.state.document_id, item.state.status]),
        ))
        setConflictEvidenceIds(new Set(snapshots.flatMap((item) => (
          item?.reconciliation?.clusters
            .filter((cluster) => (
              cluster.status === 'conflict'
              || cluster.status === 'context_required'
            ))
            .flatMap((cluster) => cluster.evidence_ids) ?? []
        ))))
      })
      .catch((caught: unknown) => setError(
        caught instanceof Error ? caught.message : 'Evidence could not be loaded.',
      ))
      .finally(() => setLoading(false))
  }, [])

  const companyNames = useMemo(
    () => Object.fromEntries(
      companies.map((company) => [company.sme_id, company.legal_name]),
    ),
    [companies],
  )
  const needsAttention = evidence.filter((item) => (
    item.validation_status === 'unvalidated'
    || conflictEvidenceIds.has(item.evidence_id)
    || item.sme_verification.status === 'correction_proposed'
    || item.sme_verification.status === 'not_applicable'
  )).length
  const ready = evidence.filter((item) => (
    item.validation_status === 'accepted'
    && !conflictEvidenceIds.has(item.evidence_id)
    && item.sme_verification.status !== 'correction_proposed'
    && item.sme_verification.status !== 'not_applicable'
  )).length
  const excluded = evidence.filter(
    (item) => item.validation_status === 'rejected',
  ).length

  async function validateEvidence(
    evidenceId: string,
    status: 'accepted' | 'rejected',
    reason?: string,
  ) {
    const updated = await api.validateEvidence(evidenceId, status, reason)
    setEvidence((current) => current.map((item) => (
      item.evidence_id === updated.evidence_id ? updated : item
    )))
  }

  async function validateEvidenceBulk(
    evidenceIds: string[],
    status: 'accepted' | 'rejected',
    reason?: string,
  ) {
    const updated = await api.validateEvidenceBulk(
      evidenceIds,
      status,
      reason,
    )
    const byId = new Map(updated.map((item) => [item.evidence_id, item]))
    setEvidence((current) => current.map(
      (item) => byId.get(item.evidence_id) ?? item,
    ))
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Human assurance</span>
          <h1>Evidence exception queue</h1>
          <p>
            Resolve conflicts, missing source grounding and SME disputes. Clean
            evidence is admitted automatically.
          </p>
        </div>
        <div className="review-assurance">
          <ShieldCheck size={18} />
          <span>Reviewer decisions are reserved for real exceptions</span>
        </div>
      </section>

      <section className="queue-summary">
        <article>
          <span className="queue-summary__icon queue-summary__icon--gold">
            <AlertTriangle size={19} />
          </span>
          <div><strong>{needsAttention}</strong><span>Needs attention</span></div>
        </article>
        <article>
          <span className="queue-summary__icon queue-summary__icon--jade">
            <CheckCircle2 size={19} />
          </span>
          <div><strong>{ready}</strong><span>Evidence ready</span></div>
        </article>
        <article>
          <span className="queue-summary__icon queue-summary__icon--coral">
            <XCircle size={19} />
          </span>
          <div><strong>{excluded}</strong><span>Excluded</span></div>
        </article>
        <article>
          <span className="queue-summary__icon queue-summary__icon--blue">
            <FileSearch size={19} />
          </span>
          <div><strong>{companies.length}</strong><span>Companies covered</span></div>
        </article>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {loading
        ? <div className="skeleton evidence-page-skeleton" />
        : (
          <EvidenceReviewPanel
            evidenceItems={evidence}
            canValidate={canValidateEvidence}
            conflictEvidenceIds={conflictEvidenceIds}
            companyNames={companyNames}
            documents={documents}
            processingStatuses={processingStatuses}
            onValidate={validateEvidence}
            onValidateMany={validateEvidenceBulk}
          />
        )}
    </>
  )
}
