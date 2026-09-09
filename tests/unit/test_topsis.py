"""Tests for TOPSIS SME scoring and ranking."""

import pytest

from greensmecapt.assessment.input_models import (
    IndicatorDefinition,
    InputStatus,
    NumericDirection,
    ResolvedIndicator,
    SMEAssessmentInput,
)
from greensmecapt.assessment.topsis import (
    IndicatorWeight,
    TopsisConfiguration,
    TopsisError,
    run_topsis,
)


def _definition(
    indicator_id: str,
    direction: NumericDirection = NumericDirection.BENEFIT,
) -> IndicatorDefinition:
    return IndicatorDefinition(
        indicator_id=indicator_id,
        criterion_id=indicator_id,
        name=indicator_id.replace("_", " ").title(),
        unit="score",
        direction=direction,
        minimum=0,
        maximum=100,
    )


def _input(
    sme_id: str,
    definitions: tuple[IndicatorDefinition, ...],
    values: tuple[float, ...],
    *,
    specification_id: str = "green_assessment",
    specification_version: str = "0.1.0",
) -> SMEAssessmentInput:
    return SMEAssessmentInput(
        sme_id=sme_id,
        specification_id=specification_id,
        specification_version=specification_version,
        indicators=tuple(
            ResolvedIndicator(
                definition=definition,
                status=InputStatus.READY,
                value=value,
                evidence_ids=(
                    f"evidence_{sme_id}_{definition.indicator_id}",
                ),
            )
            for definition, value in zip(
                definitions,
                values,
                strict=True,
            )
        ),
    )


def _configuration(
    *weights: tuple[str, float],
) -> TopsisConfiguration:
    return TopsisConfiguration(
        configuration_id="topsis_test",
        version="0.1.0",
        weights=tuple(
            IndicatorWeight(
                indicator_id=indicator_id,
                weight=weight,
            )
            for indicator_id, weight in weights
        ),
    )


def test_rank_dominant_sme_first() -> None:
    definitions = (
        _definition("green_performance"),
        _definition(
            "environmental_cost",
            NumericDirection.COST,
        ),
    )

    result = run_topsis(
        (
            _input("eco_pack", definitions, (100.0, 10.0)),
            _input("green_forge", definitions, (50.0, 20.0)),
        ),
        _configuration(
            ("green_performance", 0.6),
            ("environmental_cost", 0.4),
        ),
    )

    assert result.ranking[0].sme_id == "eco_pack"
    assert result.ranking[0].score == pytest.approx(1.0)
    assert result.ranking[1].score == pytest.approx(0.0)


def test_weights_control_tradeoff_transparently() -> None:
    definitions = (
        _definition("renewable_energy"),
        _definition("financial_strength"),
    )

    result = run_topsis(
        (
            _input("renewable_leader", definitions, (100.0, 0.0)),
            _input("financial_leader", definitions, (0.0, 100.0)),
        ),
        _configuration(
            ("renewable_energy", 8.0),
            ("financial_strength", 2.0),
        ),
    )

    assert result.normalized_weights == {
        "renewable_energy": pytest.approx(0.8),
        "financial_strength": pytest.approx(0.2),
    }
    assert result.ranking[0].sme_id == "renewable_leader"
    assert result.ranking[0].score == pytest.approx(0.8)
    assert result.ranking[1].score == pytest.approx(0.2)


def test_cost_direction_prefers_lower_value() -> None:
    definitions = (
        _definition(
            "energy_intensity",
            NumericDirection.COST,
        ),
    )

    result = run_topsis(
        (
            _input("efficient_sme", definitions, (20.0,)),
            _input("intensive_sme", definitions, (80.0,)),
        ),
        _configuration(("energy_intensity", 1.0)),
    )

    assert result.ranking[0].sme_id == "efficient_sme"
    assert result.ranking[0].score == pytest.approx(1.0)


def test_identical_smes_receive_neutral_scores() -> None:
    definitions = (_definition("green_performance"),)

    result = run_topsis(
        (
            _input("sme_a", definitions, (50.0,)),
            _input("sme_b", definitions, (50.0,)),
        ),
        _configuration(("green_performance", 1.0)),
    )

    assert all(
        item.score == pytest.approx(0.5)
        for item in result.ranking
    )


def test_reject_unresolved_indicator() -> None:
    definition = _definition("green_performance")

    unresolved = SMEAssessmentInput(
        sme_id="sme_a",
        specification_id="green_assessment",
        specification_version="0.1.0",
        indicators=(
            ResolvedIndicator(
                definition=definition,
                status=InputStatus.MISSING,
                issues=("No accepted evidence is available.",),
            ),
        ),
    )

    ready = _input("sme_b", (definition,), (50.0,))

    with pytest.raises(TopsisError, match="unresolved"):
        run_topsis(
            (unresolved, ready),
            _configuration(("green_performance", 1.0)),
        )


def test_reject_missing_or_unexpected_weight() -> None:
    definitions = (
        _definition("green_performance"),
        _definition("financial_strength"),
    )

    inputs = (
        _input("sme_a", definitions, (80.0, 60.0)),
        _input("sme_b", definitions, (60.0, 80.0)),
    )

    with pytest.raises(TopsisError, match="do not match"):
        run_topsis(
            inputs,
            _configuration(
                ("green_performance", 1.0),
                ("unrelated_indicator", 1.0),
            ),
        )


def test_reject_different_specification_versions() -> None:
    definitions = (_definition("green_performance"),)

    with pytest.raises(TopsisError, match="same assessment"):
        run_topsis(
            (
                _input("sme_a", definitions, (80.0,)),
                _input(
                    "sme_b",
                    definitions,
                    (60.0,),
                    specification_version="0.2.0",
                ),
            ),
            _configuration(("green_performance", 1.0)),
        )


def test_reject_duplicate_sme_ids() -> None:
    definitions = (_definition("green_performance"),)
    sme = _input("sme_a", definitions, (80.0,))

    with pytest.raises(TopsisError, match="unique"):
        run_topsis(
            (sme, sme),
            _configuration(("green_performance", 1.0)),
        )


def test_require_at_least_two_smes() -> None:
    definitions = (_definition("green_performance"),)

    with pytest.raises(TopsisError, match="at least two"):
        run_topsis(
            (_input("sme_a", definitions, (80.0,)),),
            _configuration(("green_performance", 1.0)),
        )