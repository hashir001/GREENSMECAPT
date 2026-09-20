import { FileCheck2, FileUp, LoaderCircle, UploadCloud, X } from 'lucide-react'
import { useRef, useState, type DragEvent, type FormEvent } from 'react'

import { api } from '../lib/api'
import type { DocumentProcessingResult } from '../types/api'
import type { DocumentJobProgress } from '../types/jobs'

const maximumBytes = 20 * 1024 * 1024
const acceptedTypes = '.pdf,.txt,.png,.jpg,.jpeg,.tif,.tiff'
const acceptedMimeTypes = new Set([
  'application/pdf',
  'text/plain',
  'image/jpeg',
  'image/png',
  'image/tiff',
])
const acceptedExtensions = new Set([
  'pdf',
  'txt',
  'png',
  'jpg',
  'jpeg',
  'tif',
  'tiff',
])

const documentTypes = [
  ['sustainability_report', 'Sustainability report'],
  ['utility_bill', 'Utility bill'],
  ['financial_statement', 'Financial statement'],
  ['permit', 'Permit or certification'],
  ['contract', 'Contract'],
  ['funding_request', 'Funding request'],
  ['other', 'Other supporting document'],
]

type DocumentUploadPanelProps = {
  smeId: string
  disabled?: boolean
  onCompleted: (result?: DocumentProcessingResult) => void | Promise<void>
}

export function DocumentUploadPanel({ smeId, disabled = false, onCompleted }: DocumentUploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [documentType, setDocumentType] = useState('sustainability_report')
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'processing' | 'completed'>('idle')
  const [progress, setProgress] = useState<DocumentJobProgress | null>(null)

  function chooseFile(nextFile: File | undefined) {
    setError('')
    setSuccess('')
    if (!nextFile) return
    const extension = nextFile.name.split('.').at(-1)?.toLowerCase() ?? ''
    if (
      !acceptedExtensions.has(extension)
      || (nextFile.type && !acceptedMimeTypes.has(nextFile.type))
    ) {
      setFile(null)
      setError('Use a PDF, plain-text file, PNG, JPEG or TIFF image.')
      return
    }
    if (nextFile.size > maximumBytes) {
      setFile(null)
      setError('This file is larger than the 20 MB upload limit.')
      return
    }
    setFile(nextFile)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files[0])
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!file || disabled) return
    setBusy(true)
    setError('')
    setSuccess('')
    setPhase('uploading')
    setProgress(null)
    let uploadedDocumentId = ''
    try {
      const uploaded = await api.uploadDocument(smeId, file, documentType)
      uploadedDocumentId = uploaded.document.document_id
      await onCompleted()
      setPhase('processing')
      const execution = await api.runDocumentProcessingJob(
        smeId,
        uploaded.document.document_id,
        setProgress,
      )

      if (execution.job.status === 'failed') {
        throw new Error(
          execution.job.failure_message || 'Document processing failed.',
        )
      }

      await onCompleted(execution.result ?? undefined)
      setPhase('completed')
      setSuccess(
        `Analysis completed with ${execution.result?.state.evidence_count ?? 0} traceable evidence item${execution.result?.state.evidence_count === 1 ? '' : 's'}.`,
      )
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
    } catch (caught: unknown) {
      if (uploadedDocumentId) await onCompleted()
      setError(caught instanceof Error ? caught.message : 'The document could not be processed.')
      setPhase('idle')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="upload-panel" onSubmit={(event) => void submit(event)}>
      <div className="section-copy">
        <span className="eyebrow">New source</span>
        <h2>Upload and analyse</h2>
        <p>PDF, scanned image or text. Native reading, OCR, tables and NLP are selected page by page.</p>
      </div>

      <div
        className={`dropzone ${dragging ? 'dropzone--active' : ''}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
        }}
      >
        <span className="dropzone__icon"><UploadCloud size={25} /></span>
        <strong>Drop a document here</strong>
        <span>or browse from your computer · up to 20 MB</span>
        <input
          ref={inputRef}
          type="file"
          accept={acceptedTypes}
          hidden
          onChange={(event) => chooseFile(event.target.files?.[0])}
        />
      </div>

      {file && (
        <div className="file-selection">
          <FileCheck2 size={18} />
          <div>
            <strong>{file.name}</strong>
            <span>{(file.size / 1024).toFixed(1)} KB</span>
          </div>
          <button type="button" aria-label="Remove selected file" onClick={() => setFile(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      <label className="field-label">
        Document type
        <select value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
          {documentTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select>
      </label>

      {error && <div className="form-error">{error}</div>}
      {success && <div className="form-success">{success}</div>}
      {progress && busy && (
        <div className="job-progress">
          <div>
            <strong>{phase === 'uploading' ? 'Securing original document' : progress.job.status === 'queued' ? 'Queued for analysis' : 'Analysing document'}</strong>
            <span>
              {progress.batches.length
                ? `${progress.batches.filter((batch) => batch.status === 'completed').length} of ${progress.batches.length} page batches complete`
                : 'Preparing page batches…'}
            </span>
          </div>
          <div className="job-progress__bar">
            <span style={{ width: `${progress.batches.length ? (progress.batches.filter((batch) => batch.status === 'completed').length / progress.batches.length) * 100 : 8}%` }} />
          </div>
        </div>
      )}
      {!disabled && (
        <button className="primary-button upload-panel__submit" type="submit" disabled={!file || busy}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <FileUp size={17} />}
          {busy ? phase === 'uploading' ? 'Uploading securely…' : 'Reading and extracting…' : 'Upload and analyse'}
        </button>
      )}
      {disabled && <div className="permission-note">Your role can view documents but cannot upload them.</div>}
    </form>
  )
}
