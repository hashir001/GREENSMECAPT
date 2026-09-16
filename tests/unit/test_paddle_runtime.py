"""Tests for PaddleOCR runtime inspection."""

from importlib.metadata import PackageNotFoundError

import pytest

from greensmecapt.document_intelligence.structure import (
    PaddleParserConfiguration,
    StructuredParsingError,
    runtime,
)


def test_inspect_installed_runtime_without_loading_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspection should report versions without constructing Paddle."""

    versions = {
        "paddleocr": "3.2.0",
        "paddlepaddle": "3.1.1",
    }
    monkeypatch.setattr(
        runtime,
        "version",
        lambda distribution: versions[distribution],
    )

    report = runtime.inspect_paddle_runtime(
        PaddleParserConfiguration(cpu_threads=4)
    )

    assert report.paddleocr_version == "3.2.0"
    assert report.paddlepaddle_version == "3.1.1"
    assert report.cpu_threads == 4
    assert not report.initialized
    assert report.initialization_seconds is None


def test_report_missing_runtime_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing optional packages should produce a controlled error."""

    def missing(distribution: str) -> str:
        raise PackageNotFoundError(distribution)

    monkeypatch.setattr(runtime, "version", missing)

    with pytest.raises(
        StructuredParsingError,
        match="Required OCR package is not installed",
    ):
        runtime.inspect_paddle_runtime()


def test_reject_missing_smoke_test_image() -> None:
    """A typo in a smoke-test path should fail before model loading."""

    with pytest.raises(
        StructuredParsingError,
        match="does not exist",
    ):
        runtime.parse_image_file(
            "/definitely/missing/ocr-image.png"
        )