"""Sensitivity and cross-method agreement analysis for SME rankings."""

from collections.abc import Mapping, Sequence
from itertools import combinations
from random import Random

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.cohort import (
    CohortComparisonError,
    CohortConfiguration,
    ComparableTopsisResult,
    run_comparable_topsis,
)
from greensmecapt.assessment.electre_iii import (
    ElectreIIIConfiguration,
    ElectreIIIError,
    ElectreIIIResult,
    ElectreThreshold,
    run_electre_iii,
)
from greensmecapt.assessment.fuzzy_topsis import (
    FuzzyTopsisError,
    FuzzyTopsisResult,
    run_fuzzy_topsis,
)
from greensmecapt.assessment.normalization import (
    NormalizedAssessmentInputs,
)


class RankingRobustnessError(ValueError):
    """Raised when no valid sensitivity analysis can be produced."""


class RobustnessModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class RobustnessConfiguration(RobustnessModel):
    """Configure deterministic development sensitivity analysis."""

    iterations: int = Field(
        default=200,
        ge=20,
        le=10_000,
    )
    weight_variation: float = Field(
        default=0.20,
        ge=0.0,
        le=0.75,
    )
    threshold_variation: float = Field(
        default=0.15,
        ge=0.0,
        le=0.75,
    )
    random_seed: int = 20_260_917
    stable_first_place_rate: float = Field(
        default=0.75,
        gt=0.0,
        le=1.0,
    )


class MethodAgreement(RobustnessModel):
    """Measure whether two methods order SME pairs similarly."""

    first_method: str = Field(min_length=1)
    second_method: str = Field(min_length=1)
    agreement_rate: float = Field(
        ge=0.0,
        le=1.0,
    )


class SMERankingStability(RobustnessModel):
    """Summarize one SME's positions across valid scenarios."""

    sme_id: str = Field(min_length=1)
    baseline_ranks: dict[str, int]
    first_place_rates: dict[str, float]
    mean_ranks: dict[str, float]
    best_ranks: dict[str, int]
    worst_ranks: dict[str, int]


class RankingRobustnessResult(RobustnessModel):
    """Explain method agreement and ranking sensitivity."""

    configuration: RobustnessConfiguration
    completed_scenarios: int = Field(ge=1)
    rejected_scenarios: int = Field(ge=0)
    baseline_agreement: tuple[MethodAgreement, ...]
    sme_stability: tuple[SMERankingStability, ...] = Field(
        min_length=2
    )
    warnings: tuple[str, ...] = ()


def analyze_ranking_robustness(
    *,
    inputs: Sequence[NormalizedAssessmentInputs],
    cohort_configuration: CohortConfiguration,
    electre_configuration: ElectreIIIConfiguration,
    baseline_topsis: ComparableTopsisResult,
    baseline_fuzzy_topsis: FuzzyTopsisResult,
    baseline_electre: ElectreIIIResult,
    configuration: RobustnessConfiguration | None = None,
) -> RankingRobustnessResult:
    """Perturb weights and thresholds and measure ranking stability."""

    selected = configuration or RobustnessConfiguration()
    baseline_rankings = {
        "topsis": _topsis_ranks(
            baseline_topsis
        ),
        "fuzzy_topsis": _fuzzy_ranks(
            baseline_fuzzy_topsis
        ),
        "electre_iii": _electre_ranks(
            baseline_electre
        ),
    }
    sme_ids = tuple(
        sorted(baseline_rankings["topsis"])
    )

    _validate_ranking_membership(
        baseline_rankings,
        sme_ids,
    )

    recorded: dict[
        str,
        dict[str, list[int]],
    ] = {
        method: {
            sme_id: []
            for sme_id in sme_ids
        }
        for method in baseline_rankings
    }

    random = Random(selected.random_seed)
    rejected = 0

    for _ in range(selected.iterations):
        perturbed_inputs = _perturb_weights(
            inputs,
            variation=selected.weight_variation,
            random=random,
        )
        perturbed_electre = _perturb_thresholds(
            electre_configuration,
            variation=selected.threshold_variation,
            random=random,
        )

        try:
            cohort = run_comparable_topsis(
                perturbed_inputs,
                cohort_configuration,
            )
            fuzzy = run_fuzzy_topsis(
                perturbed_inputs,
                cohort,
            )
            electre = run_electre_iii(
                perturbed_inputs,
                cohort,
                perturbed_electre,
            )
        except (
            CohortComparisonError,
            FuzzyTopsisError,
            ElectreIIIError,
        ):
            rejected += 1
            continue

        scenario_rankings = {
            "topsis": _topsis_ranks(cohort),
            "fuzzy_topsis": _fuzzy_ranks(fuzzy),
            "electre_iii": _electre_ranks(electre),
        }

        _validate_ranking_membership(
            scenario_rankings,
            sme_ids,
        )

        for method, ranks in scenario_rankings.items():
            for sme_id, rank in ranks.items():
                recorded[method][sme_id].append(
                    rank
                )

    completed = selected.iterations - rejected

    if completed == 0:
        raise RankingRobustnessError(
            "Every sensitivity scenario was rejected."
        )

    stability = tuple(
        _summarize_sme(
            sme_id=sme_id,
            baseline_rankings=baseline_rankings,
            recorded=recorded,
            completed=completed,
        )
        for sme_id in sme_ids
    )
    warnings = _stability_warnings(
        stability,
        selected.stable_first_place_rate,
    )

    return RankingRobustnessResult(
        configuration=selected,
        completed_scenarios=completed,
        rejected_scenarios=rejected,
        baseline_agreement=_method_agreement(
            baseline_rankings,
            sme_ids,
        ),
        sme_stability=stability,
        warnings=warnings,
    )


def _perturb_weights(
    inputs: Sequence[NormalizedAssessmentInputs],
    *,
    variation: float,
    random: Random,
) -> tuple[NormalizedAssessmentInputs, ...]:
    criterion_ids = sorted(
        {
            criterion.criterion_id
            for item in inputs
            for criterion in item.criteria
        }
    )
    multipliers = {
        criterion_id: random.uniform(
            1.0 - variation,
            1.0 + variation,
        )
        for criterion_id in criterion_ids
    }

    return tuple(
        item.model_copy(
            update={
                "criteria": tuple(
                    criterion.model_copy(
                        update={
                            "base_weight": (
                                criterion.base_weight
                                * multipliers[
                                    criterion.criterion_id
                                ]
                            )
                        }
                    )
                    for criterion in item.criteria
                )
            }
        )
        for item in inputs
    )


def _perturb_thresholds(
    configuration: ElectreIIIConfiguration,
    *,
    variation: float,
    random: Random,
) -> ElectreIIIConfiguration:
    thresholds = tuple(
        _scaled_threshold(
            threshold,
            random.uniform(
                1.0 - variation,
                1.0 + variation,
            ),
        )
        for threshold in configuration.thresholds
    )

    return configuration.model_copy(
        update={
            "thresholds": thresholds,
        }
    )


def _scaled_threshold(
    threshold: ElectreThreshold,
    multiplier: float,
) -> ElectreThreshold:
    return ElectreThreshold(
        criterion_id=threshold.criterion_id,
        indifference=(
            threshold.indifference
            * multiplier
        ),
        preference=(
            threshold.preference
            * multiplier
        ),
        veto=(
            threshold.veto
            * multiplier
        ),
    )


def _topsis_ranks(
    result: ComparableTopsisResult,
) -> dict[str, int]:
    return {
        item.sme_id: item.rank
        for item in result.topsis_result.ranking
    }


def _fuzzy_ranks(
    result: FuzzyTopsisResult,
) -> dict[str, int]:
    return {
        item.sme_id: item.rank
        for item in result.ranking
    }


def _electre_ranks(
    result: ElectreIIIResult,
) -> dict[str, int]:
    return {
        sme_id: level.level
        for level in result.rank_levels
        for sme_id in level.sme_ids
    }


def _validate_ranking_membership(
    rankings: Mapping[
        str,
        Mapping[str, int],
    ],
    sme_ids: tuple[str, ...],
) -> None:
    expected = set(sme_ids)

    for method, ranks in rankings.items():
        if set(ranks) != expected:
            raise RankingRobustnessError(
                f"Method {method!r} returned different SMEs."
            )


def _method_agreement(
    rankings: Mapping[
        str,
        Mapping[str, int],
    ],
    sme_ids: tuple[str, ...],
) -> tuple[MethodAgreement, ...]:
    return tuple(
        MethodAgreement(
            first_method=first_method,
            second_method=second_method,
            agreement_rate=_pairwise_agreement(
                rankings[first_method],
                rankings[second_method],
                sme_ids,
            ),
        )
        for first_method, second_method in combinations(
            rankings,
            2,
        )
    )


def _pairwise_agreement(
    first: Mapping[str, int],
    second: Mapping[str, int],
    sme_ids: tuple[str, ...],
) -> float:
    scores: list[float] = []

    for left, right in combinations(
        sme_ids,
        2,
    ):
        first_direction = _direction(
            first[left],
            first[right],
        )
        second_direction = _direction(
            second[left],
            second[right],
        )

        if first_direction == second_direction:
            scores.append(1.0)
        elif 0 in {
            first_direction,
            second_direction,
        }:
            scores.append(0.5)
        else:
            scores.append(0.0)

    return sum(scores) / len(scores)


def _direction(
    left_rank: int,
    right_rank: int,
) -> int:
    if left_rank < right_rank:
        return -1

    if left_rank > right_rank:
        return 1

    return 0


def _summarize_sme(
    *,
    sme_id: str,
    baseline_rankings: Mapping[
        str,
        Mapping[str, int],
    ],
    recorded: Mapping[
        str,
        Mapping[str, list[int]],
    ],
    completed: int,
) -> SMERankingStability:
    method_values = {
        method: ranks[sme_id]
        for method, ranks in recorded.items()
    }

    return SMERankingStability(
        sme_id=sme_id,
        baseline_ranks={
            method: ranks[sme_id]
            for method, ranks in (
                baseline_rankings.items()
            )
        },
        first_place_rates={
            method: (
                sum(
                    rank == 1
                    for rank in ranks
                )
                / completed
            )
            for method, ranks in method_values.items()
        },
        mean_ranks={
            method: sum(ranks) / completed
            for method, ranks in method_values.items()
        },
        best_ranks={
            method: min(ranks)
            for method, ranks in method_values.items()
        },
        worst_ranks={
            method: max(ranks)
            for method, ranks in method_values.items()
        },
    )


def _stability_warnings(
    stability: Sequence[
        SMERankingStability
    ],
    threshold: float,
) -> tuple[str, ...]:
    warnings: list[str] = []

    for method in (
        "topsis",
        "fuzzy_topsis",
        "electre_iii",
    ):
        baseline_leaders = [
            item
            for item in stability
            if item.baseline_ranks[method] == 1
        ]

        for leader in baseline_leaders:
            rate = leader.first_place_rates[
                method
            ]

            if rate < threshold:
                warnings.append(
                    f"{method} leader "
                    f"{leader.sme_id!r} retains first "
                    f"place in only {rate:.1%} "
                    "of valid scenarios."
                )

    return tuple(warnings)