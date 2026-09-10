"""Tests for structured document content models."""

import pytest
from pydantic import ValidationError

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    TextBlockKind,
    TextSource,
)


def _make_box() -> BoundingBox:
    return BoundingBox(
        x0=20,
        top=40,
        x1=200,
        bottom=80,
    )


def test_create_positioned_text_block() -> None:
    """A text block should retain location and reading order."""

    block = ExtractedTextBlock(
        block_id="page_1_block_1",
        text="Environmental performance",
        kind=TextBlockKind.HEADING,
        bounding_box=_make_box(),
        reading_order=0,
        confidence=0.97,
    )

    assert block.kind is TextBlockKind.HEADING
    assert block.bounding_box.x0 == 20
    assert block.reading_order == 0


def test_reject_invalid_bounding_box() -> None:
    """A bounding box must have positive width and height."""

    with pytest.raises(ValidationError):
        BoundingBox(
            x0=200,
            top=40,
            x1=20,
            bottom=80,
        )


def test_table_preserves_rectangular_structure() -> None:
    """A table should expose cells as a rectangular matrix."""

    table = ExtractedTable(
        table_id="page_1_table_1",
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
        bounding_box=_make_box(),
        header_row_indices=(0,),
    )

    assert table.value_at(1, 1) == "68"
    assert table.as_matrix() == (
        ("Metric", "2024", "Unit"),
        ("Renewable electricity", "68", "%"),
    )


def test_reject_cell_outside_table_bounds() -> None:
    """A cell must belong to a declared table row and column."""

    with pytest.raises(ValidationError):
        ExtractedTable(
            table_id="page_1_table_1",
            row_count=1,
            column_count=1,
            cells=(
                ExtractedTableCell(
                    row_index=1,
                    column_index=0,
                    text="Outside",
                ),
            ),
            bounding_box=_make_box(),
        )


def test_document_retains_backward_compatible_page_text() -> None:
    """Structured pages should still expose their original page text."""

    document = ExtractedDocument(
        document_id="doc_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text="Renewable electricity: 68%",
                text_source=TextSource.PDF_EMBEDDED,
                page_width=612,
                page_height=792,
                text_blocks=(
                    ExtractedTextBlock(
                        block_id="page_1_block_1",
                        text="Renewable electricity: 68%",
                        bounding_box=_make_box(),
                        reading_order=0,
                    ),
                ),
            ),
        ),
    )

    assert document.pages[0].text == (
        "Renewable electricity: 68%"
    )
    assert len(document.pages[0].text_blocks) == 1
    assert document.pages[0].tables == ()