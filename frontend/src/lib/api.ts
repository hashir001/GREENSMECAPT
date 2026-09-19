import type {
  AssessmentConfiguration,
  AssessmentRunRecord,
  AssessmentRunSummary,
  CohortAssessmentRequest,
  DocumentProcessingResult,
  DocumentUploadResponse,
  EvidenceItem,
  SME,
  StructuredInvestmentRecord,
} from '../types/api'
import {
  createPreviewAssessment,
  getPreviewAssessmentRun,
  getPreviewDocumentProcessing,
  getPreviewRecord,
  previewAssessmentConfiguration,
  previewRuns,
  previewSMEs,
  processPreviewDocument,
  uploadPreviewDocument,
  validatePreviewEvidence,
} from './previewData'
import { isPreviewMode, supabase } from './supabase'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function accessToken(): Promise<string> {
  if (!supabase) throw new ApiError('Supabase authentication is not configured.', 401)
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session?.access_token) throw new ApiError('Your session has expired. Please sign in again.', 401)
  return data.session.access_token
}

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await accessToken()
  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers })
  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`
    try {
      const payload = (await response.json()) as { detail?: string | { message?: string } }
      if (typeof payload.detail === 'string') message = payload.detail
      else if (payload.detail?.message) message = payload.detail.message
    } catch { /* Keep fallback for non-JSON responses. */ }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  listSMEs: () => isPreviewMode ? Promise.resolve(structuredClone(previewSMEs)) : apiRequest<SME[]>('/smes'),
  getSMERecord: (smeId: string) => isPreviewMode ? getPreviewRecord(smeId) : apiRequest<StructuredInvestmentRecord>(`/smes/${encodeURIComponent(smeId)}/record`),
  uploadDocument: (smeId: string, file: File, documentType: string) => {
    if (isPreviewMode) return uploadPreviewDocument(smeId, file, documentType)
    const form = new FormData()
    form.set('file', file)
    form.set('document_type', documentType)
    return apiRequest<DocumentUploadResponse>(`/smes/${encodeURIComponent(smeId)}/documents`, { method: 'POST', body: form })
  },
  getDocumentProcessing: (smeId: string, documentId: string) => isPreviewMode
    ? getPreviewDocumentProcessing(smeId, documentId)
    : apiRequest<DocumentProcessingResult>(`/smes/${encodeURIComponent(smeId)}/documents/${encodeURIComponent(documentId)}/processing`),
  processDocument: (smeId: string, documentId: string) => isPreviewMode
    ? processPreviewDocument(smeId, documentId)
    : apiRequest<DocumentProcessingResult>(`/smes/${encodeURIComponent(smeId)}/documents/${encodeURIComponent(documentId)}/process`, { method: 'POST' }),
  validateEvidence: (evidenceId: string, status: EvidenceItem['validation_status'], reason?: string) => isPreviewMode
    ? validatePreviewEvidence(evidenceId, status)
    : apiRequest<EvidenceItem>(`/evidence/${encodeURIComponent(evidenceId)}/validation`, { method: 'PATCH', body: JSON.stringify({ status, reason: reason || null }) }),
  getAssessmentConfiguration: () => isPreviewMode
    ? Promise.resolve(structuredClone(previewAssessmentConfiguration))
    : apiRequest<AssessmentConfiguration>('/assessments/configuration'),
  createAssessment: (request: CohortAssessmentRequest) => isPreviewMode
    ? createPreviewAssessment(request)
    : apiRequest<AssessmentRunRecord>('/assessments/compare', { method: 'POST', body: JSON.stringify(request) }),
  listAssessmentRuns: () => isPreviewMode ? Promise.resolve(structuredClone(previewRuns)) : apiRequest<AssessmentRunSummary[]>('/assessments/runs'),
  getAssessmentRun: (runId: string) => isPreviewMode ? getPreviewAssessmentRun(runId) : apiRequest<AssessmentRunRecord>(`/assessments/runs/${encodeURIComponent(runId)}`),
}
