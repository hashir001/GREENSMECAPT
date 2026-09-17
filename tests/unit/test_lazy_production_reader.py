"""Tests for lazy initialization of heavyweight OCR models."""

from PIL import Image

from greensmecapt.document_intelligence.models import (
    ExtractedPage,
    TextSource,
)
from greensmecapt.document_intelligence.readers import production
from greensmecapt.document_intelligence.structure import (
    PaddleParserConfiguration,
)


def test_default_paddle_parser_loads_only_when_used(
    monkeypatch,
) -> None:
    """API startup must not initialize heavyweight OCR models."""

    creations: list[PaddleParserConfiguration] = []

    class FakePaddleParser:
        def __init__(self, configuration) -> None:
            creations.append(configuration)

        def parse(
            self,
            image: Image.Image,
            *,
            page_number: int,
        ) -> ExtractedPage:
            return ExtractedPage(
                page_number=page_number,
                text="Structured OCR content",
                text_source=TextSource.OCR,
                page_width=float(image.width),
                page_height=float(image.height),
            )

    monkeypatch.setattr(
        production,
        "PaddleStructuredPageParser",
        FakePaddleParser,
    )
    parser = production.LazyPaddleStructuredPageParser(
        PaddleParserConfiguration()
    )

    assert creations == []

    parser.parse(Image.new("RGB", (20, 20)), page_number=1)
    parser.parse(Image.new("RGB", (20, 20)), page_number=2)

    assert len(creations) == 1
