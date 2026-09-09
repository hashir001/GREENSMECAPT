"""OCR engine used by image-based document readers."""

from typing import Protocol

import pytesseract
from PIL import Image

from greensmecapt.document_intelligence.readers.plain_text import (
    DocumentReadError,
)


class OcrError(DocumentReadError):
    """Raised when OCR cannot process an image."""


class OcrEngine(Protocol):
    """Recover text from a rendered document image."""

    def recognize(self, image: Image.Image) -> str:
        """Return text recovered from an image."""
        ...


class TesseractOcrEngine:
    """Run the locally installed Tesseract OCR engine."""

    def __init__(
        self,
        language: str = "eng",
        page_segmentation_mode: int = 6,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not language.strip():
            raise ValueError("OCR language must not be blank.")

        if page_segmentation_mode < 0:
            raise ValueError(
                "Page segmentation mode must not be negative."
            )

        if timeout_seconds <= 0:
            raise ValueError("OCR timeout must be positive.")

        self._language = language
        self._page_segmentation_mode = page_segmentation_mode
        self._timeout_seconds = timeout_seconds

    def recognize(self, image: Image.Image) -> str:
        """Recover text from one image using Tesseract."""

        try:
            return pytesseract.image_to_string(
                image,
                lang=self._language,
                config=f"--psm {self._page_segmentation_mode}",
                timeout=self._timeout_seconds,
            ).strip()
        except (
            pytesseract.TesseractNotFoundError,
            pytesseract.TesseractError,
            RuntimeError,
        ) as error:
            raise OcrError("Tesseract OCR failed.") from error