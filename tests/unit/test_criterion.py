"""Tests for the criterion domain model."""

import pytest
from pydantic import ValidationError

from greensmecapt.domain import Criterion, CriterionDirection


def test_create_benefit_criterion() -> None:
    """A valid benefit criterion should be created."""

    criterion = Criterion(
        criterion_id="renewable_energy",
        name="Renewable Energy Use",
        direction=CriterionDirection.BENEFIT,
    )

    assert criterion.criterion_id == "renewable_energy"
    assert criterion.name == "Renewable Energy Use"
    assert criterion.direction is CriterionDirection.BENEFIT


def test_reject_blank_criterion_name() -> None:
    """A criterion name containing only spaces should be rejected."""

    with pytest.raises(ValidationError):
        Criterion(
            criterion_id="renewable_energy",
            name="   ",
            direction=CriterionDirection.BENEFIT,
        )


def test_reject_weight_inside_criterion() -> None:
    """Criterion weights must remain separate from criterion definitions."""

    with pytest.raises(ValidationError):
        Criterion(
            criterion_id="renewable_energy",
            name="Renewable Energy Use",
            direction=CriterionDirection.BENEFIT,
            weight=0.25,
        )


def test_criterion_is_immutable() -> None:
    """A criterion should not change after its creation."""

    criterion = Criterion(
        criterion_id="carbon_emissions",
        name="Carbon Emissions",
        direction=CriterionDirection.COST,
    )

    with pytest.raises(ValidationError):
        criterion.name = "Changed Name"