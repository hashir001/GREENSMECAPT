"""SME response and criterion-observation contracts."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonBlank = Annotated[str, Field(min_length=1)]


class ObservationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True, allow_inf_nan=False
    )


class ResponseKind(StrEnum):
    EXACT_NUMBER = "exact_number"
    NUMBER_RANGE = "number_range"
    LINGUISTIC = "linguistic"
    UNKNOWN = "unknown"
    NOT_MEASURED = "not_measured"
    CLAIMED_NOT_APPLICABLE = "claimed_not_applicable"


class ObservationStatus(StrEnum):
    """Resolution state; READY means usable by an adapter, not already scored."""

    READY_NUMERIC = "ready_numeric"
    READY_RANGE = "ready_range"
    READY_LINGUISTIC = "ready_linguistic"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    NOT_MEASURED = "not_measured"
    PENDING_REVIEW = "pending_review"
    APPLICABILITY_REVIEW = "applicability_review"
    NEEDS_SELECTION = "needs_selection"
    CONFLICT = "conflict"


class CriterionResponse(ObservationModel):
    response_id: NonBlank
    sme_id: NonBlank
    criterion_id: NonBlank
    kind: ResponseKind
    exact_value: float | None = None
    lower_value: float | None = None
    upper_value: float | None = None
    unit: str | None = None
    linguistic_value: str | None = None
    narrative: str | None = None
    reporting_period: str | None = None
    scope: str | None = None
    supporting_evidence_ids: tuple[NonBlank, ...] = ()
    submitted_by: NonBlank

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        numeric_fields = (self.exact_value, self.lower_value, self.upper_value)
        if self.kind is ResponseKind.EXACT_NUMBER:
            if self.exact_value is None or any(
                value is not None for value in (self.lower_value, self.upper_value)
            ):
                raise ValueError("An exact response requires only exact_value.")
            if not self.unit:
                raise ValueError("A numeric response requires a unit.")
        elif self.kind is ResponseKind.NUMBER_RANGE:
            if (
                self.exact_value is not None
                or self.lower_value is None
                or self.upper_value is None
                or self.lower_value > self.upper_value
            ):
                raise ValueError("A range requires ordered lower and upper values.")
            if not self.unit:
                raise ValueError("A numeric response requires a unit.")
        elif self.kind is ResponseKind.LINGUISTIC:
            if not self.linguistic_value or any(
                value is not None for value in numeric_fields
            ):
                raise ValueError(
                    "A linguistic response requires only a linguistic value."
                )
        elif (
            any(value is not None for value in numeric_fields)
            or self.linguistic_value
        ):
            raise ValueError("A state response cannot contain a score or value.")

        if self.kind is ResponseKind.CLAIMED_NOT_APPLICABLE and not self.narrative:
            raise ValueError("A non-applicability claim requires an explanation.")
        return self


class CriterionObservation(ObservationModel):
    """A resolved input for a topic, never a criterion or MCDM score."""

    criterion_id: NonBlank
    status: ObservationStatus
    exact_value: float | None = None
    lower_value: float | None = None
    upper_value: float | None = None
    unit: str | None = None
    linguistic_value: str | None = None
    reporting_period: str | None = None
    scope: str | None = None
    response_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_indicator_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


class ObservationCoverage(ObservationModel):
    """Input coverage only; it is not environmental performance."""

    applicable_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    document_supported_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)


class ObservationSet(ObservationModel):
    sme_id: NonBlank
    policy_id: NonBlank
    policy_version: NonBlank
    observations: tuple[CriterionObservation, ...]
    coverage: ObservationCoverage
    unused_response_ids: tuple[str, ...] = ()
    unmapped_evidence_ids: tuple[str, ...] = ()

    @property
    def unresolved_criteria(self) -> tuple[str, ...]:
        ready = {
            ObservationStatus.READY_NUMERIC,
            ObservationStatus.READY_RANGE,
            ObservationStatus.READY_LINGUISTIC,
            ObservationStatus.NOT_APPLICABLE,
        }
        return tuple(
            item.criterion_id for item in self.observations if item.status not in ready
        )
