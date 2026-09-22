"""Selective, traceable interpretation of charts and image regions."""

import re
from collections.abc import Callable, Sequence
from hashlib import sha256
from math import isclose

from greensmecapt.document_intelligence.models import (
    ExtractedPage,
    ExtractedVisualRegion,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.semantics import (
    MetricCatalog,
    MetricDefinition,
    UnitRule,
)
from greensmecapt.document_intelligence.vision.models import (
    RejectedVisualClaim,
    VisualInterpretationRequest,
    VisualProviderStatus,
    VisualRegionDecision,
    VisualRelevance,
    VisualUnderstandingReport,
    VisualUnderstandingResult,
)
from greensmecapt.document_intelligence.vision.ports import (
    VisualProviderError,
    VisualSemanticProvider,
)
from greensmecapt.domain import EvidenceItem, SourceDocument

_NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
_ENVIRONMENTAL_TERMS = (
    "energy",
    "emission",
    "carbon",
    "water",
    "waste",
    "recycl",
    "renewable",
    "environment",
    "sustainab",
    "electric",
)


class VisualUnderstandingService:
    """Gate visual regions and validate optional multimodal claims."""

    def __init__(
        self,
        *,
        catalog: MetricCatalog,
        provider: VisualSemanticProvider | None = None,
        analyze_uncertain: bool = True,
    ) -> None:
        self._catalog = catalog
        self._provider = provider
        self._analyze_uncertain = analyze_uncertain

    @property
    def provider_configured(self) -> bool:
        """Report whether selected image regions can reach a model."""

        return self._provider is not None

    def analyze(
        self,
        *,
        document: SourceDocument,
        pages: Sequence[ExtractedPage],
        render_region: Callable[
            [ExtractedPage, ExtractedVisualRegion],
            bytes,
        ],
    ) -> VisualUnderstandingResult:
        """Interpret only selected regions and retain every rejection."""

        evidence_items: list[EvidenceItem] = []
        decisions: list[VisualRegionDecision] = []

        for page in pages:
            for region in page.visual_regions:
                relevance, reason = _classify_relevance(
                    page,
                    region,
                    self._catalog,
                )
                should_analyze = (
                    relevance is VisualRelevance.RELEVANT
                    or (
                        relevance is VisualRelevance.UNCERTAIN
                        and self._analyze_uncertain
                    )
                )

                if not should_analyze:
                    decisions.append(
                        VisualRegionDecision(
                            page_number=page.page_number,
                            region_id=region.region_id,
                            relevance=relevance,
                            relevance_reason=reason,
                            provider_status=VisualProviderStatus.SKIPPED,
                        )
                    )
                    continue

                if self._provider is None:
                    decisions.append(
                        VisualRegionDecision(
                            page_number=page.page_number,
                            region_id=region.region_id,
                            relevance=relevance,
                            relevance_reason=reason,
                            provider_status=VisualProviderStatus.DISABLED,
                            issue=(
                                "No multimodal provider is configured."
                            ),
                        )
                    )
                    continue

                try:
                    image_png = render_region(page, region)
                    output = self._provider.interpret(
                        VisualInterpretationRequest(
                            document_id=document.document_id,
                            page_number=page.page_number,
                            region=region,
                            page_context=page.text,
                            image_png=image_png,
                            catalog=self._catalog,
                        )
                    )
                except (VisualProviderError, ValueError, OSError) as error:
                    decisions.append(
                        VisualRegionDecision(
                            page_number=page.page_number,
                            region_id=region.region_id,
                            relevance=relevance,
                            relevance_reason=reason,
                            provider_status=VisualProviderStatus.FAILED,
                            issue=str(error),
                        )
                    )
                    continue

                accepted, rejected = self._validate_claims(
                    document=document,
                    page=page,
                    region=region,
                    claims=output.claims,
                )
                evidence_items.extend(accepted)
                decisions.append(
                    VisualRegionDecision(
                        page_number=page.page_number,
                        region_id=region.region_id,
                        relevance=relevance,
                        relevance_reason=reason,
                        provider_status=VisualProviderStatus.SUCCEEDED,
                        provider_summary=output.summary,
                        evidence_ids=tuple(
                            item.evidence_id for item in accepted
                        ),
                        rejected_claims=rejected,
                    )
                )

        return VisualUnderstandingResult(
            evidence_items=tuple(evidence_items),
            report=VisualUnderstandingReport(
                document_id=document.document_id,
                decisions=tuple(decisions),
            ),
        )

    def _validate_claims(
        self,
        *,
        document: SourceDocument,
        page: ExtractedPage,
        region: ExtractedVisualRegion,
        claims,
    ) -> tuple[tuple[EvidenceItem, ...], tuple[RejectedVisualClaim, ...]]:
        metrics = {
            metric.indicator_id: metric
            for metric in self._catalog.metrics
        }
        accepted: list[EvidenceItem] = []
        rejected: list[RejectedVisualClaim] = []

        for claim_index, claim in enumerate(claims):
            metric = metrics.get(claim.indicator_id)

            if metric is None:
                rejected.append(
                    _rejection(
                        claim_index,
                        claim.indicator_id,
                        "Indicator is not allowed by the metric catalog.",
                    )
                )
                continue

            unit_rule = _unit_rule(metric, claim.raw_unit)

            if unit_rule is None:
                rejected.append(
                    _rejection(
                        claim_index,
                        claim.indicator_id,
                        "Claim unit is not allowed for this indicator.",
                    )
                )
                continue

            if not _number_occurs(claim.raw_number, claim.raw_value):
                rejected.append(
                    _rejection(
                        claim_index,
                        claim.indicator_id,
                        "Claim number is absent from its raw visual value.",
                    )
                )
                continue

            if not _unit_occurs(claim.raw_unit, claim.raw_value):
                rejected.append(
                    _rejection(
                        claim_index,
                        claim.indicator_id,
                        "Claim unit is absent from its raw visual value.",
                    )
                )
                continue

            normalized_value = claim.raw_number * unit_rule.multiplier

            if (
                metric.minimum is not None
                and normalized_value < metric.minimum
            ) or (
                metric.maximum is not None
                and normalized_value > metric.maximum
            ):
                rejected.append(
                    _rejection(
                        claim_index,
                        claim.indicator_id,
                        "Normalized value is outside the allowed range.",
                    )
                )
                continue

            accepted.append(
                _evidence(
                    document=document,
                    page=page,
                    region=region,
                    metric=metric,
                    raw_value=claim.raw_value,
                    normalized_value=normalized_value,
                    source_description=claim.source_description,
                    confidence=claim.confidence,
                    provider=self._provider,
                )
            )

        return tuple(accepted), tuple(rejected)


def _classify_relevance(
    page: ExtractedPage,
    region: ExtractedVisualRegion,
    catalog: MetricCatalog,
) -> tuple[VisualRelevance, str]:
    if region.kind is VisualRegionKind.LOGO:
        return VisualRelevance.IRRELEVANT, "Logos are decorative metadata."

    context = " ".join(
        value
        for value in (region.caption, page.text)
        if value
    ).casefold()
    metric_terms = {
        alias.casefold()
        for metric in catalog.metrics
        for alias in metric.aliases
    }

    if any(term in context for term in metric_terms):
        return (
            VisualRelevance.RELEVANT,
            "Nearby text matches a configured assessment metric.",
        )

    if region.kind in {
        VisualRegionKind.CHART,
        VisualRegionKind.DIAGRAM,
    }:
        return (
            VisualRelevance.UNCERTAIN,
            "Charts and diagrams may encode values absent from page text.",
        )

    if any(term in context for term in _ENVIRONMENTAL_TERMS):
        return (
            VisualRelevance.UNCERTAIN,
            "Environmental context may make this image assessment-relevant.",
        )

    return (
        VisualRelevance.IRRELEVANT,
        "No configured metric or environmental context was detected.",
    )


def _unit_rule(
    metric: MetricDefinition,
    raw_unit: str,
) -> UnitRule | None:
    normalized = " ".join(raw_unit.casefold().split())

    for unit in metric.units:
        aliases = {
            " ".join(alias.casefold().split())
            for alias in unit.aliases
        }

        if normalized in aliases or normalized == unit.canonical_unit.casefold():
            return unit

    return None


def _number_occurs(raw_number: float, raw_value: str) -> bool:
    for match in _NUMBER_PATTERN.finditer(raw_value):
        try:
            written = float(match.group(0).replace(",", ""))
        except ValueError:
            continue

        if isclose(written, raw_number, rel_tol=1e-9, abs_tol=1e-9):
            return True

    return False


def _unit_occurs(raw_unit: str, raw_value: str) -> bool:
    """Require the claimed unit to occur in the copied visual value."""

    normalized_unit = " ".join(raw_unit.casefold().split())
    normalized_value = " ".join(raw_value.casefold().split())
    return normalized_unit in normalized_value


def _rejection(
    claim_index: int,
    indicator_id: str,
    reason: str,
) -> RejectedVisualClaim:
    return RejectedVisualClaim(
        claim_index=claim_index,
        indicator_id=indicator_id,
        reason=reason,
    )


def _evidence(
    *,
    document: SourceDocument,
    page: ExtractedPage,
    region: ExtractedVisualRegion,
    metric: MetricDefinition,
    raw_value: str,
    normalized_value: float,
    source_description: str,
    confidence: float | None,
    provider: VisualSemanticProvider,
) -> EvidenceItem:
    box = region.bounding_box
    fingerprint = sha256(
        (
            f"{document.document_id}:{page.page_number}:"
            f"{region.region_id}:{metric.indicator_id}:"
            f"{normalized_value}:{metric.canonical_unit}"
        ).encode()
    ).hexdigest()[:20]

    return EvidenceItem(
        evidence_id=f"evidence_visual_{fingerprint}",
        sme_id=document.sme_id,
        document_id=document.document_id,
        indicator_id=metric.indicator_id,
        criterion_id=metric.criterion_id,
        raw_value=raw_value,
        normalized_value=normalized_value,
        unit=metric.canonical_unit,
        source_locator=(
            f"page {page.page_number}, visual region {region.region_id}, "
            f"box {box.x0},{box.top},{box.x1},{box.bottom}"
        ),
        source_excerpt=source_description,
        extraction_method="multimodal_visual_interpretation",
        extractor_name=provider.provider_name,
        extractor_version=provider.provider_version,
        confidence=confidence,
    )
