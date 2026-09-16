"""Extract canonical metrics from prose and document tables."""

import re
from dataclasses import dataclass
from hashlib import sha256

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
)
from greensmecapt.document_intelligence.semantics.models import (
    MetricCatalog,
    MetricDefinition,
    UnitRule,
)
from greensmecapt.domain import EvidenceItem, SourceDocument

_NUMBER_PATTERN = r"[-+]?\d[\d,]*(?:\.\d+)?"


@dataclass(frozen=True)
class _TextSegment:
    """One independently traceable extraction surface."""

    text: str
    locator: str
    extraction_method: str


@dataclass(frozen=True)
class _CompiledMetric:
    """Precompiled language patterns for one metric."""

    definition: MetricDefinition
    forward_pattern: re.Pattern[str]
    reverse_pattern: re.Pattern[str]
    unit_rules: dict[str, UnitRule]


class SemanticMetricExtractor:
    """Map varied metric language into traceable evidence."""

    extractor_name = "semantic_metric_rules"
    extractor_version = "1.0.0"

    def __init__(
        self,
        catalog: MetricCatalog,
    ) -> None:
        self._catalog = catalog
        self._compiled_metrics = tuple(
            _compile_metric(metric)
            for metric in catalog.metrics
        )

    @property
    def catalog(self) -> MetricCatalog:
        """Expose the immutable semantic vocabulary."""

        return self._catalog

    def extract(
        self,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> tuple[EvidenceItem, ...]:
        """Extract normalized evidence from prose and tables."""

        if (
            extracted_document.document_id
            != document.document_id
        ):
            raise ValueError(
                "Extracted content belongs to a different "
                "document."
            )

        evidence_items: list[EvidenceItem] = []
        evidence_ids: set[str] = set()

        for page in extracted_document.pages:
            for segment in _page_segments(page):
                for compiled_metric in (
                    self._compiled_metrics
                ):
                    matches = _metric_matches(
                        compiled_metric,
                        segment.text,
                    )

                    for match in matches:
                        evidence = _build_evidence(
                            document=document,
                            page=page,
                            segment=segment,
                            compiled_metric=compiled_metric,
                            match=match,
                        )

                        if (
                            evidence is not None
                            and evidence.evidence_id
                            not in evidence_ids
                        ):
                            evidence_items.append(evidence)
                            evidence_ids.add(
                                evidence.evidence_id
                            )

        return tuple(evidence_items)


def _compile_metric(
    definition: MetricDefinition,
) -> _CompiledMetric:
    """Compile forward and reverse metric expressions."""

    alias_expression = _phrase_expression(
        definition.aliases
    )

    unit_aliases = tuple(
        alias
        for unit in definition.units
        for alias in unit.aliases
    )
    unit_expression = _unit_expression(unit_aliases)

    forward_pattern = re.compile(
        rf"(?P<alias>{alias_expression})"
        rf"(?P<gap>[^\d\n]{{0,80}}?)"
        rf"(?P<number>{_NUMBER_PATTERN})"
        rf"\s*"
        rf"(?P<unit>{unit_expression})",
        flags=re.IGNORECASE,
    )

    reverse_pattern = re.compile(
        rf"(?P<number>{_NUMBER_PATTERN})"
        rf"\s*"
        rf"(?P<unit>{unit_expression})"
        rf"(?P<gap>[^\d\n]{{0,80}}?)"
        rf"(?P<alias>{alias_expression})",
        flags=re.IGNORECASE,
    )

    unit_rules = {
        _normalize_token(alias): unit
        for unit in definition.units
        for alias in unit.aliases
    }

    return _CompiledMetric(
        definition=definition,
        forward_pattern=forward_pattern,
        reverse_pattern=reverse_pattern,
        unit_rules=unit_rules,
    )


def _phrase_expression(
    phrases: tuple[str, ...],
) -> str:
    """Build a boundary-safe expression from configured phrases."""

    alternatives = []

    for phrase in sorted(
        phrases,
        key=len,
        reverse=True,
    ):
        escaped = re.escape(phrase.strip())
        flexible = escaped.replace(r"\ ", r"[\s\-]+")

        alternatives.append(flexible)

    return (
        r"(?<!\w)(?:"
        + "|".join(alternatives)
        + r")(?!\w)"
    )
def _unit_expression(
    units: tuple[str, ...],
) -> str:
    """Build an expression for attached or separated units."""

    alternatives = []

    for unit in sorted(
        units,
        key=len,
        reverse=True,
    ):
        escaped = re.escape(unit.strip())
        flexible = escaped.replace(r"\ ", r"[\s\-]+")

        alternatives.append(flexible)

    return (
        r"(?:"
        + "|".join(alternatives)
        + r")(?!\w)"
    )

def _page_segments(
    page: ExtractedPage,
) -> tuple[_TextSegment, ...]:
    """Expose structured page regions without duplicating text."""

    segments: list[_TextSegment] = []

    for block in page.text_blocks:
        segments.append(
            _TextSegment(
                text=block.text,
                locator=(
                    f"page {page.page_number}, "
                    f"block {block.block_id}"
                ),
                extraction_method=(
                    "semantic_rule_text_block"
                ),
            )
        )

    for table in page.tables:
        for row_index, row in enumerate(
            table.as_matrix()
        ):
            row_text = " | ".join(
                cell.strip()
                for cell in row
                if cell.strip()
            )

            if not row_text:
                continue

            segments.append(
                _TextSegment(
                    text=row_text,
                    locator=(
                        f"page {page.page_number}, "
                        f"table {table.table_id}, "
                        f"row {row_index + 1}"
                    ),
                    extraction_method=(
                        "semantic_rule_table_row"
                    ),
                )
            )

    if not segments:
        segments.append(
            _TextSegment(
                text=page.text,
                locator=f"page {page.page_number}",
                extraction_method=(
                    "semantic_rule_page_text"
                ),
            )
        )

    return tuple(segments)


def _metric_matches(
    compiled_metric: _CompiledMetric,
    text: str,
) -> tuple[re.Match[str], ...]:
    """Return unique forward and reverse matches."""

    matches = [
        *compiled_metric.forward_pattern.finditer(text),
        *compiled_metric.reverse_pattern.finditer(text),
    ]

    unique: dict[
        tuple[int, int, str, str],
        re.Match[str],
    ] = {}

    for match in matches:
        key = (
            match.start(),
            match.end(),
            match.group("number"),
            match.group("unit").casefold(),
        )
        unique.setdefault(key, match)

    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.start(),
                item.end(),
            ),
        )
    )


def _build_evidence(
    *,
    document: SourceDocument,
    page: ExtractedPage,
    segment: _TextSegment,
    compiled_metric: _CompiledMetric,
    match: re.Match[str],
) -> EvidenceItem | None:
    """Normalize one semantic match into evidence."""

    raw_number = match.group("number")
    raw_unit = match.group("unit")
    normalized_unit = _normalize_token(raw_unit)

    unit_rule = compiled_metric.unit_rules.get(
        normalized_unit
    )

    if unit_rule is None:
        return None

    try:
        numeric_value = float(
            raw_number.replace(",", "")
        )
    except ValueError:
        return None

    normalized_value = (
        numeric_value * unit_rule.multiplier
    )
    definition = compiled_metric.definition

    if (
        definition.minimum is not None
        and normalized_value < definition.minimum
    ):
        return None

    if (
        definition.maximum is not None
        and normalized_value > definition.maximum
    ):
        return None

    raw_value = segment.text[
        match.start("number"):match.end("unit")
    ].strip()

    source_locator = (
        f"{segment.locator}, characters "
        f"{match.start()}-{match.end()}"
    )
    excerpt = _source_excerpt(
        segment.text,
        start=match.start(),
        end=match.end(),
    )

    fingerprint = sha256(
        (
            f"{document.document_id}:"
            f"{page.page_number}:"
            f"{segment.locator}:"
            f"{definition.indicator_id}:"
            f"{match.start()}:"
            f"{match.end()}:"
            f"{normalized_value}:"
            f"{definition.canonical_unit}"
        ).encode()
    ).hexdigest()[:20]

    return EvidenceItem(
        evidence_id=f"evidence_{fingerprint}",
        sme_id=document.sme_id,
        document_id=document.document_id,
        indicator_id=definition.indicator_id,
        criterion_id=definition.criterion_id,
        raw_value=raw_value,
        normalized_value=normalized_value,
        unit=definition.canonical_unit,
        source_locator=source_locator,
        source_excerpt=excerpt,
        extraction_method=(
            segment.extraction_method
        ),
        extractor_name=SemanticMetricExtractor.extractor_name,
        extractor_version=(
            SemanticMetricExtractor.extractor_version
        ),
        confidence=None,
    )


def _source_excerpt(
    text: str,
    *,
    start: int,
    end: int,
) -> str:
    """Return compact context around one match."""

    excerpt_start = max(0, start - 80)
    excerpt_end = min(len(text), end + 80)

    return " ".join(
        text[excerpt_start:excerpt_end].split()
    )


def _normalize_token(value: str) -> str:
    """Normalize aliases and units for lookup."""

    return " ".join(value.casefold().split())