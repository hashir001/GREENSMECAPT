"""Process securely stored documents into persisted, traceable evidence."""

from pydantic import BaseModel, ConfigDict

from greensmecapt.document_intelligence.ports import DocumentReader
from greensmecapt.document_intelligence.readers import DocumentReadError
from greensmecapt.document_intelligence.reconciliation import (
    EvidenceReconciliationReport,
    EvidenceReconciliationService,
)
from greensmecapt.document_intelligence.service import (
    DocumentIntegrityError,
    DocumentIntelligenceService,
    ExtractionConsistencyError,
)
from greensmecapt.document_intelligence.understanding import (
    DocumentUnderstandingReport,
    HybridSemanticExtractionError,
    HybridSemanticExtractor,
)
from greensmecapt.domain import (
    DocumentProcessingState,
    DocumentProcessingStatus,
    EvidenceItem,
    SourceDocument,
)
from greensmecapt.persistence import (
    GreenSMERepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from greensmecapt.storage import (
    DocumentStorage,
    DocumentStorageError,
)


class DocumentProcessingError(RuntimeError):
    """Report a controlled processing failure to the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DocumentProcessingResult(BaseModel):
    """Return processing state, evidence and current reconciliation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    state: DocumentProcessingState
    report: DocumentUnderstandingReport | None = None
    evidence_items: tuple[EvidenceItem, ...] = ()
    reconciliation: EvidenceReconciliationReport | None = None


class StoredDocumentProcessingService:
    """Join storage, document reading, NLP and persistence."""

    def __init__(
        self,
        *,
        storage: DocumentStorage,
        reader: DocumentReader,
        semantic_extractor: HybridSemanticExtractor,
        reconciliation_service: EvidenceReconciliationService | None = None,
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._semantic_extractor = semantic_extractor
        self._reconciliation_service = (
            reconciliation_service or EvidenceReconciliationService()
        )

    def process(
        self,
        *,
        repository: GreenSMERepository,
        document_id: str,
        actor_id: str,
    ) -> DocumentProcessingResult:
        """Process one stored document idempotently."""

        registration = repository.get_stored_document(document_id)
        existing_state = repository.get_document_processing_state(
            document_id
        )

        if existing_state.status is DocumentProcessingStatus.COMPLETED:
            return self.get_result(
                repository=repository,
                document_id=document_id,
            )

        repository.begin_document_processing(
            document_id=document_id,
            actor_id=actor_id,
        )

        try:
            content = self._storage.read(registration.storage_key)
            capturing_extractor = _CapturingSemanticExtractor(
                self._semantic_extractor
            )
            intelligence_service = DocumentIntelligenceService(
                reader=self._reader,
                evidence_extractor=capturing_extractor,
            )
            evidence_items = intelligence_service.process(
                document=registration.document,
                content=content,
            )
            report = capturing_extractor.report

            if report is None:
                raise ExtractionConsistencyError(
                    "Semantic extraction produced no diagnostics."
                )

            reconciliation = self._reconcile_with_existing_evidence(
                repository=repository,
                document=registration.document,
                evidence_items=evidence_items,
            )

            state = repository.complete_document_processing(
                document_id=document_id,
                evidence_items=evidence_items,
                deterministic_evidence_count=len(
                    report.deterministic_evidence_ids
                ),
                intelligent_evidence_count=len(
                    report.intelligent_evidence_ids
                ),
                rejected_intelligent_claim_count=(
                    report.rejected_intelligent_claim_count
                ),
                intelligent_provider_status=(
                    report.intelligent_provider_status.value
                ),
                report_json=report.model_dump_json(),
                actor_id=actor_id,
            )
        except Exception as error:
            failure_code, failure_message = _failure_details(error)

            repository.fail_document_processing(
                document_id=document_id,
                failure_code=failure_code,
                failure_message=failure_message,
                actor_id=actor_id,
            )

            raise DocumentProcessingError(
                failure_code,
                failure_message,
            ) from error

        return DocumentProcessingResult(
            state=state,
            report=report,
            evidence_items=evidence_items,
            reconciliation=reconciliation,
        )

    def get_result(
        self,
        *,
        repository: GreenSMERepository,
        document_id: str,
    ) -> DocumentProcessingResult:
        """Return current state and any durable processing result."""

        registration = repository.get_stored_document(document_id)
        state = repository.get_document_processing_state(document_id)
        report_json = repository.get_document_processing_report(
            document_id
        )
        report = (
            DocumentUnderstandingReport.model_validate_json(report_json)
            if report_json is not None
            else None
        )
        evidence_items = repository.list_document_evidence(document_id)
        record = repository.get_record(registration.document.sme_id)
        reconciliation = _reconcile(
            self._reconciliation_service,
            record.evidence_items,
        )

        return DocumentProcessingResult(
            state=state,
            report=report,
            evidence_items=evidence_items,
            reconciliation=reconciliation,
        )

    def _reconcile_with_existing_evidence(
        self,
        *,
        repository: GreenSMERepository,
        document: SourceDocument,
        evidence_items: tuple[EvidenceItem, ...],
    ) -> EvidenceReconciliationReport | None:
        record = repository.get_record(document.sme_id)
        existing = tuple(
            evidence
            for evidence in record.evidence_items
            if evidence.document_id != document.document_id
        )

        return _reconcile(
            self._reconciliation_service,
            (*existing, *evidence_items),
        )


class _CapturingSemanticExtractor:
    """Capture semantic diagnostics through the standard extractor port."""

    def __init__(self, extractor: HybridSemanticExtractor) -> None:
        self._extractor = extractor
        self.report: DocumentUnderstandingReport | None = None

    def extract(
        self,
        document: SourceDocument,
        extracted_document,
    ) -> tuple[EvidenceItem, ...]:
        result = self._extractor.extract_with_diagnostics(
            document=document,
            extracted_document=extracted_document,
        )
        self.report = result.report
        return result.evidence_items


def _reconcile(
    service: EvidenceReconciliationService,
    evidence_items: tuple[EvidenceItem, ...],
) -> EvidenceReconciliationReport | None:
    if not evidence_items:
        return None

    return service.reconcile(evidence_items)


def _failure_details(error: Exception) -> tuple[str, str]:
    """Map internal exceptions to stable, non-sensitive diagnostics."""

    if isinstance(error, DocumentStorageError):
        return (
            "storage_error",
            "The stored document could not be read safely.",
        )

    if isinstance(error, DocumentIntegrityError):
        return "integrity_error", str(error)

    if isinstance(error, DocumentReadError):
        return "unreadable_document", str(error)

    if isinstance(
        error,
        (
            ExtractionConsistencyError,
            HybridSemanticExtractionError,
        ),
    ):
        return "extraction_consistency_error", str(error)

    if isinstance(error, PersistenceNotFoundError):
        return "missing_processing_dependency", str(error)

    if isinstance(error, PersistenceConflictError):
        return "processing_conflict", str(error)

    return (
        "internal_processing_error",
        "Document processing failed unexpectedly.",
    )
