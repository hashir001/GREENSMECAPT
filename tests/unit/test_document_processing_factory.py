"""Tests for production processing configuration."""

import pytest

from greensmecapt.services.factory import (
    DocumentProcessingConfigurationError,
    _environment_boolean,
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
