"""Tests for grounded metric period and scope context."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    TextSource,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    IntelligentSemanticExtractionService,
    SemanticClaimPayload,
    SemanticProviderOutput,
)
from greensmecapt.domain import SourceDocument

CATALOG_PATH = Path(
    "config/metric_catalog.development.json"
)


class FakeProvider:
    """Return one controlled provider claim."""

    provider_name = "fake_provider"
    provider_version = "1.0"
    model_name = "fake_model"

    def __init__(
        self,
        claim: SemanticClaimPayload,
    ) -> None:
        self._claim = claim

    def extract(self, request):
        return SemanticProviderOutput(
            claims=(self._claim,)
        )


def _document() -> SourceDocument:
    content = b"reporting context test"

    return SourceDocument(
        document_id="doc_context_001",
        sme_id="sme_001",
        file_name="environmental-report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )


def _extract(text: str):
    extracted_document = ExtractedDocument(
        document_id="doc_context_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
                text_source=TextSource.OCR,
            ),
        ),
    )

    return SemanticMetricExtractor(
        load_metric_catalog(CATALOG_PATH)
    ).extract(
        _document(),
        extracted_document,
    )


def test_preserve_explicit_prose_period_and_scope() -> None:
    """Period and scope should travel with the metric value."""

    evidence = _extract(
        "For FY 2024, Scope 2 renewable energy share was 72%."
    )

    assert len(evidence) == 1
    assert evidence[0].reporting_period == "FY2024"
    assert evidence[0].scope == "scope 2"


def test_do_not_treat_corporate_history_as_metric_period() -> None:
    """An unrelated nearby year must not become context."""

    evidence = _extract(
        "Founded in 2014, the company reports a renewable "
        "energy share of 72%."
    )

    assert len(evidence) == 1
    assert evidence[0].reporting_period is None


def test_take_reporting_period_from_value_column_header() -> None:
    """A table value should inherit its own column period."""

    table = ExtractedTable(
        table_id="page_1_table_1",
        row_count=2,
        column_count=2,
        cells=(
            ExtractedTableCell(
                row_index=0,
                column_index=0,
                text="Metric",
                is_header=True,
            ),
            ExtractedTableCell(
                row_index=0,
                column_index=1,
                text="2025",
                is_header=True,
            ),
            ExtractedTableCell(
                row_index=1,
                column_index=0,
                text="Waste diversion rate",
            ),
            ExtractedTableCell(
                row_index=1,
                column_index=1,
                text="64%",
            ),
        ),
        bounding_box=BoundingBox(
            x0=50,
            top=100,
            x1=650,
            bottom=400,
        ),
        header_row_indices=(0,),
    )
    extracted_document = ExtractedDocument(
        document_id="doc_context_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=(
                    "Metric | 2025\n"
                    "Waste diversion rate | 64%"
                ),
                text_source=TextSource.OCR,
                page_width=700,
                page_height=900,
                tables=(table,),
            ),
        ),
    )

    evidence = SemanticMetricExtractor(
        load_metric_catalog(CATALOG_PATH)
    ).extract(
        _document(),
        extracted_document,
    )

    assert len(evidence) == 1
    assert evidence[0].reporting_period == "2025"


def test_ground_provider_period_and_scope() -> None:
    """LLM context must occur in the exact supporting quote."""

    text = (
        "For FY 2025, Scope 2 renewable energy "
        "contribution was 72 percent."
    )
    extracted_document = ExtractedDocument(
        document_id="doc_context_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
                text_source=TextSource.OCR,
            ),
        ),
    )
    claim = SemanticClaimPayload(
        segment_id="page_1_text",
        indicator_id="renewable_energy_percentage",
        raw_value="72 percent",
        raw_number=72.0,
        raw_unit="percent",
        source_quote=text,
        reporting_period="FY 2025",
        scope="Scope 2",
    )

    report = IntelligentSemanticExtractionService(
        FakeProvider(claim)
    ).extract(
        document=_document(),
        extracted_document=extracted_document,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert len(report.evidence_items) == 1
    assert (
        report.evidence_items[0].reporting_period
        == "FY2025"
    )
    assert report.evidence_items[0].scope == "scope 2"


def test_reject_provider_period_absent_from_quote() -> None:
    """A provider cannot invent reporting context."""

    text = "Renewable energy contribution was 72 percent."
    extracted_document = ExtractedDocument(
        document_id="doc_context_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
                text_source=TextSource.OCR,
            ),
        ),
    )
    claim = SemanticClaimPayload(
        segment_id="page_1_text",
        indicator_id="renewable_energy_percentage",
        raw_value="72 percent",
        raw_number=72.0,
        raw_unit="percent",
        source_quote=text,
        reporting_period="2025",
    )

    report = IntelligentSemanticExtractionService(
        FakeProvider(claim)
    ).extract(
        document=_document(),
        extracted_document=extracted_document,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert report.evidence_items == ()
    assert "reporting period" in (
        report.rejected_claims[0].reason
    )