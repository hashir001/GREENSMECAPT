import type {
  AssessmentConfiguration,
  AssessmentRunRecord,
  AssessmentRunSummary,
  ApplicationStatus,
  CohortAssessmentRequest,
  DocumentProcessingManifest,
  DocumentProcessingResult,
  DocumentProcessingState,
  DocumentUnderstandingReport,
  DocumentUploadResponse,
  EvidenceItem,
  SME,
  SMEApplication,
  SMEUpdateResponse,
  StructuredInvestmentRecord,
} from '../types/api'

export const previewSMEs: SME[] = [
  { sme_id: 'sme_ecopack', legal_name: 'EcoPack Manufacturing', sector: 'Sustainable packaging', jurisdiction: 'United Arab Emirates' },
  { sme_id: 'sme_solarworks', legal_name: 'SolarWorks MENA', sector: 'Distributed clean energy', jurisdiction: 'United Arab Emirates' },
  { sme_id: 'sme_greenforge', legal_name: 'GreenForge Industries', sector: 'Low-carbon manufacturing', jurisdiction: 'United Arab Emirates' },
  { sme_id: 'sme_circularloop', legal_name: 'CircularLoop Services', sector: 'Resource recovery', jurisdiction: 'United Arab Emirates' },
]

export const previewRuns: AssessmentRunSummary[] = [
  {
    run_id: 'run_green_portfolio_01', cohort_id: 'UAE Green SME Cohort', cohort_version: '1.0',
    requested_by: 'reviewer_preview', sme_ids: ['sme_solarworks', 'sme_ecopack', 'sme_greenforge'],
    comparison_status: 'comparable', created_at: '2026-09-17T14:30:00Z',
  },
  {
    run_id: 'run_circular_economy_01', cohort_id: 'Circular Economy Review', cohort_version: '1.0',
    requested_by: 'reviewer_preview', sme_ids: ['sme_ecopack', 'sme_circularloop'],
    comparison_status: 'comparable', created_at: '2026-09-15T10:15:00Z',
  },
]

export const previewLatestRun: AssessmentRunRecord = {
  ...previewRuns[0],
  result: {
    comparable_topsis: {
      shared_criterion_ids: ['green_contribution', 'customer_environmental_effect', 'transition_execution'],
      topsis_result: {
        normalized_weights: {
          'normalized:green_contribution': 0.44,
          'normalized:customer_environmental_effect': 0.32,
          'normalized:transition_execution': 0.24,
        },
        ranking: [
          { sme_id: 'sme_solarworks', score: 0.86, rank: 1, distance_to_ideal: 0.08, distance_to_worst: 0.49 },
          { sme_id: 'sme_ecopack', score: 0.72, rank: 2, distance_to_ideal: 0.17, distance_to_worst: 0.44 },
          { sme_id: 'sme_greenforge', score: 0.58, rank: 3, distance_to_ideal: 0.29, distance_to_worst: 0.40 },
        ],
      },
    },
    fuzzy_topsis: {
      ranking: [
        { sme_id: 'sme_solarworks', score: 0.83, rank: 1, distance_to_ideal: 0.11, distance_to_worst: 0.53 },
        { sme_id: 'sme_ecopack', score: 0.70, rank: 2, distance_to_ideal: 0.19, distance_to_worst: 0.45 },
        { sme_id: 'sme_greenforge', score: 0.56, rank: 3, distance_to_ideal: 0.31, distance_to_worst: 0.40 },
      ],
      ranking_changed_from_crisp: false,
    },
    electre_iii: {
      rank_levels: [
        { level: 1, sme_ids: ['sme_solarworks'], contains_preference_cycle: false },
        { level: 2, sme_ids: ['sme_ecopack'], contains_preference_cycle: false },
        { level: 3, sme_ids: ['sme_greenforge'], contains_preference_cycle: false },
      ],
      incomparable_pairs: [['sme_ecopack', 'sme_greenforge']],
    },
    robustness: {
      completed_scenarios: 200,
      rejected_scenarios: 0,
      baseline_agreement: [
        { first_method: 'topsis', second_method: 'fuzzy_topsis', agreement_rate: 1 },
        { first_method: 'topsis', second_method: 'electre_iii', agreement_rate: 0.83 },
        { first_method: 'fuzzy_topsis', second_method: 'electre_iii', agreement_rate: 0.83 },
      ],
      sme_stability: [
        { sme_id: 'sme_solarworks', baseline_ranks: { topsis: 1, fuzzy_topsis: 1, electre_iii: 1 }, first_place_rates: { topsis: 0.92, fuzzy_topsis: 0.88, electre_iii: 0.84 }, mean_ranks: { topsis: 1.08, fuzzy_topsis: 1.12, electre_iii: 1.18 }, best_ranks: { topsis: 1, fuzzy_topsis: 1, electre_iii: 1 }, worst_ranks: { topsis: 2, fuzzy_topsis: 2, electre_iii: 2 } },
        { sme_id: 'sme_ecopack', baseline_ranks: { topsis: 2, fuzzy_topsis: 2, electre_iii: 2 }, first_place_rates: { topsis: 0.08, fuzzy_topsis: 0.12, electre_iii: 0.12 }, mean_ranks: { topsis: 1.94, fuzzy_topsis: 1.91, electre_iii: 2.01 }, best_ranks: { topsis: 1, fuzzy_topsis: 1, electre_iii: 1 }, worst_ranks: { topsis: 3, fuzzy_topsis: 3, electre_iii: 3 } },
        { sme_id: 'sme_greenforge', baseline_ranks: { topsis: 3, fuzzy_topsis: 3, electre_iii: 3 }, first_place_rates: { topsis: 0, fuzzy_topsis: 0, electre_iii: 0.04 }, mean_ranks: { topsis: 2.98, fuzzy_topsis: 2.97, electre_iii: 2.81 }, best_ranks: { topsis: 2, fuzzy_topsis: 2, electre_iii: 1 }, worst_ranks: { topsis: 3, fuzzy_topsis: 3, electre_iii: 3 } },
      ],
      warnings: [],
    },
    calibration: {
      calibration_id: 'greensmecapt_mcdm_development', version: '0.1.0', status: 'development',
      statement: 'Transparent model-informed starting values pending structured expert calibration.',
    },
  },
}

const factQuestions: Record<string, string> = {
  manufactures_or_processes: 'Do you manufacture or process physical products?',
  burns_fuel_on_site: 'Do your operations burn fuel on site?',
  operates_vehicle_fleet: 'Does the company operate a vehicle fleet?',
  operates_facility: 'Does the company operate an office, workshop, plant or other facility?',
  uses_cloud_services: 'Does the business use cloud or data-centre services?',
  handles_materials_or_waste: 'Are physical materials or waste meaningful to operations?',
  provides_clean_energy: 'Do you deliver clean-energy generation, equipment or services?',
  provides_circular_services: 'Do you repair, reuse, recycle or recover products or materials?',
  works_on_buildings: 'Do you construct, retrofit or operate buildings?',
  works_in_agriculture_food_land: 'Do you farm, process food or manage land?',
  provides_digital_services: 'Does the company provide software or professional services?',
  offers_environmental_solution: 'Is reducing environmental impact an intended function of the offering?',
  operates_retail_or_hospitality: 'Do you operate retail, restaurant or hospitality premises?',
  plans_operational_transition: 'Does the application include an environmental improvement project?',
}

const scoredCriteria = [
  ['green_contribution', 'Nature and basis of green contribution', 'What environmental benefit does the activity provide, and what evidence supports it?', 'core'],
  ['direct_operational_emissions', 'Direct operational emissions', 'How well does the company measure and manage fuel or process emissions?', 'conditional'],
  ['purchased_energy_management', 'Purchased energy management', 'How well does the company obtain, monitor and manage electricity or cloud services?', 'conditional'],
  ['resource_use_and_recovery', 'Material use, waste and recovery', 'How effectively are material use, waste and recovery managed?', 'conditional'],
  ['customer_environmental_effect', 'Customer environmental effect', 'How strong and demonstrated is the environmental effect delivered to customers?', 'conditional'],
  ['transition_execution', 'Operational transition feasibility', 'How credible are the budget, delivery plan, baseline and schedule?', 'conditional'],
] as const

export const previewAssessmentConfiguration: AssessmentConfiguration = {
  assessment_policy: {
    policy_id: 'greensmecapt_activity_profiles', version: '0.3.0', status: 'development',
    description: 'Activity-led routing for proportionate green SME assessment.', fact_questions: factQuestions,
    criteria: scoredCriteria.map(([criterion_id, title, question, requirement]) => ({
      criterion_id, title, question, requirement, output: 'green', module_ids: [], indicator_ids: [],
      when: { all_true: [], any_true: [], all_false: [] }, evidence_routes: ['reviewed_response'],
      assessment_note: 'The backend decides applicability and preserves the response basis.',
    })),
  },
  normalization_policy: {
    policy_id: 'greensmecapt_normalization', version: '0.3.0', status: 'development',
    weight_source: 'model_informed_development_weights_pending_expert_calibration', minimum_coverage_ratio: 0.6,
    default_linguistic_scale: {
      very_low: { lower: 0, modal: 0, upper: 0.25 }, low: { lower: 0, modal: 0.25, upper: 0.5 },
      medium: { lower: 0.25, modal: 0.5, upper: 0.75 }, high: { lower: 0.5, modal: 0.75, upper: 1 },
      very_high: { lower: 0.75, modal: 1, upper: 1 },
    },
    rules: scoredCriteria.map(([criterion_id], index) => ({
      criterion_id, base_weight: [0.24, 0.13, 0.12, 0.16, 0.22, 0.13][index], allow_linguistic: true,
    })),
  },
  financial_policy: {
    policy_id: 'greensmecapt_financial_assessment', version: '1.0.0', status: 'development',
    calibration_status: 'requires_financial_calibration',
    metrics: [
      ['roa_percentage', 'Return on assets', 'business_health', 'core', ['percent'], true],
      ['revenue_growth_percentage', 'Revenue growth', 'business_health', 'core', ['percent'], true],
      ['current_ratio', 'Current ratio', 'business_health', 'core', ['ratio'], true],
      ['operating_cash_flow', 'Operating cash flow', 'business_health', 'supporting', ['aed'], true],
      ['debt_to_assets_percentage', 'Debt to assets', 'business_health', 'supporting', ['percent'], true],
      ['requested_amount', 'Requested amount', 'investment_case', 'supporting', ['aed'], false],
      ['project_cost', 'Project cost', 'investment_case', 'supporting', ['aed'], false],
      ['expected_annual_savings', 'Expected annual savings', 'investment_case', 'supporting', ['aed_per_year'], false],
    ].map(([metric_id, title, group, importance, allowed_units, requires_reporting_period]) => ({
      metric_id: String(metric_id), title: String(title),
      group: group as 'business_health' | 'investment_case',
      importance: importance as 'core' | 'supporting',
      allowed_units: allowed_units as string[],
      requires_reporting_period: Boolean(requires_reporting_period),
      description: 'Evidence-grounded financial input; no provisional threshold is applied.',
    })),
  },
  readiness_specification: {
    specification_id: 'greensmecapt_readiness_subdrivers', version: '1.0.0',
    calibration_status: 'requires_expert_calibration',
    domains: [
      ['internal_factors', 'Internal Factors'], ['government_and_institutional_support', 'Government & Institutional Support'],
      ['market_conditions', 'Market Conditions'], ['access_to_finance', 'Access to Finance'],
    ].map(([domain_id, title]) => ({ domain_id, title, description: title })),
    factors: [
      ['leadership_and_organisational_commitment', 'internal_factors', 'Leadership & organizational commitment'],
      ['workforce_technical_capability_and_training', 'internal_factors', 'Workforce / technical capability & training'],
      ['digital_data_and_ai_readiness', 'internal_factors', 'Digital, data & AI readiness'],
      ['regulation_compliance_standards_and_certifications', 'government_and_institutional_support', 'Regulation, compliance & standards/certifications'],
      ['institutional_support_and_implementation_guidance', 'government_and_institutional_support', 'Institutional support & implementation guidance'],
      ['customer_buyer_demand_competitiveness_and_reputation', 'market_conditions', 'Customer/buyer demand, competitiveness & reputation'],
      ['green_finance_availability_grants_and_incentives', 'access_to_finance', 'Green finance availability, grants & incentives'],
    ].map(([factor_id, domain_id, title]) => ({ factor_id, domain_id, title, definition: title, source_status: 'research_synthesized' })),
  },
  metric_catalog: {
    catalog_id: 'greensmecapt_environmental_metrics', version: '1.2.0',
    metrics: [
      ['renewable_energy_percentage', 'renewable_energy', 'Renewable energy share', 'direct_ratio'],
      ['electricity_consumption_kwh', 'energy_efficiency', 'Electricity consumption', 'requires_comparison_context'],
      ['water_consumption_m3', 'water_management', 'Water consumption', 'requires_comparison_context'],
      ['total_ghg_emissions_tco2e', 'emissions_management', 'Total greenhouse-gas emissions', 'requires_comparison_context'],
      ['waste_diversion_percentage', 'waste_management', 'Waste diverted from disposal', 'requires_comparison_context'],
      ['total_waste_generated_kg', 'waste_management', 'Total waste generated', 'requires_comparison_context'],
    ].map(([indicator_id, criterion_id, name, assessment_use]) => ({
      indicator_id, criterion_id, name,
      assessment_use: assessment_use as 'direct_ratio' | 'requires_comparison_context',
      comparison_requirements: ['reporting_period', 'operational_scope'],
    })),
  },
}

const now = () => new Date().toISOString()

const previewApplications: Record<string, SMEApplication> = Object.fromEntries(
  previewSMEs.map((sme) => [
    sme.sme_id,
    {
      application_id: `preview_application_${sme.sme_id}`,
      sme_id: sme.sme_id,
      status: 'under_review',
      revision: 1,
      created_by: 'preview_admin',
      updated_by: 'preview_reviewer',
      created_at: now(),
      updated_at: now(),
    },
  ]),
)

function evidence(
  values: Partial<EvidenceItem> & Pick<EvidenceItem, 'evidence_id' | 'sme_id' | 'document_id' | 'indicator_id' | 'raw_value' | 'normalized_value'>,
): EvidenceItem {
  return {
    criterion_id: 'environmental_performance', unit: 'percent', reporting_period: '2025',
    scope: 'company operations', source_locator: 'page 1, paragraph 2', source_excerpt: null,
    extraction_method: 'semantic_metric_extraction', extractor_name: 'greensmecapt_semantic_extractor',
    extractor_version: '1.0.0', confidence: 0.94, validation_status: 'unvalidated', ...values,
  }
}

const previewRecords: Record<string, StructuredInvestmentRecord> = {
  sme_ecopack: {
    sme: previewSMEs[0],
    documents: [
      { document_id: 'doc_ecopack_report', sme_id: 'sme_ecopack', file_name: 'ecopack-sustainability-report-2025.pdf', mime_type: 'application/pdf', sha256: 'a'.repeat(64), document_type: 'sustainability_report' },
      { document_id: 'doc_ecopack_utility', sme_id: 'sme_ecopack', file_name: 'electricity-statement-q4.pdf', mime_type: 'application/pdf', sha256: 'b'.repeat(64), document_type: 'utility_bill' },
    ],
    evidence_items: [
      evidence({ evidence_id: 'evidence_ecopack_renewable', sme_id: 'sme_ecopack', document_id: 'doc_ecopack_report', indicator_id: 'renewable_energy_percentage', raw_value: '72 percent', normalized_value: 72, source_locator: 'page 6, table 2, row 4', source_excerpt: 'Renewable energy share reached 72 percent in 2025.', confidence: 0.97 }),
      evidence({ evidence_id: 'evidence_ecopack_waste', sme_id: 'sme_ecopack', document_id: 'doc_ecopack_report', indicator_id: 'waste_diversion_rate', raw_value: '64%', normalized_value: 64, source_locator: 'page 9, waste performance table', source_excerpt: 'Waste diversion rate | 2025 | 64%', confidence: 0.92 }),
      evidence({ evidence_id: 'evidence_ecopack_renewable_bill', sme_id: 'sme_ecopack', document_id: 'doc_ecopack_utility', indicator_id: 'renewable_energy_percentage', raw_value: '68%', normalized_value: 68, reporting_period: '2025', source_locator: 'page 2, energy mix summary', source_excerpt: 'Renewable supply: 68% of billed electricity.', confidence: 0.89 }),
    ],
  },
  sme_solarworks: {
    sme: previewSMEs[1],
    documents: [{ document_id: 'doc_solarworks_impact', sme_id: 'sme_solarworks', file_name: 'verified-impact-summary.pdf', mime_type: 'application/pdf', sha256: 'c'.repeat(64), document_type: 'sustainability_report' }],
    evidence_items: [evidence({ evidence_id: 'evidence_solarworks_renewable', sme_id: 'sme_solarworks', document_id: 'doc_solarworks_impact', indicator_id: 'renewable_energy_percentage', raw_value: '96%', normalized_value: 96, source_locator: 'page 3, impact summary', source_excerpt: '96% of delivered generation was renewable.', validation_status: 'accepted', confidence: 0.98 })],
  },
  sme_greenforge: {
    sme: previewSMEs[2],
    documents: [{ document_id: 'doc_greenforge_statement', sme_id: 'sme_greenforge', file_name: 'environmental-statement.txt', mime_type: 'text/plain', sha256: 'd'.repeat(64), document_type: 'sustainability_report' }],
    evidence_items: [],
  },
  sme_circularloop: { sme: previewSMEs[3], documents: [], evidence_items: [] },
}

const previewProcessing: Record<string, DocumentProcessingResult> = {}

function processingState(documentId: string, smeId: string, status: DocumentProcessingState['status'], evidenceCount = 0): DocumentProcessingState {
  const timestamp = now()
  return {
    document_id: documentId, sme_id: smeId, status, attempt_count: status === 'stored' ? 0 : 1,
    evidence_count: evidenceCount, deterministic_evidence_count: evidenceCount, intelligent_evidence_count: 0,
    rejected_intelligent_claim_count: 0, intelligent_provider_status: 'disabled', failure_code: null,
    failure_message: null, started_at: status === 'stored' ? null : timestamp,
    completed_at: status === 'completed' ? timestamp : null, updated_at: timestamp,
  }
}

function previewManifest(
  documentId: string,
  mimeType: string,
  totalPages: number,
): DocumentProcessingManifest {
  const scanned = mimeType.startsWith('image/')
  const pdf = mimeType === 'application/pdf'
  const batches = Array.from(
    { length: Math.ceil(totalPages / 5) },
    (_, index) => {
      const firstPage = index * 5 + 1
      return {
        batch_id: `${documentId}_batch_${index + 1}`,
        page_numbers: Array.from(
          { length: Math.min(5, totalPages - firstPage + 1) },
          (__, offset) => firstPage + offset,
        ),
        status: 'completed' as const,
        attempt_count: 1,
        maximum_attempts: 3,
        failure_message: null,
      }
    },
  )

  return {
    document_id: documentId,
    total_pages: totalPages,
    execution_mode: totalPages > 10 ? 'background' : 'immediate',
    page_profiles: Array.from({ length: totalPages }, (_, index) => ({
      page_number: index + 1,
      text_source: scanned ? 'ocr' : pdf ? 'pdf_embedded' : 'plain_text',
      content_kinds: [
        scanned ? 'scanned_text' as const : 'digital_text' as const,
        ...(pdf && (index + 1) % 4 === 0 ? ['table' as const] : []),
        ...(pdf && (index + 1) % 6 === 0 ? ['chart' as const] : []),
      ],
      required_capabilities: [
        scanned ? 'ocr' as const : 'native_reading' as const,
        ...(pdf && (index + 1) % 4 === 0
          ? ['table_structure' as const]
          : []),
        ...(pdf && (index + 1) % 6 === 0
          ? ['multimodal_interpretation' as const]
          : []),
      ],
      table_count: pdf && (index + 1) % 4 === 0 ? 1 : 0,
      visual_region_count: pdf && (index + 1) % 6 === 0 ? 1 : 0,
      reasons: [
        scanned
          ? 'Page text was recovered through OCR.'
          : pdf
            ? 'Embedded PDF text was recovered directly.'
            : 'Born-digital text was decoded directly.',
      ],
    })),
    batches,
    unreadable_pages: [],
    table_page_count: pdf ? Math.floor(totalPages / 4) : 0,
    visual_page_count: pdf ? Math.floor(totalPages / 6) : 0,
    multimodal_page_count: pdf ? Math.floor(totalPages / 6) : 0,
    review_required_page_count: 0,
  }
}

function previewReport(
  document: StructuredInvestmentRecord['documents'][number],
  evidenceIds: string[],
): DocumentUnderstandingReport {
  const totalPages = document.mime_type === 'application/pdf' ? 14 : 1
  const manifest = previewManifest(
    document.document_id,
    document.mime_type,
    totalPages,
  )
  const decisions = manifest.page_profiles
    .filter((profile) => profile.visual_region_count > 0)
    .map((profile) => ({
      page_number: profile.page_number,
      region_id: `page_${profile.page_number}_chart_1`,
      relevance: 'relevant' as const,
      relevance_reason: 'The chart is adjacent to environmental performance data.',
      provider_status: 'disabled' as const,
      provider_summary: null,
      evidence_ids: [],
      rejected_claims: [],
      issue: 'Visual provider is not configured in presentation preview.',
    }))

  return {
    document_id: document.document_id,
    processing_manifest: manifest,
    deterministic_evidence_ids: evidenceIds,
    intelligent_evidence_ids: [],
    context_evidence_ids: [],
    intelligent_request_count: 0,
    visual_evidence_ids: [],
    visual_understanding: decisions.length
      ? { document_id: document.document_id, decisions }
      : null,
    rejected_intelligent_claim_count: 0,
    intelligent_provider_status: 'disabled',
    intelligent_provider_error: null,
    evidence_ids: evidenceIds,
  }
}

function clone<T>(value: T): T {
  return structuredClone(value)
}

function requirePreviewRecord(smeId: string): StructuredInvestmentRecord {
  const record = previewRecords[smeId]
  if (!record) throw new Error(`SME ${smeId} was not found.`)
  return record
}

export async function createPreviewSME(sme: SME): Promise<SME> {
  if (previewRecords[sme.sme_id]) {
    throw new Error(`SME ${sme.sme_id} already exists.`)
  }

  previewSMEs.push(sme)
  previewRecords[sme.sme_id] = {
    sme,
    documents: [],
    evidence_items: [],
  }
  previewApplications[sme.sme_id] = {
    application_id: `preview_application_${sme.sme_id}`,
    sme_id: sme.sme_id,
    status: 'draft',
    revision: 1,
    created_by: 'preview_user',
    updated_by: 'preview_user',
    created_at: now(),
    updated_at: now(),
  }
  return clone(sme)
}

export async function getPreviewApplication(
  smeId: string,
): Promise<SMEApplication> {
  requirePreviewRecord(smeId)
  const application = previewApplications[smeId]
  if (!application) throw new Error('SME application was not found.')
  return clone(application)
}

export async function transitionPreviewApplication(
  smeId: string,
  targetStatus: ApplicationStatus,
): Promise<SMEApplication> {
  requirePreviewRecord(smeId)
  const application = previewApplications[smeId]
  application.status = targetStatus
  application.revision += 1
  application.updated_by = 'preview_user'
  application.updated_at = now()
  return clone(application)
}

export async function updatePreviewSME(
  smeId: string,
  update: Partial<Pick<SME, 'legal_name' | 'sector' | 'jurisdiction'>>,
): Promise<SMEUpdateResponse> {
  const record = requirePreviewRecord(smeId)
  const application = previewApplications[smeId]
  record.sme = { ...record.sme, ...update }
  const index = previewSMEs.findIndex((item) => item.sme_id === smeId)
  if (index !== -1) previewSMEs[index] = record.sme
  application.revision += 1
  application.updated_at = now()
  return clone({ sme: record.sme, application })
}

export async function deletePreviewSME(smeId: string): Promise<void> {
  const record = requirePreviewRecord(smeId)
  if (record.documents.length) {
    throw new Error('Delete the SME documents before deleting its workspace.')
  }
  delete previewRecords[smeId]
  delete previewApplications[smeId]
  const index = previewSMEs.findIndex((item) => item.sme_id === smeId)
  if (index !== -1) previewSMEs.splice(index, 1)
}

function buildPreviewReconciliation(smeId: string) {
  const record = requirePreviewRecord(smeId)
  const grouped = new Map<string, EvidenceItem[]>()
  for (const item of record.evidence_items) {
    const key = `${item.indicator_id}:${item.unit}:${item.reporting_period}:${item.scope}`
    grouped.set(key, [...(grouped.get(key) ?? []), item])
  }

  return {
    sme_id: smeId,
    clusters: [...grouped.values()].map((items, index) => {
      const values = [...new Set(items.map((item) => item.normalized_value))]
      const status = values.length > 1 ? 'conflict' as const : items.length > 1 ? 'corroborated' as const : 'single_source' as const
      return {
        cluster_id: `preview_cluster_${index + 1}`, sme_id: smeId, indicator_id: items[0].indicator_id,
        criterion_id: items[0].criterion_id, unit: items[0].unit, reporting_period: items[0].reporting_period,
        scope: items[0].scope, status, candidate_values: values,
        evidence_ids: items.map((item) => item.evidence_id), document_ids: [...new Set(items.map((item) => item.document_id))],
        extraction_methods: [...new Set(items.map((item) => item.extraction_method))],
        accepted_evidence_ids: items.filter((item) => item.validation_status === 'accepted').map((item) => item.evidence_id),
        unvalidated_evidence_ids: items.filter((item) => item.validation_status === 'unvalidated').map((item) => item.evidence_id),
        issues: status === 'conflict' ? ['Different values were found for the same metric and reporting context.'] : [],
      }
    }),
    rejected_evidence_ids: record.evidence_items.filter((item) => item.validation_status === 'rejected').map((item) => item.evidence_id),
    unit_mismatch_indicator_ids: [],
  }
}

for (const record of Object.values(previewRecords)) {
  for (const document of record.documents) {
    const documentEvidence = record.evidence_items.filter((item) => item.document_id === document.document_id)
    const status = document.document_id === 'doc_greenforge_statement' ? 'stored' : 'completed'
    const ids = documentEvidence.map((item) => item.evidence_id)
    previewProcessing[document.document_id] = {
      state: processingState(document.document_id, document.sme_id, status, ids.length),
      report: status === 'completed' ? previewReport(document, ids) : null,
      evidence_items: documentEvidence,
      reconciliation: buildPreviewReconciliation(record.sme.sme_id),
    }
  }
}

export async function getPreviewRecord(smeId: string): Promise<StructuredInvestmentRecord> {
  return clone(requirePreviewRecord(smeId))
}

export async function getPreviewDocumentProcessing(smeId: string, documentId: string): Promise<DocumentProcessingResult> {
  requirePreviewRecord(smeId)
  const result = previewProcessing[documentId]
  if (!result || result.state.sme_id !== smeId) throw new Error('Document processing state was not found.')
  return clone(result)
}

export async function uploadPreviewDocument(smeId: string, file: File, documentType: string): Promise<DocumentUploadResponse> {
  const record = requirePreviewRecord(smeId)
  const documentId = `doc_${crypto.randomUUID().replaceAll('-', '').slice(0, 20)}`
  const document = {
    document_id: documentId, sme_id: smeId, file_name: file.name,
    mime_type: file.type || 'application/octet-stream',
    sha256: crypto.randomUUID().replaceAll('-', '').padEnd(64, '0').slice(0, 64), document_type: documentType,
  }
  record.documents.push(document)
  const application = previewApplications[smeId]
  application.revision += 1
  application.updated_at = now()
  previewProcessing[documentId] = { state: processingState(documentId, smeId, 'stored'), report: null, evidence_items: [], reconciliation: buildPreviewReconciliation(smeId) }
  return clone({ document, storage_key: `${smeId}/${documentId}/${document.sha256}`, processing_status: 'stored', application })
}

export async function deletePreviewDocument(
  smeId: string,
  documentId: string,
): Promise<SMEApplication> {
  const record = requirePreviewRecord(smeId)
  const index = record.documents.findIndex(
    (item) => item.document_id === documentId,
  )
  if (index === -1) throw new Error('Document was not found.')
  record.documents.splice(index, 1)
  record.evidence_items = record.evidence_items.filter(
    (item) => item.document_id !== documentId,
  )
  delete previewProcessing[documentId]
  const application = previewApplications[smeId]
  application.revision += 1
  application.updated_at = now()
  return clone(application)
}

export async function processPreviewDocument(smeId: string, documentId: string): Promise<DocumentProcessingResult> {
  const record = requirePreviewRecord(smeId)
  const document = record.documents.find((item) => item.document_id === documentId)
  if (!document) throw new Error('Document was not found.')
  let documentEvidence = record.evidence_items.filter((item) => item.document_id === documentId)
  if (!documentEvidence.length) {
    const extracted = evidence({
      evidence_id: `evidence_${crypto.randomUUID().replaceAll('-', '').slice(0, 20)}`, sme_id: smeId,
      document_id: documentId, indicator_id: 'renewable_energy_percentage', raw_value: '72 percent', normalized_value: 72,
      source_locator: document.mime_type.startsWith('image/') ? 'image region 1, line 3' : 'page 1, paragraph 2',
      source_excerpt: 'Renewable energy share: 72 percent.',
      extraction_method: document.mime_type.startsWith('image/') ? 'paddle_ocr_semantic_extraction' : 'semantic_metric_extraction',
    })
    record.evidence_items.push(extracted)
    documentEvidence = [extracted]
  }
  const ids = documentEvidence.map((item) => item.evidence_id)
  const result: DocumentProcessingResult = {
    state: processingState(documentId, smeId, 'completed', ids.length),
    report: previewReport(document, ids),
    evidence_items: documentEvidence,
    reconciliation: buildPreviewReconciliation(smeId),
  }
  previewProcessing[documentId] = result
  return clone(result)
}

export async function validatePreviewEvidence(evidenceId: string, status: EvidenceItem['validation_status']): Promise<EvidenceItem> {
  for (const record of Object.values(previewRecords)) {
    const index = record.evidence_items.findIndex((item) => item.evidence_id === evidenceId)
    if (index === -1) continue
    const updated = { ...record.evidence_items[index], validation_status: status }
    record.evidence_items[index] = updated
    for (const result of Object.values(previewProcessing)) {
      const resultIndex = result.evidence_items.findIndex((item) => item.evidence_id === evidenceId)
      if (resultIndex !== -1) result.evidence_items[resultIndex] = updated
      if (result.state.sme_id === record.sme.sme_id) result.reconciliation = buildPreviewReconciliation(record.sme.sme_id)
    }
    return clone(updated)
  }
  throw new Error('Evidence item was not found.')
}

const previewRunRecords = new Map<string, AssessmentRunRecord>([
  [previewLatestRun.run_id, previewLatestRun],
])

const ratingScores: Record<string, number> = {
  very_low: 0.08,
  low: 0.28,
  medium: 0.52,
  high: 0.76,
  very_high: 0.96,
}

function buildPreviewAssessment(request: CohortAssessmentRequest): AssessmentRunRecord {
  const scored = request.submissions.map((submission) => {
    const values = submission.responses.map((response) => ratingScores[response.linguistic_value] ?? 0.5)
    const score = values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0.5
    return { smeId: submission.context.sme_id, score }
  }).sort((left, right) => right.score - left.score || left.smeId.localeCompare(right.smeId))

  const ranking = scored.map((item, index) => ({
    sme_id: item.smeId,
    score: item.score,
    rank: index + 1,
    distance_to_ideal: 1 - item.score,
    distance_to_worst: item.score,
  }))
  const criterionIds = [...new Set(request.submissions.flatMap((submission) => submission.responses.map((response) => response.criterion_id)))]
  const equalWeight = criterionIds.length ? 1 / criterionIds.length : 1
  const normalizedWeights = Object.fromEntries(criterionIds.map((criterionId) => [`normalized:${criterionId}`, equalWeight]))

  return {
    run_id: request.run_id,
    cohort_id: request.cohort_id,
    cohort_version: request.version,
    requested_by: 'reviewer_preview',
    sme_ids: request.submissions.map((submission) => submission.context.sme_id),
    comparison_status: 'ready',
    created_at: now(),
    result: {
      preparations: request.submissions.map((submission) => {
        const financial = submission.financial_observations ?? []
        const coreIds = new Set(['roa_percentage', 'revenue_growth_percentage', 'current_ratio'])
        const coreReady = financial.filter((item) => coreIds.has(item.metric_id) && item.state === 'reported').length
        return {
          profile: { sme_id: submission.context.sme_id, active_modules: [], uncertain_modules: [] },
          observations: { coverage: { applicable_count: submission.responses.length, resolved_count: submission.responses.length, document_supported_count: 0, coverage_ratio: 1 } },
          normalized_inputs: { readiness: 'ready', coverage_ratio: 1, issues: [] },
          financial_assessment: {
            status: coreReady === 3 ? 'complete' : coreReady ? 'partial' : 'insufficient',
            core_coverage_ratio: coreReady / 3,
            calibration_status: 'requires_financial_calibration', aggregate_score: null,
            metrics: financial.map((item) => ({
              metric_id: item.metric_id,
              title: previewAssessmentConfiguration.financial_policy.metrics.find((metric) => metric.metric_id === item.metric_id)?.title ?? item.metric_id,
              group: previewAssessmentConfiguration.financial_policy.metrics.find((metric) => metric.metric_id === item.metric_id)?.group ?? 'business_health',
              importance: previewAssessmentConfiguration.financial_policy.metrics.find((metric) => metric.metric_id === item.metric_id)?.importance ?? 'supporting',
              state: item.state, value: item.value ?? null, unit: item.unit ?? null,
              reporting_period: item.reporting_period ?? null, issues: [],
            })),
            derived_indicators: [],
          },
          readiness_profile: {
            calibration_status: 'requires_expert_calibration', causal_results_available: false,
            factors: (submission.readiness_observations ?? []).map((item) => ({
              factor_id: item.factor_id,
              domain_id: previewAssessmentConfiguration.readiness_specification.factors.find((factor) => factor.factor_id === item.factor_id)?.domain_id ?? '',
              state: item.state, narrative: item.narrative ?? null,
            })),
          },
          performance_context: {
            metric_catalog_id: previewAssessmentConfiguration.metric_catalog.catalog_id,
            metric_catalog_version: previewAssessmentConfiguration.metric_catalog.version,
            metrics: [],
          },
        }
      }),
      comparable_topsis: {
        comparison_status: 'ready',
        shared_criterion_ids: criterionIds,
        coverage: request.submissions.map((submission) => ({
          sme_id: submission.context.sme_id,
          available_criterion_ids: criterionIds,
          shared_criterion_ids: criterionIds,
          excluded_criterion_ids: [],
          shared_weight_ratio: 1,
        })),
        topsis_result: { normalized_weights: normalizedWeights, ranking },
      },
      fuzzy_topsis: {
        ranking: ranking.map((item) => ({ ...item, score: Math.max(0, item.score - 0.02) })),
        ranking_changed_from_crisp: false,
      },
      electre_iii: {
        rank_levels: ranking.map((item) => ({ level: item.rank, sme_ids: [item.sme_id], contains_preference_cycle: false })),
        incomparable_pairs: [],
      },
      robustness: {
        completed_scenarios: 200,
        rejected_scenarios: 0,
        baseline_agreement: [
          { first_method: 'topsis', second_method: 'fuzzy_topsis', agreement_rate: 1 },
          { first_method: 'topsis', second_method: 'electre_iii', agreement_rate: 0.92 },
        ],
        sme_stability: ranking.map((item) => ({
          sme_id: item.sme_id,
          baseline_ranks: { topsis: item.rank, fuzzy_topsis: item.rank, electre_iii: item.rank },
          first_place_rates: { topsis: item.rank === 1 ? 0.86 : 0.08, fuzzy_topsis: item.rank === 1 ? 0.83 : 0.09, electre_iii: item.rank === 1 ? 0.78 : 0.11 },
          mean_ranks: { topsis: item.rank, fuzzy_topsis: item.rank + 0.04, electre_iii: item.rank + 0.09 },
          best_ranks: { topsis: Math.max(1, item.rank - 1), fuzzy_topsis: Math.max(1, item.rank - 1), electre_iii: Math.max(1, item.rank - 1) },
          worst_ranks: { topsis: Math.min(ranking.length, item.rank + 1), fuzzy_topsis: Math.min(ranking.length, item.rank + 1), electre_iii: Math.min(ranking.length, item.rank + 1) },
        })),
        warnings: [],
      },
      calibration: {
        calibration_id: 'greensmecapt_mcdm_development', version: '0.1.0', status: 'development',
        statement: 'Transparent model-informed starting values pending structured expert calibration.',
      },
    },
  }
}

export async function getPreviewAssessmentRun(runId: string): Promise<AssessmentRunRecord> {
  const existing = previewRunRecords.get(runId)
  if (existing) return clone(existing)
  const summary = previewRuns.find((run) => run.run_id === runId)
  if (!summary) throw new Error('Assessment run was not found.')
  return clone({ ...previewLatestRun, ...summary })
}

export async function deletePreviewAssessmentRun(runId: string): Promise<void> {
  const index = previewRuns.findIndex((run) => run.run_id === runId)
  if (index < 0) throw new Error('Assessment run was not found.')
  previewRuns.splice(index, 1)
  previewRunRecords.delete(runId)
}

export async function createPreviewAssessment(request: CohortAssessmentRequest): Promise<AssessmentRunRecord> {
  if (previewRuns.some((run) => run.run_id === request.run_id)) {
    throw new Error('An assessment run with this identifier already exists.')
  }
  const record = buildPreviewAssessment(request)
  previewRunRecords.set(record.run_id, record)
  previewRuns.unshift({
    run_id: record.run_id, cohort_id: record.cohort_id, cohort_version: record.cohort_version,
    requested_by: record.requested_by, sme_ids: record.sme_ids,
    comparison_status: record.comparison_status, created_at: record.created_at,
  })
  return clone(record)
}
