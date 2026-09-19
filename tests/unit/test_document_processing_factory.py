"""Tests for production processing configuration."""

import pytest

from greensmecapt.services.factory import (
    DocumentProcessingConfigurationError,
    _environment_boolean,
    _visual_provider_from_environment,
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
            {
                "GREENSMECAPT_VISUAL_ENDPOINT": (
                    "http://127.0.0.1:11434/v1/chat/completions"
                )
            }
        )
