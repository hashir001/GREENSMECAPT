"""Structured content recovered while reading SME documents."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TextSource(StrEnum):
    """Describe how readable text was recovered."""

    PLAIN_TEXT = "plain_text"
    PDF_EMBEDDED = "pdf_embedded"
    OCR = "ocr"


class TextBlockKind(StrEnum):
    """Describe the structural role of a recovered text block."""

    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    CAPTION = "caption"
    HEADER = "header"
    FOOTER = "footer"
    OTHER = "other"


class BoundingBox(BaseModel):
    """Locate content using top-left page coordinates."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    x0: float = Field(ge=0)
    top: float = Field(ge=0)
    x1: float = Field(ge=0)
    bottom: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        """Require a box with positive width and height."""

        if self.x1 <= self.x0:
            raise ValueError(
                "Bounding-box x1 must be greater than x0."
            )

        if self.bottom <= self.top:
            raise ValueError(
                "Bounding-box bottom must be greater than top."
            )

        return self


class ExtractedTextBlock(BaseModel):
    """Represent one positioned text region on a page."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    block_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: TextBlockKind = TextBlockKind.PARAGRAPH
    bounding_box: BoundingBox
    reading_order: int = Field(ge=0)
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )


class ExtractedTableCell(BaseModel):
    """Represent one cell recovered from a document table."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str = ""
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False
    bounding_box: BoundingBox | None = None
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )


class ExtractedTable(BaseModel):
    """Represent a table while preserving rows, columns and location."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    table_id: str = Field(min_length=1)
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    cells: tuple[ExtractedTableCell, ...] = Field(min_length=1)
    bounding_box: BoundingBox
    caption: str | None = Field(default=None, min_length=1)
    header_row_indices: tuple[int, ...] = ()

    @model_validator(mode="after")
    def validate_table_structure(self) -> Self:
        """Ensure cells occupy valid and unique table positions."""

        positions: list[tuple[int, int]] = []

        for cell in self.cells:
            if cell.row_index >= self.row_count:
                raise ValueError(
                    "Table-cell row index exceeds the table row count."
                )

            if cell.column_index >= self.column_count:
                raise ValueError(
                    "Table-cell column index exceeds the table "
                    "column count."
                )

            if cell.row_index + cell.row_span > self.row_count:
                raise ValueError(
                    "Table-cell row span exceeds the table bounds."
                )

            if (
                cell.column_index + cell.column_span
                > self.column_count
            ):
                raise ValueError(
                    "Table-cell column span exceeds the table bounds."
                )

            positions.append(
                (cell.row_index, cell.column_index)
            )

        if len(positions) != len(set(positions)):
            raise ValueError(
                "Table cells must have unique starting positions."
            )

        if len(self.header_row_indices) != len(
            set(self.header_row_indices)
        ):
            raise ValueError(
                "Header row indices must be unique."
            )

        if any(
            row_index >= self.row_count
            for row_index in self.header_row_indices
        ):
            raise ValueError(
                "Header row index exceeds the table row count."
            )

        return self

    def value_at(
        self,
        row_index: int,
        column_index: int,
    ) -> str | None:
        """Return a cell value at a requested table position."""

        for cell in self.cells:
            if (
                cell.row_index == row_index
                and cell.column_index == column_index
            ):
                return cell.text

        return None

    def as_matrix(self) -> tuple[tuple[str, ...], ...]:
        """Return a rectangular text matrix for NLP or display."""

        rows = [
            ["" for _ in range(self.column_count)]
            for _ in range(self.row_count)
        ]

        for cell in self.cells:
            rows[cell.row_index][cell.column_index] = cell.text

        return tuple(tuple(row) for row in rows)


class ExtractedPage(BaseModel):
    """Represent structured content recovered from one document page."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    page_number: int = Field(ge=1)
    text: str = Field(min_length=1)
    text_source: TextSource = TextSource.PLAIN_TEXT

    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)

    text_blocks: tuple[ExtractedTextBlock, ...] = ()
    tables: tuple[ExtractedTable, ...] = ()

    @model_validator(mode="after")
    def validate_page_structure(self) -> Self:
        """Keep page dimensions and structural identifiers consistent."""

        if (self.page_width is None) != (
            self.page_height is None
        ):
            raise ValueError(
                "Page width and height must be supplied together."
            )

        block_ids = [
            block.block_id for block in self.text_blocks
        ]
        table_ids = [
            table.table_id for table in self.tables
        ]
        reading_orders = [
            block.reading_order for block in self.text_blocks
        ]

        if len(block_ids) != len(set(block_ids)):
            raise ValueError(
                "Text-block IDs must be unique within a page."
            )

        if len(table_ids) != len(set(table_ids)):
            raise ValueError(
                "Table IDs must be unique within a page."
            )

        if len(reading_orders) != len(set(reading_orders)):
            raise ValueError(
                "Text-block reading-order values must be unique."
            )

        return self


class ExtractedDocument(BaseModel):
    """Represent structured readable content recovered from a document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    document_id: str = Field(min_length=1)
    pages: tuple[ExtractedPage, ...] = Field(min_length=1)

    total_pages: int | None = Field(default=None, ge=1)
    unreadable_pages: tuple[int, ...] = ()

    @model_validator(mode="after")
    def validate_page_sequence(self) -> Self:
        """Require consistent readable and unreadable page tracking."""

        page_numbers = [
            page.page_number for page in self.pages
        ]

        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError(
                "Extracted page numbers must be unique."
            )

        if page_numbers != sorted(page_numbers):
            raise ValueError(
                "Extracted pages must follow source-page order."
            )

        if len(self.unreadable_pages) != len(
            set(self.unreadable_pages)
        ):
            raise ValueError(
                "Unreadable page numbers must be unique."
            )

        if list(self.unreadable_pages) != sorted(
            self.unreadable_pages
        ):
            raise ValueError(
                "Unreadable pages must follow source-page order."
            )

        if any(
            page_number < 1
            for page_number in self.unreadable_pages
        ):
            raise ValueError(
                "Unreadable page numbers must be positive."
            )

        overlap = set(page_numbers) & set(
            self.unreadable_pages
        )

        if overlap:
            raise ValueError(
                "A page cannot be both readable and unreadable."
            )

        if self.total_pages is not None:
            recorded_pages = (
                page_numbers + list(self.unreadable_pages)
            )

            if any(
                page_number > self.total_pages
                for page_number in recorded_pages
            ):
                raise ValueError(
                    "Recorded page number exceeds total pages."
                )

        elif self.unreadable_pages:
            raise ValueError(
                "Total pages are required when unreadable pages "
                "are recorded."
            )

        return self