"""Tests for renewable-energy percentage extraction."""

from greensmecapt.document_intelligence import (
    ExtractedDocument,
    ExtractedPage,
    RenewableEnergyPercentageExtractor,
)
from greensmecapt.domain import SourceDocument


def _make_document() -> SourceDocument:
    return SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name="sustainability_statement.txt",
        mime_type="text/plain",
        sha256="a" * 64,
    )


def _make_extracted_document(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
            ),
        ),
    )


def test_extract_renewable_energy_percentage() -> None:
    """A percentage should become traceable structured evidence."""

    extractor = RenewableEnergyPercentageExtractor()

    evidence_items = extractor.extract(
        document=_make_document(),
        extracted_document=_make_extracted_document(
            "Renewable energy contribution: 72%"
        ),
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].raw_value == "72%"
    assert evidence_items[0].normalized_value == 72.0
    assert evidence_items[0].unit == "percent"


def test_extract_decimal_percentage() -> None:
    """Decimal percentages should be preserved."""

    extractor = RenewableEnergyPercentageExtractor()

    evidence_items = extractor.extract(
        document=_make_document(),
        extracted_document=_make_extracted_document(
            "Renewable energy use is 63.5 percent."
        ),
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].normalized_value == 63.5


def test_return_no_evidence_when_phrase_is_absent() -> None:
    """Unrelated text should not produce fabricated evidence."""

    extractor = RenewableEnergyPercentageExtractor()

    evidence_items = extractor.extract(
        document=_make_document(),
        extracted_document=_make_extracted_document(
            "The company opened a new manufacturing facility."
        ),
    )

    assert evidence_items == ()