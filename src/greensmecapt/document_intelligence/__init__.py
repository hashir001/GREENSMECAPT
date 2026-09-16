"""Document-intelligence components for GREENSMECAPT."""

from greensmecapt.document_intelligence.extractors import (
    RenewableEnergyPercentageExtractor,
)
from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    TextSource,
)
from greensmecapt.document_intelligence.ports import (
    DocumentReader,
    EvidenceExtractor,
)
from greensmecapt.document_intelligence.readers import (
    DocumentReadError,
    HybridPdfDocumentReader,
    ImageDocumentReader,
    OcrEngine,
    OcrError,
    PdfTextDocumentReader,
    PlainTextDocumentReader,
    ProductionReaderConfiguration,
    RoutingDocumentReader,
    StructuredImageDocumentReader,
    TesseractOcrEngine,
    UnsupportedMimeTypeError,
    build_production_document_reader,
)
from greensmecapt.document_intelligence.service import (
    DocumentIntegrityError,
    DocumentIntelligenceService,
    ExtractionConsistencyError,
)

__all__ = [
    "DocumentIntegrityError",
    "DocumentIntelligenceService",
    "DocumentReadError",
    "DocumentReader",
    "EvidenceExtractor",
    "ExtractedDocument",
    "ExtractedPage",
    "ExtractionConsistencyError",
    "HybridPdfDocumentReader",
    "ImageDocumentReader",
    "OcrEngine",
    "OcrError",
    "PdfTextDocumentReader",
    "PlainTextDocumentReader",
    "ProductionReaderConfiguration",
    "RenewableEnergyPercentageExtractor",
    "RoutingDocumentReader",
    "StructuredImageDocumentReader",
    "TesseractOcrEngine",
    "TextSource",
    "UnsupportedMimeTypeError",
    "build_production_document_reader",
]