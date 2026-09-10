"""Structured OCR and page-routing components."""

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

__all__ = [
    "PaddleParserConfiguration",
    "PaddleStructuredPageParser",
    "PageProcessingMode",
    "PageRoutingDecision",
    "PageRoutingPolicy",
    "PageSignals",
    "StructuredPageParser",
    "StructuredParserUnavailableError",
    "StructuredParsingError",
]