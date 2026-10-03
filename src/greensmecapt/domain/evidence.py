"""Domain model for evidence extracted from an SME document."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

type EvidenceValue = str | int | float | bool


class EvidenceValidationStatus(StrEnum):
    """Describe whether extracted evidence has been validated."""

    UNVALIDATED = "unvalidated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvidenceClaimNature(StrEnum):
    """Distinguish reported results from estimates, targets and forecasts."""

    ACTUAL = "actual"
    ESTIMATE = "estimate"
    TARGET = "target"
    PROJECTED = "projected"
    UNSPECIFIED = "unspecified"


class SMEVerificationStatus(StrEnum):
    """Describe an SME's response without changing source evidence."""

    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    CORRECTION_PROPOSED = "correction_proposed"
    NOT_APPLICABLE = "not_applicable"


class SMEVerification(BaseModel):
    """Retain SME confirmation or correction alongside immutable evidence."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    status: SMEVerificationStatus = SMEVerificationStatus.UNREVIEWED
    proposed_value: EvidenceValue | None = None
    proposed_unit: str | None = Field(default=None, min_length=1)
    proposed_reporting_period: str | None = Field(default=None, min_length=1)
    proposed_scope: str | None = Field(default=None, min_length=1)
    comment: str | None = Field(default=None, min_length=1)
    submitted_by: str | None = Field(default=None, min_length=1)
    submitted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_response(self):
        proposed = (
            self.proposed_value,
            self.proposed_unit,
            self.proposed_reporting_period,
            self.proposed_scope,
        )
        if (
            self.status is SMEVerificationStatus.CORRECTION_PROPOSED
            and not any(value is not None for value in proposed)
        ):
            raise ValueError("A proposed correction must change at least one field.")
        if (
            self.status is SMEVerificationStatus.NOT_APPLICABLE
            and self.comment is None
        ):
            raise ValueError("Not-applicable evidence requires an explanation.")
        if self.status is not SMEVerificationStatus.UNREVIEWED and (
            self.submitted_by is None or self.submitted_at is None
        ):
            raise ValueError("An SME response requires actor and timestamp provenance.")
        return self


class EvidenceItem(BaseModel):
    """Represent one traceable fact extracted from a source document."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    evidence_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    indicator_id: str = Field(min_length=1)
    criterion_id: str | None = Field(
        default=None,
        min_length=1,
    )

    raw_value: str = Field(min_length=1)
    normalized_value: EvidenceValue
    unit: str | None = Field(default=None, min_length=1)

    reporting_period: str | None = Field(
        default=None,
        min_length=1,
    )
    scope: str | None = Field(
        default=None,
        min_length=1,
    )
    claim_nature: EvidenceClaimNature = EvidenceClaimNature.UNSPECIFIED
    entity_name: str | None = Field(default=None, min_length=1)
    facility_or_site: str | None = Field(default=None, min_length=1)
    project_name: str | None = Field(default=None, min_length=1)

    source_locator: str = Field(min_length=1)
    source_excerpt: str | None = Field(
        default=None,
        min_length=1,
    )

    extraction_method: str = Field(min_length=1)
    extractor_name: str = Field(min_length=1)
    extractor_version: str | None = Field(
        default=None,
        min_length=1,
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    validation_status: EvidenceValidationStatus = (
        EvidenceValidationStatus.UNVALIDATED
    )
    sme_verification: SMEVerification = Field(default_factory=SMEVerification)
