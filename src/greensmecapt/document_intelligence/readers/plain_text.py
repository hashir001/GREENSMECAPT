"""Reader for born-digital UTF-8 text documents."""

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
)
from greensmecapt.domain import SourceDocument


class DocumentReadError(ValueError):
    """Raised when document content cannot be read."""


class UnsupportedMimeTypeError(DocumentReadError):
    """Raised when a reader receives an unsupported document type."""


class PlainTextDocumentReader:
    """Read one-page, born-digital UTF-8 text documents."""

    supported_mime_types = frozenset({"text/plain"})

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Decode document bytes into readable text."""

        if document.mime_type not in self.supported_mime_types:
            raise UnsupportedMimeTypeError(
                f"Unsupported MIME type: {document.mime_type}"
            )

        try:
            text = content.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise DocumentReadError(
                "Document content is not valid UTF-8 text."
            ) from error

        if not text:
            raise DocumentReadError(
                "Document does not contain readable text."
            )

        return ExtractedDocument(
            document_id=document.document_id,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text=text,
                ),
            ),
        )