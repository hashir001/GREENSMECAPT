"""Read embedded text, layout and tables from PDF documents."""

from collections.abc import Sequence
from io import BytesIO
from typing import Any

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedPageBatch,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    TextBlockKind,
    TextSource,
)
from greensmecapt.document_intelligence.readers.plain_text import (
    DocumentReadError,
    UnsupportedMimeTypeError,
)
from greensmecapt.domain import SourceDocument

_LINE_TOLERANCE = 3.0


class PdfTextDocumentReader:
    """Extract native PDF text, coordinates and table structure."""

    supported_mime_types = frozenset({"application/pdf"})

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Read text-bearing pages from a born-digital PDF."""

        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

        try:
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported by this reader."
                )

            total_pages = len(reader.pages)

            pages, unreadable_pages = self._read_pages(
                content=content,
                reader=reader,
                selected_pages=None,
            )

        except (
            PDFSyntaxError,
            PyPdfError,
            ValueError,
            TypeError,
            OSError,
        ) as error:
            if isinstance(error, DocumentReadError):
                raise

            raise DocumentReadError(
                "PDF text and layout could not be read."
            ) from error

        if not pages:
            raise DocumentReadError(
                "PDF contains no extractable text. "
                "It may be blank or require OCR."
            )

        return ExtractedDocument(
            document_id=document.document_id,
            pages=tuple(pages),
            total_pages=total_pages,
            unreadable_pages=tuple(unreadable_pages),
        )

    def page_count(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> int:
        """Return PDF page count without extracting page content."""

        self._require_supported(document)

        try:
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported by this reader."
                )

            return len(reader.pages)
        except (PyPdfError, ValueError, TypeError, OSError) as error:
            if isinstance(error, DocumentReadError):
                raise

            raise DocumentReadError(
                "PDF page count could not be read."
            ) from error

    def read_page_batch(
        self,
        document: SourceDocument,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> ExtractedPageBatch:
        """Extract native content only from requested PDF pages."""

        self._require_supported(document)

        try:
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported by this reader."
                )

            total_pages = len(reader.pages)
            selected = _validated_page_numbers(
                page_numbers,
                total_pages=total_pages,
            )
            pages, unreadable_pages = self._read_pages(
                content=content,
                reader=reader,
                selected_pages=set(selected),
            )
        except (
            PDFSyntaxError,
            PyPdfError,
            ValueError,
            TypeError,
            OSError,
        ) as error:
            if isinstance(error, DocumentReadError):
                raise

            raise DocumentReadError(
                "PDF text and layout could not be read."
            ) from error

        return ExtractedPageBatch(
            document_id=document.document_id,
            total_pages=total_pages,
            requested_pages=selected,
            pages=tuple(pages),
            unreadable_pages=tuple(unreadable_pages),
        )

    def _require_supported(self, document: SourceDocument) -> None:
        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

    def _read_pages(
        self,
        *,
        content: bytes,
        reader: PdfReader,
        selected_pages: set[int] | None,
    ) -> tuple[list[ExtractedPage], list[int]]:
        """Combine pypdf text with optional pdfplumber layout."""

        pages: list[ExtractedPage] = []
        unreadable_pages: list[int] = []

        with pdfplumber.open(BytesIO(content)) as layout_pdf:
            layout_pages = layout_pdf.pages

            for page_index, pdf_page in enumerate(
                reader.pages
            ):
                page_number = page_index + 1

                if (
                    selected_pages is not None
                    and page_number not in selected_pages
                ):
                    continue

                layout_page = (
                    layout_pages[page_index]
                    if page_index < len(layout_pages)
                    else None
                )

                pypdf_text = (
                    pdf_page.extract_text() or ""
                ).strip()

                layout_text = ""

                if layout_page is not None:
                    layout_text = (
                        layout_page.extract_text() or ""
                    ).strip()

                text = pypdf_text or layout_text

                if not text:
                    unreadable_pages.append(page_number)
                    continue

                if layout_page is None:
                    page_width = float(
                        pdf_page.mediabox.width
                    )
                    page_height = float(
                        pdf_page.mediabox.height
                    )
                    tables: tuple[ExtractedTable, ...] = ()
                    text_blocks: tuple[
                        ExtractedTextBlock, ...
                    ] = ()
                else:
                    page_width = float(layout_page.width)
                    page_height = float(layout_page.height)

                    tables = _extract_tables(
                        page=layout_page,
                        page_number=page_number,
                    )

                    table_boxes = tuple(
                        table.bounding_box
                        for table in tables
                    )

                    text_blocks = _extract_text_blocks(
                        page=layout_page,
                        page_number=page_number,
                        table_boxes=table_boxes,
                    )

                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=text,
                        text_source=TextSource.PDF_EMBEDDED,
                        page_width=page_width,
                        page_height=page_height,
                        text_blocks=text_blocks,
                        tables=tables,
                    )
                )

        return pages, unreadable_pages


def _validated_page_numbers(
    page_numbers: tuple[int, ...],
    *,
    total_pages: int,
) -> tuple[int, ...]:
    """Normalize a non-empty, in-range page request."""

    selected = tuple(sorted(set(page_numbers)))

    if not selected:
        raise DocumentReadError("At least one PDF page must be requested.")

    if selected[0] < 1 or selected[-1] > total_pages:
        raise DocumentReadError("Requested PDF page is outside the document.")

    return selected


def _extract_tables(
    *,
    page: Any,
    page_number: int,
) -> tuple[ExtractedTable, ...]:
    """Recover rectangular tables detected on one native PDF page."""

    extracted_tables: list[ExtractedTable] = []

    for table_number, found_table in enumerate(
        page.find_tables(),
        start=1,
    ):
        extracted_rows = found_table.extract()

        if not extracted_rows:
            continue

        cleaned_rows = [
            tuple(_clean_cell_text(cell) for cell in row)
            for row in extracted_rows
            if row is not None
        ]

        if not cleaned_rows:
            continue

        column_count = max(
            len(row) for row in cleaned_rows
        )

        if column_count == 0:
            continue

        normalized_rows = tuple(
            row + ("",) * (column_count - len(row))
            for row in cleaned_rows
        )

        if not any(
            cell
            for row in normalized_rows
            for cell in row
        ):
            continue

        cells = tuple(
            ExtractedTableCell(
                row_index=row_index,
                column_index=column_index,
                text=cell_text,
                is_header=row_index == 0,
            )
            for row_index, row in enumerate(normalized_rows)
            for column_index, cell_text in enumerate(row)
        )

        extracted_tables.append(
            ExtractedTable(
                table_id=(
                    f"page_{page_number}_table_{table_number}"
                ),
                row_count=len(normalized_rows),
                column_count=column_count,
                cells=cells,
                bounding_box=_make_bounding_box(
                    found_table.bbox
                ),
                header_row_indices=(0,),
            )
        )

    return tuple(extracted_tables)


def _extract_text_blocks(
    *,
    page: Any,
    page_number: int,
    table_boxes: Sequence[BoundingBox],
) -> tuple[ExtractedTextBlock, ...]:
    """Group positioned PDF words into ordered non-table lines."""

    words = page.extract_words(
        use_text_flow=True,
        keep_blank_chars=False,
    )

    non_table_words = [
        word
        for word in words
        if not _word_inside_any_table(
            word=word,
            table_boxes=table_boxes,
        )
    ]

    ordered_words = sorted(
        non_table_words,
        key=lambda word: (
            float(word["top"]),
            float(word["x0"]),
        ),
    )

    lines: list[list[dict[str, Any]]] = []

    for word in ordered_words:
        if not lines:
            lines.append([word])
            continue

        current_line = lines[-1]
        line_top = sum(
            float(item["top"]) for item in current_line
        ) / len(current_line)

        if (
            abs(float(word["top"]) - line_top)
            <= _LINE_TOLERANCE
        ):
            current_line.append(word)
        else:
            lines.append([word])

    blocks: list[ExtractedTextBlock] = []

    for line in lines:
        sorted_line = sorted(
            line,
            key=lambda word: float(word["x0"]),
        )

        text = " ".join(
            str(word["text"]).strip()
            for word in sorted_line
            if str(word["text"]).strip()
        ).strip()

        if not text:
            continue

        bounding_box = BoundingBox(
            x0=min(
                float(word["x0"])
                for word in sorted_line
            ),
            top=min(
                float(word["top"])
                for word in sorted_line
            ),
            x1=max(
                float(word["x1"])
                for word in sorted_line
            ),
            bottom=max(
                float(word["bottom"])
                for word in sorted_line
            ),
        )

        reading_order = len(blocks)

        blocks.append(
            ExtractedTextBlock(
                block_id=(
                    f"page_{page_number}_block_"
                    f"{reading_order + 1}"
                ),
                text=text,
                kind=TextBlockKind.PARAGRAPH,
                bounding_box=bounding_box,
                reading_order=reading_order,
                confidence=None,
            )
        )

    return tuple(blocks)


def _word_inside_any_table(
    *,
    word: dict[str, Any],
    table_boxes: Sequence[BoundingBox],
) -> bool:
    """Report whether a word's centre lies inside a table."""

    centre_x = (
        float(word["x0"]) + float(word["x1"])
    ) / 2
    centre_y = (
        float(word["top"]) + float(word["bottom"])
    ) / 2

    return any(
        box.x0 <= centre_x <= box.x1
        and box.top <= centre_y <= box.bottom
        for box in table_boxes
    )


def _make_bounding_box(
    values: Sequence[float],
) -> BoundingBox:
    """Convert a PDF-coordinate tuple into a validated box."""

    x0, top, x1, bottom = (
        float(value) for value in values
    )

    return BoundingBox(
        x0=x0,
        top=top,
        x1=x1,
        bottom=bottom,
    )


def _clean_cell_text(value: object) -> str:
    """Normalize whitespace without inventing cell content."""

    if value is None:
        return ""

    return " ".join(str(value).split())
