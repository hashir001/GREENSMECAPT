"""Run a real structured-OCR preflight on a document image."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from greensmecapt.document_intelligence.structure.output import (
    StructuredOcrReport,
)
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleParserConfiguration,
    PaddleResourceProfile,
    PaddleStructuredPageParser,
    StructuredParsingError,
)


def _argument_parser() -> argparse.ArgumentParser:
    """Build the structured-OCR command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Read one document image using GREENSMECAPT's "
            "resource-aware PaddleOCR adapter."
        )
    )

    parser.add_argument(
        "--image",
        required=True,
        type=Path,
        help="Path to a PNG, JPEG or other supported image.",
    )
    parser.add_argument(
        "--profile",
        choices=tuple(
            profile.value
            for profile in PaddleResourceProfile
        ),
        default=PaddleResourceProfile.LOCAL_CPU.value,
        help=(
            "Resource profile. Use local_cpu on constrained "
            "machines and full_structure on provisioned workers."
        ),
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Paddle device such as cpu or gpu:0.",
    )
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=None,
        help="Optional positive CPU thread override.",
    )
    parser.add_argument(
        "--page-number",
        type=int,
        default=1,
        help="Source page number represented by the image.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help=(
            "Optional output file. JSON is printed when omitted."
        ),
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run structured OCR and emit stable project JSON."""

    arguments = _argument_parser().parse_args(argv)

    if arguments.cpu_threads is not None:
        if arguments.cpu_threads < 1:
            sys.stderr.write(
                "Structured OCR failed: CPU threads must be "
                "positive.\n"
            )
            return 2

    if arguments.page_number < 1:
        sys.stderr.write(
            "Structured OCR failed: page number must be "
            "positive.\n"
        )
        return 2

    image_path: Path = arguments.image

    if not image_path.is_file():
        sys.stderr.write(
            "Structured OCR failed: image does not exist: "
            f"{image_path}\n"
        )
        return 2

    profile = PaddleResourceProfile(arguments.profile)

    configuration = PaddleParserConfiguration.for_profile(
        profile,
        device=arguments.device,
        cpu_threads=arguments.cpu_threads,
    )

    try:
        parser = PaddleStructuredPageParser(
            configuration=configuration
        )

        with Image.open(image_path) as image:
            page = parser.parse(
                image,
                page_number=arguments.page_number,
            )

    except (
        StructuredParsingError,
        UnidentifiedImageError,
        OSError,
    ) as error:
        sys.stderr.write(
            f"Structured OCR failed: {error}\n"
        )
        return 1

    report = StructuredOcrReport.from_page(
        profile=profile,
        source_name=image_path.name,
        page=page,
    )

    json_output = report.model_dump_json(indent=2)

    output_path: Path | None = arguments.output_json

    if output_path is None:
        print(json_output)
    else:
        try:
            output_path.write_text(
                f"{json_output}\n",
                encoding="utf-8",
            )
        except OSError as error:
            sys.stderr.write(
                "Structured OCR succeeded, but JSON could not "
                f"be written: {error}\n"
            )
            return 1

        print(
            "Structured OCR succeeded: "
            f"{output_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())