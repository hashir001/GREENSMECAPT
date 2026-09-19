"""Contracts and audit results for selective visual interpretation."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.models import (
    ExtractedVisualRegion,
)
from greensmecapt.document_intelligence.semantics import MetricCatalog
from greensmecapt.domain import EvidenceItem


class VisualRelevance(StrEnum):
    """Describe whether a visual may affect assessment evidence."""

    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNCERTAIN = "uncertain"


class VisualProviderStatus(StrEnum):
    """Describe provider activity for one visual region."""

    SKIPPED = "skipped"
    DISABLED = "disabled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VisualModel(BaseModel):
    """Strict immutable base for visual-understanding records."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class VisualMetricClaim(VisualModel):
    """Represent one metric proposed from an exact visual crop."""

    indicator_id: str = Field(min_length=1)
    raw_value: str = Field(min_length=1)
    raw_number: float
    raw_unit: str = Field(min_length=1)
    source_description: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class VisualProviderOutput(VisualModel):
    """Structured response required from a multimodal provider."""

    summary: str = Field(min_length=1)
    claims: tuple[VisualMetricClaim, ...] = ()


@dataclass(frozen=True)
class VisualInterpretationRequest:
    """Supply one bounded image crop and the allowed metric vocabulary."""

    document_id: str
    page_number: int
    region: ExtractedVisualRegion
    page_context: str
    image_png: bytes
    catalog: MetricCatalog


class RejectedVisualClaim(VisualModel):
    """Preserve why a provider proposal was not accepted as evidence."""

    claim_index: int = Field(ge=0)
    indicator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class VisualRegionDecision(VisualModel):
    """Record routing and interpretation for one exact visual region."""

    page_number: int = Field(ge=1)
    region_id: str = Field(min_length=1)
    relevance: VisualRelevance
    relevance_reason: str = Field(min_length=1)
    provider_status: VisualProviderStatus
    provider_summary: str | None = Field(default=None, min_length=1)
    evidence_ids: tuple[str, ...] = ()
    rejected_claims: tuple[RejectedVisualClaim, ...] = ()
    issue: str | None = Field(default=None, min_length=1)


class VisualUnderstandingReport(VisualModel):
    """Summarize selective visual processing for one document or batch."""

    document_id: str = Field(min_length=1)
    decisions: tuple[VisualRegionDecision, ...] = ()

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            evidence_id
            for decision in self.decisions
            for evidence_id in decision.evidence_ids
        )


class VisualUnderstandingResult(VisualModel):
    """Return unvalidated visual evidence with complete diagnostics."""

    evidence_items: tuple[EvidenceItem, ...]
    report: VisualUnderstandingReport
