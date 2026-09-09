"""Integration tests for image and hybrid-PDF OCR processing."""

from hashlib import sha256
from io import BytesIO

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from greensmecapt.document_intelligence import (
    DocumentIntelligenceService,
    DocumentReadError,
    HybridPdfDocumentReader,
    ImageDocumentReader,
    RenewableEnergyPercentageExtractor,
    TesseractOcrEngine,
    TextSource,
    UnsupportedMimeTypeError,
)
from greensmecapt.domain import SourceDocument


class FakeOcrEngine:
    """Return controlled OCR text while exercising reader behaviour."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def recognize(self, image: Image.Image) -> str:
        self.calls += 1
        return self._text


def _source_document(
    content: bytes,
    *,
    mime_type: str,
    file_name: str,
) -> SourceDocument:
    return SourceDocument(
        document_id="doc_ocr_001",
        sme_id="sme_001",
        file_name=file_name,
        mime_type=mime_type,
        sha256=sha256(content).hexdigest(),
    )


def _make_text_image(text: str) -> bytes:
    image = Image.new(
        "RGB",
        (1200, 160),
        color="white",
    )
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        38,
    )

    ImageDraw.Draw(image).text(
        (30, 50),
        text,
        fill="black",
        font=font,
    )

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _make_pdf(
    *page_texts: str | None,
) -> bytes:
    pdf = pymupdf.open()

    for text in page_texts:
        page = pdf.new_page()

        if text:
            page.insert_text(
                (72, 100),
                text,
                fontsize=16,
            )

    content = pdf.tobytes()
    pdf.close()
    return content


def test_real_image_ocr_becomes_evidence() -> None:
    """A real rendered image should pass through Tesseract and extraction."""

    content = _make_text_image(
        "Renewable energy contribution: 72%"
    )
    document = _source_document(
        content,
        mime_type="image/png",
        file_name="scanned_statement.png",
    )

    service = DocumentIntelligenceService(
        reader=ImageDocumentReader(
            TesseractOcrEngine(
                page_segmentation_mode=7,
            )
        ),
        evidence_extractor=RenewableEnergyPercentageExtractor(),
    )

    evidence = service.process(document, content)

    assert len(evidence) == 1
    assert evidence[0].normalized_value == 72.0
    assert evidence[0].source_locator.startswith("page 1,")


def test_hybrid_pdf_prefers_embedded_text() -> None:
    """A text-bearing page should not be sent through OCR."""

    content = _make_pdf(
        "Renewable energy contribution: 72%"
    )
    ocr_engine = FakeOcrEngine(
        "Renewable energy contribution: 10%"
    )

    extracted = HybridPdfDocumentReader(
        ocr_engine
    ).read(
        _source_document(
            content,
            mime_type="application/pdf",
            file_name="digital_statement.pdf",
        ),
        content,
    )

    assert ocr_engine.calls == 0
    assert extracted.pages[0].text_source is (
        TextSource.PDF_EMBEDDED
    )
    assert "72%" in extracted.pages[0].text


def test_hybrid_pdf_uses_ocr_fallback() -> None:
    """A PDF page without embedded text should be rendered and OCRed."""

    content = _make_pdf(None)
    ocr_engine = FakeOcrEngine(
        "Renewable energy contribution: 72%"
    )
    document = _source_document(
        content,
        mime_type="application/pdf",
        file_name="scanned_statement.pdf",
    )

    service = DocumentIntelligenceService(
        reader=HybridPdfDocumentReader(ocr_engine),
        evidence_extractor=RenewableEnergyPercentageExtractor(),
    )

    evidence = service.process(document, content)

    assert ocr_engine.calls == 1
    assert len(evidence) == 1
    assert evidence[0].normalized_value == 72.0


def test_hybrid_pdf_reports_unreadable_pages() -> None:
    """Partial extraction should identify pages still unreadable."""

    content = _make_pdf(
        None,
        "Renewable energy contribution: 72%",
    )
    ocr_engine = FakeOcrEngine("")

    extracted = HybridPdfDocumentReader(
        ocr_engine
    ).read(
        _source_document(
            content,
            mime_type="application/pdf",
            file_name="mixed_statement.pdf",
        ),
        content,
    )

    assert extracted.total_pages == 2
    assert extracted.unreadable_pages == (1,)
    assert extracted.pages[0].page_number == 2
    assert extracted.pages[0].text_source is (
        TextSource.PDF_EMBEDDED
    )


def test_reject_image_when_ocr_recovers_no_text() -> None:
    """An unreadable image must not look successfully processed."""

    content = _make_text_image("")
    reader = ImageDocumentReader(FakeOcrEngine(""))

    with pytest.raises(DocumentReadError, match="did not recover"):
        reader.read(
            _source_document(
                content,
                mime_type="image/png",
                file_name="blank.png",
            ),
            content,
        )


def test_image_reader_rejects_unsupported_type() -> None:
    """Image OCR must only accept configured image MIME types."""

    content = b"not-an-image"
    reader = ImageDocumentReader(FakeOcrEngine("text"))

    with pytest.raises(UnsupportedMimeTypeError):
        reader.read(
            _source_document(
                content,
                mime_type="application/pdf",
                file_name="document.pdf",
            ),
            content,
        )