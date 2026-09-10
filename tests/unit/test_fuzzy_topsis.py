"""Tests for triangular fuzzy TOPSIS ranking."""

import pytest

from greensmecapt.assessment.cohort import (
    CohortConfiguration,
    run_comparable_topsis,
)
from greensmecapt.assessment.fuzzy_topsis import (
    FuzzyTopsisError,
    run_fuzzy_topsis,
    triangular_distance,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
    TriangularFuzzyNumber,
)


def _criterion(
    criterion_id: str,
    lower: float,
    modal: float,
    upper: float,
    weight: float = 1.0,
) -> NormalizedCriterionInput:
    return NormalizedCriterionInput(
        criterion_id=criterion_id,
        fuzzy_value=TriangularFuzzyNumber(
            lower=lower,
            modal=modal,
            upper=upper,
        ),
        base_weight=weight,
        source_status="ready_linguistic",
        response_ids=(f"response_{criterion_id}",),
    )


def _assessment(
    sme_id: str,
    criteria: tuple[NormalizedCriterionInput, ...],
) -> NormalizedAssessmentInputs:
    return NormalizedAssessmentInputs(
        sme_id=sme_id,
        normalization_policy_id="normalization_policy",
        normalization_policy_version="1.0",
        readiness=AssessmentReadiness.READY,
        coverage_ratio=1.0,
        criteria=criteria,
        issues=(),
    )


def _inputs() -> tuple[NormalizedAssessmentInputs, ...]:
    return (
        _assessment(
            "sme_green",
            (
                _criterion(
                    "green_contribution",
                    0.75,
                    0.90,
                    1.00,
                    weight=2.0,
                ),
                _criterion(
                    "energy_management",
                    0.65,
                    0.80,
                    0.90,
                ),
            ),
        ),
        _assessment(
            "sme_conventional",
            (
                _criterion(
                    "green_contribution",
                    0.20,
                    0.35,
                    0.50,
                    weight=2.0,
                ),
                _criterion(
                    "energy_management",
                    0.25,
                    0.40,
                    0.55,
                ),
            ),
        ),
    )


def _cohort(inputs):
    return run_comparable_topsis(
        inputs=inputs,
        configuration=CohortConfiguration(
            cohort_id="cohort_001",
            version="1.0",
        ),
    )


def test_triangular_vertex_distance() -> None:
    distance = triangular_distance(
        TriangularFuzzyNumber(
            lower=0.0,
            modal=0.0,
            upper=0.0,
        ),
        TriangularFuzzyNumber(
            lower=1.0,
            modal=1.0,
            upper=1.0,
        ),
    )

    assert distance == pytest.approx(1.0)


def test_rank_using_complete_fuzzy_values() -> None:
    inputs = _inputs()
    result = run_fuzzy_topsis(
        inputs,
        _cohort(inputs),
    )

    assert result.ranking[0].sme_id == "sme_green"
    assert result.ranking[0].rank == 1
    assert result.ranking[0].score > 0.5

    positive = result.positive_ideal[
        "green_contribution"
    ]

    assert positive.lower > 0.0
    assert positive.lower < positive.modal
    assert positive.modal < positive.upper


def test_normalize_criterion_weights() -> None:
    inputs = _inputs()
    result = run_fuzzy_topsis(
        inputs,
        _cohort(inputs),
    )

    assert result.normalized_weights[
        "green_contribution"
    ] == pytest.approx(2 / 3)

    assert result.normalized_weights[
        "energy_management"
    ] == pytest.approx(1 / 3)

    assert sum(
        result.normalized_weights.values()
    ) == pytest.approx(1.0)


def test_reject_inputs_that_do_not_match_cohort() -> None:
    inputs = _inputs()
    cohort = _cohort(inputs)

    wrong_inputs = (
        inputs[0],
        _assessment(
            "another_sme",
            inputs[1].criteria,
        ),
    )

    with pytest.raises(
        FuzzyTopsisError,
        match="do not match",
    ):
        run_fuzzy_topsis(
            wrong_inputs,
            cohort,
        )


def test_reject_inconsistent_weights_after_cohort_creation() -> None:
    inputs = _inputs()
    cohort = _cohort(inputs)

    changed_second = _assessment(
        "sme_conventional",
        (
            _criterion(
                "green_contribution",
                0.20,
                0.35,
                0.50,
                weight=3.0,
            ),
            inputs[1].criteria[1],
        ),
    )

    with pytest.raises(
        FuzzyTopsisError,
        match="inconsistent weights",
    ):
        run_fuzzy_topsis(
            (inputs[0], changed_second),
            cohort,
        )


def test_identical_smes_receive_neutral_scores() -> None:
    original = _assessment(
        "sme_001",
        (
            _criterion(
                "criterion_1",
                0.4,
                0.5,
                0.6,
            ),
            _criterion(
                "criterion_2",
                0.6,
                0.7,
                0.8,
            ),
        ),
    )

    identical = original.model_copy(
        update={"sme_id": "sme_002"}
    )
    inputs = (original, identical)

    result = run_fuzzy_topsis(
        inputs,
        _cohort(inputs),
    )

    assert all(
        item.score == pytest.approx(0.5)
        for item in result.ranking
    )