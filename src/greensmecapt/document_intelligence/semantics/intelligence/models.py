"""Contracts for grounded language-model metric extraction."""

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.domain import EvidenceItem


class IntelligenceModel(BaseModel):
    """Strict base model for intelligent extraction contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class SemanticSourceSegment(IntelligenceModel):
    """Expose one traceable document region to a provider."""

    segment_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    locator: str = Field(min_length=1)
    text: str = Field(min_length=1)


class MetricInstruction(IntelligenceModel):
    """Describe one metric the provider may identify."""

    indicator_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)
    canonical_unit: str = Field(min_length=1)
    accepted_unit_aliases: tuple[str, ...] = Field(
        min_length=1
    )
    minimum: float | None = None
    maximum: float | None = None


class SemanticExtractionRequest(IntelligenceModel):
    """Supply allowed metrics and traceable source segments."""

    document_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    metrics: tuple[MetricInstruction, ...] = Field(
        min_length=1
    )
    segments: tuple[SemanticSourceSegment, ...] = Field(
        min_length=1
    )


class SemanticClaimPayload(IntelligenceModel):
    """Represent one grounded claim proposed by a provider."""

    segment_id: str = Field(min_length=1)
    indicator_id: str = Field(min_length=1)

    raw_value: str = Field(min_length=1)
    raw_number: float
    raw_unit: str = Field(min_length=1)

    source_quote: str = Field(min_length=1)
    reporting_period: str | None = Field(
        default=None,
        min_length=1,
    )
    scope: str | None = Field(default=None, min_length=1)


class SemanticProviderOutput(IntelligenceModel):
    """Structured output required from every provider."""

    claims: tuple[SemanticClaimPayload, ...] = ()


class RejectedSemanticClaim(IntelligenceModel):
    """Record why a proposed claim was rejected."""

    claim_index: int = Field(ge=0)
    indicator_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class IntelligentExtractionReport(IntelligenceModel):
    """Return grounded evidence and rejected proposals."""

    provider_name: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    model_name: str = Field(min_length=1)

    evidence_items: tuple[EvidenceItem, ...]
    rejected_claims: tuple[RejectedSemanticClaim, ...]