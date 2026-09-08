"""Exercise real PDF parsing, routing and evidence extraction."""

from hashlib import sha256
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from greensmecapt.document_intelligence import (
    DocumentIntelligenceService,
    DocumentReadError,
    PlainTextDocumentReader,
    RenewableEnergyPercentageExtractor,
    UnsupportedMimeTypeError,
)
from greensmecapt.document_intelligence.readers import (
    PdfTextDocumentReader,
    RoutingDocumentReader,
)
from greensmecapt.domain import SourceDocument


def _make_pdf(
    *,
    include_text: bool = True,
    encrypted: bool = False,
) -> bytes:
    """Build a real PDF with a blank first page and optional page-two text."""

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    page = writer.add_blank_page(width=612, height=792)

    if include_text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )

        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font}
                )
            }
        )

        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 50 700 Td "
            b"(Renewable energy contribution: 72%) Tj ET"
        )
        page[NameObject("/Contents")] = stream

    if encrypted:
        writer.encrypt("test-password")

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _make_document(
    content: bytes,
    mime_type: str = "application/pdf",
) -> SourceDocument:
    return SourceDocument(
        document_id="doc_pdf_001",
        sme_id="sme_001",
        file_name="statement.pdf",
        mime_type=mime_type,
        sha256=sha256(content).hexdigest(),
    )


def _make_service() -> DocumentIntelligenceService:
    return DocumentIntelligenceService(
        reader=RoutingDocumentReader(
            {
                "text/plain": PlainTextDocumentReader(),
                "application/pdf": PdfTextDocumentReader(),
            }
        ),
        evidence_extractor=RenewableEnergyPercentageExtractor(),
    )


def test_pdf_becomes_traceable_evidence() -> None:
    """Real PDF content should flow through the existing service."""

    content = _make_pdf()
    evidence = _make_service().process(
        document=_make_document(content),
        content=content,
    )

    assert len(evidence) == 1
    assert evidence[0].normalized_value == 72.0
    assert evidence[0].document_id == "doc_pdf_001"
    assert evidence[0].source_locator.startswith("page 2,")


def test_router_still_supports_plain_text() -> None:
    """Adding PDF routing must preserve the existing text workflow."""

    content = b"Renewable energy share: 45%"
    evidence = _make_service().process(
        document=_make_document(content, mime_type="text/plain"),
        content=content,
    )

    assert len(evidence) == 1
    assert evidence[0].normalized_value == 45.0


def test_reject_pdf_without_text() -> None:
    """A textless PDF must not look like a successful extraction."""

    content = _make_pdf(include_text=False)

    with pytest.raises(DocumentReadError, match="no extractable text"):
        _make_service().process(
            document=_make_document(content),
            content=content,
        )


def test_reject_encrypted_pdf() -> None:
    """Encrypted input should produce an explicit controlled error."""

    content = _make_pdf(encrypted=True)

    with pytest.raises(DocumentReadError, match="Encrypted"):
        _make_service().process(
            document=_make_document(content),
            content=content,
        )


def test_reject_malformed_pdf() -> None:
    """Invalid PDF bytes should produce a controlled reading error."""

    content = b"This is not a PDF."

    with pytest.raises(DocumentReadError):
        _make_service().process(
            document=_make_document(content),
            content=content,
        )


def test_reject_unconfigured_document_type() -> None:
    """Unsupported types must not be passed to an arbitrary reader."""

    content = b"image placeholder"

    with pytest.raises(UnsupportedMimeTypeError):
        _make_service().process(
            document=_make_document(content, mime_type="image/png"),
            content=content,
        )