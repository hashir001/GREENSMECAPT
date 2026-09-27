"""Fuzzy DEMATEL analysis of expert influence judgments."""

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FuzzyDematelError(ValueError):
    """Raised when fuzzy DEMATEL cannot run consistently."""


class DematelModel(BaseModel):
    """Provide immutable fuzzy DEMATEL contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class FuzzyInfluence(DematelModel):
    """Represent a non-negative triangular fuzzy influence."""

    lower: float = Field(ge=0.0)
    modal: float = Field(ge=0.0)
    upper: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not self.lower <= self.modal <= self.upper:
            raise ValueError(
                "Fuzzy influence must satisfy "
                "lower <= modal <= upper."
            )

        return self


class StakeholderAggregation(StrEnum):
    """Describe how judgments from stakeholder groups are combined."""

    GROUP_BALANCED = "group_balanced"
    EXPERT_WEIGHTED = "expert_weighted"


class DematelDomain(DematelModel):
    """Group research-grounded readiness factors without scoring them."""

    domain_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class DematelFactorDefinition(DematelModel):
    """Define one readiness factor and its research provenance."""

    factor_id: str = Field(min_length=1)
    domain_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    source_status: Literal[
        "research_grounded",
        "research_synthesized",
        "provisional",
    ]


class FactorRole(StrEnum):
    """Describe whether a factor primarily causes or receives influence."""

    CAUSE = "cause"
    EFFECT = "effect"
    NEUTRAL = "neutral"


class InfluenceJudgment(DematelModel):
    """Store one directional linguistic influence judgment."""

    source_factor_id: str = Field(min_length=1)
    target_factor_id: str = Field(min_length=1)
    linguistic_value: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_self_influence(self) -> Self:
        if self.source_factor_id == self.target_factor_id:
            raise ValueError(
                "Experts must not submit diagonal self-influence."
            )

        return self


class ExpertInfluenceAssessment(DematelModel):
    """Store one expert's complete directed influence assessment."""

    expert_id: str = Field(min_length=1)
    stakeholder_group: str = Field(min_length=1)
    expert_weight: float = Field(default=1.0, gt=0.0)
    judgments: tuple[InfluenceJudgment, ...] = Field(
        min_length=1
    )


class DematelSpecification(DematelModel):
    """Define factors, stakeholder groups and linguistic meanings."""

    specification_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: Literal["development", "approved"] = "development"
    research_basis: str | None = Field(default=None, min_length=1)
    calibration_status: Literal[
        "requires_expert_calibration",
        "calibrated",
    ] = "requires_expert_calibration"
    linguistic_scale_status: Literal[
        "development_placeholder",
        "approved",
    ] = "development_placeholder"
    domains: tuple[DematelDomain, ...] = ()
    factors: tuple[DematelFactorDefinition, ...] = ()
    factor_ids: tuple[str, ...] = Field(min_length=2)
    stakeholder_groups: tuple[str, ...] = Field(min_length=1)
    aggregation: StakeholderAggregation = (
        StakeholderAggregation.GROUP_BALANCED
    )
    convergence_margin: float = Field(
        default=0.999,
        gt=0.0,
        lt=1.0,
    )
    cause_effect_tolerance: float = Field(
        default=1e-9,
        ge=0.0,
    )
    linguistic_scale: dict[str, FuzzyInfluence] = Field(
        min_length=2
    )

    @model_validator(mode="after")
    def validate_specification(self) -> Self:
        for label, values in (
            ("factor", self.factor_ids),
            ("stakeholder group", self.stakeholder_groups),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    f"Duplicate {label} IDs are not allowed."
                )

        if bool(self.domains) != bool(self.factors):
            raise ValueError(
                "Domains and factor definitions must be supplied together."
            )

        if self.domains:
            domain_ids = [domain.domain_id for domain in self.domains]
            metadata_factor_ids = [
                factor.factor_id for factor in self.factors
            ]

            if len(domain_ids) != len(set(domain_ids)):
                raise ValueError("DEMATEL domain IDs must be unique.")

            if len(metadata_factor_ids) != len(set(metadata_factor_ids)):
                raise ValueError(
                    "DEMATEL factor definition IDs must be unique."
                )

            if set(metadata_factor_ids) != set(self.factor_ids):
                raise ValueError(
                    "Factor definitions must match factor_ids exactly."
                )

            unknown_domains = {
                factor.domain_id
                for factor in self.factors
                if factor.domain_id not in set(domain_ids)
            }

            if unknown_domains:
                raise ValueError(
                    "Every DEMATEL factor must reference a known domain."
                )

        casefolded_labels = [
            label.casefold()
            for label in self.linguistic_scale
        ]

        if len(casefolded_labels) != len(
            set(casefolded_labels)
        ):
            raise ValueError(
                "Linguistic labels must be "
                "case-insensitively unique."
            )

        if any(
            influence.upper > 1.0
            for influence in self.linguistic_scale.values()
        ):
            raise ValueError(
                "Direct linguistic influence values "
                "must not exceed one."
            )

        return self


class FuzzyRelationMatrix(DematelModel):
    """Store one square fuzzy relationship matrix."""

    factor_ids: tuple[str, ...] = Field(min_length=2)
    values: tuple[
        tuple[FuzzyInfluence, ...],
        ...,
    ] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        expected_size = len(self.factor_ids)

        if len(self.values) != expected_size:
            raise ValueError(
                "The matrix must contain one row per factor."
            )

        if any(
            len(row) != expected_size
            for row in self.values
        ):
            raise ValueError(
                "Every matrix row must contain one value per factor."
            )

        return self


class DematelFactorResult(DematelModel):
    """Store one factor's prominence, relation and final weight."""

    factor_id: str = Field(min_length=1)
    dispatching_power: float = Field(ge=0.0)
    receiving_power: float = Field(ge=0.0)
    prominence: float = Field(ge=0.0)
    relation: float
    role: FactorRole
    normalized_weight: float = Field(ge=0.0, le=1.0)


class FuzzyDematelResult(DematelModel):
    """Store a reproducible fuzzy DEMATEL result."""

    specification_id: str = Field(min_length=1)
    specification_version: str = Field(min_length=1)
    aggregation: StakeholderAggregation
    expert_ids: tuple[str, ...] = Field(min_length=1)
    represented_stakeholder_groups: tuple[str, ...] = Field(
        min_length=1
    )
    aggregated_direct_matrix: FuzzyRelationMatrix
    normalized_direct_matrix: FuzzyRelationMatrix
    total_relation_matrix: FuzzyRelationMatrix
    factors: tuple[DematelFactorResult, ...] = Field(min_length=2)
    normalized_weights: dict[str, float]

    @property
    def cause_factors(self) -> tuple[str, ...]:
        return tuple(
            factor.factor_id
            for factor in self.factors
            if factor.role is FactorRole.CAUSE
        )

    @property
    def effect_factors(self) -> tuple[str, ...]:
        return tuple(
            factor.factor_id
            for factor in self.factors
            if factor.role is FactorRole.EFFECT
        )


FuzzyArrays = tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
]


def load_dematel_specification(
    path: str | Path,
) -> DematelSpecification:
    """Load a strict DEMATEL specification from JSON."""

    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )
    return DematelSpecification.model_validate(data)


def load_expert_assessments(
    path: str | Path,
) -> tuple[ExpertInfluenceAssessment, ...]:
    """Load expert assessments from a JSON array."""

    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )

    if not isinstance(data, list):
        raise ValueError(
            "Expert assessment JSON must contain an array."
        )

    return tuple(
        ExpertInfluenceAssessment.model_validate(item)
        for item in data
    )


def run_fuzzy_dematel(
    specification: DematelSpecification,
    assessments: Sequence[ExpertInfluenceAssessment],
) -> FuzzyDematelResult:
    """Run group-aware fuzzy DEMATEL."""

    _validate_assessments(
        specification,
        assessments,
    )

    matrices = tuple(
        _assessment_matrix(specification, assessment)
        for assessment in assessments
    )

    aggregated = _aggregate_matrices(
        specification,
        assessments,
        matrices,
    )

    normalized = _normalize_direct_matrix(
        aggregated,
        specification.convergence_margin,
    )

    total = tuple(
        _total_relation(component)
        for component in normalized
    )

    factor_results = _factor_results(
        specification,
        total,
    )

    normalized_weights = {
        factor.factor_id: factor.normalized_weight
        for factor in factor_results
    }

    represented_groups = tuple(
        sorted(
            {
                assessment.stakeholder_group
                for assessment in assessments
            }
        )
    )

    return FuzzyDematelResult(
        specification_id=specification.specification_id,
        specification_version=specification.version,
        aggregation=specification.aggregation,
        expert_ids=tuple(
            sorted(
                assessment.expert_id
                for assessment in assessments
            )
        ),
        represented_stakeholder_groups=represented_groups,
        aggregated_direct_matrix=_to_fuzzy_matrix(
            specification.factor_ids,
            aggregated,
        ),
        normalized_direct_matrix=_to_fuzzy_matrix(
            specification.factor_ids,
            normalized,
        ),
        total_relation_matrix=_to_fuzzy_matrix(
            specification.factor_ids,
            total,
        ),
        factors=factor_results,
        normalized_weights=normalized_weights,
    )


def _validate_assessments(
    specification: DematelSpecification,
    assessments: Sequence[ExpertInfluenceAssessment],
) -> None:
    if not assessments:
        raise FuzzyDematelError(
            "At least one expert assessment is required."
        )

    expert_ids = [
        assessment.expert_id
        for assessment in assessments
    ]

    if len(expert_ids) != len(set(expert_ids)):
        raise FuzzyDematelError(
            "Expert IDs must be unique."
        )

    submitted_groups = {
        assessment.stakeholder_group
        for assessment in assessments
    }
    expected_groups = set(
        specification.stakeholder_groups
    )

    missing_groups = expected_groups - submitted_groups
    unexpected_groups = submitted_groups - expected_groups

    if missing_groups or unexpected_groups:
        raise FuzzyDematelError(
            "Stakeholder groups do not match the specification. "
            f"Missing: {sorted(missing_groups)}; "
            f"unexpected: {sorted(unexpected_groups)}."
        )

    factor_ids = set(specification.factor_ids)
    expected_pairs = {
        (source, target)
        for source in specification.factor_ids
        for target in specification.factor_ids
        if source != target
    }
    scale_labels = {
        label.casefold()
        for label in specification.linguistic_scale
    }

    for assessment in assessments:
        pairs = [
            (
                judgment.source_factor_id,
                judgment.target_factor_id,
            )
            for judgment in assessment.judgments
        ]

        if len(pairs) != len(set(pairs)):
            raise FuzzyDematelError(
                f"Expert {assessment.expert_id!r} "
                "submitted duplicate factor relationships."
            )

        submitted_pairs = set(pairs)
        missing_pairs = expected_pairs - submitted_pairs
        unexpected_pairs = submitted_pairs - expected_pairs

        if missing_pairs or unexpected_pairs:
            raise FuzzyDematelError(
                f"Expert {assessment.expert_id!r} did not submit "
                "the complete directed matrix. "
                f"Missing: {sorted(missing_pairs)}; "
                f"unexpected: {sorted(unexpected_pairs)}."
            )

        for judgment in assessment.judgments:
            if (
                judgment.source_factor_id not in factor_ids
                or judgment.target_factor_id not in factor_ids
            ):
                raise FuzzyDematelError(
                    "A judgment references an unknown factor."
                )

            if (
                judgment.linguistic_value.casefold()
                not in scale_labels
            ):
                raise FuzzyDematelError(
                    f"Unknown linguistic influence "
                    f"{judgment.linguistic_value!r}."
                )


def _assessment_matrix(
    specification: DematelSpecification,
    assessment: ExpertInfluenceAssessment,
) -> FuzzyArrays:
    size = len(specification.factor_ids)
    positions = {
        factor_id: index
        for index, factor_id
        in enumerate(specification.factor_ids)
    }
    scale = {
        label.casefold(): influence
        for label, influence
        in specification.linguistic_scale.items()
    }

    lower = np.zeros((size, size), dtype=float)
    modal = np.zeros((size, size), dtype=float)
    upper = np.zeros((size, size), dtype=float)

    for judgment in assessment.judgments:
        row = positions[judgment.source_factor_id]
        column = positions[judgment.target_factor_id]
        influence = scale[
            judgment.linguistic_value.casefold()
        ]

        lower[row, column] = influence.lower
        modal[row, column] = influence.modal
        upper[row, column] = influence.upper

    return lower, modal, upper


def _aggregate_matrices(
    specification: DematelSpecification,
    assessments: Sequence[ExpertInfluenceAssessment],
    matrices: Sequence[FuzzyArrays],
) -> FuzzyArrays:
    if (
        specification.aggregation
        is StakeholderAggregation.EXPERT_WEIGHTED
    ):
        return _weighted_average(
            matrices,
            [
                assessment.expert_weight
                for assessment in assessments
            ],
        )

    grouped: dict[
        str,
        list[tuple[FuzzyArrays, float]],
    ] = defaultdict(list)

    for assessment, matrix in zip(
        assessments,
        matrices,
        strict=True,
    ):
        grouped[assessment.stakeholder_group].append(
            (matrix, assessment.expert_weight)
        )

    group_matrices: list[FuzzyArrays] = []

    for group_id in specification.stakeholder_groups:
        entries = grouped[group_id]
        group_matrices.append(
            _weighted_average(
                [matrix for matrix, _ in entries],
                [weight for _, weight in entries],
            )
        )

    return _weighted_average(
        group_matrices,
        [1.0] * len(group_matrices),
    )


def _weighted_average(
    matrices: Sequence[FuzzyArrays],
    weights: Sequence[float],
) -> FuzzyArrays:
    total_weight = sum(weights)

    if total_weight <= 0.0:
        raise FuzzyDematelError(
            "The total expert weight must be positive."
        )

    components: list[np.ndarray] = []

    for component_index in range(3):
        combined = np.zeros_like(
            matrices[0][component_index],
            dtype=float,
        )

        for matrix, weight in zip(
            matrices,
            weights,
            strict=True,
        ):
            combined += (
                matrix[component_index] * weight
            )

        components.append(combined / total_weight)

    return components[0], components[1], components[2]


def _normalize_direct_matrix(
    aggregated: FuzzyArrays,
    convergence_margin: float,
) -> FuzzyArrays:
    upper = aggregated[2]
    maximum_upper_row_sum = float(
        np.max(np.sum(upper, axis=1))
    )

    if maximum_upper_row_sum <= 0.0:
        raise FuzzyDematelError(
            "The aggregated influence matrix contains no influence."
        )

    multiplier = (
        convergence_margin / maximum_upper_row_sum
    )

    return tuple(
        component * multiplier
        for component in aggregated
    )


def _total_relation(
    normalized: np.ndarray,
) -> np.ndarray:
    identity = np.eye(normalized.shape[0])

    try:
        inverse = np.linalg.inv(identity - normalized)
    except np.linalg.LinAlgError as error:
        raise FuzzyDematelError(
            "The normalized influence matrix is singular."
        ) from error

    total = normalized @ inverse

    if not np.all(np.isfinite(total)):
        raise FuzzyDematelError(
            "The total-relation matrix contains "
            "non-finite values."
        )

    return np.maximum(total, 0.0)


def _factor_results(
    specification: DematelSpecification,
    total: FuzzyArrays,
) -> tuple[DematelFactorResult, ...]:
    lower, modal, upper = total

    dispatching = (
        np.sum(lower, axis=1)
        + np.sum(modal, axis=1)
        + np.sum(upper, axis=1)
    ) / 3.0

    receiving = (
        np.sum(lower, axis=0)
        + np.sum(modal, axis=0)
        + np.sum(upper, axis=0)
    ) / 3.0

    prominence = dispatching + receiving
    prominence_total = float(np.sum(prominence))

    if prominence_total <= 0.0:
        raise FuzzyDematelError(
            "Factor prominence cannot be normalized."
        )

    results: list[DematelFactorResult] = []

    for index, factor_id in enumerate(
        specification.factor_ids
    ):
        relation = float(
            dispatching[index] - receiving[index]
        )

        if relation > specification.cause_effect_tolerance:
            role = FactorRole.CAUSE
        elif (
            relation
            < -specification.cause_effect_tolerance
        ):
            role = FactorRole.EFFECT
        else:
            role = FactorRole.NEUTRAL

        results.append(
            DematelFactorResult(
                factor_id=factor_id,
                dispatching_power=float(dispatching[index]),
                receiving_power=float(receiving[index]),
                prominence=float(prominence[index]),
                relation=relation,
                role=role,
                normalized_weight=(
                    float(prominence[index])
                    / prominence_total
                ),
            )
        )

    return tuple(results)


def _to_fuzzy_matrix(
    factor_ids: tuple[str, ...],
    arrays: FuzzyArrays,
) -> FuzzyRelationMatrix:
    lower, modal, upper = arrays
    size = len(factor_ids)
    rows: list[tuple[FuzzyInfluence, ...]] = []

    for row in range(size):
        values: list[FuzzyInfluence] = []

        for column in range(size):
            lower_value = float(lower[row, column])
            modal_value = float(modal[row, column])
            upper_value = float(upper[row, column])

            tolerance = 1e-10

            if (
                lower_value > modal_value + tolerance
                or modal_value > upper_value + tolerance
            ):
                raise FuzzyDematelError(
                    "Fuzzy matrix ordering was lost "
                    "during calculation."
                )

            modal_value = max(
                lower_value,
                modal_value,
            )
            upper_value = max(
                modal_value,
                upper_value,
            )

            values.append(
                FuzzyInfluence(
                    lower=max(0.0, lower_value),
                    modal=max(0.0, modal_value),
                    upper=max(0.0, upper_value),
                )
            )

        rows.append(tuple(values))

    return FuzzyRelationMatrix(
        factor_ids=factor_ids,
        values=tuple(rows),
    )


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


def main() -> None:
    """Run fuzzy DEMATEL using specification and expert JSON files."""

    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument(
        "specification",
        type=Path,
    )
    parser.add_argument(
        "expert_assessments",
        type=Path,
    )
    args = parser.parse_args()

    try:
        specification = load_dematel_specification(
            args.specification
        )
        assessments = load_expert_assessments(
            args.expert_assessments
        )
        result = run_fuzzy_dematel(
            specification,
            assessments,
        )
    except (OSError, ValueError) as error:
        parser.exit(
            2,
            f"Fuzzy DEMATEL could not run: {error}\n",
        )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
