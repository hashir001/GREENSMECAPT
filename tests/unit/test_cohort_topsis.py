"""Tests for fair cohort construction and TOPSIS integration."""

import pytest
from pydantic import ValidationError

from greensmecapt.assessment.cohort import (
    CohortComparisonError,
    CohortComparisonStatus,
    CohortConfiguration,
    run_comparable_topsis,
)
from greensmecapt.assessment.input_models import (
    IndicatorDefinition,
    InputStatus,
    NumericDirection,
    ResolvedIndicator,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
    TriangularFuzzyNumber,
)


def _criterion(
    criterion_id: str,
    value: float,
    weight: float = 1.0,
) -> NormalizedCriterionInput:
    return NormalizedCriterionInput(
        criterion_id=criterion_id,
        fuzzy_value=TriangularFuzzyNumber(
            lower=value,
            modal=value,
            upper=value,
        ),
        base_weight=weight,
        source_status="ready_linguistic",
        response_ids=(f"response_{criterion_id}",),
    )


def _assessment(
    sme_id: str,
    values: dict[str, float],
    readiness: AssessmentReadiness = AssessmentReadiness.READY,
) -> NormalizedAssessmentInputs:
    return NormalizedAssessmentInputs(
        sme_id=sme_id,
        normalization_policy_id="normalization_policy",
        normalization_policy_version="1.0",
        readiness=readiness,
        coverage_ratio=1.0,
        criteria=tuple(
            _criterion(criterion_id, value)
            for criterion_id, value in values.items()
        ),
        issues=(),
    )


def test_rank_shared_normalized_inputs() -> None:
    result = run_comparable_topsis(
        inputs=(
            _assessment(
                "sme_green",
                {
                    "green_contribution": 0.9,
                    "energy_management": 0.8,
                },
            ),
            _assessment(
                "sme_conventional",
                {
                    "green_contribution": 0.3,
                    "energy_management": 0.4,
                },
            ),
        ),
        configuration=CohortConfiguration(
            cohort_id="comparison_001",
            version="1.0",
        ),
    )

    assert result.comparison_status is CohortComparisonStatus.READY
    assert result.topsis_result.ranking[0].sme_id == "sme_green"
    assert result.topsis_result.ranking[0].rank == 1


def test_use_intersection_without_penalizing_missing_module() -> None:
    result = run_comparable_topsis(
        inputs=(
            _assessment(
                "manufacturer",
                {
                    "green_contribution": 0.8,
                    "energy_management": 0.7,
                    "materials_recovery": 0.9,
                },
            ),
            _assessment(
                "software_company",
                {
                    "green_contribution": 0.7,
                    "energy_management": 0.8,
                },
            ),
        ),
        configuration=CohortConfiguration(
            cohort_id="cross_sector_001",
            version="1.0",
            minimum_shared_weight_ratio=0.6,
        ),
    )

    assert result.shared_criterion_ids == (
        "energy_management",
        "green_contribution",
    )
    assert (
        result.comparison_status
        is CohortComparisonStatus.PROVISIONAL
    )

    manufacturer = next(
        item
        for item in result.coverage
        if item.sme_id == "manufacturer"
    )

    assert manufacturer.excluded_criterion_ids == (
        "materials_recovery",
    )
    assert manufacturer.shared_weight_ratio == pytest.approx(2 / 3)


def test_reject_blocked_assessment() -> None:
    with pytest.raises(
        CohortComparisonError,
        match="Assessment inputs are not ready for comparison",
    ):
        run_comparable_topsis(
            inputs=(
                _assessment(
                    "sme_001",
                    {
                        "green_contribution": 0.8,
                        "energy_management": 0.7,
                    },
                    readiness=AssessmentReadiness.BLOCKED,
                ),
                _assessment(
                    "sme_002",
                    {
                        "green_contribution": 0.6,
                        "energy_management": 0.5,
                    },
                ),
            ),
            configuration=CohortConfiguration(
                cohort_id="comparison_001",
                version="1.0",
            ),
        )


def test_reject_comparison_with_too_little_shared_weight() -> None:
    with pytest.raises(
        CohortComparisonError,
        match="cover too little",
    ):
        run_comparable_topsis(
            inputs=(
                _assessment(
                    "broad_assessment",
                    {
                        "criterion_1": 0.9,
                        "criterion_2": 0.8,
                        "criterion_3": 0.7,
                        "criterion_4": 0.6,
                    },
                ),
                _assessment(
                    "narrow_assessment",
                    {
                        "criterion_1": 0.5,
                    },
                ),
            ),
            configuration=CohortConfiguration(
                cohort_id="comparison_001",
                version="1.0",
                minimum_shared_criteria=1,
                minimum_shared_weight_ratio=0.6,
            ),
        )


def test_response_provenance_can_support_ready_input() -> None:
    definition = IndicatorDefinition(
        indicator_id="normalized:green_contribution",
        criterion_id="green_contribution",
        name="Green Contribution",
        unit="normalized_0_1",
        direction=NumericDirection.BENEFIT,
        minimum=0.0,
        maximum=1.0,
    )

    resolved = ResolvedIndicator(
        definition=definition,
        status=InputStatus.READY,
        value=0.8,
        response_ids=("reviewed_response_001",),
    )

    assert resolved.value == 0.8
    assert resolved.response_ids == ("reviewed_response_001",)

    with pytest.raises(
        ValidationError,
        match="evidence or response provenance",
    ):
        ResolvedIndicator(
            definition=definition,
            status=InputStatus.READY,
            value=0.8,
        )