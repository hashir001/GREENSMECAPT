"""Tests for explicit DEMATEL-to-criterion weight mapping."""

from pathlib import Path

import pytest

from greensmecapt.assessment.fuzzy_dematel import FuzzyDematelResult
from greensmecapt.assessment.hierarchical_weights import (
    HierarchicalWeightError,
    apply_derived_weights,
    derive_criterion_weights,
    load_dematel_criterion_mapping,
)
from greensmecapt.assessment.normalization import load_normalization_policy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = (
    PROJECT_ROOT
    / "config"
    / "dematel_criterion_mapping.development.json"
)
POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "normalization_policy.development.json"
)


def _dematel_result(
    weights: dict[str, float] | None = None,
) -> FuzzyDematelResult:
    return FuzzyDematelResult.model_construct(
        specification_id="greensmecapt_driver_dematel",
        specification_version="0.1.0",
        normalized_weights=weights
        or {
            "policy": 0.25,
            "social": 0.25,
            "technology": 0.25,
            "internal": 0.25,
        },
    )


def test_derive_normalized_criterion_weights() -> None:
    mapping = load_dematel_criterion_mapping(MAPPING_PATH)
    derived = derive_criterion_weights(_dematel_result(), mapping)

    assert sum(derived.criterion_weights.values()) == pytest.approx(1.0)
    assert set(derived.criterion_weights) == {
        "green_contribution",
        "direct_operational_emissions",
        "purchased_energy_management",
        "resource_use_and_recovery",
        "customer_environmental_effect",
        "transition_execution",
    }


def test_apply_weights_returns_versioned_policy() -> None:
    mapping = load_dematel_criterion_mapping(MAPPING_PATH)
    derived = derive_criterion_weights(_dematel_result(), mapping)
    policy = load_normalization_policy(POLICY_PATH)

    updated = apply_derived_weights(
        policy,
        derived,
        new_version="0.3.0",
    )

    assert updated.version == "0.3.0"
    assert updated.weight_source.startswith("fuzzy_dematel:")
    assert sum(rule.base_weight for rule in updated.rules) == pytest.approx(
        1.0
    )


def test_reject_mismatched_dematel_factors() -> None:
    mapping = load_dematel_criterion_mapping(MAPPING_PATH)

    with pytest.raises(HierarchicalWeightError, match="match exactly"):
        derive_criterion_weights(
            _dematel_result({"unexpected_driver": 1.0}),
            mapping,
        )
