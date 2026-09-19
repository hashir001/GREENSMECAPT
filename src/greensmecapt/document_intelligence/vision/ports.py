"""Replaceable multimodal provider boundary."""

from typing import Protocol

from greensmecapt.document_intelligence.vision.models import (
    VisualInterpretationRequest,
    VisualProviderOutput,
)


class VisualProviderError(RuntimeError):
    """Raised when a multimodal provider cannot return valid output."""


class VisualSemanticProvider(Protocol):
    """Interpret one exact crop using only configured metric definitions."""

    provider_name: str
    provider_version: str
    model_name: str

    def interpret(
        self,
        request: VisualInterpretationRequest,
    ) -> VisualProviderOutput:
        """Return structured claims grounded in the supplied crop."""
        ...
