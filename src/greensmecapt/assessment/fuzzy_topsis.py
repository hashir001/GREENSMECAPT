"""Fuzzy TOPSIS ranking using triangular fuzzy assessment inputs."""

from collections.abc import Sequence
from math import sqrt

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.cohort import (
    CohortComparisonStatus,
    ComparableTopsisResult,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
    TriangularFuzzyNumber,
)


class FuzzyTopsisError(ValueError):
    """Raised when fuzzy TOPSIS receives inconsistent cohort inputs."""


class FuzzyTopsisModel(BaseModel):
    """Provide immutable fuzzy TOPSIS result contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class FuzzyTopsisSMEResult(FuzzyTopsisModel):
    """Store one SME's fuzzy TOPSIS distances and ranking."""

    sme_id: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)
    distance_to_ideal: float = Field(ge=0.0)
    distance_to_worst: float = Field(ge=0.0)


class FuzzyTopsisResult(FuzzyTopsisModel):
    """Store a reproducible fuzzy TOPSIS cohort result."""

    cohort_id: str = Field(min_length=1)
    cohort_version: str = Field(min_length=1)
    normalization_policy_id: str = Field(min_length=1)
    normalization_policy_version: str = Field(min_length=1)
    comparison_status: CohortComparisonStatus
    shared_criterion_ids: tuple[str, ...] = Field(min_length=1)
    normalized_weights: dict[str, float]
    positive_ideal: dict[str, TriangularFuzzyNumber]
    negative_ideal: dict[str, TriangularFuzzyNumber]
    ranking: tuple[FuzzyTopsisSMEResult, ...] = Field(min_length=2)
    crisp_reference_ranking: tuple[str, ...] = Field(min_length=2)
    ranking_changed_from_crisp: bool


def triangular_distance(
    first: TriangularFuzzyNumber,
    second: TriangularFuzzyNumber,
) -> float:
    """Calculate vertex distance between triangular fuzzy numbers."""

    return sqrt(
        (
            (first.lower - second.lower) ** 2
            + (first.modal - second.modal) ** 2
            + (first.upper - second.upper) ** 2
        )
        / 3.0
    )


def run_fuzzy_topsis(
    inputs: Sequence[NormalizedAssessmentInputs],
    cohort: ComparableTopsisResult,
) -> FuzzyTopsisResult:
    """Rank an already-approved comparable cohort using fuzzy TOPSIS."""

    criterion_maps = _validate_and_map_inputs(
        inputs,
        cohort,
    )

    weights = _resolve_weights(
        criterion_maps,
        cohort.shared_criterion_ids,
    )
    total_weight = sum(weights.values())

    normalized_weights = {
        criterion_id: weights[criterion_id] / total_weight
        for criterion_id in cohort.shared_criterion_ids
    }

    weighted_values = {
        item.sme_id: {
            criterion_id: _apply_weight(
                criterion_maps[item.sme_id][
                    criterion_id
                ].fuzzy_value,
                normalized_weights[criterion_id],
            )
            for criterion_id in cohort.shared_criterion_ids
        }
        for item in inputs
    }

    positive_ideal = {
        criterion_id: _positive_ideal(
            [
                weighted_values[item.sme_id][criterion_id]
                for item in inputs
            ]
        )
        for criterion_id in cohort.shared_criterion_ids
    }

    negative_ideal = {
        criterion_id: _negative_ideal(
            [
                weighted_values[item.sme_id][criterion_id]
                for item in inputs
            ]
        )
        for criterion_id in cohort.shared_criterion_ids
    }

    raw_results: list[
        tuple[str, float, float, float]
    ] = []

    for item in inputs:
        values = weighted_values[item.sme_id]

        distance_to_ideal = sum(
            triangular_distance(
                values[criterion_id],
                positive_ideal[criterion_id],
            )
            for criterion_id in cohort.shared_criterion_ids
        )

        distance_to_worst = sum(
            triangular_distance(
                values[criterion_id],
                negative_ideal[criterion_id],
            )
            for criterion_id in cohort.shared_criterion_ids
        )

        denominator = (
            distance_to_ideal + distance_to_worst
        )

        score = (
            distance_to_worst / denominator
            if denominator > 0.0
            else 0.5
        )

        raw_results.append(
            (
                item.sme_id,
                score,
                distance_to_ideal,
                distance_to_worst,
            )
        )

    ordered = sorted(
        raw_results,
        key=lambda result: (-result[1], result[0]),
    )

    ranking = tuple(
        FuzzyTopsisSMEResult(
            sme_id=sme_id,
            score=score,
            rank=rank,
            distance_to_ideal=distance_to_ideal,
            distance_to_worst=distance_to_worst,
        )
        for rank, (
            sme_id,
            score,
            distance_to_ideal,
            distance_to_worst,
        ) in enumerate(ordered, start=1)
    )

    fuzzy_ranking = tuple(
        item.sme_id for item in ranking
    )
    crisp_ranking = tuple(
        item.sme_id
        for item in cohort.topsis_result.ranking
    )

    return FuzzyTopsisResult(
        cohort_id=cohort.cohort_id,
        cohort_version=cohort.cohort_version,
        normalization_policy_id=(
            cohort.normalization_policy_id
        ),
        normalization_policy_version=(
            cohort.normalization_policy_version
        ),
        comparison_status=cohort.comparison_status,
        shared_criterion_ids=(
            cohort.shared_criterion_ids
        ),
        normalized_weights=normalized_weights,
        positive_ideal=positive_ideal,
        negative_ideal=negative_ideal,
        ranking=ranking,
        crisp_reference_ranking=crisp_ranking,
        ranking_changed_from_crisp=(
            fuzzy_ranking != crisp_ranking
        ),
    )


def _validate_and_map_inputs(
    inputs: Sequence[NormalizedAssessmentInputs],
    cohort: ComparableTopsisResult,
) -> dict[
    str,
    dict[str, NormalizedCriterionInput],
]:
    if len(inputs) < 2:
        raise FuzzyTopsisError(
            "Fuzzy TOPSIS requires at least two SMEs."
        )

    sme_ids = [item.sme_id for item in inputs]

    if len(sme_ids) != len(set(sme_ids)):
        raise FuzzyTopsisError(
            "SME IDs must be unique."
        )

    expected_sme_ids = {
        item.sme_id for item in cohort.coverage
    }

    if set(sme_ids) != expected_sme_ids:
        raise FuzzyTopsisError(
            "Fuzzy inputs do not match the prepared cohort SMEs."
        )

    criterion_maps: dict[
        str,
        dict[str, NormalizedCriterionInput],
    ] = {}

    for item in inputs:
        if item.readiness is AssessmentReadiness.BLOCKED:
            raise FuzzyTopsisError(
                f"SME {item.sme_id!r} is blocked."
            )

        if (
            item.normalization_policy_id
            != cohort.normalization_policy_id
            or item.normalization_policy_version
            != cohort.normalization_policy_version
        ):
            raise FuzzyTopsisError(
                "Fuzzy inputs use a different normalization policy."
            )

        criterion_map = {
            criterion.criterion_id: criterion
            for criterion in item.criteria
        }

        if len(criterion_map) != len(item.criteria):
            raise FuzzyTopsisError(
                f"SME {item.sme_id!r} contains duplicate criteria."
            )

        missing = (
            set(cohort.shared_criterion_ids)
            - criterion_map.keys()
        )

        if missing:
            raise FuzzyTopsisError(
                f"SME {item.sme_id!r} is missing shared criteria: "
                f"{sorted(missing)}."
            )

        for criterion_id in cohort.shared_criterion_ids:
            criterion = criterion_map[criterion_id]

            if (
                not criterion.evidence_ids
                and not criterion.response_ids
            ):
                raise FuzzyTopsisError(
                    f"SME {item.sme_id!r}, criterion "
                    f"{criterion_id!r} has no provenance."
                )

        criterion_maps[item.sme_id] = criterion_map

    return criterion_maps


def _resolve_weights(
    criterion_maps: dict[
        str,
        dict[str, NormalizedCriterionInput],
    ],
    criterion_ids: tuple[str, ...],
) -> dict[str, float]:
    weights: dict[str, float] = {}

    for criterion_id in criterion_ids:
        candidates = {
            mapping[criterion_id].base_weight
            for mapping in criterion_maps.values()
        }

        if len(candidates) != 1:
            raise FuzzyTopsisError(
                f"Criterion {criterion_id!r} has "
                "inconsistent weights."
            )

        weights[criterion_id] = next(iter(candidates))

    return weights


def _apply_weight(
    value: TriangularFuzzyNumber,
    weight: float,
) -> TriangularFuzzyNumber:
    return TriangularFuzzyNumber(
        lower=value.lower * weight,
        modal=value.modal * weight,
        upper=value.upper * weight,
    )


def _positive_ideal(
    values: Sequence[TriangularFuzzyNumber],
) -> TriangularFuzzyNumber:
    return TriangularFuzzyNumber(
        lower=max(value.lower for value in values),
        modal=max(value.modal for value in values),
        upper=max(value.upper for value in values),
    )


def _negative_ideal(
    values: Sequence[TriangularFuzzyNumber],
) -> TriangularFuzzyNumber:
    return TriangularFuzzyNumber(
        lower=min(value.lower for value in values),
        modal=min(value.modal for value in values),
        upper=min(value.upper for value in values),
    )