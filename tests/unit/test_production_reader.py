"""Tests for the assembled production document reader."""

from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from greensmecapt.document_intelligence import (
    ProductionReaderConfiguration,
    UnsupportedMimeTypeError,
    build_production_document_reader,
)
from greensmecapt.document_intelligence.models import (
    ExtractedPage,
    TextSource,
)
from greensmecapt.domain import SourceDocument


class FakeStructuredParser:
    """Return structured content without loading Paddle models."""

    def __init__(self) -> None:
        self.calls = 0

    def parse(
        self,
        image: Image.Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        self.calls += 1
        return ExtractedPage(
            page_number=page_number,
            text="Structured OCR content",
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
        )


def _document(
    content: bytes,
    *,
    mime_type: str,
    file_name: str,
) -> SourceDocument:
    return SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name=file_name,
        mime_type=mime_type,
        sha256=sha256(content).hexdigest(),
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 50), color="white").save(
        output,
        format="PNG",
    )
    return output.getvalue()


def test_route_text_without_initializing_real_models() -> None:
    """Injected components should permit lightweight production tests."""

    parser = FakeStructuredParser()
    reader = build_production_document_reader(
        ProductionReaderConfiguration(
            enable_tesseract_fallback=False,
        ),
        structured_parser=parser,
    )
    content = b"Renewable energy contribution: 72%"

    extracted = reader.read(
        _document(
            content,
            mime_type="text/plain",
            file_name="statement.txt",
        ),
        content,
    )

    assert extracted.pages[0].text_source is TextSource.PLAIN_TEXT
    assert parser.calls == 0


def test_route_image_through_structured_parser() -> None:
    """Production image routes should preserve structured parsing."""

    parser = FakeStructuredParser()
    reader = build_production_document_reader(
        ProductionReaderConfiguration(
            enable_tesseract_fallback=False,
        ),
        structured_parser=parser,
    )
    content = _png()

    extracted = reader.read(
        _document(
            content,
            mime_type="image/png",
            file_name="scan.png",
        ),
        content,
    )

    assert extracted.pages[0].text == "Structured OCR content"
    assert parser.calls == 1


def test_reject_unconfigured_mime_type() -> None:
    """Unsupported uploads should fail before being misread."""

    reader = build_production_document_reader(
        ProductionReaderConfiguration(
            enable_tesseract_fallback=False,
        ),
        structured_parser=FakeStructuredParser(),
    )
    content = b"spreadsheet bytes"

    with pytest.raises(UnsupportedMimeTypeError):
        reader.read(
            _document(
                content,
                mime_type="application/vnd.ms-excel",
                file_name="data.xls",
            ),
            content,
        )