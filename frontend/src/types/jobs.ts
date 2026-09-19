import type { DocumentProcessingResult } from './api'

export type DocumentJobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'

export type DocumentBatchStatus =
  | 'planned'
  | 'running'
  | 'completed'
  | 'failed'

export type DocumentProcessingJob = {
  job_id: string
  document_id: string
  sme_id: string
  requested_by: string
  status: DocumentJobStatus
  attempt_count: number
  max_attempts: number
  failure_code: string | null
  failure_message: string | null
  worker_id: string | null
  lease_expires_at: string | null
  last_heartbeat_at: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

export type DocumentBatchCheckpoint = {
  checkpoint_id: string
  job_id: string
  document_id: string
  batch_id: string
  page_numbers: number[]
  status: DocumentBatchStatus
  attempt_count: number
  max_attempts: number
  worker_id: string | null
  failure_message: string | null
  result_json: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

export type DocumentJobProgress = {
  job: DocumentProcessingJob
  batches: DocumentBatchCheckpoint[]
}

export type DocumentJobExecution =
  DocumentJobProgress & {
    result: DocumentProcessingResult | null
  }