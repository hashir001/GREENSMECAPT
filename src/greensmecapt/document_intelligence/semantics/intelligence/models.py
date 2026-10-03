"""Contracts for grounded language-model document understanding."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.semantics.intelligence.policy import (
    CompanyProfileFieldInstruction,
    DocumentTypeInstruction,
    SectorInstruction,
    UnmappedMaterialCategory,
)
from greensmecapt.domain import EvidenceClaimNature, EvidenceItem


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


class QualitativeValueType(StrEnum):
    """Describe the only qualitative values a provider may propose."""

    SOURCE_TEXT = "source_text"
    BOOLEAN = "boolean"


class QualitativeInstruction(IntelligenceModel):
    """Describe one governed context claim the provider may identify."""

    claim_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    question: str = Field(min_length=1)
    value_type: QualitativeValueType
    criterion_id: str | None = Field(default=None, min_length=1)


class ReadinessFactorInstruction(IntelligenceModel):
    """Describe one research-grounded SME readiness factor."""

    factor_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class ReadinessEvidenceState(StrEnum):
    """Classify what one exact source quote says about readiness."""

    ENABLING = "enabling_evidence"
    CONSTRAINING = "constraining_evidence"
    MIXED = "mixed_evidence"


class SemanticExtractionRequest(IntelligenceModel):
    """Supply allowed metrics and traceable source segments."""

    document_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    metrics: tuple[MetricInstruction, ...] = Field(
        min_length=1
    )
    qualitative_claims: tuple[QualitativeInstruction, ...] = ()
    document_types: tuple[DocumentTypeInstruction, ...] = ()
    company_profile_fields: tuple[CompanyProfileFieldInstruction, ...] = ()
    sectors: tuple[SectorInstruction, ...] = ()
    activity_fact_ids: tuple[str, ...] = ()
    readiness_factors: tuple[ReadinessFactorInstruction, ...] = ()
    unmapped_material_categories: tuple[UnmappedMaterialCategory, ...] = ()
    maximum_unmapped_claims: int = Field(default=0, ge=0, le=50)
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
    claim_nature: EvidenceClaimNature = EvidenceClaimNature.UNSPECIFIED
    entity_name: str | None = Field(default=None, min_length=1)
    facility_or_site: str | None = Field(default=None, min_length=1)
    project_name: str | None = Field(default=None, min_length=1)


class QualitativeClaimPayload(IntelligenceModel):
    """Represent one source-grounded context proposal."""

    segment_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    boolean_value: bool | None = None
    reporting_period: str | None = Field(default=None, min_length=1)
    scope: str | None = Field(default=None, min_length=1)
    claim_nature: EvidenceClaimNature = EvidenceClaimNature.UNSPECIFIED
    entity_name: str | None = Field(default=None, min_length=1)
    facility_or_site: str | None = Field(default=None, min_length=1)
    project_name: str | None = Field(default=None, min_length=1)


class DocumentProfileClaimPayload(IntelligenceModel):
    """Propose a controlled document class from an exact source quote."""

    segment_id: str = Field(min_length=1)
    document_type_id: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    issuer_name: str | None = Field(default=None, min_length=1)
    reporting_period: str | None = Field(default=None, min_length=1)
    assurance_status: str | None = Field(default=None, min_length=1)


class CompanyProfileClaimPayload(IntelligenceModel):
    """Propose one controlled company fact from an exact source quote."""

    segment_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    raw_value: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)


class SectorActivityProposalPayload(IntelligenceModel):
    """Propose one sector and supported activity facts for review."""

    segment_id: str = Field(min_length=1)
    sector_id: str = Field(min_length=1)
    activity_fact_ids: tuple[str, ...] = ()
    source_quote: str = Field(min_length=1)


class UnmappedMaterialClaimPayload(IntelligenceModel):
    """Surface important source material outside the closed metric schema."""

    segment_id: str = Field(min_length=1)
    category_id: str = Field(min_length=1)
    suggested_label: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    model_rationale: str = Field(min_length=1)


class ReadinessClaimPayload(IntelligenceModel):
    """Propose one source-grounded SME readiness observation."""

    segment_id: str = Field(min_length=1)
    factor_id: str = Field(min_length=1)
    state: ReadinessEvidenceState
    source_quote: str = Field(min_length=1)
    model_rationale: str = Field(min_length=1)


class SemanticProviderOutput(IntelligenceModel):
    """Structured output required from every provider."""

    claims: tuple[SemanticClaimPayload, ...] = ()
    qualitative_claims: tuple[QualitativeClaimPayload, ...] = ()
    document_profile_claims: tuple[DocumentProfileClaimPayload, ...] = ()
    company_profile_claims: tuple[CompanyProfileClaimPayload, ...] = ()
    sector_activity_proposals: tuple[SectorActivityProposalPayload, ...] = ()
    readiness_claims: tuple[ReadinessClaimPayload, ...] = ()
    unmapped_material_claims: tuple[UnmappedMaterialClaimPayload, ...] = ()


class GroundedIntelligenceClaim(IntelligenceModel):
    """Store one validated non-scoring proposal with provenance."""

    claim_id: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    value: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    related_ids: tuple[str, ...] = ()
    model_rationale: str | None = Field(default=None, min_length=1)


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
    request_count: int = Field(default=1, ge=1)
    company_policy_id: str | None = Field(default=None, min_length=1)
    company_policy_version: str | None = Field(default=None, min_length=1)

    evidence_items: tuple[EvidenceItem, ...]
    intelligence_claims: tuple[GroundedIntelligenceClaim, ...] = ()
    rejected_claims: tuple[RejectedSemanticClaim, ...]


class SemanticProviderConnection(IntelligenceModel):
    """Confirm that a configured provider accepted the real contract."""

    provider_name: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
