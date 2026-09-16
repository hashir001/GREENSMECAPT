"""Tests for configurable semantic metric extraction."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    TextSource,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.domain import (
    EvidenceValidationStatus,
    SourceDocument,
)

CATALOG_PATH = Path(
    "config/metric_catalog.development.json"
)


def _document() -> SourceDocument:
    content = b"semantic test"

    return SourceDocument(
        document_id="doc_semantic_001",
        sme_id="sme_001",
        file_name="environmental-report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )


def _extract(text: str):
    catalog = load_metric_catalog(CATALOG_PATH)
    extractor = SemanticMetricExtractor(catalog)

    extracted_document = ExtractedDocument(
        document_id="doc_semantic_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
                text_source=TextSource.OCR,
            ),
        ),
    )

    return extractor.extract(
        _document(),
        extracted_document,
    )


def test_treat_percent_word_and_symbol_equally() -> None:
    """Equivalent percentage spellings should normalize equally."""

    word_evidence = _extract(
        "Renewable energy share: 72 percent."
    )
    symbol_evidence = _extract(
        "Renewable energy share: 72%."
    )

    assert len(word_evidence) == 1
    assert len(symbol_evidence) == 1
    assert word_evidence[0].normalized_value == 72.0
    assert symbol_evidence[0].normalized_value == 72.0
    assert word_evidence[0].unit == "percent"


def test_understand_value_before_metric_phrase() -> None:
    """Value-first prose should map to the same indicator."""

    evidence = _extract(
        "72 percent of electricity came from "
        "renewable sources."
    )

    assert len(evidence) == 1
    assert (
        evidence[0].indicator_id
        == "renewable_energy_percentage"
    )
    assert evidence[0].normalized_value == 72.0


def test_convert_megawatt_hours_to_kilowatt_hours() -> None:
    """Compatible energy units should become comparable."""

    evidence = _extract(
        "Total electricity use was 2.5 MWh."
    )

    assert len(evidence) == 1
    assert (
        evidence[0].indicator_id
        == "electricity_consumption_kwh"
    )
    assert evidence[0].normalized_value == 2500.0
    assert evidence[0].unit == "kwh"


def test_leave_semantic_evidence_unvalidated() -> None:
    """Automated extraction must not approve its own output."""

    evidence = _extract(
        "Water consumption was 12 cubic meters."
    )

    assert len(evidence) == 1
    assert (
        evidence[0].validation_status
        is EvidenceValidationStatus.UNVALIDATED
    )


def test_extract_metric_from_structured_table_row() -> None:
    """A table label and value should become traceable evidence."""

    catalog = load_metric_catalog(CATALOG_PATH)
    extractor = SemanticMetricExtractor(catalog)

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
        document_id="doc_semantic_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text="Metric | 2025\nWaste diversion rate | 64%",
                text_source=TextSource.OCR,
                page_width=700,
                page_height=900,
                tables=(table,),
            ),
        ),
    )

    evidence = extractor.extract(
        _document(),
        extracted_document,
    )

    assert len(evidence) == 1
    assert (
        evidence[0].indicator_id
        == "waste_diversion_percentage"
    )
    assert evidence[0].normalized_value == 64.0
    assert (
        evidence[0].extraction_method
        == "semantic_rule_table_row"
    )
    assert "table page_1_table_1" in (
        evidence[0].source_locator
    )


def test_preserve_block_provenance() -> None:
    """Evidence should identify its originating layout block."""

    catalog = load_metric_catalog(CATALOG_PATH)
    extractor = SemanticMetricExtractor(catalog)

    block = ExtractedTextBlock(
        block_id="paddle_page_2_block_4",
        text="Water withdrawal: 18 m3",
        bounding_box=BoundingBox(
            x0=80,
            top=200,
            x1=500,
            bottom=250,
        ),
        reading_order=0,
    )

    extracted_document = ExtractedDocument(
        document_id="doc_semantic_001",
        pages=(
            ExtractedPage(
                page_number=2,
                text=block.text,
                text_source=TextSource.OCR,
                page_width=700,
                page_height=900,
                text_blocks=(block,),
            ),
        ),
    )

    evidence = extractor.extract(
        _document(),
        extracted_document,
    )

    assert len(evidence) == 1
    assert "paddle_page_2_block_4" in (
        evidence[0].source_locator
    )


def test_ignore_out_of_range_percentage() -> None:
    """Impossible percentages must not become evidence."""

    evidence = _extract(
        "Renewable energy share: 172 percent."
    )

    assert evidence == ()


def test_ignore_unrelated_numbers() -> None:
    """Numbers without configured semantic context are ignored."""

    evidence = _extract(
        "The company was established in 2014 "
        "and employs 72 people."
    )

    assert evidence == ()