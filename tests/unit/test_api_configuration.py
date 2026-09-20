"""Tests for safe API deployment configuration."""

import pytest

from greensmecapt.api.configuration import (
    cors_origins_from_environment,
)


def test_parse_unique_explicit_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GREENSMECAPT_CORS_ORIGINS",
        (
            "https://app.example.com/, "
            "https://review.example.com,"
            "https://app.example.com"
        ),
    )

    assert cors_origins_from_environment() == (
        "https://app.example.com",
        "https://review.example.com",
    )


@pytest.mark.parametrize(
    "origin",
    (
        "*",
        "javascript:alert(1)",
        "https://app.example.com/path",
    ),
)
def test_reject_unsafe_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
) -> None:
    monkeypatch.setenv(
        "GREENSMECAPT_CORS_ORIGINS",
        origin,
    )

    with pytest.raises(ValueError):
        cors_origins_from_environment()
