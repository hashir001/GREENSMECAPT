import { BrainCircuit, FileImage, FileText, LoaderCircle, Play, RefreshCw, Trash2 } from 'lucide-react'

import type { DocumentProcessingResult, SourceDocument } from '../types/api'
import type { DocumentJobProgress } from '../types/jobs'
import { StatusPill } from './StatusPill'

type DocumentListProps = {
  documents: SourceDocument[]
  processing: Record<string, DocumentProcessingResult>
  jobs: Record<string, DocumentJobProgress>
  canProcess: boolean
  canDelete: boolean
  busyId: string
  selectedDocumentId: string
  onProcess: (documentId: string) => void
  onInspect: (documentId: string) => void
  onDelete: (documentId: string) => void
}

function tone(status: string) {
  if (status === 'completed') return 'positive' as const
  if (status === 'failed') return 'danger' as const
  if (status === 'processing' || status === 'running') return 'warning' as const
  return 'neutral' as const
}

export function DocumentList({ documents, processing, jobs, canProcess, canDelete, busyId, selectedDocumentId, onProcess, onInspect, onDelete }: DocumentListProps) {
  return (
    <section className="panel document-panel">
      <div className="panel__header">
        <div>
          <span className="eyebrow">Source register</span>
          <h2>Company documents</h2>
        </div>
        <span className="result-count">{documents.length} sources</span>
      </div>

      {!documents.length && (
        <div className="empty-state empty-state--compact">
          <span className="empty-state__icon"><FileText size={20} /></span>
          <strong>No documents yet</strong>
          <p>Upload the first source to begin building this company’s evidence record.</p>
        </div>
      )}

      <div className="document-list">
        {documents.map((document) => {
          const result = processing[document.document_id]
          const progress = jobs[document.document_id]
          const status = progress?.job.status ?? result?.state.status ?? 'stored'
          const busy = busyId === document.document_id
          const completedBatches = progress?.batches.filter((batch) => batch.status === 'completed').length ?? 0
          return (
            <article className={`document-row ${selectedDocumentId === document.document_id ? 'document-row--selected' : ''}`} key={document.document_id}>
              <span className="document-row__icon">
                {document.mime_type.startsWith('image/') ? <FileImage size={20} /> : <FileText size={20} />}
              </span>
              <div className="document-row__copy">
                <strong>{document.file_name}</strong>
                <span>{document.document_type.replaceAll('_', ' ')} · {document.mime_type}</span>
                {result?.state.failure_message && <small>{result.state.failure_message}</small>}
                {progress?.job.failure_message && <small>{progress.job.failure_message}</small>}
                {progress && progress.batches.length > 0 && status !== 'completed' && status !== 'failed' && (
                  <small>{completedBatches}/{progress.batches.length} page batches complete</small>
                )}
              </div>
              <div className="document-row__result">
                <StatusPill label={status} tone={tone(status)} />
                {status === 'completed' && result && (
                  <small>{result.state.evidence_count} evidence item{result.state.evidence_count === 1 ? '' : 's'}</small>
                )}
              </div>
              <div className="document-row__actions">
                <button className="icon-button" type="button" aria-label={`Inspect intelligence for ${document.file_name}`} onClick={() => onInspect(document.document_id)}>
                  <BrainCircuit size={17} />
                </button>
                {canProcess
                  && status !== 'completed'
                  && status !== 'running'
                  && status !== 'queued'
                  && !(progress?.job.status === 'failed' && progress.job.attempt_count >= progress.job.max_attempts)
                  && (
                  <button className="icon-button" type="button" disabled={busy} aria-label={`Process ${document.file_name}`} onClick={() => onProcess(document.document_id)}>
                    {busy ? <LoaderCircle className="spin" size={17} /> : status === 'failed' ? <RefreshCw size={17} /> : <Play size={17} />}
                  </button>
                )}
                {canDelete
                  && status !== 'running'
                  && status !== 'queued'
                  && (
                    <button className="icon-button icon-button--danger" type="button" disabled={busy} aria-label={`Delete ${document.file_name}`} onClick={() => onDelete(document.document_id)}>
                      <Trash2 size={17} />
                    </button>
                  )}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
