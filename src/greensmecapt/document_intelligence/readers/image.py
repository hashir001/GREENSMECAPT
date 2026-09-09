"""Read image documents using OCR."""

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
from greensmecapt.domain import SourceDocument


class ImageDocumentReader:
    """Recover text from supported document images."""

    supported_mime_types = frozenset(
        {
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
        }
    )

    def __init__(self, ocr_engine: OcrEngine) -> None:
        self._ocr_engine = ocr_engine

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Decode an image and run OCR."""

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

        text = self._ocr_engine.recognize(prepared_image).strip()

        if not text:
            raise DocumentReadError(
                "OCR did not recover readable text from the image."
            )

        return ExtractedDocument(
            document_id=document.document_id,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text=text,
                    text_source=TextSource.OCR,
                ),
            ),
            total_pages=1,
        )