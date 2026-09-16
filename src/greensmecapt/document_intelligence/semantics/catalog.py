"""Load versioned semantic metric catalogs."""

from pathlib import Path

from pydantic import ValidationError

from greensmecapt.document_intelligence.semantics.models import (
    MetricCatalog,
)


class MetricCatalogError(ValueError):
    """Raised when a metric catalog cannot be loaded."""


def load_metric_catalog(
    path: str | Path,
) -> MetricCatalog:
    """Read and validate a JSON metric catalog."""

    catalog_path = Path(path)

    try:
        raw_content = catalog_path.read_text(
            encoding="utf-8"
        )
    except OSError as error:
        raise MetricCatalogError(
            f"Metric catalog could not be read: {catalog_path}"
        ) from error

    try:
        return MetricCatalog.model_validate_json(
            raw_content
        )
    except ValidationError as error:
        raise MetricCatalogError(
            f"Metric catalog is invalid: {catalog_path}"
        ) from error