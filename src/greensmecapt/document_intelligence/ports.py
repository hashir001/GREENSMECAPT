"""Interfaces for replaceable document-intelligence components."""

from typing import Protocol

from greensmecapt.document_intelligence.models import ExtractedDocument
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


class EvidenceExtractor(Protocol):
    """Extract structured evidence from readable document content."""

    def extract(
        self,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> tuple[EvidenceItem, ...]:
        """Return evidence recovered from a document."""
        ...