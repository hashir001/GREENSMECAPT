"""Adaptive native, structured OCR and hybrid PDF reading."""

import re
from collections.abc import Sequence
from io import BytesIO
from typing import Protocol

import pymupdf
from PIL import Image
from PIL.Image import Image as PILImage
from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    ExtractedTextBlock,
    TextSource,
)
from greensmecapt.document_intelligence.readers.pdf import (
    PdfTextDocumentReader,
)
from greensmecapt.document_intelligence.readers.plain_text import (
    DocumentReadError,
    UnsupportedMimeTypeError,
)
from greensmecapt.document_intelligence.structure import (
    PageProcessingMode,
    PageRoutingPolicy,
    PageSignals,
    StructuredPageParser,
    StructuredParsingError,
)
from greensmecapt.domain import (
    DocumentType,
    SourceDocument,
)

_TABLE_HINT_PATTERN = re.compile(
    r"\b("
    r"metric|metrics|indicator|indicators|"
    r"unit|units|total|totals|"
    r"energy|electricity|emissions|waste|water|"
    r"revenue|cost|costs|amount|"
    r"20\d{2}"
    r")\b",
    flags=re.IGNORECASE,
)

_TABLE_ORIENTED_DOCUMENT_TYPES = frozenset(
    {
        DocumentType.FINANCIAL_STATEMENT,
        DocumentType.UTILITY_BILL,
        DocumentType.SUSTAINABILITY_REPORT,
    }
)


class SimpleOcrEngine(Protocol):
    """Recover unstructured text from one page image."""

    def recognize(self, image: PILImage) -> str:
        """Return readable page text."""
        ...


class PageProcessingRecord(BaseModel):
    """Record how one PDF page was processed."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    page_number: int = Field(ge=1)
    mode: PageProcessingMode
    reasons: tuple[str, ...] = Field(min_length=1)
    used_fallback_ocr: bool = False


class AdaptivePdfReadResult(BaseModel):
    """Return a document together with routing diagnostics."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document: ExtractedDocument
    processing_records: tuple[
        PageProcessingRecord, ...
    ] = Field(min_length=1)


class AdaptivePdfDocumentReader:
    """Route each PDF page through the appropriate reader."""

    supported_mime_types = frozenset({"application/pdf"})

    def __init__(
        self,
        *,
        structured_parser: StructuredPageParser,
        fallback_ocr_engine: SimpleOcrEngine | None = None,
        native_reader: PdfTextDocumentReader | None = None,
        routing_policy: PageRoutingPolicy | None = None,
        render_dpi: int = 200,
    ) -> None:
        if render_dpi < 72:
            raise ValueError(
                "PDF rendering DPI must be at least 72."
            )

        self._structured_parser = structured_parser
        self._fallback_ocr_engine = fallback_ocr_engine
        self._native_reader = (
            native_reader or PdfTextDocumentReader()
        )
        self._routing_policy = (
            routing_policy or PageRoutingPolicy()
        )
        self._render_dpi = render_dpi

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Read a PDF using adaptive page-level processing."""

        return self.read_with_diagnostics(
            document=document,
            content=content,
        ).document

    def read_with_diagnostics(
        self,
        *,
        document: SourceDocument,
        content: bytes,
    ) -> AdaptivePdfReadResult:
        """Read a PDF and retain every routing decision."""

        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

        try:
            pdf = pymupdf.open(
                stream=content,
                filetype="pdf",
            )
        except (
            pymupdf.FileDataError,
            RuntimeError,
            ValueError,
            OSError,
        ) as error:
            raise DocumentReadError(
                "PDF content could not be opened."
            ) from error

        try:
            if pdf.needs_pass:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported."
                )

            native_pages = self._read_native_pages(
                document=document,
                content=content,
            )

            extracted_pages: list[ExtractedPage] = []
            unreadable_pages: list[int] = []
            processing_records: list[
                PageProcessingRecord
            ] = []

            for page_index in range(pdf.page_count):
                page_number = page_index + 1
                pdf_page = pdf.load_page(page_index)
                native_page = native_pages.get(page_number)

                signals = _page_signals(
                    document=document,
                    pdf_page=pdf_page,
                    native_page=native_page,
                )

                decision = self._routing_policy.decide(
                    signals
                )

                if (
                    decision.mode
                    is PageProcessingMode.NATIVE
                    and native_page is not None
                ):
                    extracted_pages.append(native_page)

                    processing_records.append(
                        PageProcessingRecord(
                            page_number=page_number,
                            mode=decision.mode,
                            reasons=decision.reasons,
                        )
                    )
                    continue

                image = _render_page(
                    pdf_page,
                    dpi=self._render_dpi,
                )

                try:
                    structured_page = (
                        self._structured_parser.parse(
                            image,
                            page_number=page_number,
                        )
                    )

                    if (
                        structured_page.page_number
                        != page_number
                    ):
                        raise StructuredParsingError(
                            "Structured parser returned a "
                            "different page number."
                        )

                    if (
                        decision.mode
                        is PageProcessingMode.HYBRID
                        and native_page is not None
                    ):
                        final_page = _merge_pages(
                            native_page=native_page,
                            structured_page=structured_page,
                        )
                    else:
                        final_page = structured_page

                    extracted_pages.append(final_page)

                    processing_records.append(
                        PageProcessingRecord(
                            page_number=page_number,
                            mode=decision.mode,
                            reasons=decision.reasons,
                        )
                    )

                except StructuredParsingError as error:
                    fallback_page = self._fallback_page(
                        image=image,
                        page_number=page_number,
                    )

                    if fallback_page is not None:
                        if native_page is not None:
                            fallback_page = _merge_pages(
                                native_page=native_page,
                                structured_page=fallback_page,
                            )

                        extracted_pages.append(
                            fallback_page
                        )

                        processing_records.append(
                            PageProcessingRecord(
                                page_number=page_number,
                                mode=decision.mode,
                                reasons=(
                                    *decision.reasons,
                                    "Structured parsing failed: "
                                    f"{error}",
                                ),
                                used_fallback_ocr=True,
                            )
                        )
                    elif native_page is not None:
                        extracted_pages.append(native_page)

                        processing_records.append(
                            PageProcessingRecord(
                                page_number=page_number,
                                mode=(
                                    PageProcessingMode
                                    .REVIEW_REQUIRED
                                ),
                                reasons=(
                                    "Structured parsing failed; "
                                    "native content was retained.",
                                    str(error),
                                ),
                            )
                        )
                    else:
                        unreadable_pages.append(
                            page_number
                        )

                        escalation = (
                            self._routing_policy
                            .after_structured_failure(
                                reason=str(error)
                            )
                        )

                        processing_records.append(
                            PageProcessingRecord(
                                page_number=page_number,
                                mode=escalation.mode,
                                reasons=escalation.reasons,
                            )
                        )

            if not extracted_pages:
                raise DocumentReadError(
                    "No PDF page produced readable content."
                )

            extracted_pages.sort(
                key=lambda page: page.page_number
            )

            extracted_document = ExtractedDocument(
                document_id=document.document_id,
                pages=tuple(extracted_pages),
                total_pages=pdf.page_count,
                unreadable_pages=tuple(
                    unreadable_pages
                ),
            )

            return AdaptivePdfReadResult(
                document=extracted_document,
                processing_records=tuple(
                    processing_records
                ),
            )

        finally:
            pdf.close()

    def _read_native_pages(
        self,
        *,
        document: SourceDocument,
        content: bytes,
    ) -> dict[int, ExtractedPage]:
        """Recover any pages readable through native extraction."""

        try:
            extracted = self._native_reader.read(
                document=document,
                content=content,
            )
        except DocumentReadError:
            return {}

        return {
            page.page_number: page
            for page in extracted.pages
        }

    def _fallback_page(
        self,
        *,
        image: PILImage,
        page_number: int,
    ) -> ExtractedPage | None:
        """Attempt simple OCR after structured OCR fails."""

        if self._fallback_ocr_engine is None:
            return None
        try:
            text = self._fallback_ocr_engine.recognize(image).strip()
        except DocumentReadError:
            return None

        if not text:
            return None

        return ExtractedPage(
            page_number=page_number,
            text=text,
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
        )


def _page_signals(
    *,
    document: SourceDocument,
    pdf_page: pymupdf.Page,
    native_page: ExtractedPage | None,
) -> PageSignals:
    """Calculate deterministic routing signals for one page."""

    if native_page is None:
        embedded_character_count = 0
        native_table_count = 0
        native_text = ""
    else:
        native_text = native_page.text
        embedded_character_count = len(
            "".join(native_text.split())
        )
        native_table_count = len(
            native_page.tables
        )

    image_coverage = _image_coverage(pdf_page)

    table_hint_count = len(
        _TABLE_HINT_PATTERN.findall(native_text)
    )

    expected_tables = (
        document.document_type
        in _TABLE_ORIENTED_DOCUMENT_TYPES
        and table_hint_count >= 2
    )

    suspicious_reading_order = (
        "\ufffd" in native_text
        or "\x00" in native_text
    )

    return PageSignals(
        embedded_character_count=(
            embedded_character_count
        ),
        native_table_count=native_table_count,
        image_coverage=image_coverage,
        expected_tables=expected_tables,
        suspicious_reading_order=(
            suspicious_reading_order
        ),
        native_extraction_failed=(
            native_page is None
            and image_coverage == 0
        ),
    )


def _image_coverage(
    pdf_page: pymupdf.Page,
) -> float:
    """Estimate how much of a PDF page is occupied by images."""

    page_area = (
        float(pdf_page.rect.width)
        * float(pdf_page.rect.height)
    )

    if page_area <= 0:
        return 0

    try:
        page_dictionary = pdf_page.get_text("dict")
    except (RuntimeError, ValueError):
        return 0

    image_area = 0.0

    for block in page_dictionary.get("blocks", []):
        if block.get("type") != 1:
            continue

        raw_box = block.get("bbox")

        if (
            not isinstance(raw_box, Sequence)
            or len(raw_box) != 4
        ):
            continue

        try:
            x0, top, x1, bottom = (
                float(value) for value in raw_box
            )
        except (TypeError, ValueError):
            continue

        width = max(0, x1 - x0)
        height = max(0, bottom - top)

        image_area += width * height

    return min(1.0, image_area / page_area)


def _render_page(
    pdf_page: pymupdf.Page,
    *,
    dpi: int,
) -> PILImage:
    """Render one PDF page into a detached RGB image."""

    pixmap = pdf_page.get_pixmap(
        dpi=dpi,
        alpha=False,
    )

    with Image.open(
        BytesIO(pixmap.tobytes("png"))
    ) as image:
        return image.convert("RGB").copy()


def _merge_pages(
    *,
    native_page: ExtractedPage,
    structured_page: ExtractedPage,
) -> ExtractedPage:
    """Merge native and visual parsing without duplicating content."""

    if (
        native_page.page_number
        != structured_page.page_number
    ):
        raise ValueError(
            "Only matching source pages can be merged."
        )

    merged_blocks = _merge_text_blocks(
        native_page.text_blocks,
        structured_page.text_blocks,
        page_number=native_page.page_number,
    )

    merged_tables = _merge_tables(
        native_page.tables,
        structured_page.tables,
        page_number=native_page.page_number,
    )

    merged_text = _merge_text(
        native_page.text,
        structured_page.text,
    )

    return ExtractedPage(
        page_number=native_page.page_number,
        text=merged_text,
        text_source=TextSource.HYBRID,
        page_width=(
            native_page.page_width
            or structured_page.page_width
        ),
        page_height=(
            native_page.page_height
            or structured_page.page_height
        ),
        text_blocks=merged_blocks,
        tables=merged_tables,
    )


def _merge_text(
    native_text: str,
    structured_text: str,
) -> str:
    """Combine text lines while removing exact duplicates."""

    lines: list[str] = []
    normalized_seen: set[str] = set()

    for source_text in (
        native_text,
        structured_text,
    ):
        for raw_line in source_text.splitlines():
            line = " ".join(raw_line.split())

            if not line:
                continue

            normalized = line.casefold()

            if normalized in normalized_seen:
                continue

            normalized_seen.add(normalized)
            lines.append(line)

    return "\n".join(lines)


def _merge_text_blocks(
    native_blocks: Sequence[ExtractedTextBlock],
    structured_blocks: Sequence[ExtractedTextBlock],
    *,
    page_number: int,
) -> tuple[ExtractedTextBlock, ...]:
    """Merge blocks by normalized text and reset stable IDs."""

    selected: list[ExtractedTextBlock] = []
    normalized_seen: set[str] = set()

    for block in (
        *native_blocks,
        *structured_blocks,
    ):
        normalized = " ".join(
            block.text.casefold().split()
        )

        if normalized in normalized_seen:
            continue

        normalized_seen.add(normalized)
        selected.append(block)

    return tuple(
        block.model_copy(
            update={
                "block_id": (
                    f"adaptive_page_{page_number}_block_"
                    f"{index + 1}"
                ),
                "reading_order": index,
            }
        )
        for index, block in enumerate(selected)
    )


def _merge_tables(
    native_tables: Sequence[ExtractedTable],
    structured_tables: Sequence[ExtractedTable],
    *,
    page_number: int,
) -> tuple[ExtractedTable, ...]:
    """Merge tables without duplicating identical matrices."""

    selected: list[ExtractedTable] = []
    matrices_seen: set[
        tuple[tuple[str, ...], ...]
    ] = set()

    for table in (
        *native_tables,
        *structured_tables,
    ):
        normalized_matrix = tuple(
            tuple(
                " ".join(cell.casefold().split())
                for cell in row
            )
            for row in table.as_matrix()
        )

        if normalized_matrix in matrices_seen:
            continue

        matrices_seen.add(normalized_matrix)
        selected.append(table)

    return tuple(
        table.model_copy(
            update={
                "table_id": (
                    f"adaptive_page_{page_number}_table_"
                    f"{index + 1}"
                ),
            }
        )
        for index, table in enumerate(selected)
    )