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
  claim_nature: 'actual' | 'estimate' | 'target' | 'projected' | 'unspecified'
  entity_name: string | null
  facility_or_site: string | null
  project_name: string | null
  source_locator: string
  source_excerpt: string | null
  extraction_method: string
  extractor_name: string
  extractor_version: string | null
  confidence: number | null
  validation_status: 'unvalidated' | 'accepted' | 'rejected'
  sme_verification: SMEVerification
}

export type SMEVerificationStatus =
  | 'unreviewed'
  | 'confirmed'
  | 'correction_proposed'
  | 'not_applicable'

export type SMEVerification = {
  status: SMEVerificationStatus
  proposed_value: string | number | boolean | null
  proposed_unit: string | null
  proposed_reporting_period: string | null
  proposed_scope: string | null
  comment: string | null
  submitted_by: string | null
  submitted_at: string | null
}

export type SMEVerificationSubmission = Pick<
  SMEVerification,
  | 'status'
  | 'proposed_value'
  | 'proposed_unit'
  | 'proposed_reporting_period'
  | 'proposed_scope'
  | 'comment'
>

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
  company_policy_id: string | null
  company_policy_version: string | null
  intelligence_claims: GroundedIntelligenceClaim[]
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

export type GroundedIntelligenceClaim = {
  claim_id: string
  claim_type:
    | 'document_profile'
    | 'company_profile'
    | 'sector_activity_proposal'
    | 'readiness_observation'
    | 'unmapped_material'
  field_id: string
  value: string
  source_locator: string
  source_quote: string
  related_ids: string[]
  model_rationale: string | null
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
  application: SMEApplication
}

export type SystemCapabilities = {
  native_pdf_reading: boolean
  ocr_routing: boolean
  table_extraction: boolean
  semantic_provider_configured: boolean
  visual_provider_configured: boolean
  identity_admin_configured: boolean
  human_validation_required: boolean
}

export type ApplicationRole =
  | 'admin'
  | 'reviewer'
  | 'expert'
  | 'investor'
  | 'sme_user'

export type ApplicationStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'changes_requested'
  | 'approved'
  | 'published'
  | 'withdrawn'
  | 'archived'

export type SMEApplication = {
  application_id: string
  sme_id: string
  status: ApplicationStatus
  revision: number
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

export type SMEUpdateResponse = {
  sme: SME
  application: SMEApplication
}

export type DocumentDeletionResponse = {
  document_id: string
  application: SMEApplication
}

export type ManagedUser = {
  user_id: string
  email: string
  role: ApplicationRole | null
  sme_ids: string[]
  invited_at: string | null
  last_sign_in_at: string | null
}

export type SemanticProviderConnection = {
  provider_name: string
  provider_version: string
  model_name: string
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
  dimension: 'environmental_performance' | 'financial_health' | 'investment_case' | 'readiness_context'
  scoring_role: 'performance_criterion' | 'separate_financial_assessment' | 'non_scoring_context'
  requires_evidence_confirmation: boolean
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
    green_score_method: 'weighted_centroid'
    applicability_weight_rule: 'renormalize_applicable'
    incomplete_score_rule: 'withhold_below_minimum_otherwise_provisional'
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
  financial_policy: {
    policy_id: string
    version: string
    status: string
    calibration_status: string
    metrics: FinancialMetricDefinition[]
  }
  readiness_specification: {
    specification_id: string
    version: string
    calibration_status: string
    domains: Array<{ domain_id: string; title: string; description: string }>
    factors: ReadinessFactorDefinition[]
  }
  metric_catalog: {
    catalog_id: string
    version: string
    metrics: MetricDefinition[]
  }
  evidence_strength_policy: EvidenceStrengthPolicy
}

export type AssessmentAutofill = {
  sme_id: string
  activity_description: string
  activity_description_source_ids: string[]
  stage: string | null
  stage_source_ids: string[]
  funding_purpose: string | null
  funding_purpose_source_ids: string[]
  facts: Record<string, boolean>
  fact_source_ids: Record<string, string[]>
  financial_observations: FinancialObservation[]
  readiness_observations: Array<{
    observation_id: string
    sme_id: string
    factor_id: string
    state: 'enabling_evidence' | 'constraining_evidence' | 'mixed_evidence' | 'unknown' | 'not_applicable' | 'needs_review'
    source_ids: string[]
    narrative?: string
  }>
  metric_contexts: Array<{
    context_id: string
    sme_id: string
    indicator_id: string
    reporting_period?: string
    operational_scope?: string
    denominator_value?: number
    denominator_unit?: string
    baseline_value?: number
    benchmark_value?: number
    target_value?: number
    reference_unit?: string
    source_ids: string[]
    narrative?: string
  }>
  sector_proposals: Array<{ sector_id: string; source_ids: string[] }>
  gaps: Array<{ code: string; field_id: string; message: string; source_ids: string[] }>
}

export type FinancialMetricDefinition = {
  metric_id: string
  title: string
  group: 'business_health' | 'investment_case'
  importance: 'core' | 'supporting'
  role: 'source_input' | 'derived_indicator' | 'investment_input'
  direction: 'benefit' | 'cost' | 'context_only'
  allowed_units: string[]
  requires_reporting_period: boolean
  requires_comparison_basis: boolean
  calculation_method?: 'ratio' | 'ratio_percentage' | 'growth_percentage' | 'simple_payback_years'
  input_metric_ids: string[]
  description: string
}

export type EvidenceStrengthPolicy = {
  policy_id: string
  version: string
  status: string
  calibration_status: string
  missing_information_rule: 'unknown_not_zero'
  performance_separation: true
  source_classes: Array<{
    source_class: 'audited_or_regulatory' | 'third_party_transactional' | 'internally_generated' | 'self_declared' | 'model_inferred'
    title: string
    description: string
    requires_human_acceptance: boolean
  }>
  dimension_requirements: Array<{
    dimension_id: 'environmental_performance' | 'financial_health' | 'investment_case' | 'readiness_context'
    required_attributes: string[]
    notes: string
  }>
  bands: Array<'strong' | 'adequate' | 'limited' | 'insufficient' | 'conflicting'>
  band_rules: Array<{
    band: 'strong' | 'adequate' | 'limited' | 'insufficient' | 'conflicting'
    condition: 'conflict' | 'no_confirmed_sources' | 'missing_attributes_or_weak_only' | 'complete_internal_support' | 'complete_independent_support'
    description: string
  }>
}

export type FinancialObservation = {
  observation_id: string
  sme_id: string
  metric_id: string
  state: 'reported' | 'unknown' | 'not_measured' | 'not_applicable' | 'needs_review'
  value?: number
  unit?: string
  reporting_period?: string
  comparison_basis?: string
  source_ids: string[]
  narrative?: string
}

export type FinancialSubmissionStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'changes_requested'
  | 'approved'

export type FinancialSubmission = {
  submission_id: string
  sme_id: string
  status: FinancialSubmissionStatus
  revision: number
  observations: FinancialObservation[]
  submitted_by: string | null
  reviewed_by: string | null
  review_note: string | null
  created_at: string
  updated_at: string
  submitted_at: string | null
  reviewed_at: string | null
}

export type FinancialPolicy = {
  policy_id: string
  version: string
  status: string
  calibration_status: string
  metrics: FinancialMetricDefinition[]
}

export type ReadinessFactorDefinition = {
  factor_id: string
  domain_id: string
  title: string
  definition: string
  source_status: string
}

export type ReadinessObservation = {
  observation_id: string
  sme_id: string
  factor_id: string
  state: 'enabling_evidence' | 'constraining_evidence' | 'mixed_evidence' | 'unknown' | 'not_applicable' | 'needs_review'
  source_ids: string[]
  narrative?: string
}

export type MetricDefinition = {
  indicator_id: string
  criterion_id: string
  name: string
  dimension: 'environmental_performance' | 'financial_health' | 'investment_case'
  value_nature: 'actual_flow' | 'point_in_time' | 'ratio' | 'forecast' | 'reported_or_derived' | 'activity_denominator'
  direction: 'benefit' | 'cost' | 'context_only'
  assessment_use: 'direct_ratio' | 'requires_comparison_context' | 'evidence_only'
  comparison_requirements: string[]
}

export type MetricComparisonContext = {
  context_id: string
  sme_id: string
  indicator_id: string
  reporting_period?: string
  operational_scope?: string
  denominator_value?: number
  denominator_unit?: string
  baseline_value?: number
  benchmark_value?: number
  target_value?: number
  reference_unit?: string
  source_ids: string[]
  narrative?: string
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
    supporting_evidence_ids?: string[]
    submitted_by: string
  }>
  financial_observations: FinancialObservation[]
  readiness_observations: ReadinessObservation[]
  metric_contexts: MetricComparisonContext[]
}

export type AssessmentProfileStatus = {
  sme_id: string
  legal_name: string
  sector: string
  application_status: ApplicationStatus
  application_revision: number
  lifecycle_status: 'not_prepared' | 'approved' | 'published' | 'approved_changes' | 'reapproval_required' | 'published_outdated'
  latest_revision_id: string | null
  latest_profile_version: number | null
  latest_approved_at: string | null
  latest_policy_current: boolean
  active_publication_id: string | null
  active_revision_id: string | null
  published_at: string | null
  active_policy_current: boolean
  comparison_eligible: boolean
}

export type PreparedAssessment = {
  profile: {
    sme_id: string
    active_modules: string[]
    uncertain_modules: string[]
    decisions: Array<{
      criterion_id: string
      title: string
      output: 'green' | 'financial' | 'context'
      scoring_role: string
      requirement: 'core' | 'conditional' | 'optional' | 'informational'
      status: 'applicable' | 'not_applicable' | 'uncertain'
      missing_facts: string[]
      reason: string
    }>
    follow_ups: Array<{ request_id: string; question: string; criterion_ids: string[] }>
  }
  observations: {
    observations: Array<{
      criterion_id: string
      status: string
      linguistic_value: string | null
      evidence_ids: string[]
      issues: string[]
    }>
    coverage: {
      applicable_count: number
      resolved_count: number
      document_supported_count: number
      coverage_ratio: number
    }
  }
  green_score: {
    status: 'final' | 'provisional' | 'blocked'
    score: number | null
    coverage_ratio: number
    issues: string[]
    criteria: Array<{
      criterion_id: string
      title: string
      applicability: 'applicable' | 'not_applicable' | 'uncertain'
      resolved: boolean
      evidence_ids: string[]
      issues: string[]
    }>
  } | null
  financial_assessment: {
    status: string
    core_coverage_ratio: number
    metrics: Array<{ metric_id: string; state: string; value: number | null }>
  }
  readiness_profile: {
    calibration_status: string
    causal_results_available: boolean
    factors: Array<{ factor_id: string; state: string; interpretation: string }>
  }
  performance_context: {
    metrics: Array<{ indicator_id: string; state: string; issues: string[] }>
  }
  evidence_strength: {
    dimensions: Array<{ dimension_id: string; band: string; issues: string[] }>
  }
  normalized_inputs: { readiness: string; coverage_ratio: number; issues: Array<{ criterion_id: string; code: string; message: string }> }
  activity_fact_evidence_ids: Record<string, string[]>
}

export type StoredAssessmentProfileRevision = {
  revision_id: string
  sme_id: string
  profile_version: number
  approved_at: string
}

export type AssessmentProfilePublication = {
  publication_id: string
  sme_id: string
  revision_id: string
  active: boolean
  published_at: string
}

export type CohortAssessmentRequest = {
  run_id: string
  cohort_id: string
  version: string
  minimum_shared_criteria: number
  minimum_shared_weight_ratio: number
  submissions: AssessmentSubmission[]
}

export type AutomaticCohortAssessmentRequest = {
  run_id: string
  cohort_id: string
  version: string
  sme_ids: string[]
  minimum_shared_criteria: number
  minimum_shared_weight_ratio: number
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
      green_score?: {
        sme_id: string
        status: 'final' | 'provisional' | 'blocked'
        score: number | null
        coverage_ratio: number
        resolved_weight: number
        method: 'weighted_centroid'
        scale_min: number
        scale_max: number
        normalization_policy_id: string
        normalization_policy_version: string
        weight_source: string
        criteria: Array<{
          criterion_id: string
          title: string
          applicability: 'applicable' | 'not_applicable' | 'uncertain'
          resolved: boolean
          normalized_score: number | null
          base_weight: number
          applicable_weight: number
          scoring_weight: number
          weighted_contribution: number | null
          source_status: string | null
          response_ids: string[]
          evidence_ids: string[]
          source_indicator_ids: string[]
          issues: string[]
        }>
        issues: string[]
      } | null
      financial_assessment: {
        status: string
        core_coverage_ratio: number
        calibration_status: string
        aggregate_score: null
        metrics: Array<{
          metric_id: string
          title: string
          group: string
          importance: string
          role: 'source_input' | 'derived_indicator' | 'investment_input'
          direction: 'benefit' | 'cost' | 'context_only'
          state: string
          origin: 'unknown' | 'reported' | 'extracted' | 'calculated' | 'reported_and_calculated'
          value: number | null
          unit: string | null
          reporting_period: string | null
          issues: string[]
          calculation_method: string | null
          calculation_formula: string | null
          calculation_input_metric_ids: string[]
        }>
        derived_indicators: Array<{
          indicator_id: string
          value: number
          unit: string
          source_metric_ids: string[]
          source_ids: string[]
          calculation_method: string
          formula: string
          input_values: Record<string, number>
          interpretation: string
        }>
      }
      readiness_profile: {
        calibration_status: string
        causal_results_available: boolean
        factors: Array<{
          factor_id: string
          domain_id: string
          state: string
          narrative: string | null
          interpretation: string
          downstream_influences: Array<{
            target_factor_id: string
            influence_strength: number
          }>
        }>
      }
      performance_context: {
        metric_catalog_id: string
        metric_catalog_version: string
        metrics: Array<{
          indicator_id: string
          metric_name: string
          state: string
          measurement_value: number | null
          measurement_unit: string | null
          intensity_value: number | null
          intensity_unit: string | null
          missing_requirements: string[]
          issues: string[]
        }>
      }
      evidence_strength: {
        policy_id: string
        policy_version: string
        calibration_status: string
        performance_separation: true
        dimensions: Array<{
          dimension_id: 'environmental_performance' | 'financial_health' | 'investment_case' | 'readiness_context'
          band: 'strong' | 'adequate' | 'limited' | 'insufficient' | 'conflicting'
          sources: Array<{
            source_id: string
            source_class: string
            confirmed: boolean
            classification_basis: string
          }>
          missing_attributes: string[]
          issues: string[]
          rationale: string
        }>
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
