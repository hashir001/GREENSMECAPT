"""Integration test from structured OCR output to evidence."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedTextBlock,
    TextSource,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.domain import SourceDocument

CATALOG_PATH = Path(
    "config/metric_catalog.development.json"
)


def test_structured_ocr_output_becomes_evidence() -> None:
    """Document-image text should feed semantic extraction."""

    content = b"scanned environmental report"

    document = SourceDocument(
        document_id="doc_scan_001",
        sme_id="sme_001",
        file_name="scanned-environmental-report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )

    extracted_document = ExtractedDocument(
        document_id=document.document_id,
        pages=(
            ExtractedPage(
                page_number=3,
                text=(
                    "Total electricity use was 2.5 MWh. "
                    "Renewable energy share reached 72 percent."
                ),
                text_source=TextSource.OCR,
                page_width=1400,
                page_height=1800,
                text_blocks=(
                    ExtractedTextBlock(
                        block_id="paddle_page_3_block_1",
                        text=(
                            "Total electricity use was "
                            "2.5 MWh."
                        ),
                        bounding_box=BoundingBox(
                            x0=100,
                            top=200,
                            x1=900,
                            bottom=270,
                        ),
                        reading_order=0,
                    ),
                    ExtractedTextBlock(
                        block_id="paddle_page_3_block_2",
                        text=(
                            "Renewable energy share reached "
                            "72 percent."
                        ),
                        bounding_box=BoundingBox(
                            x0=100,
                            top=300,
                            x1=1000,
                            bottom=370,
                        ),
                        reading_order=1,
                    ),
                ),
            ),
        ),
    )

    extractor = SemanticMetricExtractor(
        load_metric_catalog(CATALOG_PATH)
    )

    evidence_items = extractor.extract(
        document,
        extracted_document,
    )

    evidence_by_indicator = {
        evidence.indicator_id: evidence
        for evidence in evidence_items
    }

    assert set(evidence_by_indicator) == {
        "electricity_consumption_kwh",
        "renewable_energy_percentage",
    }

    assert (
        evidence_by_indicator[
            "electricity_consumption_kwh"
        ].normalized_value
        == 2500.0
    )

    assert (
        evidence_by_indicator[
            "renewable_energy_percentage"
        ].normalized_value
        == 72.0
    )

    assert all(
        evidence.document_id == document.document_id
        for evidence in evidence_items
    )
    assert all(
        evidence.sme_id == document.sme_id
        for evidence in evidence_items
    )