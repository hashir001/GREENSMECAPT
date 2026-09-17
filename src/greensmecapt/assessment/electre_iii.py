"""ELECTRE III outranking for comparable normalized SME assessments."""

import json
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.cohort import (
    CohortComparisonStatus,
    ComparableTopsisResult,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
)


class ElectreIIIError(ValueError):
    """Raised when ELECTRE III cannot run consistently."""


class ElectreModel(BaseModel):
    """Provide immutable ELECTRE III contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ElectreProjection(StrEnum):
    """Describe how fuzzy values enter ELECTRE III."""

    CENTROID = "centroid"


class PairRelation(StrEnum):
    """Describe the outranking relationship between two SMEs."""

    LEFT_PREFERRED = "left_preferred"
    RIGHT_PREFERRED = "right_preferred"
    INDIFFERENT = "indifferent"
    INCOMPARABLE = "incomparable"


class ElectreThreshold(ElectreModel):
    """Define indifference, preference and veto thresholds."""

    criterion_id: str = Field(min_length=1)
    indifference: float = Field(ge=0.0)
    preference: float = Field(ge=0.0)
    veto: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not (
            self.indifference
            <= self.preference
            <= self.veto
        ):
            raise ValueError(
                "Thresholds must satisfy "
                "indifference <= preference <= veto."
            )

        return self


class ElectreIIIConfiguration(ElectreModel):
    """Configure a versioned ELECTRE III assessment."""

    configuration_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    credibility_cutoff: float = Field(
        default=0.65,
        gt=0.0,
        le=1.0,
    )
    distillation_alpha: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
    )
    distillation_beta: float = Field(
        default=-0.15,
        ge=-1.0,
        le=1.0,
    )
    projection: ElectreProjection = (
        ElectreProjection.CENTROID
    )
    thresholds: tuple[ElectreThreshold, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_unique_thresholds(self) -> Self:
        criterion_ids = [
            threshold.criterion_id
            for threshold in self.thresholds
        ]

        if len(criterion_ids) != len(
            set(criterion_ids)
        ):
            raise ValueError(
                "ELECTRE threshold criterion IDs must be unique."
            )

        if self.distillation_alpha + self.distillation_beta < 0.0:
            raise ValueError(
                "The distillation discrimination threshold must remain "
                "non-negative across credibility values from zero to one."
            )

        return self


class OrderedOutranking(ElectreModel):
    """Store the credibility of one SME outranking another."""

    source_sme_id: str = Field(min_length=1)
    target_sme_id: str = Field(min_length=1)
    global_concordance: float = Field(ge=0.0, le=1.0)
    credibility: float = Field(ge=0.0, le=1.0)
    partial_concordance: dict[str, float]
    discordance: dict[str, float]
    vetoed: bool
    outranks: bool


class SMEPairRelation(ElectreModel):
    """Store the complete relationship between two SMEs."""

    left_sme_id: str = Field(min_length=1)
    right_sme_id: str = Field(min_length=1)
    left_outranks_right: bool
    right_outranks_left: bool
    relation: PairRelation


class ElectreRankLevel(ElectreModel):
    """Store one level in the resulting partial preorder."""

    level: int = Field(ge=1)
    sme_ids: tuple[str, ...] = Field(min_length=1)
    contains_preference_cycle: bool = False


class ElectreIIIResult(ElectreModel):
    """Store traceable ELECTRE III relations and partial ranking."""

    configuration_id: str = Field(min_length=1)
    configuration_version: str = Field(min_length=1)
    cohort_id: str = Field(min_length=1)
    cohort_version: str = Field(min_length=1)
    comparison_status: CohortComparisonStatus
    projection: ElectreProjection
    shared_criterion_ids: tuple[str, ...] = Field(min_length=1)
    normalized_weights: dict[str, float]
    projected_performance: dict[str, dict[str, float]]
    ordered_outrankings: tuple[OrderedOutranking, ...]
    pair_relations: tuple[SMEPairRelation, ...]
    descending_rank_levels: tuple[ElectreRankLevel, ...] = ()
    ascending_rank_levels: tuple[ElectreRankLevel, ...] = ()
    rank_levels: tuple[ElectreRankLevel, ...]
    incomparable_pairs: tuple[tuple[str, str], ...]


def load_electre_configuration(
    path: str | Path,
) -> ElectreIIIConfiguration:
    """Load a strict ELECTRE III configuration."""

    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )
    return ElectreIIIConfiguration.model_validate(data)


def run_electre_iii(
    inputs: Sequence[NormalizedAssessmentInputs],
    cohort: ComparableTopsisResult,
    configuration: ElectreIIIConfiguration,
) -> ElectreIIIResult:
    """Build ELECTRE III credibility and partial ranking."""

    criterion_maps = _validate_and_map(
        inputs,
        cohort,
    )
    criterion_ids = cohort.shared_criterion_ids
    thresholds = {
        threshold.criterion_id: threshold
        for threshold in configuration.thresholds
    }

    missing_thresholds = (
        set(criterion_ids) - thresholds.keys()
    )

    if missing_thresholds:
        raise ElectreIIIError(
            "No ELECTRE thresholds are configured for: "
            f"{sorted(missing_thresholds)}."
        )

    weights = _resolve_weights(
        criterion_maps,
        criterion_ids,
    )
    total_weight = sum(weights.values())
    normalized_weights = {
        criterion_id: weights[criterion_id] / total_weight
        for criterion_id in criterion_ids
    }

    performance = {
        item.sme_id: {
            criterion_id: _project(
                criterion_maps[item.sme_id][criterion_id],
                configuration.projection,
            )
            for criterion_id in criterion_ids
        }
        for item in inputs
    }

    ordered_outrankings = tuple(
        _calculate_outranking(
            source_sme_id=source.sme_id,
            target_sme_id=target.sme_id,
            performance=performance,
            criterion_ids=criterion_ids,
            weights=normalized_weights,
            thresholds=thresholds,
            credibility_cutoff=(
                configuration.credibility_cutoff
            ),
        )
        for source in inputs
        for target in inputs
        if source.sme_id != target.sme_id
    )

    ordered_lookup = {
        (
            item.source_sme_id,
            item.target_sme_id,
        ): item
        for item in ordered_outrankings
    }

    sorted_sme_ids = tuple(sorted(performance))
    pair_relations: list[SMEPairRelation] = []

    for left_index, left_sme_id in enumerate(
        sorted_sme_ids
    ):
        for right_sme_id in sorted_sme_ids[
            left_index + 1:
        ]:
            left_relation = ordered_lookup[
                (left_sme_id, right_sme_id)
            ]
            right_relation = ordered_lookup[
                (right_sme_id, left_sme_id)
            ]

            relation = _classify_pair(
                left_relation.outranks,
                right_relation.outranks,
            )

            pair_relations.append(
                SMEPairRelation(
                    left_sme_id=left_sme_id,
                    right_sme_id=right_sme_id,
                    left_outranks_right=(
                        left_relation.outranks
                    ),
                    right_outranks_left=(
                        right_relation.outranks
                    ),
                    relation=relation,
                )
            )

    descending_rank_levels = _distill_credibility(
        sorted_sme_ids,
        ordered_lookup,
        configuration,
        descending=True,
    )
    ascending_rank_levels = _distill_credibility(
        sorted_sme_ids,
        ordered_lookup,
        configuration,
        descending=False,
    )
    rank_levels = _combine_distillations(
        sorted_sme_ids,
        descending_rank_levels,
        ascending_rank_levels,
    )

    incomparable_pairs = tuple(
        (
            pair.left_sme_id,
            pair.right_sme_id,
        )
        for pair in pair_relations
        if pair.relation is PairRelation.INCOMPARABLE
    )

    return ElectreIIIResult(
        configuration_id=configuration.configuration_id,
        configuration_version=configuration.version,
        cohort_id=cohort.cohort_id,
        cohort_version=cohort.cohort_version,
        comparison_status=cohort.comparison_status,
        projection=configuration.projection,
        shared_criterion_ids=criterion_ids,
        normalized_weights=normalized_weights,
        projected_performance=performance,
        ordered_outrankings=ordered_outrankings,
        pair_relations=tuple(pair_relations),
        descending_rank_levels=descending_rank_levels,
        ascending_rank_levels=ascending_rank_levels,
        rank_levels=rank_levels,
        incomparable_pairs=incomparable_pairs,
    )


def _calculate_outranking(
    *,
    source_sme_id: str,
    target_sme_id: str,
    performance: dict[str, dict[str, float]],
    criterion_ids: tuple[str, ...],
    weights: dict[str, float],
    thresholds: dict[str, ElectreThreshold],
    credibility_cutoff: float,
) -> OrderedOutranking:
    partial_concordance: dict[str, float] = {}
    discordance: dict[str, float] = {}

    for criterion_id in criterion_ids:
        source_value = performance[
            source_sme_id
        ][criterion_id]
        target_value = performance[
            target_sme_id
        ][criterion_id]

        disadvantage = target_value - source_value
        threshold = thresholds[criterion_id]

        partial_concordance[criterion_id] = (
            _partial_concordance(
                disadvantage,
                threshold,
            )
        )
        discordance[criterion_id] = (
            _discordance(
                disadvantage,
                threshold,
            )
        )

    global_concordance = sum(
        weights[criterion_id]
        * partial_concordance[criterion_id]
        for criterion_id in criterion_ids
    )

    credibility = global_concordance

    for criterion_id in criterion_ids:
        criterion_discordance = discordance[
            criterion_id
        ]

        if criterion_discordance > global_concordance:
            credibility *= (
                1.0 - criterion_discordance
            ) / (
                1.0 - global_concordance
            )

    credibility = min(
        1.0,
        max(0.0, credibility),
    )

    vetoed = any(
        value >= 1.0
        for value in discordance.values()
    )

    return OrderedOutranking(
        source_sme_id=source_sme_id,
        target_sme_id=target_sme_id,
        global_concordance=global_concordance,
        credibility=credibility,
        partial_concordance=partial_concordance,
        discordance=discordance,
        vetoed=vetoed,
        outranks=credibility >= credibility_cutoff,
    )


def _partial_concordance(
    disadvantage: float,
    threshold: ElectreThreshold,
) -> float:
    if disadvantage <= threshold.indifference:
        return 1.0

    if disadvantage >= threshold.preference:
        return 0.0

    return (
        threshold.preference - disadvantage
    ) / (
        threshold.preference
        - threshold.indifference
    )


def _discordance(
    disadvantage: float,
    threshold: ElectreThreshold,
) -> float:
    if disadvantage <= threshold.preference:
        return 0.0

    if disadvantage >= threshold.veto:
        return 1.0

    return (
        disadvantage - threshold.preference
    ) / (
        threshold.veto - threshold.preference
    )


def _classify_pair(
    left_outranks: bool,
    right_outranks: bool,
) -> PairRelation:
    if left_outranks and right_outranks:
        return PairRelation.INDIFFERENT

    if left_outranks:
        return PairRelation.LEFT_PREFERRED

    if right_outranks:
        return PairRelation.RIGHT_PREFERRED

    return PairRelation.INCOMPARABLE


def _project(
    criterion: NormalizedCriterionInput,
    projection: ElectreProjection,
) -> float:
    value = criterion.fuzzy_value

    if projection is ElectreProjection.CENTROID:
        return (
            value.lower
            + value.modal
            + value.upper
        ) / 3.0

    raise ElectreIIIError(
        f"Unsupported projection: {projection}."
    )


def _validate_and_map(
    inputs: Sequence[NormalizedAssessmentInputs],
    cohort: ComparableTopsisResult,
) -> dict[
    str,
    dict[str, NormalizedCriterionInput],
]:
    if len(inputs) < 2:
        raise ElectreIIIError(
            "ELECTRE III requires at least two SMEs."
        )

    sme_ids = [item.sme_id for item in inputs]

    if len(sme_ids) != len(set(sme_ids)):
        raise ElectreIIIError(
            "SME IDs must be unique."
        )

    expected_sme_ids = {
        item.sme_id for item in cohort.coverage
    }

    if set(sme_ids) != expected_sme_ids:
        raise ElectreIIIError(
            "ELECTRE inputs do not match the prepared cohort."
        )

    criterion_maps: dict[
        str,
        dict[str, NormalizedCriterionInput],
    ] = {}

    for item in inputs:
        if item.readiness is AssessmentReadiness.BLOCKED:
            raise ElectreIIIError(
                f"SME {item.sme_id!r} is blocked."
            )

        if (
            item.normalization_policy_id
            != cohort.normalization_policy_id
            or item.normalization_policy_version
            != cohort.normalization_policy_version
        ):
            raise ElectreIIIError(
                "Inputs use a different normalization policy."
            )

        criterion_map = {
            criterion.criterion_id: criterion
            for criterion in item.criteria
        }

        missing = (
            set(cohort.shared_criterion_ids)
            - criterion_map.keys()
        )

        if missing:
            raise ElectreIIIError(
                f"SME {item.sme_id!r} is missing "
                f"shared criteria: {sorted(missing)}."
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
            raise ElectreIIIError(
                f"Criterion {criterion_id!r} has "
                "inconsistent weights."
            )

        weights[criterion_id] = next(iter(candidates))

    return weights


def _distill_credibility(
    sme_ids: tuple[str, ...],
    ordered_lookup: dict[tuple[str, str], OrderedOutranking],
    configuration: ElectreIIIConfiguration,
    *,
    descending: bool,
) -> tuple[ElectreRankLevel, ...]:
    """Create one best-first order from the credibility relation."""

    extracted = _distill_subset(
        set(sme_ids),
        ordered_lookup,
        configuration,
        descending=descending,
    )

    best_first = extracted if descending else list(reversed(extracted))

    return tuple(
        ElectreRankLevel(
            level=level,
            sme_ids=sme_group,
        )
        for level, sme_group in enumerate(best_first, start=1)
    )


def _distill_subset(
    sme_ids: set[str],
    ordered_lookup: dict[tuple[str, str], OrderedOutranking],
    configuration: ElectreIIIConfiguration,
    *,
    descending: bool,
) -> list[tuple[str, ...]]:
    """Recursively refine a selected distillation group where possible."""

    if len(sme_ids) <= 1:
        return [tuple(sorted(sme_ids))]

    qualifications = _distillation_qualifications(
        sme_ids,
        ordered_lookup,
        configuration,
    )
    selected_qualification = (
        max(qualifications.values())
        if descending
        else min(qualifications.values())
    )
    selected = {
        sme_id
        for sme_id, qualification in qualifications.items()
        if qualification == selected_qualification
    }

    if selected == sme_ids:
        return [tuple(sorted(sme_ids))]

    remaining = sme_ids - selected

    return [
        *_distill_subset(
            selected,
            ordered_lookup,
            configuration,
            descending=descending,
        ),
        *_distill_subset(
            remaining,
            ordered_lookup,
            configuration,
            descending=descending,
        ),
    ]


def _distillation_qualifications(
    sme_ids: set[str],
    ordered_lookup: dict[tuple[str, str], OrderedOutranking],
    configuration: ElectreIIIConfiguration,
) -> dict[str, int]:
    """Measure net strong outranking within the remaining alternatives."""

    credibility_values = [
        ordered_lookup[(source, target)].credibility
        for source in sme_ids
        for target in sme_ids
        if source != target
    ]
    maximum_credibility = max(credibility_values)
    discrimination = _distillation_discrimination(
        maximum_credibility,
        configuration,
    )
    lower_values = [
        value
        for value in credibility_values
        if value < maximum_credibility - discrimination
    ]
    cut_level = max(lower_values, default=0.0)
    outranked_by = {sme_id: 0 for sme_id in sme_ids}
    outranks = {sme_id: 0 for sme_id in sme_ids}

    for source in sme_ids:
        for target in sme_ids:
            if source == target:
                continue

            forward = ordered_lookup[(source, target)].credibility
            reverse = ordered_lookup[(target, source)].credibility

            if (
                forward > cut_level
                and forward - reverse
                > _distillation_discrimination(
                    forward,
                    configuration,
                )
            ):
                outranks[source] += 1
                outranked_by[target] += 1

    return {
        sme_id: outranks[sme_id] - outranked_by[sme_id]
        for sme_id in sme_ids
    }


def _distillation_discrimination(
    credibility: float,
    configuration: ElectreIIIConfiguration,
) -> float:
    return max(
        0.0,
        configuration.distillation_alpha
        + configuration.distillation_beta * credibility,
    )


def _combine_distillations(
    sme_ids: tuple[str, ...],
    descending_levels: tuple[ElectreRankLevel, ...],
    ascending_levels: tuple[ElectreRankLevel, ...],
) -> tuple[ElectreRankLevel, ...]:
    """Intersect both orders without forcing conflicting comparisons."""

    descending_rank = _level_lookup(descending_levels)
    ascending_rank = _level_lookup(ascending_levels)
    strict_edges = {sme_id: set() for sme_id in sme_ids}

    for source in sme_ids:
        for target in sme_ids:
            if source == target:
                continue

            source_not_worse = (
                descending_rank[source] <= descending_rank[target]
                and ascending_rank[source] <= ascending_rank[target]
            )
            source_strictly_better = (
                descending_rank[source] < descending_rank[target]
                or ascending_rank[source] < ascending_rank[target]
            )

            if source_not_worse and source_strictly_better:
                strict_edges[source].add(target)

    return _build_rank_levels(sme_ids, strict_edges)


def _level_lookup(
    levels: tuple[ElectreRankLevel, ...],
) -> dict[str, int]:
    return {
        sme_id: level.level
        for level in levels
        for sme_id in level.sme_ids
    }


def _build_rank_levels(
    sme_ids: tuple[str, ...],
    edges: dict[str, set[str]],
) -> tuple[ElectreRankLevel, ...]:
    components = _strongly_connected_components(
        sme_ids,
        edges,
    )
    component_index = {
        sme_id: index
        for index, component in enumerate(components)
        for sme_id in component
    }
    component_edges = {
        index: set()
        for index in range(len(components))
    }

    for source, targets in edges.items():
        source_component = component_index[source]

        for target in targets:
            target_component = component_index[target]

            if source_component != target_component:
                component_edges[source_component].add(
                    target_component
                )

    remaining = set(component_edges)
    levels: list[ElectreRankLevel] = []
    level_number = 1

    while remaining:
        incoming = {
            component: 0
            for component in remaining
        }

        for source in remaining:
            for target in component_edges[source]:
                if target in remaining:
                    incoming[target] += 1

        leading_components = {
            component
            for component, count in incoming.items()
            if count == 0
        }

        if not leading_components:
            raise ElectreIIIError(
                "The component ranking graph is inconsistent."
            )

        level_smes = tuple(
            sorted(
                sme_id
                for component in leading_components
                for sme_id in components[component]
            )
        )

        levels.append(
            ElectreRankLevel(
                level=level_number,
                sme_ids=level_smes,
                contains_preference_cycle=any(
                    len(components[component]) > 1
                    for component in leading_components
                ),
            )
        )

        remaining -= leading_components
        level_number += 1

    return tuple(levels)


def _strongly_connected_components(
    sme_ids: tuple[str, ...],
    edges: dict[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    index = 0
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index

        indices[node] = index
        low_links[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for target in sorted(edges[node]):
            if target not in indices:
                visit(target)
                low_links[node] = min(
                    low_links[node],
                    low_links[target],
                )
            elif target in on_stack:
                low_links[node] = min(
                    low_links[node],
                    indices[target],
                )

        if low_links[node] == indices[node]:
            component: list[str] = []

            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)

                if member == node:
                    break

            components.append(tuple(sorted(component)))

    for sme_id in sorted(sme_ids):
        if sme_id not in indices:
            visit(sme_id)

    return tuple(components)


def _unique_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate JSON key: {key}"
            )

        result[key] = value

    return result
