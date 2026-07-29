"""Domain model for evidence extracted from an SME document."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

type EvidenceValue = str | int | float | bool


class EvidenceValidationStatus(StrEnum):
    """Describe whether extracted evidence has been validated."""

    UNVALIDATED = "unvalidated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


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
    criterion_id: str | None = Field(default=None, min_length=1)

    raw_value: str = Field(min_length=1)
    normalized_value: EvidenceValue
    unit: str | None = Field(default=None, min_length=1)

    source_locator: str = Field(min_length=1)
    source_excerpt: str | None = Field(default=None, min_length=1)

    extraction_method: str = Field(min_length=1)
    extractor_name: str = Field(min_length=1)
    extractor_version: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    validation_status: EvidenceValidationStatus = (
        EvidenceValidationStatus.UNVALIDATED
    )