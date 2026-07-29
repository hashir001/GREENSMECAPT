"""Intermediate models produced while reading SME documents."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedPage(BaseModel):
    """Represent text recovered from one document page."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    page_number: int = Field(ge=1)
    text: str = Field(min_length=1)


class ExtractedDocument(BaseModel):
    """Represent readable content recovered from a source document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document_id: str = Field(min_length=1)
    pages: tuple[ExtractedPage, ...] = Field(min_length=1)