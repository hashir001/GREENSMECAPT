import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  FileStack,
  LoaderCircle,
  MapPin,
  Pencil,
  RefreshCw,
  ScanSearch,
  Trash2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { DocumentIntelligencePanel } from '../components/DocumentIntelligencePanel'
import { DocumentList } from '../components/DocumentList'
import { DocumentUploadPanel } from '../components/DocumentUploadPanel'
import { EvidenceReviewPanel } from '../components/EvidenceReviewPanel'
import { StatusPill } from '../components/StatusPill'
import { usePermissions } from '../auth/usePermissions'
import { api } from '../lib/api'
import type {
  DocumentProcessingResult,
  ApplicationRole,
  ApplicationStatus,
  SME,
  SMEApplication,
  StructuredInvestmentRecord,
} from '../types/api'
import type { DocumentJobProgress } from '../types/jobs'

type LifecycleAction = {
  target: ApplicationStatus
  label: string
  reasonRequired?: boolean
}

function lifecycleActions(
  status: ApplicationStatus,
  role: ApplicationRole | null,
): LifecycleAction[] {
  const submit = { target: 'submitted' as const, label: 'Submit for review' }
  const review = { target: 'under_review' as const, label: 'Start review' }
  const approve = { target: 'approved' as const, label: 'Approve application' }
  const changes = { target: 'changes_requested' as const, label: 'Request changes', reasonRequired: true }
  const withdraw = { target: 'withdrawn' as const, label: 'Withdraw', reasonRequired: true }
  const archive = { target: 'archived' as const, label: 'Archive', reasonRequired: true }
  const unpublish = { target: 'approved' as const, label: 'Unpublish profile' }
  const restore = { target: 'draft' as const, label: 'Restore draft' }
  const updateDossier = { target: 'changes_requested' as const, label: 'Update dossier', reasonRequired: true }

  if (role === 'sme_user') {
    if (status === 'draft' || status === 'changes_requested') return [submit, withdraw]
    if (status === 'submitted' || status === 'under_review') return [withdraw]
    if (status === 'approved' || status === 'published') return [updateDossier]
    return []
  }

  if (role === 'reviewer') {
    if (status === 'submitted') return [review, changes]
    if (status === 'under_review') return [approve, changes]
    if (status === 'approved' || status === 'published') return [changes]
    return []
  }

  if (role === 'admin') {
    if (status === 'draft') return [submit, withdraw]
    if (status === 'submitted') return [review, changes, withdraw]
    if (status === 'under_review') return [approve, changes, withdraw]
    if (status === 'changes_requested') return [submit, withdraw]
    if (status === 'approved') return [changes, archive]
    if (status === 'published') return [unpublish, changes, archive]
    if (status === 'withdrawn') return [restore, archive]
  }

  return []
}

export function CompanyDetailPage() {
  const { smeId = '' } = useParams()
  const navigate = useNavigate()
  const permissions = usePermissions()
  const [record, setRecord] = useState<StructuredInvestmentRecord | null>(null)
  const [application, setApplication] = useState<SMEApplication | null>(null)
  const [processing, setProcessing] = useState<Record<string, DocumentProcessingResult>>({})
  const [jobs, setJobs] = useState<Record<string, DocumentJobProgress>>({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  const [selectedDocumentId, setSelectedDocumentId] = useState('')
  const [error, setError] = useState('')
  const [editOpen, setEditOpen] = useState(false)
  const [deleteWorkspaceOpen, setDeleteWorkspaceOpen] = useState(false)
  const [deleteDocumentId, setDeleteDocumentId] = useState('')
  const [mutationBusy, setMutationBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [transitionTarget, setTransitionTarget] = useState<LifecycleAction | null>(null)
  const [editDraft, setEditDraft] = useState<Omit<SME, 'sme_id'>>({
    legal_name: '',
    sector: '',
    jurisdiction: '',
  })

  const load = useCallback(async () => {
    setError('')
    try {
      const [nextRecord, nextApplication] = await Promise.all([
        api.getSMERecord(smeId),
        api.getSMEApplication(smeId),
      ])
      setRecord(nextRecord)
      setApplication(nextApplication)
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

  const conflictEvidenceIds = useMemo(() => new Set(
    Object.values(processing).flatMap((result) => result.reconciliation?.clusters
      .filter((cluster) => cluster.status === 'conflict' || cluster.status === 'context_required')
      .flatMap((cluster) => cluster.evidence_ids) ?? []),
  ), [processing])

  const completedDocuments = Object.values(processing)
    .filter((result) => result.state.status === 'completed').length
  const acceptedEvidence = record?.evidence_items
    .filter((item) => item.validation_status === 'accepted').length ?? 0
  const pendingEvidence = record?.evidence_items
    .filter((item) => item.validation_status === 'unvalidated').length ?? 0
  const selectedDocument = record?.documents.find(
    (document) => document.document_id === selectedDocumentId,
  ) ?? null
  const mutableStatuses = new Set([
    'draft',
    'changes_requested',
  ])
  const documentMutableStatuses = new Set([
    'draft',
    'submitted',
    'under_review',
    'changes_requested',
    'withdrawn',
  ])
  const reviewerDocumentMutableStatuses = new Set([
    'submitted',
    'under_review',
    'changes_requested',
  ])
  const applicationDocumentsMutable = Boolean(
    application
    && (
      permissions.role === 'admin'
        ? documentMutableStatuses.has(application.status)
        : permissions.role === 'reviewer'
          ? reviewerDocumentMutableStatuses.has(application.status)
          : permissions.role === 'sme_user'
            ? mutableStatuses.has(application.status)
            : false
    ),
  )
  const canEditSME = Boolean(
    application
    && permissions.canUpdateSMEs
    && (
      permissions.role === 'admin'
        ? documentMutableStatuses.has(application.status)
        : mutableStatuses.has(application.status)
    ),
  )
  const canDeleteDocuments = Boolean(
    permissions.canDeleteDocuments
    && applicationDocumentsMutable,
  )
  const canUploadDocuments = Boolean(
    permissions.canUploadDocuments
    && applicationDocumentsMutable,
  )
  const canProcessDocuments = Boolean(
    permissions.canProcessDocuments
    && applicationDocumentsMutable,
  )
  const canVerifyOwnEvidence = Boolean(
    permissions.canVerifyOwnEvidence
    && application
    && mutableStatuses.has(application.status)
  )
  const uploadDisabledReason = !permissions.canUploadDocuments
    ? 'Your role can view documents but cannot upload them.'
    : application?.status === 'approved' || application?.status === 'published'
      ? `This application is ${application.status}. Use “Request changes” before adding or reprocessing evidence.`
      : application
        ? `Document changes are locked while this application is ${application.status.replaceAll('_', ' ')}.`
        : 'The application record is unavailable.'
  const canDeleteWorkspace = Boolean(
    application
    && permissions.canDeleteSMEs
  )
  const availableTransitions = application
    ? lifecycleActions(application.status, permissions.role)
    : []

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

  async function validateEvidenceBulk(evidenceIds: string[], status: 'accepted' | 'rejected', reason?: string) {
    const updated = await api.validateEvidenceBulk(evidenceIds, status, reason)
    const byId = new Map(updated.map((item) => [item.evidence_id, item]))
    setRecord((current) => current ? {
      ...current,
      evidence_items: current.evidence_items.map((item) => byId.get(item.evidence_id) ?? item),
    } : current)
  }

  async function verifyEvidenceAsSME(
    evidenceId: string,
    submission: Parameters<typeof api.verifyEvidenceAsSME>[1],
  ) {
    const updated = await api.verifyEvidenceAsSME(evidenceId, submission)
    setRecord((current) => current ? {
      ...current,
      evidence_items: current.evidence_items.map((item) => (
        item.evidence_id === updated.evidence_id ? updated : item
      )),
    } : current)
  }

  async function uploadCompleted(result?: DocumentProcessingResult) {
    if (result) setSelectedDocumentId(result.state.document_id)
    await load()
  }

  function openEdit() {
    if (!record) return
    setEditDraft({
      legal_name: record.sme.legal_name,
      sector: record.sme.sector,
      jurisdiction: record.sme.jurisdiction,
    })
    setReason('')
    setEditOpen(true)
  }

  async function saveSME(event: FormEvent) {
    event.preventDefault()
    if (!application) return
    setMutationBusy(true)
    setError('')
    try {
      await api.updateSME(
        smeId,
        application.revision,
        editDraft,
        reason || undefined,
      )
      setEditOpen(false)
      await load()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'Company details could not be updated.')
    } finally {
      setMutationBusy(false)
    }
  }

  async function confirmDocumentDelete() {
    if (!application || !deleteDocumentId || !reason.trim()) return
    setMutationBusy(true)
    setError('')
    try {
      await api.deleteDocument(
        smeId,
        deleteDocumentId,
        application.revision,
        reason.trim(),
      )
      setDeleteDocumentId('')
      setReason('')
      await load()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The document could not be deleted.')
    } finally {
      setMutationBusy(false)
    }
  }

  async function confirmWorkspaceDelete() {
    if (!application || !reason.trim()) return
    setMutationBusy(true)
    setError('')
    try {
      await api.deleteSME(
        smeId,
        application.revision,
        reason.trim(),
      )
      void navigate('/companies', { replace: true })
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The company workspace could not be deleted.')
      setDeleteWorkspaceOpen(false)
    } finally {
      setMutationBusy(false)
    }
  }

  async function applyTransition(
    action: LifecycleAction,
    transitionReason?: string,
  ) {
    if (!application) return
    setMutationBusy(true)
    setError('')
    try {
      await api.transitionSMEApplication(
        smeId,
        application.revision,
        action.target,
        transitionReason,
      )
      setTransitionTarget(null)
      setReason('')
      await load()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The application status could not be changed.')
    } finally {
      setMutationBusy(false)
    }
  }

  function requestTransition(action: LifecycleAction) {
    if (action.reasonRequired) {
      setReason('')
      setTransitionTarget(action)
      return
    }
    void applyTransition(action)
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

      {editOpen && (
        <div className="company-create-backdrop" role="presentation" onMouseDown={() => setEditOpen(false)}>
          <form className="company-create-dialog" onSubmit={(event) => void saveSME(event)} onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span className="eyebrow">Application record</span><h2>Edit company details</h2><p>The SME identifier remains immutable.</p></div>
              <button className="icon-button" type="button" aria-label="Close edit form" onClick={() => setEditOpen(false)}><X size={17} /></button>
            </header>
            <div className="company-create-grid">
              <label className="builder-field">Legal name<input required value={editDraft.legal_name} onChange={(event) => setEditDraft((current) => ({ ...current, legal_name: event.target.value }))} /></label>
              <label className="builder-field">Sector<input required value={editDraft.sector} onChange={(event) => setEditDraft((current) => ({ ...current, sector: event.target.value }))} /></label>
              <label className="builder-field">Jurisdiction<input required value={editDraft.jurisdiction} onChange={(event) => setEditDraft((current) => ({ ...current, jurisdiction: event.target.value }))} /></label>
              <label className="builder-field">Reason (optional)<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why these details changed" /></label>
            </div>
            <footer>
              <button className="secondary-button" type="button" onClick={() => setEditOpen(false)}>Cancel</button>
              <button className="primary-button" type="submit" disabled={mutationBusy}>{mutationBusy && <LoaderCircle className="spin" size={16} />} Save changes</button>
            </footer>
          </form>
        </div>
      )}

      {(deleteDocumentId || deleteWorkspaceOpen) && (
        <div className="company-create-backdrop" role="presentation" onMouseDown={() => { setDeleteDocumentId(''); setDeleteWorkspaceOpen(false) }}>
          <div className="company-create-dialog destructive-dialog" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span className="eyebrow">Permanent deletion</span><h2>{deleteWorkspaceOpen ? 'Delete company and all data?' : 'Delete source document?'}</h2><p>{deleteWorkspaceOpen ? 'This permanently removes the company, documents, evidence, profiles and assessment runs containing it.' : 'Derived evidence and processing history for this document will also be removed.'}</p></div>
              <button className="icon-button" type="button" aria-label="Close deletion form" onClick={() => { setDeleteDocumentId(''); setDeleteWorkspaceOpen(false) }}><X size={17} /></button>
            </header>
            <div className="destructive-dialog__body">
              <label className="builder-field">Deletion reason<input required value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required for the audit trail" /></label>
            </div>
            <footer>
              <button className="secondary-button" type="button" onClick={() => { setDeleteDocumentId(''); setDeleteWorkspaceOpen(false) }}>Cancel</button>
              <button className="danger-button" type="button" disabled={mutationBusy || !reason.trim()} onClick={() => void (deleteWorkspaceOpen ? confirmWorkspaceDelete() : confirmDocumentDelete())}>{mutationBusy ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />} Delete permanently</button>
            </footer>
          </div>
        </div>
      )}

      {transitionTarget && (
        <div className="company-create-backdrop" role="presentation" onMouseDown={() => setTransitionTarget(null)}>
          <div className="company-create-dialog" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span className="eyebrow">Application lifecycle</span><h2>{transitionTarget.label}?</h2><p>This decision is revision-checked and retained in the audit trail.</p></div>
              <button className="icon-button" type="button" aria-label="Close transition form" onClick={() => setTransitionTarget(null)}><X size={17} /></button>
            </header>
            <div className="destructive-dialog__body">
              <label className="builder-field">Reason<input required value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain this decision" /></label>
            </div>
            <footer>
              <button className="secondary-button" type="button" onClick={() => setTransitionTarget(null)}>Cancel</button>
              <button className="primary-button" type="button" disabled={mutationBusy || !reason.trim()} onClick={() => void applyTransition(transitionTarget, reason.trim())}>{mutationBusy && <LoaderCircle className="spin" size={16} />} Confirm</button>
            </footer>
          </div>
        </div>
      )}

      <section className="company-hero">
        <div className="company-hero__identity">
          <span className="company-hero__avatar"><Building2 size={28} /></span>
          <div>
            <span className="eyebrow eyebrow--light">Evidence workspace</span>
            <h1>{record.sme.legal_name}</h1>
            <p><span>{record.sme.sector}</span><span><MapPin size={14} /> {record.sme.jurisdiction}</span><span>{record.sme.sme_id}</span></p>
          </div>
        </div>
        <div className="company-hero__actions">
          {application && <StatusPill label={application.status.replaceAll('_', ' ')} tone={application.status === 'published' || application.status === 'approved' ? 'positive' : 'neutral'} />}
          {availableTransitions.map((action) => <button className="secondary-button secondary-button--light" type="button" key={action.target} disabled={mutationBusy} onClick={() => requestTransition(action)}>{action.label}</button>)}
          {canEditSME && <button className="secondary-button secondary-button--light" type="button" onClick={openEdit}><Pencil size={15} /> Edit details</button>}
          {canDeleteWorkspace && <button className="danger-button danger-button--compact" type="button" onClick={() => { setReason(''); setDeleteWorkspaceOpen(true) }}><Trash2 size={15} /> Delete company</button>}
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
        <DocumentUploadPanel smeId={smeId} applicationRevision={application?.revision ?? 1} disabled={!canUploadDocuments} disabledReason={uploadDisabledReason} onCompleted={uploadCompleted} />
        <DocumentList documents={record.documents} processing={processing} jobs={jobs} canProcess={canProcessDocuments} canDelete={canDeleteDocuments} busyId={busyId} selectedDocumentId={selectedDocumentId} onInspect={setSelectedDocumentId} onProcess={(documentId) => { setSelectedDocumentId(documentId); void processDocument(documentId) }} onDelete={(documentId) => { setReason(''); setDeleteDocumentId(documentId) }} />
      </div>

      <DocumentIntelligencePanel
        key={selectedDocument?.document_id ?? 'no-document'}
        document={selectedDocument}
        processing={selectedDocument ? processing[selectedDocument.document_id] : undefined}
        progress={selectedDocument ? jobs[selectedDocument.document_id] : undefined}
        busy={selectedDocument ? busyId === selectedDocument.document_id : false}
        canProcess={canProcessDocuments}
        onProcess={(documentId) => void processDocument(documentId)}
        onRefresh={() => void load()}
      />

      <EvidenceReviewPanel
        evidenceItems={record.evidence_items}
        canValidate={permissions.canValidateEvidence}
        canVerify={canVerifyOwnEvidence}
        conflictEvidenceIds={conflictEvidenceIds}
        documents={record.documents}
        processingStatuses={Object.fromEntries(Object.entries(processing).map(([documentId, result]) => [documentId, result.state.status]))}
        onValidate={validateEvidence}
        onValidateMany={validateEvidenceBulk}
        onVerify={verifyEvidenceAsSME}
      />
    </>
  )
}
