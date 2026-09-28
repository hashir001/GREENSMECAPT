"""Structured OCR and page-routing components."""

from greensmecapt.document_intelligence.structure.google_document_ai import (
    FallbackStructuredPageParser,
    GoogleDocumentAIConfiguration,
    GoogleDocumentAIStructuredPageParser,
)
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleParserConfiguration,
    PaddleStructuredPageParser,
    StructuredParserUnavailableError,
    StructuredParsingError,
)
from greensmecapt.document_intelligence.structure.ports import (
    StructuredPageParser,
)
from greensmecapt.document_intelligence.structure.routing import (
    PageProcessingMode,
    PageRoutingDecision,
    PageRoutingPolicy,
    PageSignals,
)
from greensmecapt.document_intelligence.structure.runtime import (
    PaddleRuntimeReport,
    initialize_paddle_runtime,
    inspect_paddle_runtime,
    parse_image_file,
)

__all__ = [
    "FallbackStructuredPageParser",
    "GoogleDocumentAIConfiguration",
    "GoogleDocumentAIStructuredPageParser",
    "PaddleParserConfiguration",
    "PaddleRuntimeReport",
    "PaddleStructuredPageParser",
    "PageProcessingMode",
    "PageRoutingDecision",
    "PageRoutingPolicy",
    "PageSignals",
    "StructuredPageParser",
    "StructuredParserUnavailableError",
    "StructuredParsingError",
    "initialize_paddle_runtime",
    "inspect_paddle_runtime",
    "parse_image_file",
]
