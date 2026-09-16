"""Tests for PaddleOCR resource-profile configuration."""

import pytest
from pydantic import ValidationError

from greensmecapt.document_intelligence.structure.paddle import (
    PaddleParserConfiguration,
    PaddleResourceProfile,
)


def test_default_configuration_is_safe_for_local_cpu() -> None:
    """Default construction must not load the heavy table stack."""

    configuration = PaddleParserConfiguration()

    assert (
        configuration.profile
        is PaddleResourceProfile.LOCAL_CPU
    )
    assert (
        configuration.layout_detection_model_name
        == "PP-DocLayout-S"
    )
    assert (
        configuration.text_detection_model_name
        == "PP-OCRv5_mobile_det"
    )
    assert configuration.use_table_recognition is False
    assert configuration.use_region_detection is False
    assert configuration.enable_mkldnn is False
    assert configuration.cpu_threads == 2


def test_create_local_cpu_profile() -> None:
    """The explicit local profile should use efficient models."""

    configuration = (
        PaddleParserConfiguration.for_profile(
            PaddleResourceProfile.LOCAL_CPU,
            cpu_threads=3,
        )
    )

    assert configuration.cpu_threads == 3
    assert (
        configuration.text_recognition_model_name
        == "en_PP-OCRv4_mobile_rec"
    )
    assert configuration.use_document_unwarping is False
    assert configuration.use_table_recognition is False


def test_create_full_structure_profile() -> None:
    """The full profile should retain table understanding."""

    configuration = (
        PaddleParserConfiguration.for_profile(
            PaddleResourceProfile.FULL_STRUCTURE,
        )
    )

    assert (
        configuration.profile
        is PaddleResourceProfile.FULL_STRUCTURE
    )
    assert (
        configuration.layout_detection_model_name
        == "PP-DocLayout_plus-L"
    )
    assert configuration.use_region_detection is True
    assert (
        configuration.use_orientation_classification
        is True
    )
    assert configuration.use_document_unwarping is True
    assert configuration.use_table_recognition is True


def test_reject_unknown_resource_profile() -> None:
    """Unknown deployment profiles must fail explicitly."""

    with pytest.raises(ValueError):
        PaddleParserConfiguration.for_profile(
            "imaginary_profile"
        )


def test_reject_invalid_cpu_thread_count() -> None:
    """The configuration must reject unusable thread counts."""

    with pytest.raises(ValidationError):
        PaddleParserConfiguration.for_profile(
            PaddleResourceProfile.LOCAL_CPU,
            cpu_threads=0,
        )