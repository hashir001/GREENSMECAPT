"""Tests for the governed separation of assessment dimensions."""

from pathlib import Path

from greensmecapt.assessment.evidence_strength import (
    EvidenceDimensionInput,
    EvidenceSourceClass,
    EvidenceSourceClassification,
    EvidenceStrengthBand,
    assess_evidence_strength,
    load_evidence_strength_policy,
)
from greensmecapt.assessment.financial import (
    FinancialMetricRole,
    load_financial_policy,
)
from greensmecapt.assessment.profiles import load_policy
from greensmecapt.document_intelligence.semantics import (
    MetricAssessmentUse,
    MetricDirection,
    MetricValueNature,
    load_metric_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


def test_metric_catalog_separates_actual_forecast_and_context_values() -> None:
    catalog = load_metric_catalog(
        CONFIG_ROOT / "metric_catalog.development.json"
    )

    forecasts = [
        metric
        for metric in catalog.metrics
        if metric.value_nature is MetricValueNature.FORECAST
    ]
    denominators = [
        metric
        for metric in catalog.metrics
        if metric.value_nature is MetricValueNature.ACTIVITY_DENOMINATOR
    ]

    assert forecasts
    assert all(
        metric.assessment_use is MetricAssessmentUse.EVIDENCE_ONLY
        for metric in forecasts
    )
    assert denominators
    assert all(
        metric.direction is MetricDirection.CONTEXT_ONLY
        for metric in denominators
    )


def test_financial_derived_indicators_name_governed_source_inputs() -> None:
    catalog = load_metric_catalog(
        CONFIG_ROOT / "metric_catalog.development.json"
    )
    policy = load_financial_policy(
        CONFIG_ROOT / "financial_assessment.development.json"
    )
    catalog_ids = {metric.indicator_id for metric in catalog.metrics}
    policy_ids = {metric.metric_id for metric in policy.metrics}
    derived = [
        metric
        for metric in policy.metrics
        if metric.role is FinancialMetricRole.DERIVED_INDICATOR
    ]

    assert derived
    assert policy_ids <= catalog_ids
    assert all(set(metric.input_metric_ids) <= policy_ids for metric in derived)
    assert all(metric.calculation_method is not None for metric in derived)


def test_only_environmental_performance_criteria_are_scoring_inputs() -> None:
    policy = load_policy(
        CONFIG_ROOT / "assessment_profiles.development.json"
    )
    scoring = [
        criterion
        for criterion in policy.criteria
        if criterion.scoring_role == "performance_criterion"
    ]

    assert scoring
    assert all(
        criterion.dimension == "environmental_performance"
        for criterion in scoring
    )
    assert any(
        criterion.scoring_role == "separate_financial_assessment"
        for criterion in policy.criteria
    )
    assert any(
        criterion.scoring_role == "non_scoring_context"
        for criterion in policy.criteria
    )


def test_evidence_strength_is_separate_and_missing_is_not_zero() -> None:
    policy = load_evidence_strength_policy(
        CONFIG_ROOT / "evidence_strength.development.json"
    )

    assert policy.performance_separation is True
    assert policy.missing_information_rule == "unknown_not_zero"
    assert EvidenceStrengthBand.CONFLICTING in policy.bands
    assert {
        requirement.dimension_id
        for requirement in policy.dimension_requirements
    } == {
        "environmental_performance",
        "financial_health",
        "investment_case",
        "readiness_context",
    }


def test_evidence_strength_rules_preserve_source_provenance() -> None:
    policy = load_evidence_strength_policy(
        CONFIG_ROOT / "evidence_strength.development.json"
    )
    dimensions = (
        EvidenceDimensionInput(
            dimension_id="environmental_performance",
            source_ids=("utility_bill",),
        ),
        EvidenceDimensionInput(
            dimension_id="financial_health",
            source_ids=("management_accounts",),
        ),
        EvidenceDimensionInput(
            dimension_id="investment_case",
            source_ids=("funding_request",),
        ),
        EvidenceDimensionInput(
            dimension_id="readiness_context",
            conflicting=True,
        ),
    )
    classifications = {
        "utility_bill": EvidenceSourceClassification(
            source_id="utility_bill",
            source_class=EvidenceSourceClass.THIRD_PARTY_TRANSACTIONAL,
            confirmed=True,
            classification_basis="document_type:utility_bill",
        ),
        "management_accounts": EvidenceSourceClassification(
            source_id="management_accounts",
            source_class=EvidenceSourceClass.INTERNALLY_GENERATED,
            confirmed=True,
            classification_basis="document_type:financial_statement",
        ),
        "funding_request": EvidenceSourceClassification(
            source_id="funding_request",
            source_class=EvidenceSourceClass.SELF_DECLARED,
            confirmed=True,
            classification_basis="document_type:funding_request",
        ),
    }

    result = assess_evidence_strength(
        policy=policy,
        dimension_inputs=dimensions,
        source_classifications=classifications,
    )
    bands = {item.dimension_id: item.band for item in result.dimensions}

    assert bands == {
        "environmental_performance": EvidenceStrengthBand.STRONG,
        "financial_health": EvidenceStrengthBand.ADEQUATE,
        "investment_case": EvidenceStrengthBand.LIMITED,
        "readiness_context": EvidenceStrengthBand.CONFLICTING,
    }
    environmental = next(
        item
        for item in result.dimensions
        if item.dimension_id == "environmental_performance"
    )
    assert environmental.sources[0].classification_basis == (
        "document_type:utility_bill"
    )
