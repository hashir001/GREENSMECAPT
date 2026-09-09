"""Versioned contracts for converting observations into fuzzy MCDM inputs."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)

NonBlank = Annotated[str, Field(min_length=1)]


class NormalizationModel(BaseModel):
    """Provide strict immutable normalization contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class CriterionDirection(StrEnum):
    """Describe whether larger or smaller values are preferable."""

    BENEFIT = "benefit"
    COST = "cost"


class AssessmentReadiness(StrEnum):
    """Describe whether normalized inputs may enter cohort preparation."""

    READY = "ready"
    PROVISIONAL = "provisional"
    BLOCKED = "blocked"


class TriangularFuzzyNumber(NormalizationModel):
    """Represent lower, most plausible and upper normalized values."""

    lower: float = Field(ge=0.0, le=1.0)
    modal: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not self.lower <= self.modal <= self.upper:
            raise ValueError(
                "A fuzzy number must satisfy lower <= modal <= upper."
            )
        return self


class NumericScale(NormalizationModel):
    """Define an explicit quantitative normalization scale."""

    lower_bound: float
    upper_bound: float
    direction: CriterionDirection
    allowed_units: tuple[NonBlank, ...] = Field(min_length=1)
    allowed_indicator_ids: tuple[NonBlank, ...] = ()

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.lower_bound >= self.upper_bound:
            raise ValueError(
                "Numeric lower_bound must be below upper_bound."
            )
        return self


class CriterionNormalizationRule(NormalizationModel):
    """Define supported input routes for one assessment criterion."""

    criterion_id: NonBlank
    base_weight: float = Field(gt=0.0)
    allow_linguistic: StrictBool = False
    numeric_scale: NumericScale | None = None

    @model_validator(mode="after")
    def validate_routes(self) -> Self:
        if not self.allow_linguistic and self.numeric_scale is None:
            raise ValueError(
                "A rule requires a linguistic or numeric input route."
            )
        return self


class NormalizationPolicy(NormalizationModel):
    """Contain editable and versioned normalization decisions."""

    policy_id: NonBlank
    version: NonBlank
    status: str = "development"
    weight_source: NonBlank
    minimum_coverage_ratio: float = Field(ge=0.0, le=1.0)
    default_linguistic_scale: dict[
        NonBlank,
        TriangularFuzzyNumber,
    ] = Field(min_length=1)
    rules: tuple[CriterionNormalizationRule, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        criterion_ids = [rule.criterion_id for rule in self.rules]

        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError(
                "Normalization criterion IDs must be unique."
            )

        linguistic_labels = [
            label.casefold()
            for label in self.default_linguistic_scale
        ]

        if len(linguistic_labels) != len(set(linguistic_labels)):
            raise ValueError(
                "Linguistic labels must be case-insensitively unique."
            )

        return self


class NormalizedCriterionInput(NormalizationModel):
    """Represent one normalized input, not a final criterion score."""

    criterion_id: NonBlank
    fuzzy_value: TriangularFuzzyNumber
    base_weight: float = Field(gt=0.0)
    source_status: NonBlank
    response_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_indicator_ids: tuple[str, ...] = ()


class NormalizationIssue(NormalizationModel):
    """Explain why an observation could not become an MCDM input."""

    criterion_id: NonBlank
    code: NonBlank
    message: NonBlank


class NormalizedAssessmentInputs(NormalizationModel):
    """Contain normalized inputs and an explicit readiness decision."""

    sme_id: NonBlank
    normalization_policy_id: NonBlank
    normalization_policy_version: NonBlank
    readiness: AssessmentReadiness
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    criteria: tuple[NormalizedCriterionInput, ...]
    issues: tuple[NormalizationIssue, ...]

    @property
    def criterion_ids(self) -> tuple[str, ...]:
        return tuple(item.criterion_id for item in self.criteria)