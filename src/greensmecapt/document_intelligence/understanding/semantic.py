"""Combine deterministic and intelligent semantic extraction."""

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
)
from greensmecapt.document_intelligence.orchestration import (
    DocumentProcessingPlanner,
)
from greensmecapt.document_intelligence.semantics import (
    MetricCatalog,
    SemanticMetricExtractor,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    IntelligentSemanticExtractionService,
    SemanticProviderError,
)
from greensmecapt.document_intelligence.understanding.models import (
    DocumentUnderstandingReport,
    HybridSemanticConfiguration,
    HybridSemanticResult,
    IntelligentProviderStatus,
)
from greensmecapt.domain import (
    EvidenceItem,
    SourceDocument,
)


class HybridSemanticExtractionError(RuntimeError):
    """Raised when required intelligent extraction fails."""


class HybridSemanticExtractor:
    """Combine rules with optional grounded model extraction."""

    def __init__(
        self,
        *,
        deterministic_extractor: SemanticMetricExtractor,
        catalog: MetricCatalog,
        intelligent_service: (
            IntelligentSemanticExtractionService | None
        ) = None,
        configuration: (
            HybridSemanticConfiguration | None
        ) = None,
    ) -> None:
        self._deterministic_extractor = (
            deterministic_extractor
        )
        self._catalog = catalog
        self._intelligent_service = intelligent_service
        self._configuration = (
            configuration
            or HybridSemanticConfiguration()
        )

    def extract(
        self,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> tuple[EvidenceItem, ...]:
        """Satisfy the standard evidence-extractor interface."""

        return self.extract_with_diagnostics(
            document=document,
            extracted_document=extracted_document,
        ).evidence_items

    def extract_with_diagnostics(
        self,
        *,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> HybridSemanticResult:
        """Run rules and the optional intelligent provider."""

        deterministic = (
            self._deterministic_extractor.extract(
                document,
                extracted_document,
            )
        )

        if self._intelligent_service is None:
            return _result(
                document=document,
                extracted_document=extracted_document,
                deterministic=deterministic,
                intelligent=(),
                provider_status=(
                    IntelligentProviderStatus.DISABLED
                ),
            )

        try:
            intelligent_report = (
                self._intelligent_service.extract(
                    document=document,
                    extracted_document=extracted_document,
                    catalog=self._catalog,
                )
            )
        except SemanticProviderError as error:
            if (
                self._configuration
                .require_intelligent_success
            ):
                raise HybridSemanticExtractionError(
                    "Required intelligent semantic extraction "
                    "failed."
                ) from error

            return _result(
                document=document,
                extracted_document=extracted_document,
                deterministic=deterministic,
                intelligent=(),
                provider_status=(
                    IntelligentProviderStatus.FAILED
                ),
                provider_error=str(error),
            )

        return _result(
            document=document,
            extracted_document=extracted_document,
            deterministic=deterministic,
            intelligent=(
                intelligent_report.evidence_items
            ),
            provider_status=(
                IntelligentProviderStatus.SUCCEEDED
            ),
            rejected_claim_count=len(
                intelligent_report.rejected_claims
            ),
            intelligent_request_count=(
                intelligent_report.request_count
            ),
        )


def _result(
    *,
    document: SourceDocument,
    extracted_document: ExtractedDocument,
    deterministic: tuple[EvidenceItem, ...],
    intelligent: tuple[EvidenceItem, ...],
    provider_status: IntelligentProviderStatus,
    rejected_claim_count: int = 0,
    intelligent_request_count: int = 0,
    provider_error: str | None = None,
) -> HybridSemanticResult:
    """Build a validated combined result."""

    evidence_items = (
        *deterministic,
        *intelligent,
    )
    evidence_ids = [
        evidence.evidence_id
        for evidence in evidence_items
    ]

    if len(evidence_ids) != len(set(evidence_ids)):
        raise HybridSemanticExtractionError(
            "Semantic extractors produced duplicate "
            "evidence IDs."
        )

    for evidence in evidence_items:
        if evidence.document_id != document.document_id:
            raise HybridSemanticExtractionError(
                "Semantic evidence references another document."
            )

        if evidence.sme_id != document.sme_id:
            raise HybridSemanticExtractionError(
                "Semantic evidence references another SME."
            )

    return HybridSemanticResult(
        evidence_items=evidence_items,
        report=DocumentUnderstandingReport(
            document_id=document.document_id,
            processing_manifest=(
                DocumentProcessingPlanner().plan(
                    extracted_document
                )
            ),
            deterministic_evidence_ids=tuple(
                evidence.evidence_id
                for evidence in deterministic
            ),
            intelligent_evidence_ids=tuple(
                evidence.evidence_id
                for evidence in intelligent
            ),
            context_evidence_ids=tuple(
                evidence.evidence_id
                for evidence in intelligent
                if evidence.extraction_method
                == "language_model_grounded_context_extraction"
            ),
            intelligent_request_count=intelligent_request_count,
            rejected_intelligent_claim_count=(
                rejected_claim_count
            ),
            intelligent_provider_status=provider_status,
            intelligent_provider_error=provider_error,
            evidence_ids=tuple(evidence_ids),
        ),
    )
