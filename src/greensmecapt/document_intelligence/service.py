"""Application service coordinating document-intelligence components."""

from hashlib import sha256

from greensmecapt.document_intelligence.ports import (
    DocumentReader,
    EvidenceExtractor,
)
from greensmecapt.domain import EvidenceItem, SourceDocument


class DocumentIntegrityError(ValueError):
    """Raised when document bytes do not match their registered fingerprint."""


class ExtractionConsistencyError(ValueError):
    """Raised when extraction output references inconsistent records."""


class DocumentIntelligenceService:
    """Coordinate document reading and evidence extraction."""

    def __init__(
        self,
        reader: DocumentReader,
        evidence_extractor: EvidenceExtractor,
    ) -> None:
        self._reader = reader
        self._evidence_extractor = evidence_extractor

    def process(
        self,
        document: SourceDocument,
        content: bytes,
    ) -> tuple[EvidenceItem, ...]:
        """Verify, read and extract evidence from one document."""

        if not content:
            raise DocumentIntegrityError(
                "Document content must not be empty."
            )

        actual_sha256 = sha256(content).hexdigest()

        if actual_sha256 != document.sha256:
            raise DocumentIntegrityError(
                "Document content does not match its registered SHA-256."
            )

        extracted_document = self._reader.read(document, content)

        if extracted_document.document_id != document.document_id:
            raise ExtractionConsistencyError(
                "Reader output references a different document."
            )

        evidence_items = self._evidence_extractor.extract(
            document,
            extracted_document,
        )

        for evidence in evidence_items:
            if evidence.document_id != document.document_id:
                raise ExtractionConsistencyError(
                    "Extracted evidence references a different document."
                )

            if evidence.sme_id != document.sme_id:
                raise ExtractionConsistencyError(
                    "Extracted evidence references a different SME."
                )

        return evidence_items