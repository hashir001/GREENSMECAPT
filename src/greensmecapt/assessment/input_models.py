"""Definitions and resolved inputs for evidence-based assessment."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NumericDirection(StrEnum):
    """Describe whether larger or smaller indicator values are preferred."""

    BENEFIT = "benefit"
    COST = "cost"


class InputStatus(StrEnum):
    """Describe whether evidence resolved to a usable indicator value."""

    READY = "ready"
    MISSING = "missing"
    INVALID = "invalid"
    CONFLICT = "conflict"


class IndicatorDefinition(BaseModel):
    """Define the numeric evidence expected for one assessment indicator."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    indicator_id: str = Field(min_length=1)
    criterion_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    direction: NumericDirection
    # Required inside this fixed specification only. Applicability for an
    # individual SME is resolved before a comparison specification is built.
    required: bool = True

    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Reject contradictory allowed ranges."""

        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("Minimum must not exceed maximum.")

        return self


class AssessmentSpecification(BaseModel):
    """Versioned indicator definitions for an assessment."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    specification_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    indicators: tuple[IndicatorDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_indicators(self) -> Self:
        """Each indicator must have one unambiguous definition."""

        indicator_ids = [
            indicator.indicator_id for indicator in self.indicators
        ]

        if len(indicator_ids) != len(set(indicator_ids)):
            raise ValueError("Indicator IDs must be unique.")

        return self


class ResolvedIndicator(BaseModel):
    """Result of resolving accepted evidence against one definition."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    definition: IndicatorDefinition
    status: InputStatus
    value: float | None = None
    evidence_ids: tuple[str, ...] = ()
    response_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        """Keep status, value and provenance consistent."""

        if self.status is InputStatus.READY:
            if self.value is None:
                raise ValueError(
                    "Ready inputs require a value and supporting evidence."
                )
            if not self.evidence_ids and not self.response_ids:
                raise ValueError(
                    "Ready inputs require evidence or response provenance."
                )

            if self.issues:
                raise ValueError("Ready inputs must not contain issues.")

            if (
                self.definition.minimum is not None
                and self.value < self.definition.minimum
            ):
                raise ValueError("Ready value is below the allowed minimum.")

            if (
                self.definition.maximum is not None
                and self.value > self.definition.maximum
            ):
                raise ValueError("Ready value exceeds the allowed maximum.")

        else:
            if self.value is not None:
                raise ValueError(
                    "Unresolved inputs must not contain an assessment value."
                )

            if not self.issues:
                raise ValueError("Unresolved inputs must explain the issue.")

        return self


class SMEAssessmentInput(BaseModel):
    """Resolved indicators for one SME under one specification."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    sme_id: str = Field(min_length=1)
    specification_id: str = Field(min_length=1)
    specification_version: str = Field(min_length=1)
    indicators: tuple[ResolvedIndicator, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_indicators(self) -> Self:
        """Prevent duplicate resolved rows."""

        indicator_ids = [
            item.definition.indicator_id for item in self.indicators
        ]

        if len(indicator_ids) != len(set(indicator_ids)):
            raise ValueError("Resolved indicator IDs must be unique.")

        return self

    @property
    def required_inputs_ready(self) -> bool:
        """Report whether every required indicator has a usable value."""

        return all(
            item.status is InputStatus.READY
            for item in self.indicators
            if item.definition.required
        )

    @property
    def all_inputs_ready(self) -> bool:
        """Report whether every configured indicator has a usable value."""

        return all(
            item.status is InputStatus.READY
            for item in self.indicators
        )