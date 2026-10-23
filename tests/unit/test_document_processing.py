"""Tests for persisted end-to-end document processing."""

from hashlib import sha256
from pathlib import Path

import pytest

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedVisualRegion,
    TextSource,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.readers import (
    PlainTextDocumentReader,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.document_intelligence.understanding import (
    HybridSemanticExtractor,
)
from greensmecapt.document_intelligence.vision import (
    VisualMetricClaim,
    VisualProviderOutput,
    VisualUnderstandingService,
)
from greensmecapt.domain import (
    DocumentProcessingStatus,
    EvidenceValidationStatus,
    SME,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence import Database, GreenSMERepository
from greensmecapt.services import (
    DocumentProcessingError,
    StoredDocumentProcessingService,
)
from greensmecapt.storage import LocalDocumentStorage

CATALOG = load_metric_catalog(
    Path("config/metric_catalog.development.json")
)


class VisualReader:
    """Read one synthetic visual page and render its chart."""

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        return ExtractedDocument(
            document_id=document.document_id,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text="Environmental performance chart.",
                    text_source=TextSource.OCR,
                    page_width=600,
                    page_height=800,
                    visual_regions=(
                        ExtractedVisualRegion(
                            region_id="page_1_chart_1",
                            kind=VisualRegionKind.CHART,
                            bounding_box=BoundingBox(
                                x0=10,
                                top=20,
                                x1=200,
                                bottom=160,
                            ),
                            caption="Renewable energy share",
                        ),
                    ),
                ),
            ),
        )

    def render_visual_region(
        self,
        document,
        content,
        page,
        region,
    ) -> bytes:
        return b"visual-crop"


class VisualProvider:
    """Return one explicit chart value."""

    provider_name = "test_visual_provider"
    provider_version = "1.0"
    model_name = "test_visual_model"

    def interpret(self, request):
        return VisualProviderOutput(
            summary="One explicit metric found.",
            claims=(
                VisualMetricClaim(
                    indicator_id="renewable_energy_percentage",
                    raw_value="72 percent",
                    raw_number=72,
                    raw_unit="percent",
                    source_description="Value printed above chart bar.",
                ),
            ),
        )


def _prepare_document(
    tmp_path: Path,
    content: bytes,
) -> tuple[
    Database,
    LocalDocumentStorage,
    SourceDocument,
]:
    database = Database(
        f"sqlite:///{tmp_path / 'processing.db'}"
    )
    database.create_schema()
    storage = LocalDocumentStorage(tmp_path / "documents")
    document = SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name="report.txt",
        mime_type="text/plain",
        sha256=sha256(content).hexdigest(),
    )
    storage_key = storage.save(
        sme_id=document.sme_id,
        document_id=document.document_id,
        sha256=document.sha256,
        content=content,
    )

    with database.session() as session:
        repository = GreenSMERepository(session)
        repository.save_record(
            StructuredInvestmentRecord(
                sme=SME(
                    sme_id="sme_001",
                    legal_name="EcoPack Manufacturing LLC",
                    sector="Sustainable Packaging",
                    jurisdiction="United Arab Emirates",
                )
            )
        )
        repository.attach_document(
            document=document,
            storage_key=storage_key,
            actor_id="sme-user-001",
        )

    return database, storage, document


def _service(
    storage: LocalDocumentStorage,
) -> StoredDocumentProcessingService:
    return StoredDocumentProcessingService(
        storage=storage,
        reader=PlainTextDocumentReader(),
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=SemanticMetricExtractor(CATALOG),
            catalog=CATALOG,
        ),
    )


def test_process_stored_document_into_persisted_evidence(
    tmp_path: Path,
) -> None:
    """Stored bytes should become durable traceable evidence."""

    database, storage, document = _prepare_document(
        tmp_path,
        b"Renewable energy share: 72 percent.",
    )

    with database.session() as session:
        repository = GreenSMERepository(session)
        result = _service(storage).process(
            repository=repository,
            document_id=document.document_id,
            actor_id="sme-user-001",
        )

    assert result.state.status is DocumentProcessingStatus.COMPLETED
    assert result.state.attempt_count == 1
    assert result.state.evidence_count == 1
    assert result.state.deterministic_evidence_count == 1
    assert result.state.intelligent_provider_status == "disabled"
    assert len(result.evidence_items) == 1
    assert result.evidence_items[0].normalized_value == 72.0
    assert (
        result.evidence_items[0].validation_status
        is EvidenceValidationStatus.ACCEPTED
    )
    assert result.reconciliation is not None

    with database.session() as session:
        record = GreenSMERepository(session).get_record("sme_001")

    assert record.evidence_items == result.evidence_items


def test_completed_processing_is_idempotent(tmp_path: Path) -> None:
    """Repeating a completed request must not duplicate evidence."""

    database, storage, document = _prepare_document(
        tmp_path,
        b"Renewable energy share: 72 percent.",
    )
    service = _service(storage)

    with database.session() as session:
        repository = GreenSMERepository(session)
        first = service.process(
            repository=repository,
            document_id=document.document_id,
            actor_id="sme-user-001",
        )
        second = service.process(
            repository=repository,
            document_id=document.document_id,
            actor_id="sme-user-001",
        )

    assert first.evidence_items == second.evidence_items
    assert second.state.attempt_count == 1


def test_complete_document_without_recognized_metrics(
    tmp_path: Path,
) -> None:
    """Readable documents may validly produce no evidence."""

    database, storage, document = _prepare_document(
        tmp_path,
        b"The company opened a new facility.",
    )

    with database.session() as session:
        result = _service(storage).process(
            repository=GreenSMERepository(session),
            document_id=document.document_id,
            actor_id="sme-user-001",
        )

    assert result.state.status is DocumentProcessingStatus.COMPLETED
    assert result.state.evidence_count == 0
    assert result.evidence_items == ()
    assert result.reconciliation is None


def test_synchronous_processing_includes_visual_evidence(
    tmp_path: Path,
) -> None:
    """The direct processing path should not omit visual understanding."""

    database, storage, document = _prepare_document(
        tmp_path,
        b"synthetic visual source",
    )
    service = StoredDocumentProcessingService(
        storage=storage,
        reader=VisualReader(),
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=SemanticMetricExtractor(CATALOG),
            catalog=CATALOG,
        ),
        visual_service=VisualUnderstandingService(
            catalog=CATALOG,
            provider=VisualProvider(),
        ),
    )

    with database.session() as session:
        result = service.process(
            repository=GreenSMERepository(session),
            document_id=document.document_id,
            actor_id="sme-user-001",
        )

    assert len(result.evidence_items) == 1
    assert result.report is not None
    assert result.report.visual_evidence_ids == (
        result.evidence_items[0].evidence_id,
    )
    assert result.report.visual_understanding is not None


def test_record_failure_and_allow_retry(tmp_path: Path) -> None:
    """Unreadable content should fail explicitly and remain retryable."""

    database, storage, document = _prepare_document(
        tmp_path,
        b"\xff\xfe",
    )
    service = _service(storage)

    with database.session() as session:
        repository = GreenSMERepository(session)

        with pytest.raises(DocumentProcessingError) as first_error:
            service.process(
                repository=repository,
                document_id=document.document_id,
                actor_id="sme-user-001",
            )

        first_state = repository.get_document_processing_state(
            document.document_id
        )

        with pytest.raises(DocumentProcessingError):
            service.process(
                repository=repository,
                document_id=document.document_id,
                actor_id="sme-user-001",
            )

        second_state = repository.get_document_processing_state(
            document.document_id
        )

    assert first_error.value.code == "unreadable_document"
    assert first_state.status is DocumentProcessingStatus.FAILED
    assert first_state.attempt_count == 1
    assert second_state.status is DocumentProcessingStatus.FAILED
    assert second_state.attempt_count == 2

