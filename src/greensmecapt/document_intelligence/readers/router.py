"""Select a document reader using the registered MIME type."""

from collections.abc import Mapping

from greensmecapt.document_intelligence.models import ExtractedDocument
from greensmecapt.document_intelligence.ports import DocumentReader
from greensmecapt.document_intelligence.readers.plain_text import (
    UnsupportedMimeTypeError,
)
from greensmecapt.domain import SourceDocument


class RoutingDocumentReader:
    """Delegate reading to the configured reader for a document type."""

    def __init__(
        self,
        readers: Mapping[str, DocumentReader],
    ) -> None:
        self._readers = dict(readers)

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Select a reader and return its extracted document."""

        reader = self._readers.get(document.mime_type)

        if reader is None:
            raise UnsupportedMimeTypeError(
                f"No reader configured for MIME type: {document.mime_type}"
            )

        return reader.read(document, content)