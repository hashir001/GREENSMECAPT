"""Read standalone images using structured OCR."""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    TextSource,
)
from greensmecapt.document_intelligence.readers.ocr import OcrEngine
from greensmecapt.document_intelligence.readers.plain_text import (
    DocumentReadError,
    UnsupportedMimeTypeError,
)
from greensmecapt.document_intelligence.structure import (
    StructuredPageParser,
    StructuredParsingError,
)
from greensmecapt.domain import SourceDocument


class StructuredImageDocumentReader:
    """Recover text, layout and tables from one image document."""

    supported_mime_types = frozenset(
        {
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
        }
    )

    def __init__(
        self,
        structured_parser: StructuredPageParser,
        *,
        fallback_ocr_engine: OcrEngine | None = None,
    ) -> None:
        self._structured_parser = structured_parser
        self._fallback_ocr_engine = fallback_ocr_engine

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Decode an image and preserve structured OCR output."""

        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

        try:
            with Image.open(BytesIO(content)) as image:
                prepared_image = image.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise DocumentReadError(
                "Document content is not a readable image."
            ) from error

        try:
            page = self._structured_parser.parse(
                prepared_image,
                page_number=1,
            )
        except StructuredParsingError as structured_error:
            page = self._fallback_page(prepared_image)

            if page is None:
                raise DocumentReadError(
                    "Structured OCR could not read the image."
                ) from structured_error

        if page.page_number != 1:
            raise DocumentReadError(
                "Structured OCR returned an invalid image page number."
            )

        return ExtractedDocument(
            document_id=document.document_id,
            pages=(page,),
            total_pages=1,
        )

    def _fallback_page(
        self,
        image: Image.Image,
    ) -> ExtractedPage | None:
        """Attempt plain OCR when structured parsing fails."""

        if self._fallback_ocr_engine is None:
            return None

        try:
            text = self._fallback_ocr_engine.recognize(image).strip()
        except DocumentReadError:
            return None

        if not text:
            return None

        return ExtractedPage(
            page_number=1,
            text=text,
            text_source=TextSource.OCR,
            page_width=float(image.width),
            page_height=float(image.height),
        )