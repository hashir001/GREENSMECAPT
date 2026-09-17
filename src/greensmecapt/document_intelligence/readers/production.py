"""Construct the production document-reader graph."""

from threading import Lock

from PIL.Image import Image
from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.models import ExtractedPage
from greensmecapt.document_intelligence.ports import DocumentReader
from greensmecapt.document_intelligence.readers.adaptive_pdf import (
    AdaptivePdfDocumentReader,
)
from greensmecapt.document_intelligence.readers.ocr import (
    OcrEngine,
    TesseractOcrEngine,
)
from greensmecapt.document_intelligence.readers.plain_text import (
    PlainTextDocumentReader,
)
from greensmecapt.document_intelligence.readers.router import (
    RoutingDocumentReader,
)
from greensmecapt.document_intelligence.readers.structured_image import (
    StructuredImageDocumentReader,
)
from greensmecapt.document_intelligence.structure import (
    PaddleParserConfiguration,
    PaddleStructuredPageParser,
    StructuredPageParser,
)


class LazyPaddleStructuredPageParser:
    """Load Paddle models only when a page truly requires OCR."""

    def __init__(
        self,
        configuration: PaddleParserConfiguration,
    ) -> None:
        self._configuration = configuration
        self._parser: PaddleStructuredPageParser | None = None
        self._lock = Lock()

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        """Initialize once, then delegate structured page parsing."""

        parser = self._parser

        if parser is None:
            with self._lock:
                parser = self._parser

                if parser is None:
                    parser = PaddleStructuredPageParser(
                        self._configuration
                    )
                    self._parser = parser

        return parser.parse(
            image,
            page_number=page_number,
        )


class ProductionReaderConfiguration(BaseModel):
    """Configure production PDF, image and text reading."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    paddle: PaddleParserConfiguration = Field(
        default_factory=PaddleParserConfiguration
    )
    pdf_render_dpi: int = Field(default=200, ge=72, le=600)
    enable_tesseract_fallback: bool = True
    tesseract_language: str = Field(default="eng", min_length=1)
    tesseract_page_segmentation_mode: int = Field(default=6, ge=0)
    tesseract_timeout_seconds: float = Field(default=30, gt=0)


def build_production_document_reader(
    configuration: ProductionReaderConfiguration | None = None,
    *,
    structured_parser: StructuredPageParser | None = None,
    fallback_ocr_engine: OcrEngine | None = None,
) -> DocumentReader:
    """Build MIME routing with adaptive PDF and structured image OCR."""

    resolved = configuration or ProductionReaderConfiguration()
    resolved_structured_parser = (
        structured_parser
        if structured_parser is not None
        else LazyPaddleStructuredPageParser(resolved.paddle)
    )

    resolved_fallback = fallback_ocr_engine

    if (
        resolved_fallback is None
        and resolved.enable_tesseract_fallback
    ):
        resolved_fallback = TesseractOcrEngine(
            language=resolved.tesseract_language,
            page_segmentation_mode=(
                resolved.tesseract_page_segmentation_mode
            ),
            timeout_seconds=resolved.tesseract_timeout_seconds,
        )

    pdf_reader = AdaptivePdfDocumentReader(
        structured_parser=resolved_structured_parser,
        fallback_ocr_engine=resolved_fallback,
        render_dpi=resolved.pdf_render_dpi,
    )
    image_reader = StructuredImageDocumentReader(
        resolved_structured_parser,
        fallback_ocr_engine=resolved_fallback,
    )
    text_reader = PlainTextDocumentReader()

    return RoutingDocumentReader(
        {
            "application/pdf": pdf_reader,
            "text/plain": text_reader,
            **{
                mime_type: image_reader
                for mime_type in image_reader.supported_mime_types
            },
        }
    )
