"""Integration tests for page-bounded resumable processing."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    ExtractedPage,
    ExtractedPageBatch,
    TextSource,
)
from greensmecapt.document_intelligence.orchestration import (
    LongDocumentPolicy,
)
from greensmecapt.document_intelligence.readers import DocumentReadError
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.document_intelligence.understanding import (
    HybridSemanticExtractor,
)
from greensmecapt.domain import (
    SME,
    DocumentBatchStatus,
    DocumentJobStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence import Database, GreenSMERepository
from greensmecapt.services import (
    DocumentProcessingJobService,
    StoredDocumentProcessingService,
)
from greensmecapt.storage import LocalDocumentStorage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    PROJECT_ROOT
    / "config"
    / "metric_catalog.development.json"
)


class FailOncePagedReader:
    """Fail one middle batch and record every page request."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, ...]] = []
        self.failed_once = False

    def page_count(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> int:
        return 5

    def read_page_batch(
        self,
        document: SourceDocument,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> ExtractedPageBatch:
        self.calls.append(page_numbers)

        if page_numbers == (3, 4) and not self.failed_once:
            self.failed_once = True
            raise DocumentReadError("Temporary OCR failure on page 4.")

        return ExtractedPageBatch(
            document_id=document.document_id,
            total_pages=5,
            requested_pages=page_numbers,
            pages=tuple(
                ExtractedPage(
                    page_number=page_number,
                    text=(
                        "Renewable energy share: 72 percent."
                        if page_number == 1
                        else f"Environmental report page {page_number}."
                    ),
                    text_source=TextSource.PLAIN_TEXT,
                )
                for page_number in page_numbers
            ),
        )


def test_retry_resumes_after_completed_page_checkpoint(
    tmp_path: Path,
) -> None:
    """A retry should begin at the failed batch, not page one."""

    database = Database(
        f"sqlite:///{tmp_path / 'resumable-processing.db'}"
    )
    database.create_schema()
    storage = LocalDocumentStorage(tmp_path / "documents")
    reader = FailOncePagedReader()
    catalog = load_metric_catalog(CATALOG_PATH)
    processor = StoredDocumentProcessingService(
        storage=storage,
        reader=reader,
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=SemanticMetricExtractor(catalog),
            catalog=catalog,
        ),
        long_document_policy=LongDocumentPolicy(
            page_batch_size=2
        ),
    )
    runner = DocumentProcessingJobService(processor)
    content = b"synthetic five-page source"
    sme = SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )
    document = SourceDocument(
        document_id="doc_001",
        sme_id=sme.sme_id,
        file_name="environmental-report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )
    storage_key = storage.save(
        sme_id=sme.sme_id,
        document_id=document.document_id,
        sha256=document.sha256,
        content=content,
    )

    with database.session() as session:
        repository = GreenSMERepository(session)
        repository.save_record(
            StructuredInvestmentRecord(sme=sme)
        )
        repository.attach_document(
            document=document,
            storage_key=storage_key,
            actor_id="user_001",
        )
        queued = repository.enqueue_document_processing(
            document_id=document.document_id,
            actor_id="user_001",
        )
        first_attempt = runner.run(
            repository=repository,
            job_id=queued.job_id,
        )
        first_checkpoints = (
            repository.list_document_batch_checkpoints(
                queued.job_id
            )
        )
        second_attempt = runner.run(
            repository=repository,
            job_id=queued.job_id,
        )
        final_checkpoints = (
            repository.list_document_batch_checkpoints(
                queued.job_id
            )
        )
        result = processor.get_result(
            repository=repository,
            document_id=document.document_id,
        )

    assert first_attempt.status is DocumentJobStatus.FAILED
    assert [item.status for item in first_checkpoints] == [
        DocumentBatchStatus.COMPLETED,
        DocumentBatchStatus.FAILED,
        DocumentBatchStatus.PLANNED,
    ]
    assert second_attempt.status is DocumentJobStatus.COMPLETED
    assert all(
        item.status is DocumentBatchStatus.COMPLETED
        for item in final_checkpoints
    )
    assert reader.calls == [
        (1, 2),
        (3, 4),
        (3, 4),
        (5,),
    ]
    assert result.state.evidence_count == 1
    assert result.evidence_items[0].normalized_value == 72.0
