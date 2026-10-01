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
            if metric_id in {
                "revenue_growth_percentage",
                "revenue_previous_period",
            }
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
    assert derived["requested_share_of_project_cost"].value == 40.0
    assert derived["simple_payback_years"].value == 4.0


def test_financial_indicators_are_calculated_from_source_inputs() -> None:
    result = build_financial_assessment(
        sme_id="sme_001",
        policy=POLICY,
        observations=(
            _reported("revenue_current_period", 1_200_000, "aed"),
            _reported("revenue_previous_period", 1_000_000, "aed"),
            _reported("net_profit_current_period", 120_000, "aed"),
            _reported("total_assets", 1_500_000, "aed"),
            _reported("current_assets", 600_000, "aed"),
            _reported("current_liabilities", 300_000, "aed"),
            _reported("total_debt", 450_000, "aed"),
        ),
    )

    derived = {item.indicator_id: item for item in result.derived_indicators}
    assert derived["roa_percentage"].value == 8.0
    assert derived["revenue_growth_percentage"].value == 20.0
    assert derived["current_ratio"].value == 2.0
    assert derived["debt_to_assets_percentage"].value == 30.0
    assert derived["roa_percentage"].formula == (
        "(net_profit_current_period / total_assets) × 100"
    )
    assert derived["roa_percentage"].source_ids == ("document_financials",)
    assert result.status == "complete"


def test_missing_financials_remain_unknown_not_zero() -> None:
    result = build_financial_assessment(
        sme_id="sme_001",
        policy=POLICY,
    )

    assert result.status == "insufficient"
    assert result.core_coverage_ratio == 0.0
    assert all(item.value is None for item in result.metrics)
    assert all(item.state == "unknown" for item in result.metrics)


def test_reported_indicator_conflict_requires_review() -> None:
    result = build_financial_assessment(
        sme_id="sme_001",
        policy=POLICY,
        observations=(
            _reported("net_profit_current_period", 120_000, "aed"),
            _reported("total_assets", 1_500_000, "aed"),
            _reported("roa_percentage", 9.0, "percent"),
        ),
    )

    roa = next(item for item in result.metrics if item.metric_id == "roa_percentage")
    assert roa.state == "needs_review"
    assert roa.value is None
    assert "conflicts" in roa.issues[-1]


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
