"""Choose native or structured OCR processing for document pages."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PageProcessingMode(StrEnum):
    """Describe how one document page should be processed."""

    NATIVE = "native"
    STRUCTURED_OCR = "structured_ocr"
    HYBRID = "hybrid"
    REVIEW_REQUIRED = "review_required"


class PageSignals(BaseModel):
    """Record observable signals used to route one page."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    embedded_character_count: int = Field(ge=0)
    native_table_count: int = Field(default=0, ge=0)
    image_coverage: float = Field(default=0, ge=0, le=1)

    expected_tables: bool = False
    suspicious_reading_order: bool = False
    native_extraction_failed: bool = False


class PageRoutingDecision(BaseModel):
    """Explain a page-processing decision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    mode: PageProcessingMode
    reasons: tuple[str, ...] = Field(min_length=1)


class PageRoutingPolicy(BaseModel):
    """Configure deterministic page-routing decisions."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    minimum_embedded_characters: int = Field(
        default=40,
        ge=1,
    )
    partial_image_coverage: float = Field(
        default=0.15,
        ge=0,
        le=1,
    )
    dominant_image_coverage: float = Field(
        default=0.65,
        ge=0,
        le=1,
    )

    def decide(
        self,
        signals: PageSignals,
    ) -> PageRoutingDecision:
        """Choose an initial processing mode for one page."""

        if signals.native_extraction_failed:
            return PageRoutingDecision(
                mode=PageProcessingMode.STRUCTURED_OCR,
                reasons=(
                    "Native page extraction failed.",
                ),
            )

        if (
            signals.embedded_character_count
            < self.minimum_embedded_characters
        ):
            return PageRoutingDecision(
                mode=PageProcessingMode.STRUCTURED_OCR,
                reasons=(
                    "The page does not contain enough embedded "
                    "text for reliable native extraction.",
                ),
            )

        reasons: list[str] = []

        if signals.suspicious_reading_order:
            reasons.append(
                "Native text has suspicious reading order."
            )

        if (
            signals.expected_tables
            and signals.native_table_count == 0
        ):
            reasons.append(
                "A table is expected but native extraction "
                "found none."
            )

        if (
            signals.image_coverage
            >= self.dominant_image_coverage
        ):
            reasons.append(
                "Images occupy most of the page."
            )
        elif (
            signals.image_coverage
            >= self.partial_image_coverage
        ):
            reasons.append(
                "The page contains substantial image content."
            )

        if reasons:
            return PageRoutingDecision(
                mode=PageProcessingMode.HYBRID,
                reasons=tuple(reasons),
            )

        return PageRoutingDecision(
            mode=PageProcessingMode.NATIVE,
            reasons=(
                "Native extraction provides sufficient "
                "structured content.",
            ),
        )

    def after_structured_failure(
        self,
        *,
        reason: str,
    ) -> PageRoutingDecision:
        """Escalate a page after structured parsing fails."""

        clean_reason = reason.strip()

        if not clean_reason:
            clean_reason = (
                "Structured document parsing failed."
            )

        return PageRoutingDecision(
            mode=PageProcessingMode.REVIEW_REQUIRED,
            reasons=(clean_reason,),
        )