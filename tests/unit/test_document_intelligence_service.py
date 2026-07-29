"""Tests for the document-intelligence orchestration service."""

from hashlib import sha256

import pytest

from greensmecapt.document_intelligence import (
    DocumentIntegrityError,
    DocumentIntelligenceService,
    ExtractedDocument,
    ExtractedPage,
    ExtractionConsistencyError,
)
from greensmecapt.domain import (
    DocumentType,
    EvidenceItem,
    SourceDocument,
)

DOCUMENT_CONTENT = b"Renewable energy contribution: 72%"


class FakeDocumentReader:
    """Return predictable text without requiring a real OCR model."""

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
                    text=content.decode("utf-8"),
                ),
            ),
        )


class WrongDocumentReader:
    """Return content associated with an incorrect document."""

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        return ExtractedDocument(
            document_id="wrong_document",
            pages=(
                ExtractedPage(
                    page_number=1,
                    text=content.decode("utf-8"),
                ),
            ),
        )


class FakeEvidenceExtractor:
    """Return predictable evidence without requiring a real NLP model."""

    def extract(
        self,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> tuple[EvidenceItem, ...]:
        page = extracted_document.pages[0]

        return (
            EvidenceItem(
                evidence_id="evidence_001",
                sme_id=document.sme_id,
                document_id=document.document_id,
                indicator_id="renewable_energy_percentage",
                criterion_id="renewable_energy",
                raw_value="72%",
                normalized_value=72.0,
                unit="percent",
                source_locator=f"page {page.page_number}",
                source_excerpt=page.text,
                extraction_method="fake_extractor",
                extractor_name="test_extractor",
                extractor_version="1.0",
                confidence=0.94,
            ),
        )


def _make_document() -> SourceDocument:
    return SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name="electricity_bill_2026.pdf",
        mime_type="application/pdf",
        sha256=sha256(DOCUMENT_CONTENT).hexdigest(),
        document_type=DocumentType.UTILITY_BILL,
    )


def test_process_document() -> None:
    """The service should return evidence from valid document content."""

    service = DocumentIntelligenceService(
        reader=FakeDocumentReader(),
        evidence_extractor=FakeEvidenceExtractor(),
    )

    evidence_items = service.process(
        document=_make_document(),
        content=DOCUMENT_CONTENT,
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].normalized_value == 72.0
    assert evidence_items[0].document_id == "doc_001"


def test_reject_tampered_document_content() -> None:
    """Document content must match its registered fingerprint."""

    service = DocumentIntelligenceService(
        reader=FakeDocumentReader(),
        evidence_extractor=FakeEvidenceExtractor(),
    )

    with pytest.raises(DocumentIntegrityError):
        service.process(
            document=_make_document(),
            content=b"Different document content",
        )


def test_reject_reader_output_for_wrong_document() -> None:
    """Reader output must refer to the supplied source document."""

    service = DocumentIntelligenceService(
        reader=WrongDocumentReader(),
        evidence_extractor=FakeEvidenceExtractor(),
    )

    with pytest.raises(ExtractionConsistencyError):
        service.process(
            document=_make_document(),
            content=DOCUMENT_CONTENT,
        )