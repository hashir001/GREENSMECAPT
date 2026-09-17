"""Build one reconciled record from multiple SME documents."""

from collections.abc import Sequence

from greensmecapt.document_intelligence.ports import (
    DocumentReader,
)
from greensmecapt.document_intelligence.reconciliation import (
    EvidenceReconciliationService,
)
from greensmecapt.document_intelligence.service import (
    DocumentIntelligenceService,
)
from greensmecapt.document_intelligence.understanding.models import (
    DocumentSubmission,
    DocumentUnderstandingReport,
    SMEUnderstandingResult,
)
from greensmecapt.document_intelligence.understanding.semantic import (
    HybridSemanticExtractor,
)
from greensmecapt.domain import (
    SME,
    EvidenceItem,
    SourceDocument,
    StructuredInvestmentRecord,
)


class SMEUnderstandingError(ValueError):
    """Raised when an SME submission is internally inconsistent."""


class SMEDocumentUnderstandingService:
    """Process and reconcile all documents submitted by one SME."""

    def __init__(
        self,
        *,
        reader: DocumentReader,
        semantic_extractor: HybridSemanticExtractor,
        reconciliation_service: (
            EvidenceReconciliationService | None
        ) = None,
    ) -> None:
        self._reader = reader
        self._semantic_extractor = semantic_extractor
        self._reconciliation_service = (
            reconciliation_service
            or EvidenceReconciliationService()
        )

    def process(
        self,
        *,
        sme: SME,
        submissions: Sequence[DocumentSubmission],
    ) -> SMEUnderstandingResult:
        """Build a complete traceable investment record."""

        if not submissions:
            raise SMEUnderstandingError(
                "At least one document submission is required."
            )

        documents = tuple(
            submission.document
            for submission in submissions
        )
        _validate_documents(
            sme=sme,
            documents=documents,
        )

        evidence_items: list[EvidenceItem] = []
        reports: list[DocumentUnderstandingReport] = []

        for submission in submissions:
            capturing_extractor = _CapturingExtractor(
                self._semantic_extractor
            )

            service = DocumentIntelligenceService(
                reader=self._reader,
                evidence_extractor=capturing_extractor,
            )

            document_evidence = service.process(
                document=submission.document,
                content=submission.content,
            )

            if capturing_extractor.report is None:
                raise SMEUnderstandingError(
                    "Semantic extraction produced no diagnostics."
                )

            evidence_items.extend(document_evidence)
            reports.append(capturing_extractor.report)

        record = StructuredInvestmentRecord(
            sme=sme,
            documents=documents,
            evidence_items=tuple(evidence_items),
        )

        reconciliation = None

        if evidence_items:
            reconciliation = (
                self._reconciliation_service.reconcile(
                    tuple(evidence_items)
                )
            )

        return SMEUnderstandingResult(
            record=record,
            document_reports=tuple(reports),
            reconciliation=reconciliation,
        )


class _CapturingExtractor:
    """Capture diagnostics while satisfying the extractor port."""

    def __init__(
        self,
        extractor: HybridSemanticExtractor,
    ) -> None:
        self._extractor = extractor
        self.report: DocumentUnderstandingReport | None = (
            None
        )

    def extract(
        self,
        document: SourceDocument,
        extracted_document,
    ) -> tuple[EvidenceItem, ...]:
        """Extract evidence and retain its diagnostics."""

        result = self._extractor.extract_with_diagnostics(
            document=document,
            extracted_document=extracted_document,
        )
        self.report = result.report

        return result.evidence_items


def _validate_documents(
    *,
    sme: SME,
    documents: Sequence[SourceDocument],
) -> None:
    """Validate company ownership and document identity."""

    document_ids = [
        document.document_id
        for document in documents
    ]

    if len(document_ids) != len(set(document_ids)):
        raise SMEUnderstandingError(
            "Document IDs must be unique within a submission."
        )

    wrong_sme = [
        document.document_id
        for document in documents
        if document.sme_id != sme.sme_id
    ]

    if wrong_sme:
        raise SMEUnderstandingError(
            "Every submitted document must belong to the SME. "
            f"Invalid documents: {sorted(wrong_sme)}."
        )