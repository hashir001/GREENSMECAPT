"""Integration tests for adaptive PDF processing."""

from hashlib import sha256
from io import BytesIO

import pymupdf
from PIL import Image as PILImage
from PIL.Image import Image

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedVisualRegion,
    TextSource,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.readers.adaptive_pdf import (
    AdaptivePdfDocumentReader,
)
from greensmecapt.document_intelligence.structure import (
    PageProcessingMode,
    StructuredParsingError,
)
from greensmecapt.domain import (
    DocumentType,
    SourceDocument,
)


class FakeStructuredParser:
    """Return structured OCR without loading real models."""

    def __init__(self) -> None:
        self.page_numbers: list[int] = []

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        self.page_numbers.append(page_number)

        return ExtractedPage(
            page_number=page_number,
            text=(
                f"Structured OCR content for page "
                f"{page_number}"
            ),
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
        )


class TableStructuredParser:
    """Return a table for hybrid visual processing."""

    def __init__(self) -> None:
        self.page_numbers: list[int] = []

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        self.page_numbers.append(page_number)

        return ExtractedPage(
            page_number=page_number,
            text=(
                "Environmental metrics 2024\n"
                "Renewable electricity | 68 | %"
            ),
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
            tables=(
                ExtractedTable(
                    table_id="visual_table",
                    row_count=2,
                    column_count=3,
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
                            text="2024",
                            is_header=True,
                        ),
                        ExtractedTableCell(
                            row_index=0,
                            column_index=2,
                            text="Unit",
                            is_header=True,
                        ),
                        ExtractedTableCell(
                            row_index=1,
                            column_index=0,
                            text="Renewable electricity",
                        ),
                        ExtractedTableCell(
                            row_index=1,
                            column_index=1,
                            text="68",
                        ),
                        ExtractedTableCell(
                            row_index=1,
                            column_index=2,
                            text="%",
                        ),
                    ),
                    bounding_box=BoundingBox(
                        x0=10,
                        top=10,
                        x1=500,
                        bottom=300,
                    ),
                    header_row_indices=(0,),
                ),
            ),
        )


class VisualStructuredParser:
    """Return one detected chart from structured parsing."""

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        return ExtractedPage(
            page_number=page_number,
            text="Renewable energy share chart.",
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
            visual_regions=(
                ExtractedVisualRegion(
                    region_id=f"page_{page_number}_chart_1",
                    kind=VisualRegionKind.CHART,
                    bounding_box=BoundingBox(
                        x0=100,
                        top=100,
                        x1=300,
                        bottom=250,
                    ),
                    caption="Renewable energy share",
                ),
            ),
        )


class FailingStructuredParser:
    """Simulate a controlled structured-parser failure."""

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        raise StructuredParsingError(
            "The page layout could not be recovered."
        )


class FakeFallbackOcr:
    """Return simple text after structured OCR fails."""

    def recognize(self, image: Image) -> str:
        return "Fallback OCR recovered this page."


def _make_pdf(
    page_texts: tuple[str | None, ...],
) -> bytes:
    pdf = pymupdf.open()

    for page_text in page_texts:
        page = pdf.new_page(
            width=612,
            height=792,
        )

        if page_text:
            page.insert_text(
                (72, 100),
                page_text,
                fontsize=12,
            )

    content = pdf.tobytes()
    pdf.close()

    return content


def _make_document(
    content: bytes,
    *,
    document_type: DocumentType = (
        DocumentType.OTHER
    ),
) -> SourceDocument:
    return SourceDocument(
        document_id="doc_adaptive_001",
        sme_id="sme_001",
        file_name="adaptive_report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
        document_type=document_type,
    )


def test_keep_clean_digital_page_native() -> None:
    """A clean digital page should avoid structured OCR."""

    content = _make_pdf(
        (
            "This digital environmental report contains "
            "sufficient embedded text for native extraction.",
        )
    )
    parser = FakeStructuredParser()

    result = AdaptivePdfDocumentReader(
        structured_parser=parser
    ).read_with_diagnostics(
        document=_make_document(content),
        content=content,
    )

    assert parser.page_numbers == []
    assert (
        result.document.pages[0].text_source
        is TextSource.PDF_EMBEDDED
    )
    assert (
        result.processing_records[0].mode
        is PageProcessingMode.NATIVE
    )


def test_route_scanned_page_to_structured_ocr() -> None:
    """A page without embedded text should use structured OCR."""

    content = _make_pdf((None,))
    parser = FakeStructuredParser()

    result = AdaptivePdfDocumentReader(
        structured_parser=parser
    ).read_with_diagnostics(
        document=_make_document(content),
        content=content,
    )

    assert parser.page_numbers == [1]
    assert (
        result.document.pages[0].text_source
        is TextSource.OCR
    )
    assert (
        result.processing_records[0].mode
        is PageProcessingMode.STRUCTURED_OCR
    )


def test_process_mixed_pdf_page_by_page() -> None:
    """Digital and scanned pages should use different routes."""

    content = _make_pdf(
        (
            "This first page contains enough embedded "
            "environmental reporting text.",
            None,
        )
    )
    parser = FakeStructuredParser()

    result = AdaptivePdfDocumentReader(
        structured_parser=parser
    ).read_with_diagnostics(
        document=_make_document(content),
        content=content,
    )

    assert parser.page_numbers == [2]
    assert len(result.document.pages) == 2

    assert (
        result.document.pages[0].text_source
        is TextSource.PDF_EMBEDDED
    )
    assert (
        result.document.pages[1].text_source
        is TextSource.OCR
    )


def test_read_only_requested_pdf_pages() -> None:
    """A page batch must not render or OCR pages outside its boundary."""

    content = _make_pdf(
        (
            "This first page has sufficient embedded report text.",
            None,
            "This third page also has sufficient embedded report text.",
        )
    )
    parser = FakeStructuredParser()
    batch = AdaptivePdfDocumentReader(
        structured_parser=parser
    ).read_page_batch(
        document=_make_document(content),
        content=content,
        page_numbers=(2,),
    )

    assert batch.total_pages == 3
    assert batch.requested_pages == (2,)
    assert tuple(page.page_number for page in batch.pages) == (2,)
    assert parser.page_numbers == [2]


def test_hybrid_processing_adds_missing_table() -> None:
    """A table-oriented page may combine native and visual data."""

    content = _make_pdf(
        (
            "Environmental metrics for 2024 include "
            "energy, emissions, waste and water totals.",
        )
    )
    parser = TableStructuredParser()

    result = AdaptivePdfDocumentReader(
        structured_parser=parser
    ).read_with_diagnostics(
        document=_make_document(
            content,
            document_type=(
                DocumentType.SUSTAINABILITY_REPORT
            ),
        ),
        content=content,
    )

    page = result.document.pages[0]

    assert parser.page_numbers == [1]
    assert page.text_source is TextSource.HYBRID
    assert len(page.tables) == 1
    assert page.tables[0].value_at(1, 1) == "68"

    assert (
        result.processing_records[0].mode
        is PageProcessingMode.HYBRID
    )


def test_fallback_ocr_after_structured_failure() -> None:
    """Simple OCR should remain available as a fallback."""

    content = _make_pdf((None,))

    result = AdaptivePdfDocumentReader(
        structured_parser=FailingStructuredParser(),
        fallback_ocr_engine=FakeFallbackOcr(),
    ).read_with_diagnostics(
        document=_make_document(content),
        content=content,
    )

    assert (
        result.document.pages[0].text
        == "Fallback OCR recovered this page."
    )
    assert (
        result.processing_records[0]
        .used_fallback_ocr
        is True
    )


def test_preserve_and_render_detected_visual_region() -> None:
    """A structured chart should survive reading and yield an exact crop."""

    content = _make_pdf((None,))
    document = _make_document(content)
    reader = AdaptivePdfDocumentReader(
        structured_parser=VisualStructuredParser(),
    )
    extracted = reader.read(document, content)
    page = extracted.pages[0]

    assert len(page.visual_regions) == 1
    png = reader.render_visual_region(
        document,
        content,
        page,
        page.visual_regions[0],
    )

    with PILImage.open(BytesIO(png)) as image:
        assert image.format == "PNG"
        assert 195 <= image.width <= 205
        assert 145 <= image.height <= 155


def test_hybrid_merge_preserves_structured_visual_regions() -> None:
    """Native text must not erase charts found by structured parsing."""

    content = _make_pdf(
        (
            "Environmental metrics for 2024 include energy, "
            "emissions, waste and water totals.",
        )
    )
    result = AdaptivePdfDocumentReader(
        structured_parser=VisualStructuredParser(),
    ).read_with_diagnostics(
        document=_make_document(
            content,
            document_type=DocumentType.SUSTAINABILITY_REPORT,
        ),
        content=content,
    )

    assert result.document.pages[0].text_source is TextSource.HYBRID
    assert (
        result.document.pages[0].visual_regions[0].region_id
        == "page_1_chart_1"
    )
