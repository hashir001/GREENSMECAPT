"""Tests for page-processing route selection."""

from greensmecapt.document_intelligence.structure import (
    PageProcessingMode,
    PageRoutingPolicy,
    PageSignals,
)


def test_use_native_processing_for_clean_digital_page() -> None:
    """Clean embedded text should remain on the native path."""

    decision = PageRoutingPolicy().decide(
        PageSignals(
            embedded_character_count=500,
            native_table_count=1,
            image_coverage=0.02,
        )
    )

    assert decision.mode is PageProcessingMode.NATIVE


def test_use_structured_ocr_when_text_is_missing() -> None:
    """A scanned page should use structured OCR."""

    decision = PageRoutingPolicy().decide(
        PageSignals(
            embedded_character_count=0,
            image_coverage=1.0,
        )
    )

    assert (
        decision.mode
        is PageProcessingMode.STRUCTURED_OCR
    )


def test_use_hybrid_when_expected_table_is_missing() -> None:
    """A missing native table should trigger visual parsing."""

    decision = PageRoutingPolicy().decide(
        PageSignals(
            embedded_character_count=800,
            native_table_count=0,
            image_coverage=0.05,
            expected_tables=True,
        )
    )

    assert decision.mode is PageProcessingMode.HYBRID


def test_use_hybrid_for_substantial_page_images() -> None:
    """Image content should not be ignored because text exists."""

    decision = PageRoutingPolicy().decide(
        PageSignals(
            embedded_character_count=300,
            native_table_count=0,
            image_coverage=0.4,
        )
    )

    assert decision.mode is PageProcessingMode.HYBRID


def test_escalate_after_structured_parsing_failure() -> None:
    """Failed structured parsing should become reviewable."""

    decision = (
        PageRoutingPolicy().after_structured_failure(
            reason="The scan is unreadable.",
        )
    )

    assert (
        decision.mode
        is PageProcessingMode.REVIEW_REQUIRED
    )
    assert decision.reasons == (
        "The scan is unreadable.",
    )