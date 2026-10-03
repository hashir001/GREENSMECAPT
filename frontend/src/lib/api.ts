import type {
  AssessmentConfiguration,
  AssessmentAutofill,
  AssessmentProfilePublication,
  AssessmentProfileStatus,
  AssessmentRunRecord,
  AssessmentRunSummary,
  AssessmentSubmission,
  AutomaticCohortAssessmentRequest,
  CohortAssessmentRequest,
  PreparedAssessment,
  StoredAssessmentProfileRevision,
  DocumentProcessingResult,
  DocumentDeletionResponse,
  DocumentUploadResponse,
  EvidenceItem,
  FinancialObservation,
  FinancialPolicy,
  FinancialSubmission,
  ApplicationRole,
  ManagedUser,
  SME,
  SMEApplication,
  ApplicationStatus,
  SMEUpdateResponse,
  SMEVerificationSubmission,
  SemanticProviderConnection,
  StructuredInvestmentRecord,
  SystemCapabilities,
} from '../types/api'
import type {
  DocumentBatchCheckpoint,
  DocumentJobExecution,
  DocumentJobProgress,
  DocumentProcessingJob,
} from '../types/jobs'
import {
  createPreviewSME,
  deletePreviewDocument,
  deletePreviewAssessmentRun,
  deletePreviewSME,
  getPreviewApplication,
  createPreviewAssessment,
  getPreviewAssessmentRun,
  getPreviewDocumentProcessing,
  getPreviewRecord,
  previewAssessmentConfiguration,
  previewRuns,
  previewSMEs,
  processPreviewDocument,
  transitionPreviewApplication,
  uploadPreviewDocument,
  updatePreviewSME,
  validatePreviewEvidence,
} from './previewData'
import { isPreviewMode, supabase } from './supabase'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api'
).replace(/\/$/, '')

const jobPollIntervalMs = 750
const maximumJobPolls = 800

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function accessToken(): Promise<string> {
  if (!supabase) {
    throw new ApiError(
      'Supabase authentication is not configured.',
      401,
    )
  }

  const { data, error } = await supabase.auth.getSession()

  if (error || !data.session?.access_token) {
    throw new ApiError(
      'Your session has expired. Please sign in again.',
      401,
    )
  }

  return data.session.access_token
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await authenticatedRequest(path, options)
  return response.json() as Promise<T>
}

async function authenticatedRequest(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  let token = await accessToken()
  const headers = new Headers(options.headers)

  headers.set('Authorization', `Bearer ${token}`)

  if (
    options.body
    && !(options.body instanceof FormData)
  ) {
    headers.set('Content-Type', 'application/json')
  }

  let response = await fetch(
    `${apiBaseUrl}${path}`,
    {
      ...options,
      headers,
    },
  )

  if (response.status === 401 && supabase) {
    const { data, error } = await supabase.auth.refreshSession()

    if (!error && data.session?.access_token) {
      token = data.session.access_token
      headers.set('Authorization', `Bearer ${token}`)
      response = await fetch(
        `${apiBaseUrl}${path}`,
        {
          ...options,
          headers,
        },
      )
    }
  }

  if (!response.ok) {
    let message =
      `Request failed with status ${response.status}.`

    try {
      const payload = await response.json() as {
        detail?: string | { message?: string } | Array<{ msg?: string }>
      }

      if (typeof payload.detail === 'string') {
        message = payload.detail
      } else if (Array.isArray(payload.detail)) {
        message = payload.detail
          .map((item) => item.msg)
          .filter(Boolean)
          .join(' ') || message
      } else if (payload.detail?.message) {
        message = payload.detail.message
      }
    } catch {
      // Retain the fallback for non-JSON responses.
    }

    throw new ApiError(message, response.status)
  }

  return response
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds)
  })
}

function previewJob(
  smeId: string,
  documentId: string,
  status: DocumentProcessingJob['status'],
): DocumentProcessingJob {
  const now = new Date().toISOString()

  return {
    job_id: `preview_job_${documentId}`,
    document_id: documentId,
    sme_id: smeId,
    requested_by: 'preview_user',
    status,
    attempt_count: status === 'queued' ? 0 : 1,
    max_attempts: 3,
    failure_code: null,
    failure_message: null,
    worker_id:
      status === 'running'
        ? 'preview_worker'
        : null,
    lease_expires_at:
      status === 'running'
        ? now
        : null,
    last_heartbeat_at:
      status === 'running'
        ? now
        : null,
    created_at: now,
    started_at:
      status === 'queued'
        ? null
        : now,
    completed_at:
      status === 'completed'
      || status === 'failed'
        ? now
        : null,
    updated_at: now,
  }
}

async function pollDocumentJob(
  smeId: string,
  documentId: string,
  initialJob: DocumentProcessingJob,
  onProgress?: (
    progress: DocumentJobProgress
  ) => void,
  minimumPolls = 0,
): Promise<DocumentJobExecution> {
  let job = initialJob
  let batches: DocumentBatchCheckpoint[] = []

  onProgress?.({
    job,
    batches,
  })

  for (
    let poll = 0;
    poll < maximumJobPolls;
    poll += 1
  ) {
    if (
      poll >= minimumPolls
      && job.status === 'completed'
    ) {
      const result =
        await apiRequest<DocumentProcessingResult>(
          `/smes/${
            encodeURIComponent(smeId)
          }/documents/${
            encodeURIComponent(documentId)
          }/processing`,
        )

      return {
        job,
        batches,
        result,
      }
    }

    if (
      poll >= minimumPolls
      && job.status === 'failed'
    ) {
      return {
        job,
        batches,
        result: null,
      }
    }

    await wait(jobPollIntervalMs)

    const jobsPath =
      `/smes/${
        encodeURIComponent(smeId)
      }/documents/${
        encodeURIComponent(documentId)
      }/processing-jobs/${
        encodeURIComponent(job.job_id)
      }`

    const nextProgress = await Promise.all([
      apiRequest<DocumentProcessingJob>(
        jobsPath,
      ),
      apiRequest<DocumentBatchCheckpoint[]>(
        `${jobsPath}/batches`,
      ),
    ])

    job = nextProgress[0]
    batches = nextProgress[1]

    onProgress?.({
      job,
      batches,
    })
  }

  throw new ApiError(
    'Document processing did not finish within ten minutes.',
    408,
  )
}

async function runPreviewDocumentJob(
  smeId: string,
  documentId: string,
  onProgress?: (
    progress: DocumentJobProgress
  ) => void,
): Promise<DocumentJobExecution> {
  onProgress?.({
    job: previewJob(
      smeId,
      documentId,
      'queued',
    ),
    batches: [],
  })

  await wait(250)

  const result = await processPreviewDocument(
    smeId,
    documentId,
  )

  const manifestBatches = result.report?.processing_manifest?.batches ?? []
  let batches: DocumentBatchCheckpoint[] = manifestBatches.map((batch) => ({
    checkpoint_id: `checkpoint_${batch.batch_id}`,
    job_id: `preview_job_${documentId}`,
    document_id: documentId,
    batch_id: batch.batch_id,
    page_numbers: batch.page_numbers,
    status: 'planned',
    attempt_count: 0,
    max_attempts: batch.maximum_attempts,
    worker_id: null,
    failure_message: null,
    result_json: null,
    created_at: new Date().toISOString(),
    started_at: null,
    completed_at: null,
    updated_at: new Date().toISOString(),
  }))

  for (let index = 0; index < batches.length; index += 1) {
    batches = batches.map((batch, batchIndex) => ({
      ...batch,
      status: batchIndex < index
        ? 'completed'
        : batchIndex === index
          ? 'running'
          : 'planned',
      attempt_count: batchIndex <= index ? 1 : 0,
      worker_id: batchIndex === index ? 'preview_worker' : null,
      started_at: batchIndex <= index ? new Date().toISOString() : null,
      completed_at: batchIndex < index ? new Date().toISOString() : null,
      updated_at: new Date().toISOString(),
    }))
    onProgress?.({
      job: previewJob(smeId, documentId, 'running'),
      batches,
    })
    await wait(220)
  }

  batches = batches.map((batch) => ({
    ...batch,
    status: 'completed',
    attempt_count: 1,
    worker_id: null,
    completed_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }))

  const job = previewJob(
    smeId,
    documentId,
    'completed',
  )

  onProgress?.({
    job,
    batches,
  })

  return {
    job,
    batches,
    result,
  }
}

export const api = {
  getFinancialConfiguration: () => apiRequest<FinancialPolicy>('/financial/configuration'),

  getFinancialSubmission: (smeId: string) => apiRequest<FinancialSubmission | null>(
    `/smes/${encodeURIComponent(smeId)}/financial-submission`,
  ),

  listFinancialSubmissions: () => apiRequest<FinancialSubmission[]>(
    '/financial/submissions',
  ),

  saveFinancialSubmission: (
    smeId: string,
    expectedRevision: number | null,
    observations: FinancialObservation[],
  ) => apiRequest<FinancialSubmission>(
    `/smes/${encodeURIComponent(smeId)}/financial-submission`,
    {
      method: 'PUT',
      body: JSON.stringify({
        expected_revision: expectedRevision,
        observations,
      }),
    },
  ),

  submitFinancialSubmission: (smeId: string, expectedRevision: number) => (
    apiRequest<FinancialSubmission>(
      `/smes/${encodeURIComponent(smeId)}/financial-submission/submit`,
      {
        method: 'POST',
        body: JSON.stringify({ expected_revision: expectedRevision }),
      },
    )
  ),

  reviewFinancialSubmission: (
    smeId: string,
    expectedRevision: number,
    decision: 'approved' | 'changes_requested',
    note?: string,
  ) => apiRequest<FinancialSubmission>(
    `/smes/${encodeURIComponent(smeId)}/financial-submission/review`,
    {
      method: 'POST',
      body: JSON.stringify({
        expected_revision: expectedRevision,
        decision,
        note: note || null,
      }),
    },
  ),

  getSystemCapabilities: () => (
    isPreviewMode
      ? Promise.resolve<SystemCapabilities>({
          native_pdf_reading: true,
          ocr_routing: true,
          table_extraction: true,
          semantic_provider_configured: false,
          visual_provider_configured: false,
          identity_admin_configured: false,
          human_validation_required: true,
        })
      : apiRequest<SystemCapabilities>('/system/capabilities')
  ),

  checkSemanticProvider: () => (
    apiRequest<SemanticProviderConnection>(
      '/system/providers/semantic/check',
      { method: 'POST' },
    )
  ),

  listManagedUsers: () => (
    isPreviewMode
      ? Promise.resolve<ManagedUser[]>([])
      : apiRequest<ManagedUser[]>('/admin/users')
  ),

  inviteManagedUser: (
    email: string,
    role: ApplicationRole,
    smeIds: string[],
  ) => apiRequest<ManagedUser>(
    '/admin/users/invitations',
    {
      method: 'POST',
      body: JSON.stringify({
        email,
        role,
        sme_ids: smeIds,
      }),
    },
  ),

  updateManagedUserAccess: (
    userId: string,
    role: ApplicationRole,
    smeIds: string[],
  ) => apiRequest<ManagedUser>(
    `/admin/users/${encodeURIComponent(userId)}/access`,
    {
      method: 'PATCH',
      body: JSON.stringify({
        role,
        sme_ids: smeIds,
      }),
    },
  ),

  createSME: (sme: SME) => {
    if (isPreviewMode) {
      return createPreviewSME(sme)
    }

    return apiRequest<SME>('/smes', {
      method: 'POST',
      body: JSON.stringify(sme),
    })
  },

  listSMEs: () => (
    isPreviewMode
      ? Promise.resolve(
          structuredClone(previewSMEs)
        )
      : apiRequest<SME[]>('/smes')
  ),

  getSMERecord: (smeId: string) => (
    isPreviewMode
      ? getPreviewRecord(smeId)
      : apiRequest<StructuredInvestmentRecord>(
          `/smes/${
            encodeURIComponent(smeId)
          }/record`,
        )
  ),

  getSMEApplication: (smeId: string) => (
    isPreviewMode
      ? getPreviewApplication(smeId)
      : apiRequest<SMEApplication>(
          `/smes/${encodeURIComponent(smeId)}/application`,
        )
  ),

  transitionSMEApplication: (
    smeId: string,
    expectedRevision: number,
    targetStatus: ApplicationStatus,
    reason?: string,
  ) => (
    isPreviewMode
      ? transitionPreviewApplication(smeId, targetStatus)
      : apiRequest<SMEApplication>(
          `/smes/${encodeURIComponent(smeId)}/application`,
          {
            method: 'PATCH',
            body: JSON.stringify({
              expected_revision: expectedRevision,
              target_status: targetStatus,
              reason: reason || null,
            }),
          },
        )
  ),

  updateSME: (
    smeId: string,
    expectedApplicationRevision: number,
    update: Partial<Pick<SME, 'legal_name' | 'sector' | 'jurisdiction'>>,
    reason?: string,
  ) => (
    isPreviewMode
      ? updatePreviewSME(smeId, update)
      : apiRequest<SMEUpdateResponse>(
          `/smes/${encodeURIComponent(smeId)}`,
          {
            method: 'PATCH',
            body: JSON.stringify({
              expected_application_revision: expectedApplicationRevision,
              ...update,
              reason: reason || null,
            }),
          },
        )
  ),

  deleteSME: (
    smeId: string,
    expectedApplicationRevision: number,
    reason: string,
  ) => (
    isPreviewMode
      ? deletePreviewSME(smeId)
      : authenticatedRequest(
          `/smes/${encodeURIComponent(smeId)}`,
          {
            method: 'DELETE',
            body: JSON.stringify({
              expected_application_revision: expectedApplicationRevision,
              reason,
            }),
          },
        ).then(() => undefined)
  ),

  uploadDocument: (
    smeId: string,
    file: File,
    documentType: string,
    expectedApplicationRevision: number,
  ) => {
    if (isPreviewMode) {
      return uploadPreviewDocument(
        smeId,
        file,
        documentType,
      )
    }

    const form = new FormData()

    form.set('file', file)
    form.set(
      'document_type',
      documentType,
    )
    form.set(
      'expected_application_revision',
      String(expectedApplicationRevision),
    )

    return apiRequest<DocumentUploadResponse>(
      `/smes/${
        encodeURIComponent(smeId)
      }/documents`,
      {
        method: 'POST',
        body: form,
      },
    )
  },

  getDocumentProcessing: (
    smeId: string,
    documentId: string,
  ) => (
    isPreviewMode
      ? getPreviewDocumentProcessing(
          smeId,
          documentId,
        )
      : apiRequest<DocumentProcessingResult>(
          `/smes/${
            encodeURIComponent(smeId)
          }/documents/${
            encodeURIComponent(documentId)
          }/processing`,
        )
  ),

  deleteDocument: (
    smeId: string,
    documentId: string,
    expectedApplicationRevision: number,
    reason: string,
  ) => (
    isPreviewMode
      ? deletePreviewDocument(smeId, documentId).then(
          (application): DocumentDeletionResponse => ({
            document_id: documentId,
            application,
          }),
        )
      : apiRequest<DocumentDeletionResponse>(
          `/smes/${encodeURIComponent(smeId)}/documents/${encodeURIComponent(documentId)}`,
          {
            method: 'DELETE',
            body: JSON.stringify({
              expected_application_revision: expectedApplicationRevision,
              reason,
            }),
          },
        )
  ),

  getLatestDocumentJobProgress: async (
    smeId: string,
    documentId: string,
  ): Promise<DocumentJobProgress | null> => {
    if (isPreviewMode) {
      const result = await getPreviewDocumentProcessing(smeId, documentId)
      if (result.state.status === 'stored') return null
      const job = previewJob(
        smeId,
        documentId,
        result.state.status === 'processing' ? 'running' : result.state.status,
      )
      const batches = (result.report?.processing_manifest?.batches ?? []).map(
        (batch): DocumentBatchCheckpoint => ({
          checkpoint_id: `checkpoint_${batch.batch_id}`,
          job_id: job.job_id,
          document_id: documentId,
          batch_id: batch.batch_id,
          page_numbers: batch.page_numbers,
          status: batch.status === 'processing' ? 'running' : batch.status,
          attempt_count: batch.attempt_count,
          max_attempts: batch.maximum_attempts,
          worker_id: null,
          failure_message: batch.failure_message,
          result_json: null,
          created_at: job.created_at,
          started_at: job.started_at,
          completed_at: job.completed_at,
          updated_at: job.updated_at,
        }),
      )
      return { job, batches }
    }

    const path = `/smes/${encodeURIComponent(smeId)}/documents/${encodeURIComponent(documentId)}/processing-jobs`
    const job = await apiRequest<DocumentProcessingJob | null>(`${path}/latest`)

    if (!job) return null

    const batches = await apiRequest<DocumentBatchCheckpoint[]>(
      `${path}/${encodeURIComponent(job.job_id)}/batches`,
    )
    return { job, batches }
  },

  watchDocumentProcessingJob: (
    smeId: string,
    documentId: string,
    progress: DocumentJobProgress,
    onProgress?: (next: DocumentJobProgress) => void,
  ) => pollDocumentJob(
    smeId,
    documentId,
    progress.job,
    onProgress,
  ),

  getDocumentContent: (smeId: string, documentId: string) => (
    isPreviewMode
      ? Promise.resolve(new Blob(
          ['Presentation preview: original source bytes are available in connected mode.'],
          { type: 'text/plain' },
        ))
      : authenticatedRequest(
          `/smes/${encodeURIComponent(smeId)}/documents/${encodeURIComponent(documentId)}/content`,
        ).then((response) => response.blob())
  ),

  processDocument: (
    smeId: string,
    documentId: string,
  ) => (
    isPreviewMode
      ? processPreviewDocument(
          smeId,
          documentId,
        )
      : apiRequest<DocumentProcessingResult>(
          `/smes/${
            encodeURIComponent(smeId)
          }/documents/${
            encodeURIComponent(documentId)
          }/process`,
          {
            method: 'POST',
          },
        )
  ),

  runDocumentProcessingJob: async (
    smeId: string,
    documentId: string,
    onProgress?: (
      progress: DocumentJobProgress
    ) => void,
  ) => {
    if (isPreviewMode) {
      return runPreviewDocumentJob(
        smeId,
        documentId,
        onProgress,
      )
    }

    const jobsPath =
      `/smes/${
        encodeURIComponent(smeId)
      }/documents/${
        encodeURIComponent(documentId)
      }/processing-jobs`

    const job =
      await apiRequest<DocumentProcessingJob>(
        jobsPath,
        {
          method: 'POST',
        },
      )

    return pollDocumentJob(
      smeId,
      documentId,
      job,
      onProgress,
      1,
    )
  },

  retryDocumentProcessingJob: async (
    smeId: string,
    documentId: string,
    jobId: string,
    onProgress?: (
      progress: DocumentJobProgress
    ) => void,
  ) => {
    if (isPreviewMode) {
      return runPreviewDocumentJob(
        smeId,
        documentId,
        onProgress,
      )
    }

    const jobsPath =
      `/smes/${
        encodeURIComponent(smeId)
      }/documents/${
        encodeURIComponent(documentId)
      }/processing-jobs/${
        encodeURIComponent(jobId)
      }`

    const job =
      await apiRequest<DocumentProcessingJob>(
        `${jobsPath}/retry`,
        {
          method: 'POST',
        },
      )

    return pollDocumentJob(
      smeId,
      documentId,
      job,
      onProgress,
      1,
    )
  },

  validateEvidence: (
    evidenceId: string,
    status: EvidenceItem[
      'validation_status'
    ],
    reason?: string,
  ) => (
    isPreviewMode
      ? validatePreviewEvidence(
          evidenceId,
          status,
        )
      : apiRequest<EvidenceItem>(
          `/evidence/${
            encodeURIComponent(evidenceId)
          }/validation`,
          {
            method: 'PATCH',
            body: JSON.stringify({
              status,
              reason: reason || null,
            }),
          },
        )
  ),

  validateEvidenceBulk: async (
    evidenceIds: string[],
    status: 'accepted' | 'rejected',
    reason?: string,
  ) => {
    if (isPreviewMode) {
      return Promise.all(
        evidenceIds.map((evidenceId) => validatePreviewEvidence(evidenceId, status)),
      )
    }
    return apiRequest<EvidenceItem[]>(
      '/evidence/validation/bulk',
      {
        method: 'PATCH',
        body: JSON.stringify({
          evidence_ids: evidenceIds,
          status,
          reason: reason || null,
        }),
      },
    )
  },

  verifyEvidenceAsSME: (
    evidenceId: string,
    submission: SMEVerificationSubmission,
  ) => (
    isPreviewMode
      ? Promise.reject(new ApiError('SME verification is unavailable in reviewer preview mode.', 403))
      : apiRequest<EvidenceItem>(
          `/evidence/${encodeURIComponent(evidenceId)}/sme-verification`,
          {
            method: 'PATCH',
            body: JSON.stringify(submission),
          },
        )
  ),

  getAssessmentConfiguration: () => (
    isPreviewMode
      ? Promise.resolve(
          structuredClone(
            previewAssessmentConfiguration,
          ),
        )
      : apiRequest<AssessmentConfiguration>(
          '/assessments/configuration',
        )
  ),

  getAssessmentAutofill: (smeId: string) => (
    isPreviewMode
      ? Promise.resolve<AssessmentAutofill>({
          sme_id: smeId,
          activity_description: previewSMEs.find((item) => item.sme_id === smeId)?.sector ?? 'Company activity requires review.',
          activity_description_source_ids: [],
          stage: null,
          stage_source_ids: [],
          funding_purpose: null,
          funding_purpose_source_ids: [],
          facts: {},
          fact_source_ids: {},
          financial_observations: [],
          readiness_observations: [],
          metric_contexts: [],
          sector_proposals: [],
          gaps: [],
        })
      : apiRequest<AssessmentAutofill>(
          `/assessments/autofill/${encodeURIComponent(smeId)}`,
        )
  ),

  listAssessmentProfileStatuses: () => {
    if (isPreviewMode) {
      return Promise.resolve<AssessmentProfileStatus[]>([])
    }
    return apiRequest<AssessmentProfileStatus[]>('/assessments/profiles')
  },

  getAssessmentProfileStatus: (smeId: string) => {
    if (isPreviewMode) {
      return Promise.reject(new ApiError('Profile governance requires the connected backend.', 501))
    }
    return apiRequest<AssessmentProfileStatus>(
      `/assessments/profiles/${encodeURIComponent(smeId)}/status`,
    )
  },

  prepareAssessment: (submission: AssessmentSubmission) => {
    if (isPreviewMode) {
      return Promise.reject(new ApiError('Profile preparation requires the connected backend.', 501))
    }
    return apiRequest<PreparedAssessment>('/assessments/prepare', {
      method: 'POST',
      body: JSON.stringify(submission),
    })
  },

  approveAssessmentProfile: (smeId: string, submission: AssessmentSubmission) => (
    apiRequest<StoredAssessmentProfileRevision>(
      `/assessments/profiles/${encodeURIComponent(smeId)}/approve`,
      { method: 'POST', body: JSON.stringify(submission) },
    )
  ),

  publishAssessmentProfile: (
    smeId: string,
    revisionId: string,
    expectedApplicationRevision: number,
  ) => apiRequest<AssessmentProfilePublication>(
    `/assessments/profiles/${encodeURIComponent(smeId)}/publish`,
    {
      method: 'POST',
      body: JSON.stringify({
        revision_id: revisionId,
        expected_application_revision: expectedApplicationRevision,
      }),
    },
  ),

  createAssessment: (
    request: CohortAssessmentRequest,
  ) => (
    isPreviewMode
      ? createPreviewAssessment(request)
      : apiRequest<AssessmentRunRecord>(
          '/assessments/compare',
          {
            method: 'POST',
            body: JSON.stringify(request),
          },
        )
  ),

  createAutomaticAssessment: (
    request: AutomaticCohortAssessmentRequest,
  ) => {
    if (isPreviewMode) {
      return Promise.reject(
        new ApiError(
          'Automatic comparison requires the connected backend.',
          501,
        ),
      )
    }

    return apiRequest<AssessmentRunRecord>(
      '/assessments/compare/automatic',
      {
        method: 'POST',
        body: JSON.stringify(request),
      },
    )
  },

  listAssessmentRuns: () => (
    isPreviewMode
      ? Promise.resolve(
          structuredClone(previewRuns)
        )
      : apiRequest<AssessmentRunSummary[]>(
          '/assessments/runs',
        )
  ),

  getAssessmentRun: (
    runId: string,
  ) => (
    isPreviewMode
      ? getPreviewAssessmentRun(runId)
      : apiRequest<AssessmentRunRecord>(
          `/assessments/runs/${
            encodeURIComponent(runId)
          }`,
        )
  ),

  deleteAssessmentRun: (
    runId: string,
    reason: string,
  ) => (
    isPreviewMode
      ? deletePreviewAssessmentRun(runId)
      : authenticatedRequest(
          `/assessments/runs/${encodeURIComponent(runId)}`,
          {
            method: 'DELETE',
            body: JSON.stringify({ reason }),
          },
        ).then(() => undefined)
  ),
}
