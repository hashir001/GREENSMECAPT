"""Tests for page classification and bounded long-document plans."""

import pytest
from pydantic import ValidationError

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedVisualRegion,
    TextSource,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.orchestration import (
    DocumentExecutionMode,
    DocumentProcessingPlanner,
    LongDocumentPolicy,
    PageContentKind,
    ProcessingCapability,
)


def _box(
    *,
    top: float = 20,
    bottom: float = 220,
) -> BoundingBox:
    return BoundingBox(
        x0=20,
        top=top,
        x1=500,
        bottom=bottom,
    )


def _page(
    page_number: int,
    *,
    source: TextSource = TextSource.PDF_EMBEDDED,
) -> ExtractedPage:
    return ExtractedPage(
        page_number=page_number,
        text=f"Readable environmental report page {page_number}.",
        text_source=source,
    )


def test_plan_short_digital_document_for_immediate_processing() -> None:
    document = ExtractedDocument(
        document_id="doc_short",
        pages=tuple(_page(number) for number in range(1, 4)),
        total_pages=3,
    )

    manifest = DocumentProcessingPlanner().plan(document)

    assert manifest.execution_mode is DocumentExecutionMode.IMMEDIATE
    assert len(manifest.batches) == 1
    assert manifest.batches[0].page_numbers == (1, 2, 3)
    assert all(
        profile.content_kinds == (PageContentKind.DIGITAL_TEXT,)
        for profile in manifest.page_profiles
    )


def test_split_long_document_into_retryable_page_batches() -> None:
    document = ExtractedDocument(
        document_id="doc_long",
        pages=tuple(_page(number) for number in range(1, 26)),
        total_pages=25,
    )
    planner = DocumentProcessingPlanner(
        LongDocumentPolicy(
            immediate_page_limit=10,
            page_batch_size=10,
            maximum_batch_attempts=4,
        )
    )

    manifest = planner.plan(document)

    assert manifest.execution_mode is DocumentExecutionMode.BACKGROUND
    assert tuple(
        batch.page_numbers for batch in manifest.batches
    ) == (
        tuple(range(1, 11)),
        tuple(range(11, 21)),
        tuple(range(21, 26)),
    )
    assert all(
        batch.maximum_attempts == 4 for batch in manifest.batches
    )


def test_route_table_chart_and_image_regions_separately() -> None:
    table = ExtractedTable(
        table_id="table_1",
        row_count=1,
        column_count=1,
        cells=(
            ExtractedTableCell(
                row_index=0,
                column_index=0,
                text="Renewable energy: 72%",
            ),
        ),
        bounding_box=_box(top=20, bottom=180),
    )
    page = ExtractedPage(
        page_number=1,
        text="Energy performance table and supporting visual evidence.",
        text_source=TextSource.HYBRID,
        tables=(table,),
        visual_regions=(
            ExtractedVisualRegion(
                region_id="chart_1",
                kind=VisualRegionKind.CHART,
                bounding_box=_box(top=220, bottom=420),
                caption="Renewable electricity share",
            ),
            ExtractedVisualRegion(
                region_id="photo_1",
                kind=VisualRegionKind.PHOTOGRAPH,
                bounding_box=_box(top=440, bottom=700),
            ),
            ExtractedVisualRegion(
                region_id="logo_1",
                kind=VisualRegionKind.LOGO,
                bounding_box=BoundingBox(
                    x0=520,
                    top=20,
                    x1=600,
                    bottom=80,
                ),
            ),
        ),
    )

    manifest = DocumentProcessingPlanner().plan(
        ExtractedDocument(
            document_id="doc_mixed",
            pages=(page,),
            total_pages=1,
        )
    )
    profile = manifest.page_profiles[0]

    assert PageContentKind.TABLE in profile.content_kinds
    assert PageContentKind.CHART in profile.content_kinds
    assert PageContentKind.IMAGE in profile.content_kinds
    assert (
        ProcessingCapability.TABLE_STRUCTURE
        in profile.required_capabilities
    )
    assert (
        ProcessingCapability.MULTIMODAL_INTERPRETATION
        in profile.required_capabilities
    )
    assert (
        ProcessingCapability.VISUAL_RELEVANCE_REVIEW
        in profile.required_capabilities
    )
    assert manifest.table_page_count == 1
    assert manifest.visual_page_count == 1
    assert manifest.multimodal_page_count == 1
    assert manifest.review_required_page_count == 1


def test_preserve_unreadable_page_for_targeted_retry_or_review() -> None:
    document = ExtractedDocument(
        document_id="doc_partial",
        pages=(
            _page(1),
            _page(3, source=TextSource.OCR),
        ),
        total_pages=3,
        unreadable_pages=(2,),
    )

    manifest = DocumentProcessingPlanner().plan(document)
    profile = manifest.page_profiles[1]

    assert profile.page_number == 2
    assert profile.content_kinds == (PageContentKind.UNKNOWN,)
    assert profile.required_capabilities == (
        ProcessingCapability.HUMAN_REVIEW,
    )
    assert manifest.review_required_page_count == 1


def test_reject_duplicate_visual_region_ids() -> None:
    region = ExtractedVisualRegion(
        region_id="figure_1",
        kind=VisualRegionKind.DIAGRAM,
        bounding_box=_box(),
    )

    with pytest.raises(ValidationError):
        ExtractedPage(
            page_number=1,
            text="Process diagram",
            visual_regions=(region, region),
        )
