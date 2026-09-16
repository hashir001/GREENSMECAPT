"""PaddleOCR-backed structured page parsing."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from typing import Any

import numpy as np
from PIL.Image import Image
from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedPage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    TextBlockKind,
    TextSource,
)


class StructuredParsingError(ValueError):
    """Raised when structured page parsing fails."""


class StructuredParserUnavailableError(
    StructuredParsingError
):
    """Raised when the configured parser cannot be loaded."""


class PaddleResourceProfile(StrEnum):
    """Describe a supported structured-OCR resource profile."""

    LOCAL_CPU = "local_cpu"
    FULL_STRUCTURE = "full_structure"


class PaddleParserConfiguration(BaseModel):
    """Configure resource-aware PaddleOCR structured inference."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    profile: PaddleResourceProfile = (
        PaddleResourceProfile.LOCAL_CPU
    )

    device: str = Field(default="cpu", min_length=1)
    cpu_threads: int = Field(default=2, ge=1, le=64)
    enable_mkldnn: bool = False

    layout_detection_model_name: str = Field(
        default="PP-DocLayout-S",
        min_length=1,
    )
    text_detection_model_name: str = Field(
        default="PP-OCRv5_mobile_det",
        min_length=1,
    )
    text_recognition_model_name: str = Field(
        default="en_PP-OCRv4_mobile_rec",
        min_length=1,
    )

    use_region_detection: bool = False
    use_orientation_classification: bool = False
    use_document_unwarping: bool = False
    use_textline_orientation: bool = False
    use_table_recognition: bool = False
    use_formula_recognition: bool = False
    use_chart_recognition: bool = False

    text_recognition_threshold: float = Field(
        default=0.5,
        ge=0,
        le=1,
    )

    @classmethod
    def for_profile(
        cls,
        profile: PaddleResourceProfile | str,
        *,
        device: str = "cpu",
        cpu_threads: int | None = None,
    ) -> "PaddleParserConfiguration":
        """Create a safe configuration for a named profile."""

        selected_profile = PaddleResourceProfile(profile)

        if selected_profile is PaddleResourceProfile.LOCAL_CPU:
            return cls(
                profile=selected_profile,
                device=device,
                cpu_threads=(
                    2 if cpu_threads is None else cpu_threads
                ),
                enable_mkldnn=False,
                layout_detection_model_name="PP-DocLayout-S",
                text_detection_model_name=(
                    "PP-OCRv5_mobile_det"
                ),
                text_recognition_model_name=(
                    "en_PP-OCRv4_mobile_rec"
                ),
                use_region_detection=False,
                use_orientation_classification=False,
                use_document_unwarping=False,
                use_textline_orientation=False,
                use_table_recognition=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
            )

        return cls(
            profile=selected_profile,
            device=device,
            cpu_threads=(
                4 if cpu_threads is None else cpu_threads
            ),
            enable_mkldnn=False,
            layout_detection_model_name=(
                "PP-DocLayout_plus-L"
            ),
            text_detection_model_name=(
                "PP-OCRv5_server_det"
            ),
            text_recognition_model_name=(
                "PP-OCRv5_server_rec"
            ),
            use_region_detection=True,
            use_orientation_classification=True,
            use_document_unwarping=True,
            use_textline_orientation=True,
            use_table_recognition=True,
            use_formula_recognition=False,
            use_chart_recognition=False,
        )

@dataclass(frozen=True)
class _HTMLCell:
    """Temporarily store one cell parsed from table HTML."""

    text: str
    is_header: bool
    row_span: int
    column_span: int


class _TableHTMLParser(HTMLParser):
    """Recover table rows and cell spans from Paddle HTML."""

    def __init__(self) -> None:
        super().__init__()

        self.rows: list[list[_HTMLCell]] = []
        self._current_row: list[_HTMLCell] | None = None
        self._current_text: list[str] | None = None

        self._current_is_header = False
        self._current_row_span = 1
        self._current_column_span = 1

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Begin rows and cells while retaining span attributes."""

        normalized_tag = tag.lower()

        if normalized_tag == "tr":
            self._current_row = []
            return

        if normalized_tag not in {"td", "th"}:
            return

        if self._current_row is None:
            self._current_row = []

        attributes = dict(attrs)

        self._current_text = []
        self._current_is_header = normalized_tag == "th"
        self._current_row_span = _positive_integer(
            attributes.get("rowspan")
        )
        self._current_column_span = _positive_integer(
            attributes.get("colspan")
        )

    def handle_data(self, data: str) -> None:
        """Collect text inside the current table cell."""

        if self._current_text is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Finish cells and rows."""

        normalized_tag = tag.lower()

        if (
            normalized_tag in {"td", "th"}
            and self._current_text is not None
        ):
            if self._current_row is None:
                self._current_row = []

            text = " ".join(
                "".join(self._current_text).split()
            )

            self._current_row.append(
                _HTMLCell(
                    text=text,
                    is_header=self._current_is_header,
                    row_span=self._current_row_span,
                    column_span=self._current_column_span,
                )
            )

            self._current_text = None
            return

        if (
            normalized_tag == "tr"
            and self._current_row is not None
        ):
            self.rows.append(self._current_row)
            self._current_row = None


class PaddleStructuredPageParser:
    """Convert PaddleOCR structure results into project models."""

    def __init__(
        self,
        configuration: PaddleParserConfiguration | None = None,
        *,
        pipeline: object | None = None,
    ) -> None:
        self._configuration = (
            configuration or PaddleParserConfiguration()
        )
        self._pipeline = (
            pipeline
            if pipeline is not None
            else self._create_pipeline()
        )

    @property
    def configuration(self) -> PaddleParserConfiguration:
        """Expose immutable runtime configuration."""

        return self._configuration

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        """Recover text blocks and tables from one page image."""

        if page_number < 1:
            raise StructuredParsingError(
                "Page number must be positive."
            )

        prepared_image = image.convert("RGB")

        try:
            predictions = self._pipeline.predict(
                input=np.asarray(prepared_image),
                use_doc_orientation_classify=(
                    self._configuration
                    .use_orientation_classification
                ),
                use_doc_unwarping=(
                    self._configuration
                    .use_document_unwarping
                ),
                use_textline_orientation=(
                    self._configuration
                    .use_textline_orientation
                ),
                use_table_recognition=(
                    self._configuration
                    .use_table_recognition
                ),
                use_formula_recognition=(
                    self._configuration
                    .use_formula_recognition
                ),
                use_chart_recognition=(
                    self._configuration
                    .use_chart_recognition
                ),
                text_rec_score_thresh=(
                    self._configuration
                    .text_recognition_threshold
                ),
            )

            results = list(predictions)
        except Exception as error:
            raise StructuredParsingError(
                "PaddleOCR page prediction failed."
            ) from error

        if len(results) != 1:
            raise StructuredParsingError(
                "A page prediction must return exactly one result."
            )

        payload = _result_payload(results[0])

        width = _positive_dimension(
            payload.get("width"),
            fallback=prepared_image.width,
        )
        height = _positive_dimension(
            payload.get("height"),
            fallback=prepared_image.height,
        )

        raw_parsing_results = _mapping_sequence(
            payload.get("parsing_res_list")
        )
        raw_table_results = _mapping_sequence(
            payload.get("table_res_list")
        )

        text_blocks = _convert_text_blocks(
            raw_parsing_results=raw_parsing_results,
            page_number=page_number,
        )

        tables = _convert_tables(
            raw_table_results=raw_table_results,
            raw_parsing_results=raw_parsing_results,
            page_number=page_number,
            page_width=width,
            page_height=height,
        )

        text = _compose_page_text(
            text_blocks=text_blocks,
            tables=tables,
            payload=payload,
        )

        if not text:
            raise StructuredParsingError(
                "Structured OCR recovered no readable content."
            )

        return ExtractedPage(
            page_number=page_number,
            text=text,
            text_source=TextSource.OCR,
            page_width=width,
            page_height=height,
            text_blocks=text_blocks,
            tables=tables,
        )

    def _create_pipeline(self) -> object:
        """Create Paddle lazily using the selected resource profile."""

        try:
            from paddleocr import PPStructureV3
        except ImportError as error:
            raise StructuredParserUnavailableError(
                "PaddleOCR is not installed. Install the "
                "'document-ai' project option."
            ) from error

        try:
            return PPStructureV3(
                device=self._configuration.device,
                cpu_threads=self._configuration.cpu_threads,
                enable_mkldnn=(
                    self._configuration.enable_mkldnn
                ),
                layout_detection_model_name=(
                    self._configuration
                    .layout_detection_model_name
                ),
                text_detection_model_name=(
                    self._configuration
                    .text_detection_model_name
                ),
                text_recognition_model_name=(
                    self._configuration
                    .text_recognition_model_name
                ),
                use_region_detection=(
                    self._configuration
                    .use_region_detection
                ),
                use_doc_orientation_classify=(
                    self._configuration
                    .use_orientation_classification
                ),
                use_doc_unwarping=(
                    self._configuration
                    .use_document_unwarping
                ),
                use_textline_orientation=(
                    self._configuration
                    .use_textline_orientation
                ),
                use_table_recognition=(
                    self._configuration
                    .use_table_recognition
                ),
                use_formula_recognition=(
                    self._configuration
                    .use_formula_recognition
                ),
                use_chart_recognition=(
                    self._configuration
                    .use_chart_recognition
                ),
                text_rec_score_thresh=(
                    self._configuration
                    .text_recognition_threshold
                ),
                enable_hpi=False,
                precision="fp32",
            )
        except Exception as error:
            raise StructuredParserUnavailableError(
                "PaddleOCR could not initialize the "
                f"{self._configuration.profile.value!r} "
                "structured-document profile."
            ) from error


def _result_payload(result: object) -> Mapping[str, Any]:
    """Read a Paddle Result object's JSON payload."""

    raw_payload = getattr(result, "json", None)

    if callable(raw_payload):
        raw_payload = raw_payload()

    if not isinstance(raw_payload, Mapping):
        raise StructuredParsingError(
            "PaddleOCR result does not expose JSON output."
        )

    nested_result = raw_payload.get("res")

    if isinstance(nested_result, Mapping):
        return nested_result

    return raw_payload


def _convert_text_blocks(
    *,
    raw_parsing_results: Sequence[Mapping[str, Any]],
    page_number: int,
) -> tuple[ExtractedTextBlock, ...]:
    """Convert Paddle layout regions into ordered text blocks."""

    blocks: list[ExtractedTextBlock] = []

    for raw_block in raw_parsing_results:
        label = str(
            raw_block.get("block_label", "other")
        ).strip().lower()

        if label == "table":
            continue

        content = " ".join(
            str(
                raw_block.get("block_content", "")
            ).split()
        )

        if not content:
            continue

        bounding_box = _bounding_box(
            raw_block.get("block_bbox")
        )

        if bounding_box is None:
            continue

        reading_order = len(blocks)

        blocks.append(
            ExtractedTextBlock(
                block_id=(
                    f"paddle_page_{page_number}_block_"
                    f"{reading_order + 1}"
                ),
                text=content,
                kind=_block_kind(label),
                bounding_box=bounding_box,
                reading_order=reading_order,
                confidence=None,
            )
        )

    return tuple(blocks)


def _convert_tables(
    *,
    raw_table_results: Sequence[Mapping[str, Any]],
    raw_parsing_results: Sequence[Mapping[str, Any]],
    page_number: int,
    page_width: float,
    page_height: float,
) -> tuple[ExtractedTable, ...]:
    """Convert Paddle HTML and cell geometry into tables."""

    table_region_boxes = tuple(
        bounding_box
        for item in raw_parsing_results
        if str(
            item.get("block_label", "")
        ).strip().lower() == "table"
        if (
            bounding_box := _bounding_box(
                item.get("block_bbox")
            )
        )
        is not None
    )

    tables: list[ExtractedTable] = []

    for table_index, raw_table in enumerate(
        raw_table_results
    ):
        html = str(
            raw_table.get("pred_html", "")
        ).strip()

        if not html:
            continue

        parser = _TableHTMLParser()
        parser.feed(html)
        parser.close()

        cells, row_count, column_count, header_rows = (
            _position_html_cells(parser.rows)
        )

        if not cells:
            continue

        raw_cell_boxes = _object_sequence(
            raw_table.get("cell_box_list")
        )
        raw_scores = _table_scores(raw_table)

        positioned_cells = tuple(
            cell.model_copy(
                update={
                    "bounding_box": (
                        _bounding_box(
                            raw_cell_boxes[cell_index]
                        )
                        if cell_index
                        < len(raw_cell_boxes)
                        else None
                    ),
                    "confidence": (
                        raw_scores[cell_index]
                        if cell_index < len(raw_scores)
                        else None
                    ),
                }
            )
            for cell_index, cell in enumerate(cells)
        )

        available_cell_boxes = tuple(
            cell.bounding_box
            for cell in positioned_cells
            if cell.bounding_box is not None
        )

        if available_cell_boxes:
            table_box = _union_boxes(
                available_cell_boxes
            )
        elif table_index < len(table_region_boxes):
            table_box = table_region_boxes[table_index]
        else:
            table_box = BoundingBox(
                x0=0,
                top=0,
                x1=page_width,
                bottom=page_height,
            )

        tables.append(
            ExtractedTable(
                table_id=(
                    f"paddle_page_{page_number}_table_"
                    f"{table_index + 1}"
                ),
                row_count=row_count,
                column_count=column_count,
                cells=positioned_cells,
                bounding_box=table_box,
                header_row_indices=header_rows,
            )
        )

    return tuple(tables)


def _position_html_cells(
    rows: Sequence[Sequence[_HTMLCell]],
) -> tuple[
    tuple[ExtractedTableCell, ...],
    int,
    int,
    tuple[int, ...],
]:
    """Resolve HTML row and column spans into table positions."""

    occupied: set[tuple[int, int]] = set()
    cells: list[ExtractedTableCell] = []
    header_rows: set[int] = set()

    row_count = len(rows)
    column_count = 0

    for row_index, row in enumerate(rows):
        column_index = 0

        for raw_cell in row:
            while (
                row_index,
                column_index,
            ) in occupied:
                column_index += 1

            cells.append(
                ExtractedTableCell(
                    row_index=row_index,
                    column_index=column_index,
                    text=raw_cell.text,
                    row_span=raw_cell.row_span,
                    column_span=raw_cell.column_span,
                    is_header=raw_cell.is_header,
                )
            )

            if raw_cell.is_header:
                header_rows.add(row_index)

            for covered_row in range(
                row_index,
                row_index + raw_cell.row_span,
            ):
                for covered_column in range(
                    column_index,
                    column_index
                    + raw_cell.column_span,
                ):
                    occupied.add(
                        (
                            covered_row,
                            covered_column,
                        )
                    )

            row_count = max(
                row_count,
                row_index + raw_cell.row_span,
            )
            column_count = max(
                column_count,
                column_index + raw_cell.column_span,
            )

            column_index += raw_cell.column_span

    return (
        tuple(cells),
        row_count,
        column_count,
        tuple(sorted(header_rows)),
    )


def _compose_page_text(
    *,
    text_blocks: Sequence[ExtractedTextBlock],
    tables: Sequence[ExtractedTable],
    payload: Mapping[str, Any],
) -> str:
    """Create searchable text without discarding structure."""

    sections = [
        block.text
        for block in text_blocks
        if block.text
    ]

    for table in tables:
        sections.extend(
            " | ".join(cell for cell in row if cell)
            for row in table.as_matrix()
            if any(cell for cell in row)
        )

    if not sections:
        overall_ocr = payload.get("overall_ocr_res")

        if isinstance(overall_ocr, Mapping):
            recognized_texts = _object_sequence(
                overall_ocr.get("rec_texts")
            )

            sections.extend(
                " ".join(str(text).split())
                for text in recognized_texts
                if " ".join(str(text).split())
            )

    return "\n".join(
        section for section in sections if section
    ).strip()


def _table_scores(
    raw_table: Mapping[str, Any],
) -> tuple[float, ...]:
    """Return valid table OCR scores when available."""

    table_ocr = raw_table.get("table_ocr_pred")

    if not isinstance(table_ocr, Mapping):
        return ()

    scores: list[float] = []

    for raw_score in _object_sequence(
        table_ocr.get("rec_scores")
    ):
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue

        if 0 <= score <= 1:
            scores.append(score)

    return tuple(scores)


def _bounding_box(
    raw_value: object,
) -> BoundingBox | None:
    """Convert a flat rectangle or polygon into a bounding box."""

    values = _object_sequence(raw_value)

    if len(values) == 4 and all(
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        for value in values
    ):
        try:
            x0, top, x1, bottom = (
                float(value) for value in values
            )
        except (TypeError, ValueError):
            return None
    else:
        points: list[tuple[float, float]] = []

        for raw_point in values:
            point = _object_sequence(raw_point)

            if len(point) < 2:
                continue

            try:
                points.append(
                    (
                        float(point[0]),
                        float(point[1]),
                    )
                )
            except (TypeError, ValueError):
                continue

        if not points:
            return None

        x0 = min(point[0] for point in points)
        top = min(point[1] for point in points)
        x1 = max(point[0] for point in points)
        bottom = max(point[1] for point in points)

    x0 = max(0, x0)
    top = max(0, top)
    x1 = max(0, x1)
    bottom = max(0, bottom)

    if x1 <= x0 or bottom <= top:
        return None

    return BoundingBox(
        x0=x0,
        top=top,
        x1=x1,
        bottom=bottom,
    )


def _union_boxes(
    boxes: Sequence[BoundingBox],
) -> BoundingBox:
    """Return the smallest box containing all supplied boxes."""

    return BoundingBox(
        x0=min(box.x0 for box in boxes),
        top=min(box.top for box in boxes),
        x1=max(box.x1 for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


def _block_kind(label: str) -> TextBlockKind:
    """Map Paddle layout labels into stable project labels."""

    mapping = {
        "document_title": TextBlockKind.TITLE,
        "title": TextBlockKind.TITLE,
        "paragraph_title": TextBlockKind.HEADING,
        "heading": TextBlockKind.HEADING,
        "text": TextBlockKind.PARAGRAPH,
        "paragraph": TextBlockKind.PARAGRAPH,
        "list": TextBlockKind.LIST,
        "figure_caption": TextBlockKind.CAPTION,
        "table_caption": TextBlockKind.CAPTION,
        "caption": TextBlockKind.CAPTION,
        "header": TextBlockKind.HEADER,
        "footer": TextBlockKind.FOOTER,
    }

    return mapping.get(label, TextBlockKind.OTHER)


def _mapping_sequence(
    raw_value: object,
) -> tuple[Mapping[str, Any], ...]:
    """Return only dictionary-like items from a sequence."""

    return tuple(
        item
        for item in _object_sequence(raw_value)
        if isinstance(item, Mapping)
    )


def _object_sequence(
    raw_value: object,
) -> tuple[Any, ...]:
    """Safely normalize a vendor sequence to a tuple."""

    if raw_value is None:
        return ()

    if isinstance(raw_value, np.ndarray):
        return tuple(raw_value.tolist())

    if isinstance(raw_value, Sequence) and not isinstance(
        raw_value,
        (str, bytes),
    ):
        return tuple(raw_value)

    return ()


def _positive_integer(
    raw_value: str | None,
) -> int:
    """Parse a positive HTML span with a safe default."""

    try:
        value = int(raw_value or "1")
    except ValueError:
        return 1

    return max(1, value)


def _positive_dimension(
    raw_value: object,
    *,
    fallback: int,
) -> float:
    """Return a positive page dimension."""

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = float(fallback)

    if value <= 0:
        value = float(fallback)

    return value