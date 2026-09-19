"""Interfaces for replaceable document-intelligence components."""

from typing import Protocol, runtime_checkable

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPageBatch,
)
from greensmecapt.domain import EvidenceItem, SourceDocument


class DocumentReader(Protocol):
    """Read text from a born-digital or scanned document."""

    def read(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> ExtractedDocument:
        """Recover readable document content."""
        ...


@runtime_checkable
class PagedDocumentReader(Protocol):
    """Read selected pages without processing the whole document."""

    def page_count(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> int:
        """Return source page count without OCR or semantic extraction."""
        ...

    def read_page_batch(
        self,
        document: SourceDocument,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> ExtractedPageBatch:
        """Read exactly the requested source pages."""
        ...


class EvidenceExtractor(Protocol):
    """Extract structured evidence from readable document content."""

    def extract(
        self,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> tuple[EvidenceItem, ...]:
        """Return evidence recovered from a document."""
        ...
