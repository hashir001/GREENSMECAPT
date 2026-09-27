"""Tests for the distinct financial and investment assessment."""

from pathlib import Path

from greensmecapt.assessment.financial import (
    FinancialObservation,
    FinancialObservationState,
    build_financial_assessment,
    load_financial_policy,
)

POLICY = load_financial_policy(
    Path("config/financial_assessment.development.json")
)


def _reported(metric_id: str, value: float, unit: str) -> FinancialObservation:
    return FinancialObservation(
        observation_id=f"observation_{metric_id}",
        sme_id="sme_001",
        metric_id=metric_id,
        state=FinancialObservationState.REPORTED,
        value=value,
        unit=unit,
        reporting_period="FY2025",
        comparison_basis=(
            "FY2025 against FY2024"
            if metric_id == "revenue_growth_percentage"
            else None
        ),
        source_ids=("document_financials",),
    )


def test_financial_assessment_is_separate_and_non_scoring() -> None:
    observations = (
        _reported("roa_percentage", 8.2, "percent"),
        _reported("revenue_growth_percentage", 12.0, "percent"),
        _reported("current_ratio", 1.6, "ratio"),
        _reported("requested_amount", 400_000, "aed"),
        _reported("project_cost", 1_000_000, "aed"),
        _reported("expected_annual_savings", 250_000, "aed_per_year"),
    )

    result = build_financial_assessment(
        sme_id="sme_001",
        policy=POLICY,
        observations=observations,
    )

    assert result.status == "complete"
    assert result.core_coverage_ratio == 1.0
    assert result.aggregate_score is None
    derived = {item.indicator_id: item for item in result.derived_indicators}
    assert derived["requested_share_of_project_cost"].value == 0.4
    assert derived["simple_payback_years"].value == 4.0


def test_missing_financials_remain_unknown_not_zero() -> None:
    result = build_financial_assessment(
        sme_id="sme_001",
        policy=POLICY,
    )

    assert result.status == "insufficient"
    assert result.core_coverage_ratio == 0.0
    assert all(item.value is None for item in result.metrics)
    assert all(item.state == "unknown" for item in result.metrics)


def test_invalid_financial_unit_requires_review() -> None:
    result = build_financial_assessment(
        sme_id="sme_001",
        policy=POLICY,
        observations=(
            _reported("current_ratio", 1.4, "percent"),
        ),
    )

    metric = next(item for item in result.metrics if item.metric_id == "current_ratio")
    assert metric.state == "needs_review"
    assert metric.value is None
    assert metric.issues
