"""Process securely stored documents into persisted, traceable evidence."""

from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, ConfigDict

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPageBatch,
)
from greensmecapt.document_intelligence.orchestration import (
    DocumentProcessingPlanner,
    LongDocumentPolicy,
)
from greensmecapt.document_intelligence.ports import (
    DocumentReader,
    PagedDocumentReader,
    VisualRegionRenderer,
)
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
    HybridSemanticResult,
    IntelligentProviderStatus,
)
from greensmecapt.document_intelligence.vision import (
    VisualUnderstandingReport,
    VisualUnderstandingResult,
    VisualUnderstandingService,
)
from greensmecapt.domain import (
    DocumentBatchCheckpoint,
    DocumentBatchStatus,
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


class DocumentBatchProcessingResult(BaseModel):
    """Persist structured page output and its semantic evidence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    page_batch: ExtractedPageBatch
    semantic_result: HybridSemanticResult | None = None
    visual_result: VisualUnderstandingResult | None = None


class StoredDocumentProcessingService:
    """Join storage, document reading, NLP and persistence."""

    def __init__(
        self,
        *,
        storage: DocumentStorage,
        reader: DocumentReader,
        semantic_extractor: HybridSemanticExtractor,
        reconciliation_service: EvidenceReconciliationService | None = None,
        long_document_policy: LongDocumentPolicy | None = None,
        visual_service: VisualUnderstandingService | None = None,
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._semantic_extractor = semantic_extractor
        self._reconciliation_service = (
            reconciliation_service or EvidenceReconciliationService()
        )
        self._long_document_policy = (
            long_document_policy or LongDocumentPolicy()
        )
        self._visual_service = visual_service

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

            if (
                self._visual_service is not None
                and isinstance(self._reader, VisualRegionRenderer)
                and capturing_extractor.extracted_document is not None
            ):
                visual_result = self._visual_service.analyze(
                    document=registration.document,
                    pages=capturing_extractor.extracted_document.pages,
                    render_region=lambda page, region: (
                        self._reader.render_visual_region(
                            registration.document,
                            content,
                            page,
                            region,
                        )
                    ),
                )
                evidence_items, report = _append_visual_result(
                    evidence_items=evidence_items,
                    report=report,
                    visual_result=visual_result,
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

    def process_in_batches(
        self,
        *,
        repository: GreenSMERepository,
        document_id: str,
        actor_id: str,
        job_id: str,
        worker_id: str,
    ) -> DocumentProcessingResult:
        """Process bounded pages and resume from completed checkpoints."""

        if not isinstance(self._reader, PagedDocumentReader):
            return self.process(
                repository=repository,
                document_id=document_id,
                actor_id=actor_id,
            )

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
            _verify_document_content(
                registration.document,
                content,
            )
            total_pages = self._reader.page_count(
                registration.document,
                content,
            )
            checkpoints = repository.list_document_batch_checkpoints(
                job_id
            )

            if not checkpoints:
                checkpoints = repository.initialize_document_batch_checkpoints(
                    job_id=job_id,
                    checkpoints=_planned_checkpoints(
                        job_id=job_id,
                        document_id=document_id,
                        total_pages=total_pages,
                        policy=self._long_document_policy,
                    ),
                )

            results: list[DocumentBatchProcessingResult] = []

            for checkpoint in checkpoints:
                if checkpoint.status is DocumentBatchStatus.COMPLETED:
                    results.append(
                        DocumentBatchProcessingResult.model_validate_json(
                            checkpoint.result_json
                        )
                    )
                    continue

                active = repository.start_document_batch_checkpoint(
                    checkpoint_id=checkpoint.checkpoint_id,
                    worker_id=worker_id,
                )

                try:
                    page_batch = self._reader.read_page_batch(
                        registration.document,
                        content,
                        active.page_numbers,
                    )
                    semantic_result = (
                        self._semantic_extractor.extract_with_diagnostics(
                            document=registration.document,
                            extracted_document=(
                                page_batch.as_extracted_document()
                            ),
                        )
                        if page_batch.pages
                        else None
                    )
                    visual_result = (
                        self._visual_service.analyze(
                            document=registration.document,
                            pages=page_batch.pages,
                            render_region=lambda page, region: (
                                self._reader.render_visual_region(
                                    registration.document,
                                    content,
                                    page,
                                    region,
                                )
                            ),
                        )
                        if (
                            self._visual_service is not None
                            and isinstance(
                                self._reader,
                                VisualRegionRenderer,
                            )
                        )
                        else None
                    )
                    batch_result = DocumentBatchProcessingResult(
                        page_batch=page_batch,
                        semantic_result=semantic_result,
                        visual_result=visual_result,
                    )
                    repository.complete_document_batch_checkpoint(
                        checkpoint_id=active.checkpoint_id,
                        worker_id=worker_id,
                        result_json=batch_result.model_dump_json(),
                    )
                    repository.heartbeat_document_processing_job(
                        job_id=job_id,
                        worker_id=worker_id,
                    )
                    results.append(batch_result)
                except Exception as error:
                    repository.fail_document_batch_checkpoint(
                        checkpoint_id=active.checkpoint_id,
                        worker_id=worker_id,
                        failure_message=_batch_failure_message(error),
                    )
                    raise

            extracted_document = _merge_page_batches(
                document_id=document_id,
                total_pages=total_pages,
                results=tuple(results),
            )
            evidence_items, report = _merge_semantic_results(
                document=registration.document,
                extracted_document=extracted_document,
                results=tuple(results),
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
        self.extracted_document: ExtractedDocument | None = None

    def extract(
        self,
        document: SourceDocument,
        extracted_document,
    ) -> tuple[EvidenceItem, ...]:
        self.extracted_document = extracted_document
        result = self._extractor.extract_with_diagnostics(
            document=document,
            extracted_document=extracted_document,
        )
        self.report = result.report
        return result.evidence_items


def _append_visual_result(
    *,
    evidence_items: tuple[EvidenceItem, ...],
    report: DocumentUnderstandingReport,
    visual_result: VisualUnderstandingResult,
) -> tuple[tuple[EvidenceItem, ...], DocumentUnderstandingReport]:
    """Attach visual results while preserving semantic diagnostics."""

    combined = (*evidence_items, *visual_result.evidence_items)
    evidence_ids = tuple(item.evidence_id for item in combined)

    if len(evidence_ids) != len(set(evidence_ids)):
        raise ExtractionConsistencyError(
            "Semantic and visual extraction produced duplicate evidence IDs."
        )

    return combined, report.model_copy(
        update={
            "visual_evidence_ids": visual_result.report.evidence_ids,
            "visual_understanding": visual_result.report,
            "evidence_ids": evidence_ids,
        }
    )


def _reconcile(
    service: EvidenceReconciliationService,
    evidence_items: tuple[EvidenceItem, ...],
) -> EvidenceReconciliationReport | None:
    if not evidence_items:
        return None

    return service.reconcile(evidence_items)


def _planned_checkpoints(
    *,
    job_id: str,
    document_id: str,
    total_pages: int,
    policy: LongDocumentPolicy,
) -> tuple[DocumentBatchCheckpoint, ...]:
    """Create deterministic page checkpoints for one job."""

    now = datetime.now(UTC)

    return tuple(
        DocumentBatchCheckpoint(
            checkpoint_id=(
                f"{job_id}_checkpoint_{batch_index:04d}"
            ),
            job_id=job_id,
            document_id=document_id,
            batch_id=f"{document_id}_batch_{batch_index}",
            page_numbers=tuple(
                range(
                    start_page,
                    min(
                        start_page + policy.page_batch_size,
                        total_pages + 1,
                    ),
                )
            ),
            max_attempts=policy.maximum_batch_attempts,
            created_at=now,
            updated_at=now,
        )
        for batch_index, start_page in enumerate(
            range(
                1,
                total_pages + 1,
                policy.page_batch_size,
            ),
            start=1,
        )
    )


def _verify_document_content(
    document: SourceDocument,
    content: bytes,
) -> None:
    """Verify stored bytes once before any batch is processed."""

    if not content:
        raise DocumentIntegrityError(
            "Document content must not be empty."
        )

    if sha256(content).hexdigest() != document.sha256:
        raise DocumentIntegrityError(
            "Document content does not match its registered SHA-256."
        )


def _merge_page_batches(
    *,
    document_id: str,
    total_pages: int,
    results: tuple[DocumentBatchProcessingResult, ...],
) -> ExtractedDocument:
    """Reconstruct source order from independently saved page batches."""

    pages = tuple(
        sorted(
            (
                page
                for result in results
                for page in result.page_batch.pages
            ),
            key=lambda page: page.page_number,
        )
    )
    unreadable_pages = tuple(
        sorted(
            {
                page_number
                for result in results
                for page_number in result.page_batch.unreadable_pages
            }
        )
    )
    recorded_pages = {
        page.page_number for page in pages
    } | set(unreadable_pages)

    if recorded_pages != set(range(1, total_pages + 1)):
        raise ExtractionConsistencyError(
            "Page checkpoints do not cover the complete document."
        )

    if not pages:
        raise DocumentReadError(
            "No document page produced readable content."
        )

    return ExtractedDocument(
        document_id=document_id,
        pages=pages,
        total_pages=total_pages,
        unreadable_pages=unreadable_pages,
    )


def _merge_semantic_results(
    *,
    document: SourceDocument,
    extracted_document: ExtractedDocument,
    results: tuple[DocumentBatchProcessingResult, ...],
) -> tuple[tuple[EvidenceItem, ...], DocumentUnderstandingReport]:
    """Combine independently extracted batches into one final report."""

    semantic_results = tuple(
        result.semantic_result
        for result in results
        if result.semantic_result is not None
    )
    evidence_items = tuple(
        evidence
        for result in semantic_results
        for evidence in result.evidence_items
    )
    visual_results = tuple(
        result.visual_result
        for result in results
        if result.visual_result is not None
    )
    visual_evidence = tuple(
        evidence
        for result in visual_results
        for evidence in result.evidence_items
    )
    evidence_items = (*evidence_items, *visual_evidence)
    evidence_ids = tuple(
        evidence.evidence_id
        for evidence in evidence_items
    )

    if len(evidence_ids) != len(set(evidence_ids)):
        raise ExtractionConsistencyError(
            "Page batches produced duplicate evidence IDs."
        )

    deterministic_ids = tuple(
        evidence_id
        for result in semantic_results
        for evidence_id in result.report.deterministic_evidence_ids
    )
    intelligent_ids = tuple(
        evidence_id
        for result in semantic_results
        for evidence_id in result.report.intelligent_evidence_ids
    )
    visual_ids = tuple(
        evidence.evidence_id
        for evidence in visual_evidence
    )
    statuses = {
        result.report.intelligent_provider_status
        for result in semantic_results
    }

    if IntelligentProviderStatus.FAILED in statuses:
        provider_status = IntelligentProviderStatus.FAILED
    elif IntelligentProviderStatus.SUCCEEDED in statuses:
        provider_status = IntelligentProviderStatus.SUCCEEDED
    else:
        provider_status = IntelligentProviderStatus.DISABLED

    provider_errors = tuple(
        dict.fromkeys(
            result.report.intelligent_provider_error
            for result in semantic_results
            if result.report.intelligent_provider_error is not None
        )
    )
    report = DocumentUnderstandingReport(
        document_id=document.document_id,
        processing_manifest=DocumentProcessingPlanner().plan(
            extracted_document
        ),
        deterministic_evidence_ids=deterministic_ids,
        intelligent_evidence_ids=intelligent_ids,
        visual_evidence_ids=visual_ids,
        visual_understanding=(
            VisualUnderstandingReport(
                document_id=document.document_id,
                decisions=tuple(
                    decision
                    for result in visual_results
                    for decision in result.report.decisions
                ),
            )
            if visual_results
            else None
        ),
        rejected_intelligent_claim_count=sum(
            result.report.rejected_intelligent_claim_count
            for result in semantic_results
        ),
        intelligent_provider_status=provider_status,
        intelligent_provider_error=(
            " | ".join(provider_errors)
            if provider_errors
            else None
        ),
        evidence_ids=evidence_ids,
    )
    return evidence_items, report


def _batch_failure_message(error: Exception) -> str:
    """Return stable checkpoint diagnostics without internal details."""

    return _failure_details(error)[1]


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
