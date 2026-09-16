"""Runtime inspection and activation for local PaddleOCR models."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.models import ExtractedPage
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleParserConfiguration,
    PaddleStructuredPageParser,
    StructuredParsingError,
)


class PaddleRuntimeReport(BaseModel):
    """Describe the local Paddle installation and initialization result."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    paddleocr_version: str = Field(min_length=1)
    paddlepaddle_version: str = Field(min_length=1)
    device: str = Field(min_length=1)
    cpu_threads: int = Field(ge=1)
    initialized: bool
    initialization_seconds: float | None = Field(default=None, ge=0)


def inspect_paddle_runtime(
    configuration: PaddleParserConfiguration | None = None,
) -> PaddleRuntimeReport:
    """Inspect installed packages without loading model weights."""

    resolved = configuration or PaddleParserConfiguration()

    return PaddleRuntimeReport(
        paddleocr_version=_installed_version("paddleocr"),
        paddlepaddle_version=_installed_version("paddlepaddle"),
        device=resolved.device,
        cpu_threads=resolved.cpu_threads,
        initialized=False,
    )


def initialize_paddle_runtime(
    configuration: PaddleParserConfiguration | None = None,
) -> tuple[PaddleStructuredPageParser, PaddleRuntimeReport]:
    """Load PaddleOCR and download/cache required models when absent."""

    resolved = configuration or PaddleParserConfiguration()
    installation = inspect_paddle_runtime(resolved)
    started_at = perf_counter()
    parser = PaddleStructuredPageParser(resolved)
    elapsed = perf_counter() - started_at

    return (
        parser,
        installation.model_copy(
            update={
                "initialized": True,
                "initialization_seconds": elapsed,
            }
        ),
    )


def parse_image_file(
    image_path: str | Path,
    *,
    page_number: int = 1,
    configuration: PaddleParserConfiguration | None = None,
) -> tuple[ExtractedPage, PaddleRuntimeReport]:
    """Run a real structured-OCR smoke test on a local image."""

    path = Path(image_path).expanduser()

    if not path.is_file():
        raise StructuredParsingError(
            f"OCR smoke-test image does not exist: {path}"
        )

    try:
        with Image.open(path) as image:
            prepared_image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise StructuredParsingError(
            "OCR smoke-test input is not a readable image."
        ) from error

    parser, report = initialize_paddle_runtime(configuration)

    return (
        parser.parse(prepared_image, page_number=page_number),
        report,
    )


def _installed_version(distribution: str) -> str:
    """Return a package version or raise a controlled installation error."""

    try:
        return version(distribution)
    except PackageNotFoundError as error:
        raise StructuredParsingError(
            f"Required OCR package is not installed: {distribution}."
        ) from error