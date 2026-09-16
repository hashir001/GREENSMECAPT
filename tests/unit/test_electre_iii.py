"""Tests for ELECTRE III SME outranking."""

from pathlib import Path

import pytest

from greensmecapt.assessment.cohort import (
    CohortConfiguration,
    run_comparable_topsis,
)
from greensmecapt.assessment.electre_iii import (
    ElectreIIIConfiguration,
    ElectreIIIError,
    ElectreThreshold,
    PairRelation,
    load_electre_configuration,
    run_electre_iii,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
    TriangularFuzzyNumber,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION_PATH = (
    PROJECT_ROOT
    / "config"
    / "electre_iii.development.json"
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
) -> NormalizedAssessmentInputs:
    return NormalizedAssessmentInputs(
        sme_id=sme_id,
        normalization_policy_id="normalization_policy",
        normalization_policy_version="1.0",
        readiness=AssessmentReadiness.READY,
        coverage_ratio=1.0,
        criteria=tuple(
            _criterion(criterion_id, value)
            for criterion_id, value in values.items()
        ),
        issues=(),
    )


def _configuration(
    criterion_ids: tuple[str, ...],
) -> ElectreIIIConfiguration:
    return ElectreIIIConfiguration(
        configuration_id="electre_test",
        version="1.0",
        credibility_cutoff=0.65,
        thresholds=tuple(
            ElectreThreshold(
                criterion_id=criterion_id,
                indifference=0.05,
                preference=0.15,
                veto=0.4,
            )
            for criterion_id in criterion_ids
        ),
    )


def _run(
    first: NormalizedAssessmentInputs,
    second: NormalizedAssessmentInputs,
):
    inputs = (first, second)
    cohort = run_comparable_topsis(
        inputs,
        CohortConfiguration(
            cohort_id="cohort_001",
            version="1.0",
            minimum_shared_criteria=2,
        ),
    )
    criterion_ids = cohort.shared_criterion_ids

    return run_electre_iii(
        inputs,
        cohort,
        _configuration(criterion_ids),
    )


def test_clear_preference_creates_rank_levels() -> None:
    result = _run(
        _assessment(
            "strong_sme",
            {
                "criterion_1": 0.9,
                "criterion_2": 0.8,
            },
        ),
        _assessment(
            "weaker_sme",
            {
                "criterion_1": 0.4,
                "criterion_2": 0.3,
            },
        ),
    )

    relation = result.pair_relations[0]

    assert relation.relation is PairRelation.LEFT_PREFERRED
    assert result.rank_levels[0].sme_ids == ("strong_sme",)
    assert result.rank_levels[1].sme_ids == ("weaker_sme",)


def test_similar_smes_can_be_indifferent() -> None:
    result = _run(
        _assessment(
            "sme_a",
            {
                "criterion_1": 0.70,
                "criterion_2": 0.60,
            },
        ),
        _assessment(
            "sme_b",
            {
                "criterion_1": 0.72,
                "criterion_2": 0.62,
            },
        ),
    )

    assert (
        result.pair_relations[0].relation
        is PairRelation.INDIFFERENT
    )


def test_strong_tradeoff_can_produce_incomparability() -> None:
    result = _run(
        _assessment(
            "sme_a",
            {
                "criterion_1": 0.9,
                "criterion_2": 0.2,
            },
        ),
        _assessment(
            "sme_b",
            {
                "criterion_1": 0.2,
                "criterion_2": 0.9,
            },
        ),
    )

    assert (
        result.pair_relations[0].relation
        is PairRelation.INCOMPARABLE
    )
    assert result.incomparable_pairs == (
        ("sme_a", "sme_b"),
    )


def test_veto_blocks_otherwise_supported_outranking() -> None:
    first = _assessment(
        "sme_a",
        {
            "criterion_1": 0.9,
            "criterion_2": 0.9,
            "criterion_3": 0.1,
        },
    )
    second = _assessment(
        "sme_b",
        {
            "criterion_1": 0.4,
            "criterion_2": 0.4,
            "criterion_3": 0.9,
        },
    )
    inputs = (first, second)
    cohort = run_comparable_topsis(
        inputs,
        CohortConfiguration(
            cohort_id="cohort_001",
            version="1.0",
            minimum_shared_criteria=3,
        ),
    )

    result = run_electre_iii(
        inputs,
        cohort,
        _configuration(cohort.shared_criterion_ids),
    )

    a_over_b = next(
        relation
        for relation in result.ordered_outrankings
        if (
            relation.source_sme_id == "sme_a"
            and relation.target_sme_id == "sme_b"
        )
    )

    assert a_over_b.vetoed
    assert a_over_b.credibility == pytest.approx(0.0)
    assert not a_over_b.outranks


def test_reject_missing_threshold() -> None:
    first = _assessment(
        "sme_a",
        {
            "criterion_1": 0.8,
            "criterion_2": 0.7,
        },
    )
    second = _assessment(
        "sme_b",
        {
            "criterion_1": 0.6,
            "criterion_2": 0.5,
        },
    )
    inputs = (first, second)
    cohort = run_comparable_topsis(
        inputs,
        CohortConfiguration(
            cohort_id="cohort_001",
            version="1.0",
        ),
    )

    with pytest.raises(
        ElectreIIIError,
        match="No ELECTRE thresholds",
    ):
        run_electre_iii(
            inputs,
            cohort,
            _configuration(("criterion_1",)),
        )


def test_load_project_electre_configuration() -> None:
    configuration = load_electre_configuration(
        CONFIGURATION_PATH
    )

    assert configuration.credibility_cutoff == 0.65
    assert len(configuration.thresholds) == 6