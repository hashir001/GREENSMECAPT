"""Tests for production processing configuration."""

import pytest

from greensmecapt.assessment.profiles import load_policy
from greensmecapt.document_intelligence.semantics.intelligence import (
    QualitativeValueType,
)
from greensmecapt.services.factory import (
    DocumentProcessingConfigurationError,
    _environment_boolean,
    _qualitative_instructions,
    _visual_provider_from_environment,
    production_reader_configuration_from_environment,
)


def test_parse_true_and_false_environment_values() -> None:
    assert _environment_boolean(
        {"FEATURE": "yes"},
        "FEATURE",
        default=False,
    )
    assert not _environment_boolean(
        {"FEATURE": "off"},
        "FEATURE",
        default=True,
    )


def test_reject_invalid_environment_boolean() -> None:
    with pytest.raises(DocumentProcessingConfigurationError):
        _environment_boolean(
            {"FEATURE": "perhaps"},
            "FEATURE",
            default=False,
        )


def test_visual_provider_is_optional() -> None:
    assert _visual_provider_from_environment({}) is None


def test_visual_provider_requires_complete_configuration() -> None:
    with pytest.raises(DocumentProcessingConfigurationError):
        _visual_provider_from_environment(
            {"GREENSMECAPT_VISUAL_ENDPOINT": ("http://127.0.0.1:11434/v1/chat/completions")}
        )


def test_build_governed_qualitative_instructions() -> None:
    instructions = _qualitative_instructions(
        load_policy("config/assessment_profiles.development.json")
    )

    by_id = {item.claim_id: item for item in instructions}

    assert by_id["activity_fact:operates_facility"].value_type is QualitativeValueType.BOOLEAN
    assert (
        by_id["criterion_context:green_contribution"].value_type is QualitativeValueType.SOURCE_TEXT
    )


def test_configure_google_document_ai_without_removing_local_fallback() -> None:
    configuration = production_reader_configuration_from_environment(
        {
            "GREENSMECAPT_STRUCTURED_OCR_PROVIDER": "google_document_ai",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID": "project",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_LOCATION": "eu",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROCESSOR_ID": "processor",
        }
    )

    assert configuration.google_document_ai is not None
    assert configuration.google_document_ai.processor_name == (
        "projects/project/locations/eu/processors/processor"
    )
    assert configuration.paddle is not None


def test_reject_incomplete_google_document_ai_configuration() -> None:
    with pytest.raises(
        DocumentProcessingConfigurationError,
        match="PROCESSOR_ID",
    ):
        production_reader_configuration_from_environment(
            {
                "GREENSMECAPT_STRUCTURED_OCR_PROVIDER": "google_document_ai",
                "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID": "project",
                "GREENSMECAPT_GOOGLE_DOCUMENT_AI_LOCATION": "eu",
            }
        )
