"""Translate broad DEMATEL driver importance into criterion weights."""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.fuzzy_dematel import FuzzyDematelResult
from greensmecapt.assessment.normalization import NormalizationPolicy


class HierarchicalWeightError(ValueError):
    """Raised when driver-to-criterion weighting is inconsistent."""


class WeightModel(BaseModel):
    """Provide immutable hierarchical-weight contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class DriverCriterionAllocation(WeightModel):
    """Distribute one broad driver's importance across criteria."""

    driver_id: str = Field(min_length=1)
    criterion_shares: dict[str, float] = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_shares(self) -> Self:
        if any(share < 0.0 for share in self.criterion_shares.values()):
            raise ValueError("Criterion shares must not be negative.")

        if abs(sum(self.criterion_shares.values()) - 1.0) > 1e-9:
            raise ValueError(
                "Each driver's criterion shares must sum to one."
            )

        return self


class DematelCriterionMapping(WeightModel):
    """Version the explicit bridge from DEMATEL drivers to criteria."""

    mapping_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: Literal["development", "approved", "deprecated"] = "development"
    source: str = Field(min_length=1)
    deprecated_reason: str | None = Field(default=None, min_length=1)
    review_required: bool = True
    allocations: tuple[DriverCriterionAllocation, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        if self.status == "deprecated" and self.deprecated_reason is None:
            raise ValueError(
                "Deprecated mappings must state a deprecation reason."
            )

        driver_ids = [item.driver_id for item in self.allocations]

        if len(driver_ids) != len(set(driver_ids)):
            raise ValueError("Driver allocation IDs must be unique.")

        criterion_sets = [
            set(item.criterion_shares) for item in self.allocations
        ]

        if any(items != criterion_sets[0] for items in criterion_sets[1:]):
            raise ValueError(
                "Every driver must allocate across the same criteria."
            )

        return self


class DerivedCriterionWeights(WeightModel):
    """Record criterion weights derived from one DEMATEL result."""

    mapping_id: str = Field(min_length=1)
    mapping_version: str = Field(min_length=1)
    dematel_specification_id: str = Field(min_length=1)
    dematel_specification_version: str = Field(min_length=1)
    driver_weights: dict[str, float] = Field(min_length=1)
    criterion_weights: dict[str, float] = Field(min_length=1)


def load_dematel_criterion_mapping(
    path: str | Path,
) -> DematelCriterionMapping:
    """Load a strict driver-to-criterion mapping."""

    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )
    return DematelCriterionMapping.model_validate(data)


def derive_criterion_weights(
    result: FuzzyDematelResult,
    mapping: DematelCriterionMapping,
) -> DerivedCriterionWeights:
    """Distribute DEMATEL driver weights through the explicit mapping."""

    if mapping.status == "deprecated":
        raise HierarchicalWeightError(
            "Deprecated DEMATEL mappings cannot produce performance weights."
        )

    driver_weights = result.normalized_weights
    mapping_drivers = {item.driver_id for item in mapping.allocations}

    if set(driver_weights) != mapping_drivers:
        raise HierarchicalWeightError(
            "DEMATEL factors and mapping drivers must match exactly."
        )

    if any(weight < 0.0 for weight in driver_weights.values()):
        raise HierarchicalWeightError(
            "DEMATEL driver weights must not be negative."
        )

    if abs(sum(driver_weights.values()) - 1.0) > 1e-9:
        raise HierarchicalWeightError(
            "DEMATEL driver weights must sum to one."
        )

    criterion_weights: dict[str, float] = {}

    for allocation in mapping.allocations:
        driver_weight = driver_weights[allocation.driver_id]

        for criterion_id, share in allocation.criterion_shares.items():
            criterion_weights[criterion_id] = (
                criterion_weights.get(criterion_id, 0.0)
                + driver_weight * share
            )

    total = sum(criterion_weights.values())

    if total <= 0.0:
        raise HierarchicalWeightError(
            "Derived criterion weights must have positive total weight."
        )

    normalized = {
        criterion_id: weight / total
        for criterion_id, weight in criterion_weights.items()
    }

    return DerivedCriterionWeights(
        mapping_id=mapping.mapping_id,
        mapping_version=mapping.version,
        dematel_specification_id=result.specification_id,
        dematel_specification_version=result.specification_version,
        driver_weights=dict(driver_weights),
        criterion_weights=normalized,
    )


def apply_derived_weights(
    policy: NormalizationPolicy,
    derived: DerivedCriterionWeights,
    *,
    new_version: str,
) -> NormalizationPolicy:
    """Return a new policy using traceable DEMATEL-derived weights."""

    policy_criteria = {rule.criterion_id for rule in policy.rules}

    if policy_criteria != set(derived.criterion_weights):
        raise HierarchicalWeightError(
            "Derived weights and normalization criteria must match exactly."
        )

    rules = tuple(
        rule.model_copy(
            update={
                "base_weight": derived.criterion_weights[
                    rule.criterion_id
                ]
            }
        )
        for rule in policy.rules
    )

    return policy.model_copy(
        update={
            "version": new_version,
            "weight_source": (
                f"fuzzy_dematel:{derived.dematel_specification_id}:"
                f"{derived.dematel_specification_version};"
                f"mapping:{derived.mapping_id}:{derived.mapping_version}"
            ),
            "rules": rules,
        }
    )


def _unique_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value

    return result
