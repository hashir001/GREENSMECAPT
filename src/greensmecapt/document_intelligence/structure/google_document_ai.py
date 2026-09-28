"""Google Document AI-backed structured page parsing."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from io import BytesIO
from threading import Lock
from typing import Any

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
from greensmecapt.document_intelligence.structure.paddle import (
    StructuredParserUnavailableError,
    StructuredParsingError,
)

_LOGGER = logging.getLogger(__name__)


class GoogleDocumentAIConfiguration(BaseModel):
    """Identify one regional Google Document AI processor."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    project_id: str = Field(min_length=1)
    location: str = Field(min_length=1)
    processor_id: str = Field(min_length=1)
    processor_version: str | None = Field(default=None, min_length=1)
    timeout_seconds: float = Field(default=120, gt=0)

    @property
    def processor_name(self) -> str:
        """Return the fully-qualified processor or processor-version name."""

        base = (
            f"projects/{self.project_id}/locations/{self.location}/processors/{self.processor_id}"
        )
        if self.processor_version is None:
            return base
        return f"{base}/processorVersions/{self.processor_version}"


class GoogleDocumentAIStructuredPageParser:
    """Convert a Google Document AI page response to project models."""

    def __init__(
        self,
        configuration: GoogleDocumentAIConfiguration,
        *,
        client: object | None = None,
    ) -> None:
        self._configuration = configuration
        self._client = client
        self._lock = Lock()

    @property
    def configuration(self) -> GoogleDocumentAIConfiguration:
        return self._configuration

    def parse(
        self,
        image: Image,
        *,
        page_number: int,
    ) -> ExtractedPage:
        """Send one rendered page and preserve its text, layout and tables."""

        if page_number < 1:
            raise StructuredParsingError("Page number must be positive.")

        prepared = image.convert("RGB")
        payload = BytesIO()
        prepared.save(payload, format="PNG")

        try:
            response = self._resolved_client().process_document(
                request={
                    "name": self._configuration.processor_name,
                    "raw_document": {
                        "content": payload.getvalue(),
                        "mime_type": "image/png",
                    },
                },
                timeout=self._configuration.timeout_seconds,
            )
        except StructuredParsingError:
            raise
        except Exception as error:
            raise StructuredParsingError("Google Document AI page processing failed.") from error

        document = _attribute(response, "document")
        full_text = str(_attribute(document, "text", "")).strip()
        pages = tuple(_attribute(document, "pages", ()) or ())

        if not full_text or not pages:
            raise StructuredParsingError("Google Document AI returned no readable page content.")

        source_page = pages[0]
        width = float(prepared.width)
        height = float(prepared.height)
        text_blocks = _text_blocks(
            source_page,
            document_text=full_text,
            page_number=page_number,
            width=width,
            height=height,
        )
        tables = _tables(
            source_page,
            document_text=full_text,
            page_number=page_number,
            width=width,
            height=height,
        )

        if not text_blocks:
            text_blocks = (
                ExtractedTextBlock(
                    block_id=f"p{page_number}_block_1",
                    text=full_text,
                    kind=TextBlockKind.PARAGRAPH,
                    bounding_box=BoundingBox(
                        x0=0,
                        top=0,
                        x1=width,
                        bottom=height,
                    ),
                    reading_order=0,
                ),
            )

        _LOGGER.info(
            "Google Document AI processed page %s with processor %s.",
            page_number,
            self._configuration.processor_name,
        )

        return ExtractedPage(
            page_number=page_number,
            text=full_text,
            text_source=TextSource.OCR,
            page_width=width,
            page_height=height,
            text_blocks=text_blocks,
            tables=tables,
        )

    def _resolved_client(self) -> object:
        client = self._client
        if client is not None:
            return client

        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from google.api_core.client_options import ClientOptions
                from google.cloud import documentai
            except ImportError as error:
                raise StructuredParserUnavailableError(
                    "Google Document AI support is not installed. "
                    "Install the 'google-document-ai' project extra."
                ) from error

            try:
                self._client = documentai.DocumentProcessorServiceClient(
                    client_options=ClientOptions(
                        api_endpoint=(f"{self._configuration.location}-documentai.googleapis.com")
                    )
                )
            except Exception as error:
                raise StructuredParserUnavailableError(
                    "Google Document AI credentials or client setup failed."
                ) from error

        return self._client


class FallbackStructuredPageParser:
    """Use a preferred parser while retaining the existing local parser."""

    def __init__(self, preferred: object, fallback: object) -> None:
        self._preferred = preferred
        self._fallback = fallback

    def parse(self, image: Image, *, page_number: int) -> ExtractedPage:
        try:
            return self._preferred.parse(image, page_number=page_number)
        except StructuredParsingError as error:
            _LOGGER.warning(
                "Preferred structured parser %s failed on page %s; "
                "using fallback %s: %s",
                type(self._preferred).__name__,
                page_number,
                type(self._fallback).__name__,
                error,
            )
            return self._fallback.parse(image, page_number=page_number)


def _text_blocks(
    page: object,
    *,
    document_text: str,
    page_number: int,
    width: float,
    height: float,
) -> tuple[ExtractedTextBlock, ...]:
    converted: list[ExtractedTextBlock] = []
    for index, block in enumerate(_attribute(page, "blocks", ()) or ()):
        layout = _attribute(block, "layout")
        text = _layout_text(layout, document_text).strip()
        box = _bounding_box(layout, width=width, height=height)
        if not text or box is None:
            continue
        converted.append(
            ExtractedTextBlock(
                block_id=f"p{page_number}_block_{index + 1}",
                text=text,
                kind=TextBlockKind.PARAGRAPH,
                bounding_box=box,
                reading_order=len(converted),
                confidence=_confidence(layout),
            )
        )
    return tuple(converted)


def _tables(
    page: object,
    *,
    document_text: str,
    page_number: int,
    width: float,
    height: float,
) -> tuple[ExtractedTable, ...]:
    converted: list[ExtractedTable] = []
    for table_index, table in enumerate(_attribute(page, "tables", ()) or ()):
        header_rows = tuple(_attribute(table, "header_rows", ()) or ())
        body_rows = tuple(_attribute(table, "body_rows", ()) or ())
        rows = (*header_rows, *body_rows)
        if not rows:
            continue
        column_count = max(
            (
                sum(
                    max(1, int(_attribute(cell, "col_span", 1) or 1))
                    for cell in tuple(_attribute(row, "cells", ()) or ())
                )
                for row in rows
            ),
            default=0,
        )
        if column_count == 0:
            continue
        cells: list[ExtractedTableCell] = []
        for row_index, row in enumerate(rows):
            column_index = 0
            for cell in tuple(_attribute(row, "cells", ()) or ()):
                layout = _attribute(cell, "layout")
                row_span = max(1, int(_attribute(cell, "row_span", 1) or 1))
                column_span = max(1, int(_attribute(cell, "col_span", 1) or 1))
                cells.append(
                    ExtractedTableCell(
                        row_index=row_index,
                        column_index=column_index,
                        text=_layout_text(layout, document_text).strip(),
                        row_span=min(row_span, len(rows) - row_index),
                        column_span=min(column_span, column_count - column_index),
                        is_header=row_index < len(header_rows),
                        bounding_box=_bounding_box(layout, width=width, height=height),
                        confidence=_confidence(layout),
                    )
                )
                column_index += column_span
        table_box = _bounding_box(_attribute(table, "layout"), width=width, height=height)
        if table_box is None:
            table_box = _union_boxes(
                cell.bounding_box for cell in cells if cell.bounding_box is not None
            )
        if not cells or table_box is None:
            continue
        converted.append(
            ExtractedTable(
                table_id=f"p{page_number}_table_{table_index + 1}",
                row_count=len(rows),
                column_count=column_count,
                cells=tuple(cells),
                bounding_box=table_box,
                header_row_indices=tuple(range(len(header_rows))),
            )
        )
    return tuple(converted)


def _layout_text(layout: object, document_text: str) -> str:
    anchor = _attribute(layout, "text_anchor")
    segments = tuple(_attribute(anchor, "text_segments", ()) or ())
    parts: list[str] = []
    for segment in segments:
        start = int(_attribute(segment, "start_index", 0) or 0)
        end = int(_attribute(segment, "end_index", 0) or 0)
        if 0 <= start < end <= len(document_text):
            parts.append(document_text[start:end])
    return "".join(parts)


def _bounding_box(
    layout: object,
    *,
    width: float,
    height: float,
) -> BoundingBox | None:
    polygon = _attribute(layout, "bounding_poly")
    normalized = tuple(_attribute(polygon, "normalized_vertices", ()) or ())
    vertices = normalized or tuple(_attribute(polygon, "vertices", ()) or ())
    if not vertices:
        return None
    xs = [float(_attribute(vertex, "x", 0) or 0) for vertex in vertices]
    ys = [float(_attribute(vertex, "y", 0) or 0) for vertex in vertices]
    if normalized:
        xs = [value * width for value in xs]
        ys = [value * height for value in ys]
    x0, x1 = max(0.0, min(xs)), min(width, max(xs))
    top, bottom = max(0.0, min(ys)), min(height, max(ys))
    if x1 <= x0 or bottom <= top:
        return None
    return BoundingBox(x0=x0, top=top, x1=x1, bottom=bottom)


def _union_boxes(boxes: Iterable[BoundingBox]) -> BoundingBox | None:
    materialized = tuple(boxes)
    if not materialized:
        return None
    return BoundingBox(
        x0=min(box.x0 for box in materialized),
        top=min(box.top for box in materialized),
        x1=max(box.x1 for box in materialized),
        bottom=max(box.bottom for box in materialized),
    )


def _confidence(layout: object) -> float | None:
    raw = _attribute(layout, "confidence")
    if raw is None:
        return None
    return max(0.0, min(1.0, float(raw)))


def _attribute(value: object, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)
