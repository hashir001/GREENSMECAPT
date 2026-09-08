"""Read embedded text from PDF documents."""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
)
from greensmecapt.document_intelligence.readers.plain_text import (
    DocumentReadError,
    UnsupportedMimeTypeError,
)
from greensmecapt.domain import SourceDocument


class PdfTextDocumentReader:
    """Extract existing PDF text while preserving original page numbers."""

    supported_mime_types = frozenset({"application/pdf"})

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Read text-bearing pages from a PDF."""

        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

        try:
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported by this reader."
                )

            pages: list[ExtractedPage] = []

            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()

                if text:
                    pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            text=text,
                        )
                    )

        except (PyPdfError, ValueError, TypeError, OSError) as error:
            if isinstance(error, DocumentReadError):
                raise

            raise DocumentReadError(
                "PDF text could not be read."
            ) from error

        if not pages:
            raise DocumentReadError(
                "PDF contains no extractable text. "
                "It may be blank or require OCR."
            )

        return ExtractedDocument(
            document_id=document.document_id,
            pages=tuple(pages),
        )