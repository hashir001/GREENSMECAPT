"""Tests for ranking sensitivity and cross-method agreement."""

import pytest

from greensmecapt.assessment.cohort import (
    CohortConfiguration,
    run_comparable_topsis,
)
from greensmecapt.assessment.electre_iii import (
    ElectreIIIConfiguration,
    ElectreThreshold,
    run_electre_iii,
)
from greensmecapt.assessment.fuzzy_topsis import (
    run_fuzzy_topsis,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
    TriangularFuzzyNumber,
)
from greensmecapt.assessment.robustness import (
    RobustnessConfiguration,
    analyze_ranking_robustness,
)


def _criterion(
    criterion_id: str,
    value: float,
    weight: float,
) -> NormalizedCriterionInput:
    return NormalizedCriterionInput(
        criterion_id=criterion_id,
        fuzzy_value=TriangularFuzzyNumber(
            lower=max(
                0.0,
                value - 0.05,
            ),
            modal=value,
            upper=min(
                1.0,
                value + 0.05,
            ),
        ),
        base_weight=weight,
        source_status="ready_linguistic",
        response_ids=(
            f"response_{criterion_id}",
        ),
    )


def _input(
    sme_id: str,
    first: float,
    second: float,
) -> NormalizedAssessmentInputs:
    return NormalizedAssessmentInputs(
        sme_id=sme_id,
        normalization_policy_id="policy_001",
        normalization_policy_version="1.0",
        readiness=AssessmentReadiness.READY,
        coverage_ratio=1.0,
        criteria=(
            _criterion(
                "impact",
                first,
                0.6,
            ),
            _criterion(
                "execution",
                second,
                0.4,
            ),
        ),
        issues=(),
    )


def _analysis_inputs():
    inputs = (
        _input(
            "sme_strong",
            0.90,
            0.80,
        ),
        _input(
            "sme_middle",
            0.65,
            0.60,
        ),
        _input(
            "sme_weaker",
            0.35,
            0.40,
        ),
    )
    cohort_configuration = CohortConfiguration(
        cohort_id="cohort_001",
        version="1.0",
        minimum_shared_criteria=2,
    )
    electre_configuration = (
        ElectreIIIConfiguration(
            configuration_id="electre_001",
            version="1.0",
            thresholds=(
                ElectreThreshold(
                    criterion_id="impact",
                    indifference=0.05,
                    preference=0.15,
                    veto=0.40,
                ),
                ElectreThreshold(
                    criterion_id="execution",
                    indifference=0.05,
                    preference=0.15,
                    veto=0.40,
                ),
            ),
        )
    )
    cohort = run_comparable_topsis(
        inputs,
        cohort_configuration,
    )
    fuzzy = run_fuzzy_topsis(
        inputs,
        cohort,
    )
    electre = run_electre_iii(
        inputs,
        cohort,
        electre_configuration,
    )

    return (
        inputs,
        cohort_configuration,
        electre_configuration,
        cohort,
        fuzzy,
        electre,
    )


def test_clear_leader_is_stable() -> None:
    (
        inputs,
        cohort_configuration,
        electre_configuration,
        cohort,
        fuzzy,
        electre,
    ) = _analysis_inputs()

    result = analyze_ranking_robustness(
        inputs=inputs,
        cohort_configuration=(
            cohort_configuration
        ),
        electre_configuration=(
            electre_configuration
        ),
        baseline_topsis=cohort,
        baseline_fuzzy_topsis=fuzzy,
        baseline_electre=electre,
        configuration=RobustnessConfiguration(
            iterations=50,
            random_seed=7,
        ),
    )

    strong = next(
        item
        for item in result.sme_stability
        if item.sme_id == "sme_strong"
    )

    assert result.completed_scenarios == 50
    assert result.rejected_scenarios == 0
    assert (
        strong.first_place_rates["topsis"]
        == 1.0
    )
    assert (
        strong.first_place_rates["fuzzy_topsis"]
        == 1.0
    )
    assert strong.mean_ranks["topsis"] == 1.0
    assert result.warnings == ()


def test_analysis_is_reproducible() -> None:
    values = _analysis_inputs()
    configuration = RobustnessConfiguration(
        iterations=30,
        random_seed=123,
    )

    first = analyze_ranking_robustness(
        inputs=values[0],
        cohort_configuration=values[1],
        electre_configuration=values[2],
        baseline_topsis=values[3],
        baseline_fuzzy_topsis=values[4],
        baseline_electre=values[5],
        configuration=configuration,
    )
    second = analyze_ranking_robustness(
        inputs=values[0],
        cohort_configuration=values[1],
        electre_configuration=values[2],
        baseline_topsis=values[3],
        baseline_fuzzy_topsis=values[4],
        baseline_electre=values[5],
        configuration=configuration,
    )

    assert first == second


def test_method_agreement_is_bounded() -> None:
    values = _analysis_inputs()

    result = analyze_ranking_robustness(
        inputs=values[0],
        cohort_configuration=values[1],
        electre_configuration=values[2],
        baseline_topsis=values[3],
        baseline_fuzzy_topsis=values[4],
        baseline_electre=values[5],
        configuration=RobustnessConfiguration(
            iterations=20,
        ),
    )

    assert len(result.baseline_agreement) == 3
    assert all(
        0.0 <= item.agreement_rate <= 1.0
        for item in result.baseline_agreement
    )
    assert sum(
        item.agreement_rate
        for item in result.baseline_agreement
    ) == pytest.approx(3.0)