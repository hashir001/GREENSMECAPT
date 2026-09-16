"""Stable JSON output for structured document-image parsing."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.models import (
    ExtractedPage,
)
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleResourceProfile,
)


class StructuredOcrReport(BaseModel):
    """Describe one successful structured-OCR operation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    status: Literal["ready"] = "ready"
    profile: PaddleResourceProfile
    source_name: str = Field(min_length=1)
    text_block_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    page: ExtractedPage

    @classmethod
    def from_page(
        cls,
        *,
        profile: PaddleResourceProfile,
        source_name: str,
        page: ExtractedPage,
    ) -> "StructuredOcrReport":
        """Build a concise report from project-owned models."""

        return cls(
            profile=profile,
            source_name=source_name,
            text_block_count=len(page.text_blocks),
            table_count=len(page.tables),
            page=page,
        )