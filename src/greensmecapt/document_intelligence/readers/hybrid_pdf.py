"""Read PDF pages using embedded text with OCR fallback."""

from io import BytesIO

import pymupdf
from PIL import Image

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


class HybridPdfDocumentReader:
    """Use embedded PDF text and OCR pages that need it."""

    supported_mime_types = frozenset({"application/pdf"})

    def __init__(
        self,
        ocr_engine: OcrEngine,
        *,
        minimum_embedded_characters: int = 20,
        render_dpi: int = 200,
    ) -> None:
        if minimum_embedded_characters < 1:
            raise ValueError(
                "Minimum embedded characters must be positive."
            )

        if render_dpi < 72:
            raise ValueError("PDF render DPI must be at least 72.")

        self._ocr_engine = ocr_engine
        self._minimum_embedded_characters = (
            minimum_embedded_characters
        )
        self._render_dpi = render_dpi

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Extract embedded text or OCR each page independently."""

        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

        try:
            pdf = pymupdf.open(
                stream=content,
                filetype="pdf",
            )
        except (
            pymupdf.FileDataError,
            RuntimeError,
            ValueError,
            OSError,
        ) as error:
            raise DocumentReadError(
                "PDF content could not be opened."
            ) from error

        try:
            if pdf.needs_pass:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported."
                )

            extracted_pages: list[ExtractedPage] = []
            unreadable_pages: list[int] = []

            for page_index in range(pdf.page_count):
                page_number = page_index + 1
                page = pdf.load_page(page_index)
                embedded_text = page.get_text("text").strip()

                significant_character_count = len(
                    "".join(embedded_text.split())
                )

                if (
                    significant_character_count
                    >= self._minimum_embedded_characters
                ):
                    extracted_pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            text=embedded_text,
                            text_source=TextSource.PDF_EMBEDDED,
                        )
                    )
                    continue

                pixmap = page.get_pixmap(
                    dpi=self._render_dpi,
                    alpha=False,
                )

                with Image.open(
                    BytesIO(pixmap.tobytes("png"))
                ) as image:
                    prepared_image = image.convert("RGB")

                ocr_text = self._ocr_engine.recognize(
                    prepared_image
                ).strip()

                if ocr_text:
                    extracted_pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            text=ocr_text,
                            text_source=TextSource.OCR,
                        )
                    )
                else:
                    unreadable_pages.append(page_number)

            if not extracted_pages:
                raise DocumentReadError(
                    "Neither embedded-text extraction nor OCR "
                    "recovered readable PDF text."
                )

            return ExtractedDocument(
                document_id=document.document_id,
                pages=tuple(extracted_pages),
                total_pages=pdf.page_count,
                unreadable_pages=tuple(unreadable_pages),
            )
        except DocumentReadError:
            raise
        except (
            RuntimeError,
            ValueError,
            OSError,
        ) as error:
            raise DocumentReadError(
                "PDF page processing failed."
            ) from error
        finally:
            pdf.close()