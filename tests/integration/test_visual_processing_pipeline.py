"""Integration test for durable, selective visual understanding."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedPage,
    ExtractedPageBatch,
    ExtractedVisualRegion,
    TextSource,
    VisualRegionKind,
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
    VisualProviderStatus,
    VisualUnderstandingService,
)
from greensmecapt.domain import (
    SME,
    DocumentJobStatus,
    EvidenceValidationStatus,
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


class VisualPagedReader:
    """Return one chart and expose its exact source crop."""

    def __init__(self) -> None:
        self.rendered_regions: list[str] = []

    def page_count(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> int:
        return 1

    def read_page_batch(
        self,
        document: SourceDocument,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> ExtractedPageBatch:
        region = ExtractedVisualRegion(
            region_id="page_1_chart_1",
            kind=VisualRegionKind.CHART,
            bounding_box=BoundingBox(
                x0=50,
                top=80,
                x1=450,
                bottom=380,
            ),
            caption="Renewable energy share",
        )
        return ExtractedPageBatch(
            document_id=document.document_id,
            requested_pages=page_numbers,
            total_pages=1,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text="Environmental performance chart.",
                    text_source=TextSource.OCR,
                    page_width=600,
                    page_height=800,
                    visual_regions=(region,),
                ),
            ),
        )

    def render_visual_region(
        self,
        document: SourceDocument,
        content: bytes,
        page: ExtractedPage,
        region: ExtractedVisualRegion,
    ) -> bytes:
        self.rendered_regions.append(region.region_id)
        return b"bounded-chart-png"


class VisualProvider:
    """Return one controlled metric from the bounded chart."""

    provider_name = "integration_visual_provider"
    provider_version = "1.0"
    model_name = "integration_visual_model"

    def __init__(self) -> None:
        self.image_payloads: list[bytes] = []

    def interpret(self, request):
        self.image_payloads.append(request.image_png)
        return VisualProviderOutput(
            summary="The chart explicitly labels a 72 percent share.",
            claims=(
                VisualMetricClaim(
                    indicator_id="renewable_energy_percentage",
                    raw_value="72 percent",
                    raw_number=72,
                    raw_unit="percent",
                    source_description=(
                        "72 percent is printed above the renewable bar."
                    ),
                    confidence=0.9,
                ),
            ),
        )


def test_persist_visual_evidence_and_audit_report(
    tmp_path: Path,
) -> None:
    """A durable job should retain visual evidence and routing decisions."""

    database = Database(
        f"sqlite:///{tmp_path / 'visual-processing.db'}"
    )
    database.create_schema()
    storage = LocalDocumentStorage(tmp_path / "documents")
    catalog = load_metric_catalog(CATALOG_PATH)
    reader = VisualPagedReader()
    provider = VisualProvider()
    processor = StoredDocumentProcessingService(
        storage=storage,
        reader=reader,
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=SemanticMetricExtractor(catalog),
            catalog=catalog,
        ),
        visual_service=VisualUnderstandingService(
            catalog=catalog,
            provider=provider,
        ),
    )
    content = b"synthetic-chart-document"
    sme = SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )
    document = SourceDocument(
        document_id="doc_visual_001",
        sme_id=sme.sme_id,
        file_name="environmental-chart.pdf",
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
        repository.save_record(StructuredInvestmentRecord(sme=sme))
        repository.attach_document(
            document=document,
            storage_key=storage_key,
            actor_id="user_001",
        )
        queued = repository.enqueue_document_processing(
            document_id=document.document_id,
            actor_id="user_001",
        )
        job = DocumentProcessingJobService(processor).run(
            repository=repository,
            job_id=queued.job_id,
        )
        result = processor.get_result(
            repository=repository,
            document_id=document.document_id,
        )

    assert job.status is DocumentJobStatus.COMPLETED
    assert reader.rendered_regions == ["page_1_chart_1"]
    assert provider.image_payloads == [b"bounded-chart-png"]
    assert len(result.evidence_items) == 1
    assert (
        result.evidence_items[0].validation_status
        is EvidenceValidationStatus.ACCEPTED
    )
    assert result.report is not None
    assert len(result.report.visual_evidence_ids) == 1
    assert result.report.visual_understanding is not None
    assert (
        result.report.visual_understanding.decisions[0].provider_status
        is VisualProviderStatus.SUCCEEDED
    )

