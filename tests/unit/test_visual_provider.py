"""Tests for the OpenAI-compatible multimodal provider."""

import base64
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedVisualRegion,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.semantics import (
    load_metric_catalog,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    OpenAICompatibleProviderConfiguration,
)
from greensmecapt.document_intelligence.vision import (
    OpenAICompatibleVisualProvider,
    VisualInterpretationRequest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    PROJECT_ROOT
    / "config"
    / "metric_catalog.development.json"
)


class CapturingTransport:
    """Capture the provider request and return strict JSON."""

    def __init__(self) -> None:
        self.payload: Mapping[str, Any] | None = None

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.payload = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "One explicit value found.",
                                "claims": [
                                    {
                                        "indicator_id": (
                                            "renewable_energy_percentage"
                                        ),
                                        "raw_value": "72 percent",
                                        "raw_number": 72,
                                        "raw_unit": "percent",
                                        "source_description": (
                                            "Value printed above the bar."
                                        ),
                                        "confidence": 0.9,
                                    }
                                ],
                            }
                        )
                    }
                }
            ]
        }


def test_send_exact_crop_and_allowed_catalog_as_structured_request() -> None:
    """The adapter should send image bytes and constrain model output."""

    transport = CapturingTransport()
    provider = OpenAICompatibleVisualProvider(
        OpenAICompatibleProviderConfiguration(
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            model="local-vision-model",
        ),
        transport=transport,
    )
    image_png = b"bounded-image-pixels"
    output = provider.interpret(
        VisualInterpretationRequest(
            document_id="doc_001",
            page_number=2,
            region=ExtractedVisualRegion(
                region_id="page_2_chart_1",
                kind=VisualRegionKind.CHART,
                bounding_box=BoundingBox(
                    x0=10,
                    top=20,
                    x1=200,
                    bottom=150,
                ),
                caption="Renewable energy share",
            ),
            page_context="Environmental performance chart.",
            image_png=image_png,
            catalog=load_metric_catalog(CATALOG_PATH),
        )
    )

    assert output.claims[0].raw_number == 72
    assert transport.payload is not None
    user_content = transport.payload["messages"][1]["content"]
    image_url = user_content[1]["image_url"]["url"]
    assert image_url == (
        "data:image/png;base64,"
        + base64.b64encode(image_png).decode("ascii")
    )
    assert transport.payload["temperature"] == 0
    assert (
        transport.payload["response_format"]["type"]
        == "json_schema"
    )
    assert "renewable_energy_percentage" in user_content[0]["text"]

