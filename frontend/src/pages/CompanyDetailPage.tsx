import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  FileStack,
  MapPin,
  RefreshCw,
  ScanSearch,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { DocumentIntelligencePanel } from '../components/DocumentIntelligencePanel'
import { DocumentList } from '../components/DocumentList'
import { DocumentUploadPanel } from '../components/DocumentUploadPanel'
import { EvidenceReviewPanel } from '../components/EvidenceReviewPanel'
import { usePermissions } from '../auth/usePermissions'
import { api } from '../lib/api'
import type {
  DocumentProcessingResult,
  StructuredInvestmentRecord,
} from '../types/api'
import type { DocumentJobProgress } from '../types/jobs'

export function CompanyDetailPage() {
  const { smeId = '' } = useParams()
  const permissions = usePermissions()
  const [record, setRecord] = useState<StructuredInvestmentRecord | null>(null)
  const [processing, setProcessing] = useState<Record<string, DocumentProcessingResult>>({})
  const [jobs, setJobs] = useState<Record<string, DocumentJobProgress>>({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  const [selectedDocumentId, setSelectedDocumentId] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const nextRecord = await api.getSMERecord(smeId)
      setRecord(nextRecord)
      const snapshots = await Promise.all(
        nextRecord.documents.map(async (document) => {
          const [result, job] = await Promise.all([
            api.getDocumentProcessing(smeId, document.document_id)
              .catch(() => null),
            api.getLatestDocumentJobProgress(smeId, document.document_id)
              .catch(() => null),
          ])
          return { result, job }
        }),
      )
      setProcessing(Object.fromEntries(
        snapshots.map((snapshot) => snapshot.result)
          .filter((result): result is DocumentProcessingResult => result !== null)
          .map((result) => [result.state.document_id, result]),
      ))
      setJobs(Object.fromEntries(
        snapshots.map((snapshot) => snapshot.job)
          .filter((job): job is DocumentJobProgress => job !== null)
          .map((job) => [job.job.document_id, job]),
      ))
      setSelectedDocumentId((current) => (
        nextRecord.documents.some((document) => document.document_id === current)
          ? current
          : nextRecord.documents[0]?.document_id ?? ''
      ))
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The company record could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [smeId])

  // Loading an external record is the synchronization this effect owns.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void load() }, [load])

  useEffect(() => {
    const activeDocuments = Object.entries(jobs).filter(([, progress]) =>
      progress.job.status === 'queued' || progress.job.status === 'running',
    )

    if (!activeDocuments.length) return

    const timer = window.setTimeout(() => {
      void Promise.all(
        activeDocuments.map(async ([documentId]) => {
          const next = await api.getLatestDocumentJobProgress(smeId, documentId)
          if (!next) return false
          setJobs((current) => ({ ...current, [documentId]: next }))
          return next.job.status === 'completed' || next.job.status === 'failed'
        }),
      ).then((terminalStates) => {
        if (terminalStates.some(Boolean)) void load()
      }).catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Document progress could not be refreshed.')
      })
    }, 900)

    return () => window.clearTimeout(timer)
  }, [jobs, load, smeId])

  const reconciliation = Object.values(processing)
    .map((result) => result.reconciliation)
    .find((report) => report !== null)

  const conflictEvidenceIds = useMemo(() => new Set(
    reconciliation?.clusters
      .filter((cluster) => cluster.status === 'conflict' || cluster.status === 'context_required')
      .flatMap((cluster) => cluster.evidence_ids) ?? [],
  ), [reconciliation])

  const completedDocuments = Object.values(processing)
    .filter((result) => result.state.status === 'completed').length
  const acceptedEvidence = record?.evidence_items
    .filter((item) => item.validation_status === 'accepted').length ?? 0
  const pendingEvidence = record?.evidence_items
    .filter((item) => item.validation_status === 'unvalidated').length ?? 0
  const selectedDocument = record?.documents.find(
    (document) => document.document_id === selectedDocumentId,
  ) ?? null

  async function processDocument(documentId: string) {
    setBusyId(documentId)
    setError('')
    try {
      const currentJob = jobs[documentId]?.job
      const updateProgress = (progress: DocumentJobProgress) => {
        setJobs((current) => ({ ...current, [documentId]: progress }))
      }
      const execution = currentJob?.status === 'failed'
        ? await api.retryDocumentProcessingJob(
            smeId,
            documentId,
            currentJob.job_id,
            updateProgress,
          )
        : await api.runDocumentProcessingJob(
            smeId,
            documentId,
            updateProgress,
          )

      if (execution.job.status === 'failed') {
        throw new Error(
          execution.job.failure_message || 'Document processing failed.',
        )
      }

      await load()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The document could not be processed.')
      await load()
    } finally {
      setBusyId('')
    }
  }

  async function validateEvidence(evidenceId: string, status: 'accepted' | 'rejected', reason?: string) {
    await api.validateEvidence(evidenceId, status, reason)
    await load()
  }

  async function uploadCompleted(result?: DocumentProcessingResult) {
    if (result) setSelectedDocumentId(result.state.document_id)
    await load()
  }

  if (loading) {
    return <div className="company-detail-loading"><div className="skeleton company-hero-skeleton" /><div className="skeleton workspace-skeleton" /></div>
  }

  if (!record) {
    return (
      <section className="panel empty-state">
        <strong>Company record unavailable</strong>
        <p>{error || 'This record could not be found.'}</p>
        <Link className="secondary-button" to="/companies"><ArrowLeft size={16} /> Return to portfolio</Link>
      </section>
    )
  }

  return (
    <>
      <div className="breadcrumbs"><Link to="/companies"><ArrowLeft size={14} /> SME portfolio</Link><span>/</span><span>{record.sme.legal_name}</span></div>

      <section className="company-hero">
        <div className="company-hero__identity">
          <span className="company-hero__avatar"><Building2 size={28} /></span>
          <div>
            <span className="eyebrow eyebrow--light">Evidence workspace</span>
            <h1>{record.sme.legal_name}</h1>
            <p><span>{record.sme.sector}</span><span><MapPin size={14} /> {record.sme.jurisdiction}</span><span>{record.sme.sme_id}</span></p>
          </div>
        </div>
        <div className="company-hero__metrics">
          <div><FileStack size={18} /><strong>{record.documents.length}</strong><span>documents</span></div>
          <div><ScanSearch size={18} /><strong>{record.evidence_items.length}</strong><span>evidence items</span></div>
          <div><CheckCircle2 size={18} /><strong>{acceptedEvidence}</strong><span>accepted</span></div>
        </div>
      </section>

      {error && <div className="error-banner"><span>{error}</span><button type="button" onClick={() => void load()}><RefreshCw size={13} /> Retry</button></div>}

      {(conflictEvidenceIds.size > 0 || pendingEvidence > 0) && (
        <div className="insight-banner">
          <span className="insight-banner__icon"><AlertTriangle size={20} /></span>
          <div>
            <strong>{conflictEvidenceIds.size > 0 ? 'This record needs reviewer attention' : 'Evidence is ready for validation'}</strong>
            <p>{conflictEvidenceIds.size > 0
              ? `${conflictEvidenceIds.size} evidence item${conflictEvidenceIds.size === 1 ? '' : 's'} belong to conflicting or unclear contexts. Reviewers must resolve them explicitly; the system never auto-averages them.`
              : `${pendingEvidence} extracted item${pendingEvidence === 1 ? ' is' : 's are'} waiting for a reviewer decision.`}</p>
          </div>
          <span className="insight-banner__stat">{completedDocuments}/{record.documents.length}<small>processed</small></span>
        </div>
      )}

      <div className="workspace-grid">
        <DocumentUploadPanel smeId={smeId} disabled={!permissions.canUploadDocuments} onCompleted={uploadCompleted} />
        <DocumentList documents={record.documents} processing={processing} jobs={jobs} canProcess={permissions.canProcessDocuments} busyId={busyId} selectedDocumentId={selectedDocumentId} onInspect={setSelectedDocumentId} onProcess={(documentId) => { setSelectedDocumentId(documentId); void processDocument(documentId) }} />
      </div>

      <DocumentIntelligencePanel
        key={selectedDocument?.document_id ?? 'no-document'}
        document={selectedDocument}
        processing={selectedDocument ? processing[selectedDocument.document_id] : undefined}
        progress={selectedDocument ? jobs[selectedDocument.document_id] : undefined}
        busy={selectedDocument ? busyId === selectedDocument.document_id : false}
        canProcess={permissions.canProcessDocuments}
        onProcess={(documentId) => void processDocument(documentId)}
        onRefresh={() => void load()}
      />

      <EvidenceReviewPanel
        evidenceItems={record.evidence_items}
        canValidate={permissions.canValidateEvidence}
        conflictEvidenceIds={conflictEvidenceIds}
        documentNames={Object.fromEntries(
          record.documents.map((document) => [
            document.document_id,
            document.file_name,
          ]),
        )}
        onValidate={validateEvidence}
      />
    </>
  )
}
