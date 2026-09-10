"""Interfaces for structured document-page parsing."""

from typing import Protocol

from PIL.Image import Image

from greensmecapt.document_intelligence.models import (
    ExtractedPage,
)


class StructuredPageParser(Protocol):
    """Recover text, layout and tables from a page image."""

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        """Return a structured representation of one page."""
        ...