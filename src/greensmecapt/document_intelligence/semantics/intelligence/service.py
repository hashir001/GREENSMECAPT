"""Ground intelligent semantic claims in document evidence."""

import re
from hashlib import sha256
from math import isclose

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
)
from greensmecapt.document_intelligence.semantics.context import (
    normalize_reporting_period,
    normalize_scope,
)
from greensmecapt.document_intelligence.semantics.intelligence.models import (
    IntelligentExtractionReport,
    MetricInstruction,
    RejectedSemanticClaim,
    SemanticClaimPayload,
    SemanticExtractionRequest,
    SemanticSourceSegment,
)
from greensmecapt.document_intelligence.semantics.intelligence.provider import (
    SemanticExtractionProvider,
)
from greensmecapt.document_intelligence.semantics.models import (
    MetricCatalog,
    MetricDefinition,
    UnitRule,
)
from greensmecapt.domain import EvidenceItem, SourceDocument

_WRITTEN_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.])"
)


class IntelligentSemanticExtractionService:
    """Convert only grounded provider claims into evidence."""

    def __init__(
        self,
        provider: SemanticExtractionProvider,
    ) -> None:
        self._provider = provider

    def extract(
        self,
        *,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
        catalog: MetricCatalog,
    ) -> IntelligentExtractionReport:
        """Extract, verify and convert intelligent claims."""

        if (
            extracted_document.document_id
            != document.document_id
        ):
            raise ValueError(
                "Extracted content belongs to a different "
                "document."
            )

        request = _build_request(
            extracted_document=extracted_document,
            catalog=catalog,
        )
        provider_output = self._provider.extract(request)

        segments = {
            segment.segment_id: segment
            for segment in request.segments
        }
        metrics = {
            metric.indicator_id: metric
            for metric in catalog.metrics
        }

        evidence_items: list[EvidenceItem] = []
        rejected_claims: list[RejectedSemanticClaim] = []

        for claim_index, claim in enumerate(
            provider_output.claims
        ):
            result = _ground_claim(
                claim=claim,
                document=document,
                segments=segments,
                metrics=metrics,
                provider_name=self._provider.provider_name,
                provider_version=(
                    self._provider.provider_version
                ),
                model_name=self._provider.model_name,
            )

            if isinstance(result, EvidenceItem):
                evidence_items.append(result)
            else:
                rejected_claims.append(
                    RejectedSemanticClaim(
                        claim_index=claim_index,
                        indicator_id=claim.indicator_id,
                        segment_id=claim.segment_id,
                        reason=result,
                    )
                )

        return IntelligentExtractionReport(
            provider_name=self._provider.provider_name,
            provider_version=(
                self._provider.provider_version
            ),
            model_name=self._provider.model_name,
            evidence_items=tuple(evidence_items),
            rejected_claims=tuple(rejected_claims),
        )


def _build_request(
    *,
    extracted_document: ExtractedDocument,
    catalog: MetricCatalog,
) -> SemanticExtractionRequest:
    """Build a bounded request from structured document regions."""

    segments = tuple(
        segment
        for page in extracted_document.pages
        for segment in _page_segments(page)
    )

    if not segments:
        raise ValueError(
            "No readable source segments are available."
        )

    metrics = tuple(
        MetricInstruction(
            indicator_id=metric.indicator_id,
            name=metric.name,
            aliases=metric.aliases,
            canonical_unit=metric.canonical_unit,
            accepted_unit_aliases=tuple(
                alias
                for unit in metric.units
                for alias in unit.aliases
            ),
            minimum=metric.minimum,
            maximum=metric.maximum,
        )
        for metric in catalog.metrics
    )

    return SemanticExtractionRequest(
        document_id=extracted_document.document_id,
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.version,
        metrics=metrics,
        segments=segments,
    )


def _page_segments(
    page: ExtractedPage,
) -> tuple[SemanticSourceSegment, ...]:
    """Create stable provider segments from page structure."""

    segments: list[SemanticSourceSegment] = []

    for block_index, block in enumerate(
        page.text_blocks,
        start=1,
    ):
        segments.append(
            SemanticSourceSegment(
                segment_id=(
                    f"page_{page.page_number}_"
                    f"block_{block_index}"
                ),
                page_number=page.page_number,
                locator=(
                    f"page {page.page_number}, "
                    f"block {block.block_id}"
                ),
                text=block.text,
            )
        )

    for table_index, table in enumerate(
        page.tables,
        start=1,
    ):
        for row_index, row in enumerate(
            table.as_matrix(),
            start=1,
        ):
            text = " | ".join(
                value.strip()
                for value in row
                if value.strip()
            )

            if not text:
                continue

            segments.append(
                SemanticSourceSegment(
                    segment_id=(
                        f"page_{page.page_number}_"
                        f"table_{table_index}_row_{row_index}"
                    ),
                    page_number=page.page_number,
                    locator=(
                        f"page {page.page_number}, "
                        f"table {table.table_id}, "
                        f"row {row_index}"
                    ),
                    text=text,
                )
            )

    if not segments:
        segments.append(
            SemanticSourceSegment(
                segment_id=f"page_{page.page_number}_text",
                page_number=page.page_number,
                locator=f"page {page.page_number}",
                text=page.text,
            )
        )

    return tuple(segments)


def _ground_claim(
    *,
    claim: SemanticClaimPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    metrics: dict[str, MetricDefinition],
    provider_name: str,
    provider_version: str,
    model_name: str,
) -> EvidenceItem | str:
    """Return evidence or a precise rejection reason."""

    segment = segments.get(claim.segment_id)

    if segment is None:
        return "The claim references an unknown source segment."

    metric = metrics.get(claim.indicator_id)

    if metric is None:
        return "The claim references an unconfigured indicator."

    if not _contains_text(
        segment.text,
        claim.source_quote,
    ):
        return (
            "The source quote does not occur in the referenced "
            "segment."
        )

    if not _contains_text(
        claim.source_quote,
        claim.raw_value,
    ):
        return (
            "The raw value does not occur in the source quote."
        )

    if not _contains_text(
        claim.raw_value,
        claim.raw_unit,
    ):
        return (
            "The raw unit does not occur in the raw value."
        )

    if (
        claim.reporting_period is not None
        and not _contains_text(
            claim.source_quote,
            claim.reporting_period,
        )
    ):
        return (
            "The reporting period does not occur in the "
            "source quote."
        )

    if (
        claim.scope is not None
        and not _contains_text(
            claim.source_quote,
            claim.scope,
        )
    ):
        return "The scope does not occur in the source quote."

    unit_rule = _find_unit_rule(
        metric,
        claim.raw_unit,
    )

    if unit_rule is None:
        return (
            "The raw unit is not allowed for this indicator."
        )

    normalized_value = (
        claim.raw_number * unit_rule.multiplier
    )
    reporting_period = (
        normalize_reporting_period(claim.reporting_period)
        if claim.reporting_period is not None
        else None
    )
    scope = (
        normalize_scope(claim.scope)
        if claim.scope is not None
        else None
    )

    if (
        metric.minimum is not None
        and normalized_value < metric.minimum
    ):
        return (
            "The normalized value is below the metric minimum."
        )

    if (
        metric.maximum is not None
        and normalized_value > metric.maximum
    ):
        return (
            "The normalized value exceeds the metric maximum."
        )

    if not _raw_number_occurs_in_value(
        claim.raw_number,
        claim.raw_value,
    ):
        return (
            "The structured raw number does not match the number "
            "written in the raw value."
        )

    fingerprint = sha256(
        (
            f"{document.document_id}:"
            f"{claim.segment_id}:"
            f"{claim.indicator_id}:"
            f"{claim.raw_value}:"
            f"{normalized_value}:"
            f"{unit_rule.canonical_unit}:"
            f"{reporting_period}:"
            f"{scope}:"
            f"{provider_name}:"
            f"{model_name}"
        ).encode()
    ).hexdigest()[:20]

    return EvidenceItem(
        evidence_id=f"evidence_{fingerprint}",
        sme_id=document.sme_id,
        document_id=document.document_id,
        indicator_id=metric.indicator_id,
        criterion_id=metric.criterion_id,
        raw_value=claim.raw_value,
        normalized_value=normalized_value,
        unit=unit_rule.canonical_unit,
        source_locator=segment.locator,
        source_excerpt=claim.source_quote,
        extraction_method=(
            "language_model_structured_extraction"
        ),
        extractor_name=(
            f"{provider_name}:{model_name}"
        ),
        extractor_version=provider_version,
        confidence=None,
        reporting_period=reporting_period,
        scope=scope,
    )


def _find_unit_rule(
    metric: MetricDefinition,
    raw_unit: str,
) -> UnitRule | None:
    """Resolve a provider unit using configured aliases."""

    normalized_unit = _normalize_text(raw_unit)

    for unit_rule in metric.units:
        if any(
            _normalize_text(alias) == normalized_unit
            for alias in unit_rule.aliases
        ):
            return unit_rule

    return None


def _raw_number_occurs_in_value(
    raw_number: float,
    raw_value: str,
) -> bool:
    """Require the provider's number to occur in its quoted value."""

    for match in _WRITTEN_NUMBER_PATTERN.finditer(raw_value):
        try:
            written_number = float(
                match.group(0).replace(",", "")
            )
        except ValueError:
            continue

        if isclose(
            written_number,
            raw_number,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            return True

    return False


def _contains_text(
    container: str,
    candidate: str,
) -> bool:
    """Compare text despite harmless spacing differences."""

    return _normalize_text(candidate) in _normalize_text(
        container
    )


def _normalize_text(value: str) -> str:
    """Normalize spacing and case without changing meaning."""

    return " ".join(value.casefold().split())