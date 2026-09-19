import { FileImage, FileText, LoaderCircle, Play, RefreshCw } from 'lucide-react'

import type { DocumentProcessingResult, SourceDocument } from '../types/api'
import { StatusPill } from './StatusPill'

type DocumentListProps = {
  documents: SourceDocument[]
  processing: Record<string, DocumentProcessingResult>
  canProcess: boolean
  busyId: string
  onProcess: (documentId: string) => void
}

function tone(status: string) {
  if (status === 'completed') return 'positive' as const
  if (status === 'failed') return 'danger' as const
  if (status === 'processing') return 'warning' as const
  return 'neutral' as const
}

export function DocumentList({ documents, processing, canProcess, busyId, onProcess }: DocumentListProps) {
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
          const status = result?.state.status ?? 'stored'
          const busy = busyId === document.document_id
          return (
            <article className="document-row" key={document.document_id}>
              <span className="document-row__icon">
                {document.mime_type.startsWith('image/') ? <FileImage size={20} /> : <FileText size={20} />}
              </span>
              <div className="document-row__copy">
                <strong>{document.file_name}</strong>
                <span>{document.document_type.replaceAll('_', ' ')} · {document.mime_type}</span>
                {result?.state.failure_message && <small>{result.state.failure_message}</small>}
              </div>
              <div className="document-row__result">
                <StatusPill label={status} tone={tone(status)} />
                {status === 'completed' && <small>{result.state.evidence_count} evidence item{result.state.evidence_count === 1 ? '' : 's'}</small>}
              </div>
              {canProcess && status !== 'completed' && (
                <button className="icon-button" type="button" disabled={busy} aria-label={`Process ${document.file_name}`} onClick={() => onProcess(document.document_id)}>
                  {busy ? <LoaderCircle className="spin" size={17} /> : status === 'failed' ? <RefreshCw size={17} /> : <Play size={17} />}
                </button>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
