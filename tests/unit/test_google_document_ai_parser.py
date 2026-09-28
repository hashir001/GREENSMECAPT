"""Tests for the isolated Google Document AI adapter."""

from types import SimpleNamespace

from PIL import Image

from greensmecapt.document_intelligence.models import TextSource
from greensmecapt.document_intelligence.structure import (
    FallbackStructuredPageParser,
    GoogleDocumentAIConfiguration,
    GoogleDocumentAIStructuredPageParser,
    StructuredParsingError,
)


def _layout(start: int, end: int, *, top: float, bottom: float):
    vertices = (
        SimpleNamespace(x=0.1, y=top),
        SimpleNamespace(x=0.9, y=top),
        SimpleNamespace(x=0.9, y=bottom),
        SimpleNamespace(x=0.1, y=bottom),
    )
    return SimpleNamespace(
        text_anchor=SimpleNamespace(
            text_segments=(SimpleNamespace(start_index=start, end_index=end),)
        ),
        bounding_poly=SimpleNamespace(
            normalized_vertices=vertices,
            vertices=(),
        ),
        confidence=0.97,
    )


class _FakeClient:
    def __init__(self, *, expected_timeout: float = 30) -> None:
        self.request = None
        self.expected_timeout = expected_timeout

    def process_document(self, *, request, timeout):
        self.request = request
        assert timeout == self.expected_timeout
        text = "Metric Value\nEnergy 120 kWh\n"
        header = SimpleNamespace(
            cells=(
                SimpleNamespace(layout=_layout(0, 6, top=0.1, bottom=0.2)),
                SimpleNamespace(layout=_layout(7, 12, top=0.1, bottom=0.2)),
            )
        )
        body = SimpleNamespace(
            cells=(
                SimpleNamespace(layout=_layout(13, 19, top=0.2, bottom=0.3)),
                SimpleNamespace(layout=_layout(20, 27, top=0.2, bottom=0.3)),
            )
        )
        table = SimpleNamespace(
            layout=_layout(0, 27, top=0.1, bottom=0.3),
            header_rows=(header,),
            body_rows=(body,),
        )
        page = SimpleNamespace(
            blocks=(SimpleNamespace(layout=_layout(0, 27, top=0.1, bottom=0.3)),),
            tables=(table,),
        )
        return SimpleNamespace(document=SimpleNamespace(text=text, pages=(page,)))


def test_convert_google_response_to_existing_models() -> None:
    client = _FakeClient()
    parser = GoogleDocumentAIStructuredPageParser(
        GoogleDocumentAIConfiguration(
            project_id="project",
            location="eu",
            processor_id="processor",
            timeout_seconds=30,
        ),
        client=client,
    )

    page = parser.parse(Image.new("RGB", (1000, 500)), page_number=3)

    assert page.page_number == 3
    assert page.text_source is TextSource.OCR
    assert page.text_blocks[0].confidence == 0.97
    assert page.tables[0].as_matrix() == (
        ("Metric", "Value"),
        ("Energy", "120 kWh"),
    )
    assert client.request["name"] == ("projects/project/locations/eu/processors/processor")
    assert client.request["raw_document"]["mime_type"] == "image/png"


class _FailingParser:
    def parse(self, image, *, page_number):
        raise StructuredParsingError("provider unavailable")


class _LocalParser:
    def parse(self, image, *, page_number):
        return GoogleDocumentAIStructuredPageParser(
            GoogleDocumentAIConfiguration(project_id="p", location="eu", processor_id="id"),
            client=_FakeClient(expected_timeout=120),
        ).parse(image, page_number=page_number)


def test_cloud_failure_retains_local_fallback() -> None:
    parser = FallbackStructuredPageParser(_FailingParser(), _LocalParser())

    page = parser.parse(Image.new("RGB", (100, 50)), page_number=1)

    assert page.text.startswith("Metric Value")
