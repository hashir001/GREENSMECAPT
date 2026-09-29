"""Results and controls for complete SME document understanding."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.orchestration import (
    DocumentProcessingManifest,
)
from greensmecapt.document_intelligence.reconciliation import (
    EvidenceReconciliationReport,
)
from greensmecapt.document_intelligence.semantics.intelligence.models import (
    GroundedIntelligenceClaim,
)
from greensmecapt.document_intelligence.vision import (
    VisualUnderstandingReport,
)
from greensmecapt.domain import (
    EvidenceItem,
    SourceDocument,
    StructuredInvestmentRecord,
)


class UnderstandingModel(BaseModel):
    """Strict base model for document-understanding results."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class IntelligentProviderStatus(StrEnum):
    """Describe whether intelligent extraction was attempted."""

    DISABLED = "disabled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HybridSemanticConfiguration(UnderstandingModel):
    """Control intelligent-provider failure behavior."""

    require_intelligent_success: bool = False


class DocumentSubmission(UnderstandingModel):
    """Associate registered metadata with supplied bytes."""

    document: SourceDocument
    content: bytes = Field(min_length=1)


class DocumentUnderstandingReport(UnderstandingModel):
    """Summarize semantic extraction for one document."""

    document_id: str = Field(min_length=1)
    processing_manifest: DocumentProcessingManifest | None = None
    deterministic_evidence_ids: tuple[str, ...] = ()
    intelligent_evidence_ids: tuple[str, ...] = ()
    context_evidence_ids: tuple[str, ...] = ()
    intelligent_request_count: int = Field(default=0, ge=0)
    company_policy_id: str | None = Field(default=None, min_length=1)
    company_policy_version: str | None = Field(default=None, min_length=1)
    intelligence_claims: tuple[GroundedIntelligenceClaim, ...] = ()
    visual_evidence_ids: tuple[str, ...] = ()
    visual_understanding: VisualUnderstandingReport | None = None
    rejected_intelligent_claim_count: int = Field(
        default=0,
        ge=0,
    )
    intelligent_provider_status: IntelligentProviderStatus
    intelligent_provider_error: str | None = Field(
        default=None,
        min_length=1,
    )
    evidence_ids: tuple[str, ...] = ()


class HybridSemanticResult(UnderstandingModel):
    """Return evidence plus extraction diagnostics."""

    evidence_items: tuple[EvidenceItem, ...]
    report: DocumentUnderstandingReport


class SMEUnderstandingResult(UnderstandingModel):
    """Return one complete multi-document SME result."""

    record: StructuredInvestmentRecord
    document_reports: tuple[
        DocumentUnderstandingReport, ...
    ]
    reconciliation: EvidenceReconciliationReport | None
