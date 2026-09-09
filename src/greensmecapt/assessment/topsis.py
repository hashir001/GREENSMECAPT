"""TOPSIS scoring and ranking for resolved SME assessment inputs."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.input_models import (
    InputStatus,
    NumericDirection,
    SMEAssessmentInput,
)


class TopsisError(ValueError):
    """Raised when TOPSIS cannot run on inconsistent assessment inputs."""


class TopsisNormalization(StrEnum):
    """Describe the normalization method used by TOPSIS."""

    VECTOR = "vector"


class IndicatorWeight(BaseModel):
    """Assign a positive decision weight to one assessment indicator."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    indicator_id: str = Field(min_length=1)
    weight: float = Field(gt=0)


class TopsisConfiguration(BaseModel):
    """Versioned configuration for a reproducible TOPSIS assessment."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    configuration_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    weights: tuple[IndicatorWeight, ...] = Field(min_length=1)
    normalization: TopsisNormalization = TopsisNormalization.VECTOR

    @model_validator(mode="after")
    def validate_unique_weights(self) -> Self:
        """Require exactly one configured weight per indicator."""

        indicator_ids = [
            item.indicator_id for item in self.weights
        ]

        if len(indicator_ids) != len(set(indicator_ids)):
            raise ValueError("Weight indicator IDs must be unique.")

        return self


class TopsisSMEResult(BaseModel):
    """Store one SME's TOPSIS result and its geometric distances."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    sme_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)
    distance_to_ideal: float = Field(ge=0)
    distance_to_worst: float = Field(ge=0)


class TopsisResult(BaseModel):
    """Store a reproducible ranked TOPSIS assessment."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    specification_id: str = Field(min_length=1)
    specification_version: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    configuration_version: str = Field(min_length=1)
    normalized_weights: dict[str, float]
    ranking: tuple[TopsisSMEResult, ...] = Field(min_length=2)


def run_topsis(
    inputs: Sequence[SMEAssessmentInput],
    configuration: TopsisConfiguration,
) -> TopsisResult:
    """Score and rank SMEs using vector-normalized TOPSIS."""

    if len(inputs) < 2:
        raise TopsisError("TOPSIS requires at least two SMEs.")

    _validate_sme_ids(inputs)

    reference = inputs[0]
    reference_ids = tuple(
        item.definition.indicator_id
        for item in reference.indicators
    )

    if not reference_ids:
        raise TopsisError(
            "TOPSIS requires at least one assessment indicator."
        )

    _validate_inputs(
        inputs=inputs,
        reference=reference,
        reference_ids=reference_ids,
    )

    configured_weights = {
        item.indicator_id: item.weight
        for item in configuration.weights
    }

    configured_ids = set(configured_weights)
    required_ids = set(reference_ids)

    if configured_ids != required_ids:
        missing = sorted(required_ids - configured_ids)
        unexpected = sorted(configured_ids - required_ids)

        raise TopsisError(
            "Configured weights do not match assessment indicators. "
            f"Missing: {missing}; unexpected: {unexpected}."
        )

    total_weight = sum(configured_weights.values())

    normalized_weight_map = {
        indicator_id: configured_weights[indicator_id] / total_weight
        for indicator_id in reference_ids
    }

    weight_vector = np.array(
        [
            normalized_weight_map[indicator_id]
            for indicator_id in reference_ids
        ],
        dtype=float,
    )

    matrix = np.array(
        [
            [item.value for item in sme_input.indicators]
            for sme_input in inputs
        ],
        dtype=float,
    )

    column_norms = np.linalg.norm(matrix, axis=0)

    normalized_matrix = np.divide(
        matrix,
        column_norms,
        out=np.zeros_like(matrix, dtype=float),
        where=column_norms != 0,
    )

    weighted_matrix = normalized_matrix * weight_vector

    directions = tuple(
        item.definition.direction
        for item in reference.indicators
    )

    ideal = np.array(
        [
            (
                weighted_matrix[:, index].max()
                if direction is NumericDirection.BENEFIT
                else weighted_matrix[:, index].min()
            )
            for index, direction in enumerate(directions)
        ],
        dtype=float,
    )

    worst = np.array(
        [
            (
                weighted_matrix[:, index].min()
                if direction is NumericDirection.BENEFIT
                else weighted_matrix[:, index].max()
            )
            for index, direction in enumerate(directions)
        ],
        dtype=float,
    )

    distance_to_ideal = np.linalg.norm(
        weighted_matrix - ideal,
        axis=1,
    )
    distance_to_worst = np.linalg.norm(
        weighted_matrix - worst,
        axis=1,
    )

    raw_results: list[tuple[str, float, float, float]] = []

    for index, sme_input in enumerate(inputs):
        ideal_distance = float(distance_to_ideal[index])
        worst_distance = float(distance_to_worst[index])
        denominator = ideal_distance + worst_distance

        score = (
            worst_distance / denominator
            if denominator > 0
            else 0.5
        )

        raw_results.append(
            (
                sme_input.sme_id,
                float(score),
                ideal_distance,
                worst_distance,
            )
        )

    ordered_results = sorted(
        raw_results,
        key=lambda item: (-item[1], item[0]),
    )

    ranking = tuple(
        TopsisSMEResult(
            sme_id=sme_id,
            score=score,
            rank=rank,
            distance_to_ideal=ideal_distance,
            distance_to_worst=worst_distance,
        )
        for rank, (
            sme_id,
            score,
            ideal_distance,
            worst_distance,
        ) in enumerate(ordered_results, start=1)
    )

    return TopsisResult(
        specification_id=reference.specification_id,
        specification_version=reference.specification_version,
        configuration_id=configuration.configuration_id,
        configuration_version=configuration.version,
        normalized_weights=normalized_weight_map,
        ranking=ranking,
    )


def _validate_sme_ids(
    inputs: Sequence[SMEAssessmentInput],
) -> None:
    """Reject duplicate SMEs in one comparison."""

    sme_ids = [item.sme_id for item in inputs]

    if len(sme_ids) != len(set(sme_ids)):
        raise TopsisError(
            "SME IDs must be unique within a TOPSIS assessment."
        )


def _validate_inputs(
    *,
    inputs: Sequence[SMEAssessmentInput],
    reference: SMEAssessmentInput,
    reference_ids: tuple[str, ...],
) -> None:
    """Require comparable, ready inputs under one specification."""

    reference_definitions = tuple(
        item.definition for item in reference.indicators
    )

    for sme_input in inputs:
        if (
            sme_input.specification_id
            != reference.specification_id
            or sme_input.specification_version
            != reference.specification_version
        ):
            raise TopsisError(
                "Every SME must use the same assessment specification."
            )

        current_ids = tuple(
            item.definition.indicator_id
            for item in sme_input.indicators
        )

        if current_ids != reference_ids:
            raise TopsisError(
                "Every SME must contain the same ordered indicators."
            )

        current_definitions = tuple(
            item.definition for item in sme_input.indicators
        )

        if current_definitions != reference_definitions:
            raise TopsisError(
                "Indicator definitions differ between SME inputs."
            )

        unresolved = [
            item.definition.indicator_id
            for item in sme_input.indicators
            if item.status is not InputStatus.READY
            or item.value is None
        ]

        if unresolved:
            raise TopsisError(
                f"SME {sme_input.sme_id!r} has unresolved "
                f"indicators: {unresolved}."
            )