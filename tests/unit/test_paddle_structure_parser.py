"""Tests for converting PaddleOCR results into project models."""

import numpy as np
import pytest
from PIL import Image

from greensmecapt.document_intelligence import TextSource
from greensmecapt.document_intelligence.structure import (
    PaddleParserConfiguration,
    PaddleStructuredPageParser,
    StructuredParsingError,
)


class FakeResult:
    """Expose the JSON interface returned by PaddleOCR results."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.json = {"res": payload}


class FakePipeline:
    """Return controlled structured predictions and retain options."""

    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.options: dict[str, object] = {}

    def predict(self, **options: object) -> list[object]:
        self.options = options
        return self.results


class FailingPipeline:
    """Simulate a vendor inference failure."""

    def predict(self, **options: object) -> list[object]:
        raise RuntimeError("inference unavailable")


def _image() -> Image.Image:
    return Image.new("RGB", (800, 1200), color="white")


def _payload() -> dict[str, object]:
    return {
        "width": 800,
        "height": 1200,
        "parsing_res_list": [
            {
                "block_label": "document_title",
                "block_content": "Environmental Report",
                "block_bbox": [20, 20, 500, 80],
            },
            {
                "block_label": "table",
                "block_content": "",
                "block_bbox": [20, 120, 700, 360],
            },
            {
                "block_label": "chart",
                "block_content": "Renewable energy trend",
                "block_bbox": [20, 400, 700, 760],
            },
        ],
        "table_res_list": [
            {
                "pred_html": (
                    "<table><tr><th>Metric</th><th>Value</th></tr>"
                    "<tr><td>Renewable energy</td><td>72%</td></tr>"
                    "</table>"
                ),
                "cell_box_list": [
                    [20, 120, 300, 180],
                    [300, 120, 700, 180],
                    [20, 180, 300, 240],
                    [300, 180, 700, 240],
                ],
                "table_ocr_pred": {
                    "rec_scores": [0.99, 0.98, 0.97, 0.96]
                },
            }
        ],
    }


def test_convert_paddle_blocks_and_tables() -> None:
    """Paddle layout output should retain text, geometry and cells."""

    parser = PaddleStructuredPageParser(
        pipeline=FakePipeline([FakeResult(_payload())])
    )

    page = parser.parse(_image(), page_number=3)

    assert page.page_number == 3
    assert page.text_source is TextSource.OCR
    assert page.page_width == 800
    assert page.page_height == 1200
    assert page.text_blocks[0].text == "Environmental Report"
    assert page.tables[0].as_matrix() == (
        ("Metric", "Value"),
        ("Renewable energy", "72%"),
    )
    assert page.tables[0].header_row_indices == (0,)
    assert page.tables[0].cells[0].confidence == pytest.approx(0.99)
    assert page.visual_regions[0].kind == "chart"
    assert page.visual_regions[0].caption == (
        "Renewable energy trend"
    )
    assert "Renewable energy | 72%" in page.text


def test_forward_cpu_and_feature_configuration() -> None:
    """Runtime feature switches should reach the Paddle prediction call."""

    pipeline = FakePipeline([FakeResult(_payload())])
    configuration = PaddleParserConfiguration(
        cpu_threads=4,
        use_document_unwarping=False,
        use_formula_recognition=True,
        text_recognition_threshold=0.72,
    )
    parser = PaddleStructuredPageParser(
        configuration,
        pipeline=pipeline,
    )

    parser.parse(_image(), page_number=1)

    assert isinstance(pipeline.options["input"], np.ndarray)
    assert pipeline.options["use_doc_unwarping"] is False
    assert pipeline.options["use_formula_recognition"] is True
    assert pipeline.options["text_rec_score_thresh"] == pytest.approx(0.72)


def test_use_overall_ocr_when_layout_is_empty() -> None:
    """Readable OCR text should survive even without layout regions."""

    payload = {
        "overall_ocr_res": {
            "rec_texts": ["Water use", "reduced by 18 percent"]
        }
    }
    parser = PaddleStructuredPageParser(
        pipeline=FakePipeline([FakeResult(payload)])
    )

    page = parser.parse(_image(), page_number=1)

    assert page.text == "Water use\nreduced by 18 percent"
    assert page.text_blocks == ()
    assert page.tables == ()


def test_reject_invalid_prediction_cardinality() -> None:
    """One page must produce exactly one vendor result."""

    parser = PaddleStructuredPageParser(
        pipeline=FakePipeline([])
    )

    with pytest.raises(
        StructuredParsingError,
        match="exactly one result",
    ):
        parser.parse(_image(), page_number=1)


def test_wrap_vendor_prediction_failure() -> None:
    """Vendor exceptions should not leak through the project boundary."""

    parser = PaddleStructuredPageParser(
        pipeline=FailingPipeline()
    )

    with pytest.raises(
        StructuredParsingError,
        match="prediction failed",
    ):
        parser.parse(_image(), page_number=1)


def test_reject_non_positive_source_page() -> None:
    """Structured output must retain a valid source-page identity."""

    parser = PaddleStructuredPageParser(
        pipeline=FakePipeline([FakeResult(_payload())])
    )

    with pytest.raises(
        StructuredParsingError,
        match="must be positive",
    ):
        parser.parse(_image(), page_number=0)
