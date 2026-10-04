"""End-to-end preparation and multi-method SME comparison workflow."""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.calibration import (
    MCDMCalibrationManifest,
    load_calibration_manifest,
)
from greensmecapt.assessment.cohort import (
    CohortConfiguration,
    ComparableTopsisResult,
    run_comparable_topsis,
)
from greensmecapt.assessment.electre_iii import (
    ElectreIIIConfiguration,
    ElectreIIIResult,
    load_electre_configuration,
    run_electre_iii,
)
from greensmecapt.assessment.evidence_strength import (
    EvidenceDimensionInput,
    EvidenceSourceClass,
    EvidenceSourceClassification,
    EvidenceStrengthAssessment,
    EvidenceStrengthPolicy,
    assess_evidence_strength,
    load_evidence_strength_policy,
)
from greensmecapt.assessment.financial import (
    FinancialAssessmentPolicy,
    FinancialInvestmentAssessment,
    FinancialMetricGroup,
    FinancialObservation,
    FinancialObservationState,
    build_financial_assessment,
    load_financial_policy,
)
from greensmecapt.assessment.fuzzy_dematel import (
    DematelSpecification,
    FuzzyDematelResult,
    load_dematel_result,
    load_dematel_specification,
)
from greensmecapt.assessment.fuzzy_topsis import (
    FuzzyTopsisResult,
    run_fuzzy_topsis,
)
from greensmecapt.assessment.green_score import (
    GreenScoreResult,
    calculate_green_score,
)
from greensmecapt.assessment.evidence_eligibility import (
    is_current_reviewed_evidence,
    is_reviewed_evidence,
)
from greensmecapt.assessment.normalization import (
    NormalizationPolicy,
    NormalizedAssessmentInputs,
    load_normalization_policy,
    normalize_observations,
)
from greensmecapt.assessment.observations import (
    CriterionResponse,
    ObservationSet,
    ObservationStatus,
    build_observations,
)
from greensmecapt.assessment.performance_context import (
    ComparisonContextState,
    EnvironmentalPerformanceContextProfile,
    MetricComparisonContext,
    build_performance_context_profile,
)
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    AssessmentPolicy,
    AssessmentProfile,
    build_profile,
    load_policy,
)
from greensmecapt.assessment.readiness import (
    ReadinessObservation,
    ReadinessState,
    SMEReadinessProfile,
    build_readiness_profile,
    merge_readiness_observations,
    readiness_observations_from_evidence,
)
from greensmecapt.assessment.robustness import (
    RankingRobustnessResult,
    RobustnessConfiguration,
    analyze_ranking_robustness,
)
from greensmecapt.document_intelligence.semantics import (
    MetricCatalog,
    load_metric_catalog,
)
from greensmecapt.domain import (
    DocumentType,
    EvidenceItem,
    StructuredInvestmentRecord,
)


class AssessmentWorkflowError(ValueError):
    """Raised when an assessment workflow request is inconsistent."""


class AssessmentWorkflowModel(BaseModel):
    """Provide immutable assessment workflow contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class PreparedAssessment(AssessmentWorkflowModel):
    """Contain the complete traceable preparation result for one SME."""

    profile: AssessmentProfile
    observations: ObservationSet
    normalized_inputs: NormalizedAssessmentInputs
    green_score: GreenScoreResult | None = None
    financial_assessment: FinancialInvestmentAssessment
    readiness_profile: SMEReadinessProfile
    performance_context: EnvironmentalPerformanceContextProfile
    evidence_strength: EvidenceStrengthAssessment
    activity_fact_evidence_ids: dict[str, tuple[str, ...]] = Field(
        default_factory=dict
    )


class CohortAssessmentResult(AssessmentWorkflowModel):
    """Contain complementary cohort rankings from one shared input set."""

    preparations: tuple[PreparedAssessment, ...] = Field(min_length=2)
    comparable_topsis: ComparableTopsisResult
    fuzzy_topsis: FuzzyTopsisResult
    electre_iii: ElectreIIIResult
    robustness: RankingRobustnessResult | None = None
    calibration: MCDMCalibrationManifest | None = None


def _validate_policy_alignment(
    *,
    assessment_policy: AssessmentPolicy,
    normalization_policy: NormalizationPolicy,
    financial_policy: FinancialAssessmentPolicy,
    metric_catalog: MetricCatalog,
    evidence_strength_policy: EvidenceStrengthPolicy,
) -> None:
    """Reject configuration sets that describe different assessment systems."""

    metric_by_id = {
        metric.indicator_id: metric for metric in metric_catalog.metrics
    }
    criterion_by_id = {
        criterion.criterion_id: criterion
        for criterion in assessment_policy.criteria
    }
    referenced_indicators = {
        indicator_id
        for criterion in assessment_policy.criteria
        for indicator_id in criterion.indicator_ids
    }
    unknown_indicators = referenced_indicators - metric_by_id.keys()
    if unknown_indicators:
        raise AssessmentWorkflowError(
            "Assessment criteria reference unknown metrics: "
            f"{sorted(unknown_indicators)}"
        )

    financial_ids = {metric.metric_id for metric in financial_policy.metrics}
    missing_financial_metrics = financial_ids - metric_by_id.keys()
    if missing_financial_metrics:
        raise AssessmentWorkflowError(
            "Financial policy metrics are absent from the extraction catalogue: "
            f"{sorted(missing_financial_metrics)}"
        )
    misclassified_financial = {
        metric_id
        for metric_id in financial_ids
        if metric_by_id[metric_id].dimension.value
        not in {"financial_health", "investment_case"}
    }
    if misclassified_financial:
        raise AssessmentWorkflowError(
            "Financial policy metrics have incompatible dimensions: "
            f"{sorted(misclassified_financial)}"
        )

    unknown_normalization = {
        rule.criterion_id
        for rule in normalization_policy.rules
        if rule.criterion_id not in criterion_by_id
    }
    if unknown_normalization:
        raise AssessmentWorkflowError(
            "Normalization rules reference unknown criteria: "
            f"{sorted(unknown_normalization)}"
        )
    non_performance_rules = {
        rule.criterion_id
        for rule in normalization_policy.rules
        if criterion_by_id[rule.criterion_id].scoring_role
        != "performance_criterion"
    }
    if non_performance_rules:
        raise AssessmentWorkflowError(
            "Only environmental performance criteria may enter MCDM: "
            f"{sorted(non_performance_rules)}"
        )

    governed_dimensions = {
        requirement.dimension_id
        for requirement in evidence_strength_policy.dimension_requirements
    }
    required_dimensions = {
        "environmental_performance",
        "financial_health",
        "investment_case",
        "readiness_context",
    }
    missing_dimensions = required_dimensions - governed_dimensions
    if missing_dimensions:
        raise AssessmentWorkflowError(
            "Evidence-strength policy omits assessment dimensions: "
            f"{sorted(missing_dimensions)}"
        )


class AssessmentWorkflow:
    """Prepare SME evidence and run reproducible comparison methods."""

    def __init__(
        self,
        *,
        assessment_policy: AssessmentPolicy,
        normalization_policy: NormalizationPolicy,
        financial_policy: FinancialAssessmentPolicy,
        readiness_specification: DematelSpecification,
        readiness_dematel_result: FuzzyDematelResult | None = None,
        metric_catalog: MetricCatalog,
        evidence_strength_policy: EvidenceStrengthPolicy,
        electre_configuration: ElectreIIIConfiguration,
        robustness_configuration: RobustnessConfiguration | None = None,
        calibration_manifest: MCDMCalibrationManifest | None = None,
    ) -> None:
        _validate_policy_alignment(
            assessment_policy=assessment_policy,
            normalization_policy=normalization_policy,
            financial_policy=financial_policy,
            metric_catalog=metric_catalog,
            evidence_strength_policy=evidence_strength_policy,
        )
        if readiness_dematel_result is not None and (
            readiness_dematel_result.specification_id
            != readiness_specification.specification_id
            or readiness_dematel_result.specification_version
            != readiness_specification.version
        ):
            raise AssessmentWorkflowError(
                "DEMATEL result and readiness specification must match."
            )
        self._assessment_policy = assessment_policy
        self._normalization_policy = normalization_policy
        self._financial_policy = financial_policy
        self._readiness_specification = readiness_specification
        self._readiness_dematel_result = readiness_dematel_result
        self._metric_catalog = metric_catalog
        self._evidence_strength_policy = evidence_strength_policy
        self._electre_configuration = electre_configuration
        self._robustness_configuration = (
            robustness_configuration or RobustnessConfiguration()
        )
        self._calibration_manifest = calibration_manifest

    @property
    def assessment_policy(self) -> AssessmentPolicy:
        """Expose the immutable policy snapshot used by this workflow."""

        return self._assessment_policy

    @property
    def normalization_policy(self) -> NormalizationPolicy:
        """Expose the immutable normalization policy used by this workflow."""

        return self._normalization_policy

    @property
    def financial_policy(self) -> FinancialAssessmentPolicy:
        return self._financial_policy

    @property
    def readiness_specification(self) -> DematelSpecification:
        return self._readiness_specification

    @property
    def metric_catalog(self) -> MetricCatalog:
        return self._metric_catalog

    @property
    def evidence_strength_policy(self) -> EvidenceStrengthPolicy:
        return self._evidence_strength_policy

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "AssessmentWorkflow":
        """Load versioned assessment policy from configured JSON files."""

        configured = environment if environment is not None else os.environ

        readiness_result_path = configured.get("GREENSMECAPT_READINESS_DEMATEL_RESULT")
        return cls(
            assessment_policy=load_policy(
                Path(
                    configured.get(
                        "GREENSMECAPT_ASSESSMENT_POLICY",
                        "config/assessment_profiles.development.json",
                    )
                )
            ),
            normalization_policy=load_normalization_policy(
                Path(
                    configured.get(
                        "GREENSMECAPT_NORMALIZATION_POLICY",
                        "config/normalization_policy.development.json",
                    )
                )
            ),
            financial_policy=load_financial_policy(
                Path(
                    configured.get(
                        "GREENSMECAPT_FINANCIAL_POLICY",
                        "config/financial_assessment.development.json",
                    )
                )
            ),
            readiness_specification=load_dematel_specification(
                Path(
                    configured.get(
                        "GREENSMECAPT_READINESS_SPECIFICATION",
                        "config/dematel_specification.development.json",
                    )
                )
            ),
            readiness_dematel_result=(
                load_dematel_result(Path(readiness_result_path))
                if readiness_result_path
                else None
            ),
            metric_catalog=load_metric_catalog(
                Path(
                    configured.get(
                        "GREENSMECAPT_METRIC_CATALOG",
                        "config/metric_catalog.development.json",
                    )
                )
            ),
            evidence_strength_policy=load_evidence_strength_policy(
                Path(
                    configured.get(
                        "GREENSMECAPT_EVIDENCE_STRENGTH_POLICY",
                        "config/evidence_strength.development.json",
                    )
                )
            ),
            electre_configuration=load_electre_configuration(
                Path(
                    configured.get(
                        "GREENSMECAPT_ELECTRE_CONFIGURATION",
                        "config/electre_iii.development.json",
                    )
                )
            ),
            calibration_manifest=load_calibration_manifest(
                Path(
                    configured.get(
                        "GREENSMECAPT_MCDM_CALIBRATION",
                        "config/mcdm_calibration.development.json",
                    )
                )
            ),
        )

    def prepare(
        self,
        *,
        record: StructuredInvestmentRecord,
        context: AssessmentContext,
        responses: Sequence[CriterionResponse] = (),
        financial_observations: Sequence[FinancialObservation] = (),
        readiness_observations: Sequence[ReadinessObservation] = (),
        metric_contexts: Sequence[MetricComparisonContext] = (),
    ) -> PreparedAssessment:
        """Resolve applicability, observations and normalized inputs."""

        if record.sme.sme_id != context.sme_id:
            raise AssessmentWorkflowError(
                "The assessment context belongs to a different SME."
            )

        context, fact_evidence = _merge_reviewed_activity_facts(
            context,
            record.evidence_items,
        )
        profile = build_profile(context, self._assessment_policy)
        observations = build_observations(
            profile,
            responses=responses,
            evidence_items=record.evidence_items,
            numeric_scoring_scales={
                rule.criterion_id: rule.numeric_scale
                for rule in self._normalization_policy.rules
                if rule.numeric_scale is not None
            },
        )
        normalized = normalize_observations(
            profile,
            observations,
            self._normalization_policy,
        )
        green_score = calculate_green_score(
            profile=profile,
            normalized=normalized,
            policy=self._normalization_policy,
        )
        readiness_observations = merge_readiness_observations(
            supplied=tuple(readiness_observations),
            extracted=readiness_observations_from_evidence(
                sme_id=record.sme.sme_id,
                specification=self._readiness_specification,
                evidence_items=record.evidence_items,
            ),
        )
        valid_source_ids = {
            *(item.document_id for item in record.documents),
            *(item.evidence_id for item in record.evidence_items),
        }
        referenced_source_ids = {
            source_id
            for collection in (
                financial_observations,
                readiness_observations,
                metric_contexts,
            )
            for item in collection
            for source_id in item.source_ids
        }
        unknown_source_ids = referenced_source_ids - valid_source_ids
        if unknown_source_ids:
            raise AssessmentWorkflowError(
                "Assessment inputs reference unknown sources: "
                f"{sorted(unknown_source_ids)}"
            )
        financial = build_financial_assessment(
            sme_id=record.sme.sme_id,
            policy=self._financial_policy,
            observations=financial_observations,
            evidence_items=record.evidence_items,
        )
        readiness = build_readiness_profile(
            record.sme.sme_id,
            self._readiness_specification,
            tuple(readiness_observations),
            self._readiness_dematel_result,
        )
        performance_context = build_performance_context_profile(
            sme_id=record.sme.sme_id,
            catalog=self._metric_catalog,
            evidence_items=record.evidence_items,
            contexts=metric_contexts,
        )
        evidence_strength = self._build_evidence_strength_assessment(
            policy=self._evidence_strength_policy,
            record=record,
            observations=observations,
            financial=financial,
            readiness=readiness,
            performance_context=performance_context,
            referenced_source_ids=referenced_source_ids,
        )

        return PreparedAssessment(
            profile=profile,
            observations=observations,
            normalized_inputs=normalized,
            green_score=green_score,
            financial_assessment=financial,
            readiness_profile=readiness,
            performance_context=performance_context,
            evidence_strength=evidence_strength,
            activity_fact_evidence_ids=fact_evidence,
        )
    def _build_evidence_strength_assessment(
        self,
        *,
        policy: EvidenceStrengthPolicy,
        record: StructuredInvestmentRecord,
        observations: ObservationSet,
        financial: FinancialInvestmentAssessment,
        readiness: SMEReadinessProfile,
        performance_context: EnvironmentalPerformanceContextProfile,
        referenced_source_ids: set[str],
    ) -> EvidenceStrengthAssessment:
        classifications = self._classify_sources(record, referenced_source_ids)
    
        environmental_sources = tuple(sorted({
            source_id
            for metric in performance_context.metrics
            for source_id in metric.source_ids
        }))
        environmental_missing = tuple(sorted({
            requirement
            for metric in performance_context.metrics
            for requirement in metric.missing_requirements
        }))
        environmental_issues = tuple(
            issue
            for metric in performance_context.metrics
            for issue in metric.issues
        )
    
        business_metrics = tuple(
            metric
            for metric in financial.metrics
            if metric.group is FinancialMetricGroup.BUSINESS_HEALTH
        )
        investment_metrics = tuple(
            metric
            for metric in financial.metrics
            if metric.group is FinancialMetricGroup.INVESTMENT_CASE
        )
        financial_missing: set[str] = set()
        if any(
            metric.importance.value == "core"
            and metric.state is not FinancialObservationState.REPORTED
            for metric in business_metrics
        ):
            financial_missing.add("core_financial_indicators")
        financial_sources = self._metric_sources(business_metrics)
        if financial_sources and not self._has_document_type(
            financial_sources,
            record,
            DocumentType.FINANCIAL_STATEMENT,
        ):
            financial_missing.add("statement_basis")
    
        investment_sources = set(self._metric_sources(investment_metrics))
        transition = next(
            (
                item
                for item in observations.observations
                if item.criterion_id == "transition_execution"
            ),
            None,
        )
        if transition is not None:
            investment_sources.update(transition.evidence_ids)
        expected_savings = next(
            (
                item
                for item in investment_metrics
                if item.metric_id == "expected_annual_savings"
            ),
            None,
        )
        investment_missing: set[str] = set()
        if (
            expected_savings is not None
            and expected_savings.state is FinancialObservationState.REPORTED
            and not expected_savings.narrative
        ):
            investment_missing.add("assumption_basis")
    
        readiness_sources = tuple(sorted({
            source_id
            for factor in readiness.factors
            for source_id in factor.source_ids
        }))
        readiness_missing: set[str] = set()
        evidenced_states = {
            ReadinessState.ENABLING_EVIDENCE,
            ReadinessState.CONSTRAINING_EVIDENCE,
            ReadinessState.MIXED_EVIDENCE,
        }
        if any(
            factor.state in evidenced_states and not factor.narrative
            for factor in readiness.factors
        ):
            readiness_missing.add("narrative_basis")
        if any(factor.state is ReadinessState.UNKNOWN for factor in readiness.factors):
            readiness_missing.add("factor_coverage")
    
        inputs = (
            EvidenceDimensionInput(
                dimension_id="environmental_performance",
                source_ids=environmental_sources,
                missing_attributes=environmental_missing,
                conflicting=any(
                    metric.state is ComparisonContextState.NEEDS_REVIEW
                    for metric in performance_context.metrics
                ),
                issues=environmental_issues,
            ),
            EvidenceDimensionInput(
                dimension_id="financial_health",
                source_ids=financial_sources,
                missing_attributes=tuple(sorted(financial_missing)),
            conflicting=self._has_financial_conflict(business_metrics),
            issues=self._metric_issues(business_metrics),
            ),
            EvidenceDimensionInput(
                dimension_id="investment_case",
                source_ids=tuple(sorted(investment_sources)),
                missing_attributes=tuple(sorted(investment_missing)),
            conflicting=self._has_financial_conflict(investment_metrics)
                or bool(transition and transition.status is ObservationStatus.CONFLICT),
                issues=(
                *self._metric_issues(investment_metrics),
                    *(transition.issues if transition else ()),
                ),
            ),
            EvidenceDimensionInput(
                dimension_id="readiness_context",
                source_ids=readiness_sources,
                missing_attributes=tuple(sorted(readiness_missing)),
                conflicting=any(
                    factor.state is ReadinessState.NEEDS_REVIEW
                    for factor in readiness.factors
                ),
            ),
        )
        return assess_evidence_strength(
            policy=policy,
            dimension_inputs=inputs,
            source_classifications=classifications,
        )
    
    
    def _classify_sources(
        self,
        record: StructuredInvestmentRecord,
        reviewed_source_ids: set[str],
    ) -> dict[str, EvidenceSourceClassification]:
        documents = {item.document_id: item for item in record.documents}
        classifications: dict[str, EvidenceSourceClassification] = {}
        for document in record.documents:
            source_class = self._document_source_class(document.document_type)
            classifications[document.document_id] = EvidenceSourceClassification(
                source_id=document.document_id,
                source_class=source_class,
                confirmed=document.document_id in reviewed_source_ids,
                classification_basis=f"document_type:{document.document_type.value}",
            )
        for evidence in record.evidence_items:
            document = documents.get(evidence.document_id)
            source_class = (
                self._document_source_class(document.document_type)
                if document is not None
                else EvidenceSourceClass.MODEL_INFERRED
            )
            document_label = (
                document.document_type.value
                if document is not None
                else "missing_source_document"
            )
            classifications[evidence.evidence_id] = EvidenceSourceClassification(
                source_id=evidence.evidence_id,
                source_class=source_class,
                confirmed=(
                    is_reviewed_evidence(evidence)
                ),
                classification_basis=(
                    f"accepted_extraction_from:{document_label}"
                    if is_reviewed_evidence(evidence)
                    else f"unconfirmed_extraction_from:{document_label}"
                ),
            )
        return classifications
    
    
    def _document_source_class(
        self,
        document_type: DocumentType,
    ) -> EvidenceSourceClass:
        if document_type is DocumentType.PERMIT:
            return EvidenceSourceClass.AUDITED_OR_REGULATORY
        if document_type in {DocumentType.UTILITY_BILL, DocumentType.CONTRACT}:
            return EvidenceSourceClass.THIRD_PARTY_TRANSACTIONAL
        if document_type in {
            DocumentType.FINANCIAL_STATEMENT,
            DocumentType.SUSTAINABILITY_REPORT,
            DocumentType.OTHER,
        }:
            return EvidenceSourceClass.INTERNALLY_GENERATED
        return EvidenceSourceClass.SELF_DECLARED
    
    
    def _metric_sources(self, metrics) -> tuple[str, ...]:
        return tuple(sorted({source for metric in metrics for source in metric.source_ids}))
    
    
    def _metric_issues(self, metrics) -> tuple[str, ...]:
        return tuple(issue for metric in metrics for issue in metric.issues)
    
    
    def _has_financial_conflict(self, metrics) -> bool:
        return any(
            "conflict" in issue.casefold()
            for issue in self._metric_issues(metrics)
        )
    
    
    def _has_document_type(
        self,
        source_ids: tuple[str, ...],
        record: StructuredInvestmentRecord,
        document_type: DocumentType,
    ) -> bool:
        documents = {item.document_id: item for item in record.documents}
        evidence_documents = {
            item.evidence_id: item.document_id for item in record.evidence_items
        }
        return any(
            documents.get(evidence_documents.get(source_id, source_id)) is not None
            and documents[evidence_documents.get(source_id, source_id)].document_type
            is document_type
            for source_id in source_ids
        )

    def compare(
        self,
        preparations: Sequence[PreparedAssessment],
        configuration: CohortConfiguration,
    ) -> CohortAssessmentResult:
        """Run crisp TOPSIS, fuzzy TOPSIS and ELECTRE III together."""

        if len(preparations) < 2:
            raise AssessmentWorkflowError(
                "A cohort assessment requires at least two SMEs."
            )

        sme_ids = [
            item.normalized_inputs.sme_id
            for item in preparations
        ]

        if len(sme_ids) != len(set(sme_ids)):
            raise AssessmentWorkflowError(
                "A cohort assessment cannot contain duplicate SMEs."
            )

        normalized_inputs = tuple(
            item.normalized_inputs for item in preparations
        )
        comparable_topsis = run_comparable_topsis(
            normalized_inputs,
            configuration,
        )

        fuzzy_topsis = run_fuzzy_topsis(
            normalized_inputs,
            comparable_topsis,
        )
        electre_iii = run_electre_iii(
            normalized_inputs,
            comparable_topsis,
            self._electre_configuration,
        )
        robustness = analyze_ranking_robustness(
            inputs=normalized_inputs,
            cohort_configuration=configuration,
            electre_configuration=self._electre_configuration,
            baseline_topsis=comparable_topsis,
            baseline_fuzzy_topsis=fuzzy_topsis,
            baseline_electre=electre_iii,
            configuration=self._robustness_configuration,
        )

        return CohortAssessmentResult(
            preparations=tuple(preparations),
            comparable_topsis=comparable_topsis,
            fuzzy_topsis=fuzzy_topsis,
            electre_iii=electre_iii,
            robustness=robustness,
            calibration=self._calibration_manifest,
        )


def _merge_reviewed_activity_facts(
    context: AssessmentContext,
    evidence_items: Sequence[EvidenceItem],
) -> tuple[AssessmentContext, dict[str, tuple[str, ...]]]:
    """Apply only accepted, non-conflicting document activity facts."""

    grouped: dict[str, list[EvidenceItem]] = {}

    for evidence in evidence_items:
        prefix = "activity_fact:"

        if (
            not is_current_reviewed_evidence(evidence)
            or not evidence.indicator_id.startswith(prefix)
        ):
            continue

        fact_id = evidence.indicator_id.removeprefix(prefix)

        if not isinstance(evidence.normalized_value, bool):
            raise AssessmentWorkflowError(
                f"Accepted activity fact {fact_id!r} must be boolean."
            )

        grouped.setdefault(fact_id, []).append(evidence)

    merged = dict(context.facts)
    provenance: dict[str, tuple[str, ...]] = {}

    for fact_id, evidence_group in grouped.items():
        values = {item.normalized_value for item in evidence_group}

        if len(values) != 1:
            raise AssessmentWorkflowError(
                f"Accepted evidence conflicts for activity fact {fact_id!r}."
            )

        evidence_value = values.pop()
        supplied_value = merged.get(fact_id)

        if supplied_value is not None and supplied_value is not evidence_value:
            raise AssessmentWorkflowError(
                f"Assessment context conflicts with accepted evidence for "
                f"activity fact {fact_id!r}."
            )

        merged[fact_id] = evidence_value
        provenance[fact_id] = tuple(
            sorted(item.evidence_id for item in evidence_group)
        )

    return (
        context.model_copy(update={"facts": merged}),
        provenance,
    )
