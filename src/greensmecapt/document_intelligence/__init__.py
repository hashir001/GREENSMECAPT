"""Document-intelligence components for GREENSMECAPT."""

from greensmecapt.document_intelligence.extractors import (
    RenewableEnergyPercentageExtractor,
)
from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedPageBatch,
    ExtractedVisualRegion,
    TextSource,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.orchestration import (
    DocumentExecutionMode,
    DocumentProcessingManifest,
    DocumentProcessingPlanner,
    LongDocumentPolicy,
    PageContentKind,
    ProcessingCapability,
)
from greensmecapt.document_intelligence.ports import (
    DocumentReader,
    EvidenceExtractor,
    PagedDocumentReader,
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
    "DocumentExecutionMode",
    "DocumentProcessingManifest",
    "DocumentProcessingPlanner",
    "DocumentReadError",
    "DocumentReader",
    "EvidenceExtractor",
    "ExtractedDocument",
    "ExtractedPage",
    "ExtractedPageBatch",
    "ExtractedVisualRegion",
    "ExtractionConsistencyError",
    "HybridPdfDocumentReader",
    "ImageDocumentReader",
    "LongDocumentPolicy",
    "OcrEngine",
    "OcrError",
    "PageContentKind",
    "PagedDocumentReader",
    "PdfTextDocumentReader",
    "PlainTextDocumentReader",
    "ProductionReaderConfiguration",
    "ProcessingCapability",
    "RenewableEnergyPercentageExtractor",
    "RoutingDocumentReader",
    "StructuredImageDocumentReader",
    "TesseractOcrEngine",
    "TextSource",
    "UnsupportedMimeTypeError",
    "VisualRegionKind",
    "build_production_document_reader",
]
