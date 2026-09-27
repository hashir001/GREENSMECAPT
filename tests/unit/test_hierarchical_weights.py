"""Tests for the deprecated DEMATEL-to-performance-weight bridge."""

from pathlib import Path

import pytest

from greensmecapt.assessment.fuzzy_dematel import FuzzyDematelResult
from greensmecapt.assessment.hierarchical_weights import (
    HierarchicalWeightError,
    derive_criterion_weights,
    load_dematel_criterion_mapping,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = (
    PROJECT_ROOT
    / "config"
    / "dematel_criterion_mapping.development.json"
)


def _dematel_result() -> FuzzyDematelResult:
    return FuzzyDematelResult.model_construct(
        specification_id="historical_driver_dematel",
        specification_version="0.1.0",
        normalized_weights={
            "policy": 0.25,
            "social": 0.25,
            "technology": 0.25,
            "internal": 0.25,
        },
    )


def test_project_mapping_is_explicitly_deprecated() -> None:
    mapping = load_dematel_criterion_mapping(MAPPING_PATH)

    assert mapping.status == "deprecated"
    assert mapping.deprecated_reason


def test_deprecated_mapping_cannot_create_performance_weights() -> None:
    mapping = load_dematel_criterion_mapping(MAPPING_PATH)

    with pytest.raises(
        HierarchicalWeightError,
        match="cannot produce performance weights",
    ):
        derive_criterion_weights(_dematel_result(), mapping)
