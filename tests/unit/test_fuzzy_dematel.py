"""Tests for group-balanced fuzzy DEMATEL."""

from pathlib import Path

import pytest

from greensmecapt.assessment.fuzzy_dematel import (
    DematelSpecification,
    ExpertInfluenceAssessment,
    FactorRole,
    FuzzyDematelError,
    FuzzyInfluence,
    InfluenceJudgment,
    StakeholderAggregation,
    load_dematel_specification,
    run_fuzzy_dematel,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION_PATH = (
    PROJECT_ROOT
    / "config"
    / "dematel_specification.development.json"
)


def _specification() -> DematelSpecification:
    return DematelSpecification(
        specification_id="test_dematel",
        version="1.0",
        factor_ids=(
            "policy",
            "technology",
            "internal",
        ),
        stakeholder_groups=(
            "academics",
            "lenders",
        ),
        aggregation=(
            StakeholderAggregation.GROUP_BALANCED
        ),
        convergence_margin=0.999,
        linguistic_scale={
            "none": FuzzyInfluence(
                lower=0.0,
                modal=0.0,
                upper=0.0,
            ),
            "low": FuzzyInfluence(
                lower=0.1,
                modal=0.25,
                upper=0.4,
            ),
            "medium": FuzzyInfluence(
                lower=0.3,
                modal=0.5,
                upper=0.7,
            ),
            "high": FuzzyInfluence(
                lower=0.6,
                modal=0.8,
                upper=1.0,
            ),
        },
    )


def _judgments(
    values: dict[tuple[str, str], str],
) -> tuple[InfluenceJudgment, ...]:
    return tuple(
        InfluenceJudgment(
            source_factor_id=source,
            target_factor_id=target,
            linguistic_value=value,
        )
        for (source, target), value in values.items()
    )


def _academic(
    expert_id: str = "academic_001",
) -> ExpertInfluenceAssessment:
    return ExpertInfluenceAssessment(
        expert_id=expert_id,
        stakeholder_group="academics",
        judgments=_judgments(
            {
                ("policy", "technology"): "high",
                ("policy", "internal"): "medium",
                ("technology", "policy"): "low",
                ("technology", "internal"): "high",
                ("internal", "policy"): "low",
                ("internal", "technology"): "medium",
            }
        ),
    )


def _lender() -> ExpertInfluenceAssessment:
    return ExpertInfluenceAssessment(
        expert_id="lender_001",
        stakeholder_group="lenders",
        judgments=_judgments(
            {
                ("policy", "technology"): "medium",
                ("policy", "internal"): "high",
                ("technology", "policy"): "low",
                ("technology", "internal"): "medium",
                ("internal", "policy"): "low",
                ("internal", "technology"): "low",
            }
        ),
    )


def test_run_group_balanced_fuzzy_dematel() -> None:
    result = run_fuzzy_dematel(
        _specification(),
        (
            _academic(),
            _lender(),
        ),
    )

    assert sum(
        result.normalized_weights.values()
    ) == pytest.approx(1.0)

    assert result.cause_factors
    assert result.effect_factors

    policy = next(
        factor
        for factor in result.factors
        if factor.factor_id == "policy"
    )

    assert policy.role is FactorRole.CAUSE
    assert (
        len(result.total_relation_matrix.values)
        == 3
    )


def test_group_balancing_prevents_large_group_domination() -> None:
    specification = _specification()

    original = run_fuzzy_dematel(
        specification,
        (
            _academic(),
            _lender(),
        ),
    )

    duplicated_academic = _academic(
        expert_id="academic_002"
    )

    duplicated = run_fuzzy_dematel(
        specification,
        (
            _academic(),
            duplicated_academic,
            _lender(),
        ),
    )

    for factor_id in specification.factor_ids:
        assert duplicated.normalized_weights[
            factor_id
        ] == pytest.approx(
            original.normalized_weights[factor_id]
        )


def test_reject_incomplete_expert_matrix() -> None:
    incomplete = ExpertInfluenceAssessment(
        expert_id="academic_001",
        stakeholder_group="academics",
        judgments=(
            InfluenceJudgment(
                source_factor_id="policy",
                target_factor_id="technology",
                linguistic_value="high",
            ),
        ),
    )

    with pytest.raises(
        FuzzyDematelError,
        match="complete directed matrix",
    ):
        run_fuzzy_dematel(
            _specification(),
            (
                incomplete,
                _lender(),
            ),
        )


def test_reject_missing_stakeholder_group() -> None:
    with pytest.raises(
        FuzzyDematelError,
        match="Stakeholder groups",
    ):
        run_fuzzy_dematel(
            _specification(),
            (_academic(),),
        )


def test_convergence_margin_handles_symmetric_influence() -> None:
    specification = DematelSpecification(
        specification_id="symmetric_test",
        version="1.0",
        factor_ids=("factor_a", "factor_b"),
        stakeholder_groups=("academics",),
        convergence_margin=0.999,
        linguistic_scale={
            "none": FuzzyInfluence(
                lower=0.0,
                modal=0.0,
                upper=0.0,
            ),
            "high": FuzzyInfluence(
                lower=0.6,
                modal=0.8,
                upper=1.0,
            ),
        },
    )

    assessment = ExpertInfluenceAssessment(
        expert_id="academic_001",
        stakeholder_group="academics",
        judgments=(
            InfluenceJudgment(
                source_factor_id="factor_a",
                target_factor_id="factor_b",
                linguistic_value="high",
            ),
            InfluenceJudgment(
                source_factor_id="factor_b",
                target_factor_id="factor_a",
                linguistic_value="high",
            ),
        ),
    )

    result = run_fuzzy_dematel(
        specification,
        (assessment,),
    )

    assert all(
        factor.role is FactorRole.NEUTRAL
        for factor in result.factors
    )

    assert all(
        factor.normalized_weight
        == pytest.approx(0.5)
        for factor in result.factors
    )


def test_load_project_driver_specification() -> None:
    specification = load_dematel_specification(
        SPECIFICATION_PATH
    )

    assert specification.factor_ids == (
        "policy",
        "social",
        "technology",
        "internal",
    )

    assert specification.stakeholder_groups == (
        "academics",
        "government",
        "sme_managers",
        "lenders",
    )