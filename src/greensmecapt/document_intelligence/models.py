"""Intermediate models produced while reading SME documents."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TextSource(StrEnum):
    """Describe how readable page text was recovered."""

    UNKNOWN = "unknown"
    PLAIN_TEXT = "plain_text"
    PDF_EMBEDDED = "pdf_embedded"
    OCR = "ocr"


class ExtractedPage(BaseModel):
    """Represent text recovered from one document page."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    page_number: int = Field(ge=1)
    text: str = Field(min_length=1)
    text_source: TextSource = TextSource.UNKNOWN


class ExtractedDocument(BaseModel):
    """Represent readable content recovered from a source document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document_id: str = Field(min_length=1)
    pages: tuple[ExtractedPage, ...] = Field(min_length=1)
    total_pages: int | None = Field(default=None, ge=1)
    unreadable_pages: tuple[int, ...] = ()

    @model_validator(mode="after")
    def validate_page_coverage(self) -> Self:
        """Keep extracted and unreadable page references consistent."""

        extracted_numbers = [
            page.page_number for page in self.pages
        ]

        if len(extracted_numbers) != len(set(extracted_numbers)):
            raise ValueError("Extracted page numbers must be unique.")

        if len(self.unreadable_pages) != len(set(self.unreadable_pages)):
            raise ValueError("Unreadable page numbers must be unique.")

        if set(extracted_numbers) & set(self.unreadable_pages):
            raise ValueError(
                "A page cannot be both extracted and unreadable."
            )

        all_page_numbers = [
            *extracted_numbers,
            *self.unreadable_pages,
        ]

        if self.total_pages is not None and any(
            page_number > self.total_pages
            for page_number in all_page_numbers
        ):
            raise ValueError(
                "Page numbers must not exceed the document page count."
            )

        return self