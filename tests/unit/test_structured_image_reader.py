"""Tests for structured OCR of standalone image documents."""

from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from greensmecapt.document_intelligence import (
    DocumentReadError,
    StructuredImageDocumentReader,
    UnsupportedMimeTypeError,
)
from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    TextSource,
)
from greensmecapt.document_intelligence.structure import (
    StructuredParsingError,
)
from greensmecapt.domain import DocumentType, SourceDocument


class TableParser:
    """Return one predictable structured page."""

    def parse(
        self,
        image: Image.Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        return ExtractedPage(
            page_number=page_number,
            text="Metric | Value\nRenewable energy | 72%",
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
            tables=(
                ExtractedTable(
                    table_id="table_1",
                    row_count=1,
                    column_count=2,
                    cells=(
                        ExtractedTableCell(
                            row_index=0,
                            column_index=0,
                            text="Renewable energy",
                        ),
                        ExtractedTableCell(
                            row_index=0,
                            column_index=1,
                            text="72%",
                        ),
                    ),
                    bounding_box=BoundingBox(
                        x0=1,
                        top=1,
                        x1=100,
                        bottom=50,
                    ),
                ),
            ),
        )


class FailingParser:
    """Simulate structured OCR failure."""

    def parse(
        self,
        image: Image.Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        raise StructuredParsingError("layout unavailable")


class FakeOcr:
    """Return controlled fallback OCR text."""

    def __init__(self, text: str) -> None:
        self.text = text

    def recognize(self, image: Image.Image) -> str:
        return self.text


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (200, 100), color="white").save(
        output,
        format="PNG",
    )
    return output.getvalue()


def _document(
    content: bytes,
    *,
    mime_type: str = "image/png",
    document_type: DocumentType = DocumentType.UNKNOWN,
) -> SourceDocument:
    return SourceDocument(
        document_id="image_001",
        sme_id="sme_001",
        file_name="evidence.png",
        mime_type=mime_type,
        sha256=sha256(content).hexdigest(),
        document_type=document_type,
    )


def test_preserve_structured_image_table() -> None:
    """Image reading should retain tables instead of flattening them."""

    content = _image_bytes()
    extracted = StructuredImageDocumentReader(TableParser()).read(_document(content), content)

    assert extracted.total_pages == 1
    assert extracted.pages[0].tables[0].value_at(0, 1) == "72%"


def test_use_plain_ocr_after_structured_failure() -> None:
    """Simple OCR should remain an operational fallback."""

    content = _image_bytes()
    extracted = StructuredImageDocumentReader(
        FailingParser(),
        fallback_ocr_engine=FakeOcr("Recovered fallback text"),
    ).read(_document(content), content)

    assert extracted.pages[0].text == "Recovered fallback text"
    assert extracted.pages[0].tables == ()


def test_report_unreadable_image_after_both_paths_fail() -> None:
    """Failed structured and fallback OCR must not look successful."""

    content = _image_bytes()
    reader = StructuredImageDocumentReader(
        FailingParser(),
        fallback_ocr_engine=FakeOcr(""),
    )

    with pytest.raises(DocumentReadError, match="could not read"):
        reader.read(_document(content), content)


def test_reject_unsupported_image_mime_type() -> None:
    """The reader should reject documents assigned to another route."""

    content = _image_bytes()

    with pytest.raises(UnsupportedMimeTypeError):
        StructuredImageDocumentReader(TableParser()).read(
            _document(content, mime_type="application/pdf"),
            content,
        )


class LabeledParser:
    """Expose which cloud route handled an image."""

    def __init__(self, label: str) -> None:
        self.label = label

    def parse(self, image: Image.Image, *, page_number: int) -> ExtractedPage:
        return ExtractedPage(
            page_number=page_number,
            text=self.label,
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
        )


def test_route_financial_image_to_form_parser() -> None:
    content = _image_bytes()
    reader = StructuredImageDocumentReader(
        LabeledParser("document ocr"),
        form_parser=LabeledParser("form parser"),
    )

    extracted = reader.read(
        _document(
            content,
            document_type=DocumentType.FINANCIAL_STATEMENT,
        ),
        content,
    )

    assert extracted.pages[0].text == "form parser"


def test_route_general_image_to_document_ocr() -> None:
    content = _image_bytes()
    reader = StructuredImageDocumentReader(
        LabeledParser("document ocr"),
        form_parser=LabeledParser("form parser"),
    )

    extracted = reader.read(_document(content), content)

    assert extracted.pages[0].text == "document ocr"
