"""Select a document reader using the registered MIME type."""

from collections.abc import Mapping

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedPageBatch,
    ExtractedVisualRegion,
)
from greensmecapt.document_intelligence.ports import (
    DocumentReader,
    PagedDocumentReader,
    VisualRegionRenderer,
)
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

        reader = self._reader_for(document)

        return reader.read(document, content)

    def page_count(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> int:
        """Return page count through the selected reader."""

        reader = self._reader_for(document)

        if isinstance(reader, PagedDocumentReader):
            return reader.page_count(document, content)

        extracted = reader.read(document, content)
        return extracted.total_pages or len(extracted.pages)

    def read_page_batch(
        self,
        document: SourceDocument,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> ExtractedPageBatch:
        """Read selected pages or adapt a non-paged one-page reader."""

        reader = self._reader_for(document)

        if isinstance(reader, PagedDocumentReader):
            return reader.read_page_batch(
                document,
                content,
                page_numbers,
            )

        extracted = reader.read(document, content)
        total_pages = extracted.total_pages or len(extracted.pages)
        requested = tuple(sorted(set(page_numbers)))
        readable = tuple(
            page
            for page in extracted.pages
            if page.page_number in requested
        )
        unreadable = tuple(
            page_number
            for page_number in requested
            if page_number not in {
                page.page_number for page in readable
            }
        )

        return ExtractedPageBatch(
            document_id=document.document_id,
            total_pages=total_pages,
            requested_pages=requested,
            pages=readable,
            unreadable_pages=unreadable,
        )

    def _reader_for(
        self,
        document: SourceDocument,
    ) -> DocumentReader:
        """Resolve a registered reader or raise a controlled error."""

        reader = self._readers.get(document.mime_type)

        if reader is None:
            raise UnsupportedMimeTypeError(
                f"No reader configured for MIME type: {document.mime_type}"
            )

        return reader

    def render_visual_region(
        self,
        document: SourceDocument,
        content: bytes,
        page: ExtractedPage,
        region: ExtractedVisualRegion,
    ) -> bytes:
        """Delegate exact-region rendering to a capable reader."""

        reader = self._reader_for(document)

        if not isinstance(reader, VisualRegionRenderer):
            raise UnsupportedMimeTypeError(
                "The selected reader cannot render visual regions."
            )

        return reader.render_visual_region(
            document,
            content,
            page,
            region,
        )
