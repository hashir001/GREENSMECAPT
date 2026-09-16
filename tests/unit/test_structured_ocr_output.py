"""Tests for stable structured-OCR JSON output."""

import json

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedPage,
    ExtractedTextBlock,
    TextBlockKind,
    TextSource,
)
from greensmecapt.document_intelligence.structure.output import (
    StructuredOcrReport,
)
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleResourceProfile,
)


def _make_page() -> ExtractedPage:
    return ExtractedPage(
        page_number=1,
        text="Renewable energy contribution: 72%",
        text_source=TextSource.OCR,
        page_width=1400,
        page_height=700,
        text_blocks=(
            ExtractedTextBlock(
                block_id="paddle_page_1_block_1",
                text=(
                    "Renewable energy contribution: 72%"
                ),
                kind=TextBlockKind.PARAGRAPH,
                bounding_box=BoundingBox(
                    x0=75,
                    top=120,
                    x1=610,
                    bottom=175,
                ),
                reading_order=0,
                confidence=0.97,
            ),
        ),
    )


def test_build_structured_ocr_report() -> None:
    """A parsed page should become stable project output."""

    report = StructuredOcrReport.from_page(
        profile=PaddleResourceProfile.LOCAL_CPU,
        source_name="sustainability-report.png",
        page=_make_page(),
    )

    assert report.status == "ready"
    assert (
        report.profile
        is PaddleResourceProfile.LOCAL_CPU
    )
    assert report.text_block_count == 1
    assert report.table_count == 0
    assert report.page.page_number == 1


def test_serialize_structured_ocr_report_to_json() -> None:
    """The report should be consumable by APIs and frontends."""

    report = StructuredOcrReport.from_page(
        profile=PaddleResourceProfile.LOCAL_CPU,
        source_name="sustainability-report.png",
        page=_make_page(),
    )

    payload = json.loads(
        report.model_dump_json()
    )

    assert payload["status"] == "ready"
    assert payload["profile"] == "local_cpu"
    assert payload["page"]["text_source"] == "ocr"

    assert (
        payload["page"]["text_blocks"][0]["text"]
        == "Renewable energy contribution: 72%"
    )

    assert (
        payload["page"]["text_blocks"][0]
        ["bounding_box"]["x0"]
        == 75.0
    )