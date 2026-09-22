export type SME = {
  sme_id: string
  legal_name: string
  sector: string
  jurisdiction: string
}

export type SourceDocument = {
  document_id: string
  sme_id: string
  file_name: string
  mime_type: string
  sha256: string
  document_type: string
}

export type EvidenceItem = {
  evidence_id: string
  sme_id: string
  document_id: string
  indicator_id: string
  criterion_id: string | null
  raw_value: string
  normalized_value: string | number | boolean
  unit: string | null
  reporting_period: string | null
  scope: string | null
  source_locator: string
  source_excerpt: string | null
  extraction_method: string
  extractor_name: string
  extractor_version: string | null
  confidence: number | null
  validation_status: 'unvalidated' | 'accepted' | 'rejected'
}

export type DocumentProcessingStatus =
  | 'stored'
  | 'processing'
  | 'completed'
  | 'failed'

export type DocumentProcessingState = {
  document_id: string
  sme_id: string
  status: DocumentProcessingStatus
  attempt_count: number
  evidence_count: number
  deterministic_evidence_count: number
  intelligent_evidence_count: number
  rejected_intelligent_claim_count: number
  intelligent_provider_status: string | null
  failure_code: string | null
  failure_message: string | null
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

export type PageContentKind =
  | 'digital_text'
  | 'scanned_text'
  | 'table'
  | 'chart'
  | 'diagram'
  | 'image'
  | 'unknown'

export type ProcessingCapability =
  | 'native_reading'
  | 'ocr'
  | 'table_structure'
  | 'multimodal_interpretation'
  | 'visual_relevance_review'
  | 'human_review'

export type PageProcessingProfile = {
  page_number: number
  text_source: 'plain_text' | 'pdf_embedded' | 'ocr' | 'hybrid' | null
  content_kinds: PageContentKind[]
  required_capabilities: ProcessingCapability[]
  table_count: number
  visual_region_count: number
  reasons: string[]
}

export type DocumentProcessingManifest = {
  document_id: string
  total_pages: number
  execution_mode: 'immediate' | 'background'
  page_profiles: PageProcessingProfile[]
  batches: Array<{
    batch_id: string
    page_numbers: number[]
    status: 'planned' | 'processing' | 'completed' | 'failed'
    attempt_count: number
    maximum_attempts: number
    failure_message: string | null
  }>
  unreadable_pages: number[]
  table_page_count: number
  visual_page_count: number
  multimodal_page_count: number
  review_required_page_count: number
}

export type VisualRegionDecision = {
  page_number: number
  region_id: string
  relevance: 'relevant' | 'irrelevant' | 'uncertain'
  relevance_reason: string
  provider_status: 'skipped' | 'disabled' | 'succeeded' | 'failed'
  provider_summary: string | null
  evidence_ids: string[]
  rejected_claims: Array<{
    claim_index: number
    indicator_id: string
    reason: string
  }>
  issue: string | null
}

export type DocumentUnderstandingReport = {
  document_id: string
  processing_manifest: DocumentProcessingManifest | null
  deterministic_evidence_ids: string[]
  intelligent_evidence_ids: string[]
  context_evidence_ids: string[]
  intelligent_request_count: number
  visual_evidence_ids: string[]
  visual_understanding: {
    document_id: string
    decisions: VisualRegionDecision[]
  } | null
  rejected_intelligent_claim_count: number
  intelligent_provider_status: 'disabled' | 'succeeded' | 'failed'
  intelligent_provider_error: string | null
  evidence_ids: string[]
}

export type EvidenceCluster = {
  cluster_id: string
  sme_id: string
  indicator_id: string
  criterion_id: string | null
  unit: string | null
  reporting_period: string | null
  scope: string | null
  status:
    | 'single_source'
    | 'duplicate_extraction'
    | 'corroborated'
    | 'context_required'
    | 'conflict'
  candidate_values: Array<string | number | boolean>
  evidence_ids: string[]
  document_ids: string[]
  extraction_methods: string[]
  accepted_evidence_ids: string[]
  unvalidated_evidence_ids: string[]
  issues: string[]
}

export type ReconciliationReport = {
  sme_id: string
  clusters: EvidenceCluster[]
  rejected_evidence_ids: string[]
  unit_mismatch_indicator_ids: string[]
}

export type DocumentProcessingResult = {
  state: DocumentProcessingState
  report: DocumentUnderstandingReport | null
  evidence_items: EvidenceItem[]
  reconciliation: ReconciliationReport | null
}

export type DocumentUploadResponse = {
  document: SourceDocument
  storage_key: string
  processing_status: string
}

export type StructuredInvestmentRecord = {
  sme: SME
  documents: SourceDocument[]
  evidence_items: EvidenceItem[]
}

export type AssessmentRunSummary = {
  run_id: string
  cohort_id: string
  cohort_version: string
  requested_by: string
  sme_ids: string[]
  comparison_status: string
  created_at: string
}

export type RankedSME = {
  sme_id: string
  score: number
  rank: number
  distance_to_ideal: number
  distance_to_worst: number
}

export type AssessmentRule = {
  all_true: string[]
  any_true: string[]
  all_false: string[]
}

export type AssessmentCriterionPolicy = {
  criterion_id: string
  title: string
  output: 'green' | 'financial' | 'context'
  requirement: 'core' | 'conditional' | 'optional' | 'informational'
  module_ids: string[]
  indicator_ids: string[]
  when: AssessmentRule
  question: string
  evidence_routes: string[]
  assessment_note: string
}

export type AssessmentConfiguration = {
  assessment_policy: {
    policy_id: string
    version: string
    status: string
    description: string
    fact_questions: Record<string, string>
    criteria: AssessmentCriterionPolicy[]
  }
  normalization_policy: {
    policy_id: string
    version: string
    status: string
    weight_source: string
    minimum_coverage_ratio: number
    default_linguistic_scale: Record<string, {
      lower: number
      modal: number
      upper: number
    }>
    rules: Array<{
      criterion_id: string
      base_weight: number
      allow_linguistic: boolean
    }>
  }
}

export type AssessmentSubmission = {
  context: {
    sme_id: string
    activity_description: string
    sector?: string
    stage?: string
    funding_purpose?: string
    facts: Record<string, boolean | null>
  }
  responses: Array<{
    response_id: string
    sme_id: string
    criterion_id: string
    kind: 'linguistic'
    linguistic_value: string
    narrative?: string
    submitted_by: string
  }>
}

export type CohortAssessmentRequest = {
  run_id: string
  cohort_id: string
  version: string
  minimum_shared_criteria: number
  minimum_shared_weight_ratio: number
  submissions: AssessmentSubmission[]
}

export type SMECohortCoverage = {
  sme_id: string
  available_criterion_ids: string[]
  shared_criterion_ids: string[]
  excluded_criterion_ids: string[]
  shared_weight_ratio: number
}

export type MethodAgreement = {
  first_method: string
  second_method: string
  agreement_rate: number
}

export type SMERankingStability = {
  sme_id: string
  baseline_ranks: Record<string, number>
  first_place_rates: Record<string, number>
  mean_ranks: Record<string, number>
  best_ranks: Record<string, number>
  worst_ranks: Record<string, number>
}

export type AssessmentRunRecord = AssessmentRunSummary & {
  result: {
    preparations?: Array<{
      profile: {
        sme_id: string
        active_modules: string[]
        uncertain_modules: string[]
      }
      observations: {
        coverage: {
          applicable_count: number
          resolved_count: number
          document_supported_count: number
          coverage_ratio: number
        }
      }
      normalized_inputs: {
        readiness: string
        coverage_ratio: number
        issues: Array<{ criterion_id: string; code: string; message: string }>
      }
    }>
    comparable_topsis: {
      comparison_status?: string
      shared_criterion_ids: string[]
      coverage?: SMECohortCoverage[]
      topsis_result: {
        normalized_weights?: Record<string, number>
        ranking: RankedSME[]
      }
    }
    fuzzy_topsis: {
      ranking: RankedSME[]
      ranking_changed_from_crisp: boolean
    }
    electre_iii: {
      rank_levels: Array<{
        level: number
        sme_ids: string[]
        contains_preference_cycle: boolean
      }>
      incomparable_pairs: Array<[string, string]>
      pair_relations?: Array<{
        left_sme_id: string
        right_sme_id: string
        left_outranks_right: boolean
        right_outranks_left: boolean
        relation: string
      }>
    }
    robustness: {
      completed_scenarios: number
      rejected_scenarios?: number
      baseline_agreement?: MethodAgreement[]
      sme_stability?: SMERankingStability[]
      warnings: string[]
    } | null
    calibration?: {
      calibration_id: string
      version: string
      status: string
      statement: string
    } | null
  }
}
