"""Tests for selective, grounded visual interpretation."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedPage,
    ExtractedVisualRegion,
    TextSource,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.semantics import (
    load_metric_catalog,
)
from greensmecapt.document_intelligence.vision import (
    VisualMetricClaim,
    VisualProviderOutput,
    VisualProviderStatus,
    VisualUnderstandingService,
)
from greensmecapt.domain import (
    EvidenceValidationStatus,
    SourceDocument,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    PROJECT_ROOT
    / "config"
    / "metric_catalog.development.json"
)


class FakeVisualProvider:
    """Return controlled claims and retain exact image requests."""

    provider_name = "fake_visual_provider"
    provider_version = "1.0"
    model_name = "fake_vision_model"

    def __init__(
        self,
        claims: tuple[VisualMetricClaim, ...],
    ) -> None:
        self._claims = claims
        self.requests = []

    def interpret(self, request):
        self.requests.append(request)
        return VisualProviderOutput(
            summary="The chart contains an explicit metric label.",
            claims=self._claims,
        )


def _document() -> SourceDocument:
    content = b"visual-understanding-test"

    return SourceDocument(
        document_id="doc_visual_001",
        sme_id="sme_001",
        file_name="environmental-report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )


def _region(
    *,
    region_id: str = "page_1_chart_1",
    kind: VisualRegionKind = VisualRegionKind.CHART,
    caption: str | None = "Renewable energy share",
) -> ExtractedVisualRegion:
    return ExtractedVisualRegion(
        region_id=region_id,
        kind=kind,
        bounding_box=BoundingBox(
            x0=10,
            top=20,
            x1=210,
            bottom=140,
        ),
        caption=caption,
        confidence=0.93,
    )


def _page(
    *regions: ExtractedVisualRegion,
    text: str = "Environmental performance dashboard.",
) -> ExtractedPage:
    return ExtractedPage(
        page_number=1,
        text=text,
        text_source=TextSource.OCR,
        page_width=600,
        page_height=800,
        visual_regions=tuple(regions),
    )


def _claim(**updates) -> VisualMetricClaim:
    values = {
        "indicator_id": "renewable_energy_percentage",
        "raw_value": "72 percent",
        "raw_number": 72.0,
        "raw_unit": "percent",
        "source_description": (
            "The value appears beside the renewable-energy label."
        ),
        "confidence": 0.91,
    }
    values.update(updates)
    return VisualMetricClaim(**values)


def test_extract_unvalidated_evidence_from_relevant_chart() -> None:
    """An explicit visual value should remain traceable and unvalidated."""

    provider = FakeVisualProvider((_claim(),))
    rendered: list[str] = []
    result = VisualUnderstandingService(
        catalog=load_metric_catalog(CATALOG_PATH),
        provider=provider,
    ).analyze(
        document=_document(),
        pages=(_page(_region()),),
        render_region=lambda page, region: (
            rendered.append(region.region_id) or b"exact-png-crop"
        ),
    )

    assert rendered == ["page_1_chart_1"]
    assert provider.requests[0].image_png == b"exact-png-crop"
    assert len(result.evidence_items) == 1

    evidence = result.evidence_items[0]

    assert evidence.normalized_value == 72.0
    assert evidence.unit == "percent"
    assert evidence.validation_status is EvidenceValidationStatus.UNVALIDATED
    assert "page 1, visual region page_1_chart_1" in (
        evidence.source_locator
    )
    assert (
        result.report.decisions[0].provider_status
        is VisualProviderStatus.SUCCEEDED
    )


def test_skip_logo_without_rendering_or_provider_call() -> None:
    """Decorative regions must not consume model calls."""

    provider = FakeVisualProvider((_claim(),))
    rendered: list[str] = []
    result = VisualUnderstandingService(
        catalog=load_metric_catalog(CATALOG_PATH),
        provider=provider,
    ).analyze(
        document=_document(),
        pages=(
            _page(
                _region(
                    region_id="page_1_logo_1",
                    kind=VisualRegionKind.LOGO,
                    caption="Company logo",
                )
            ),
        ),
        render_region=lambda page, region: (
            rendered.append(region.region_id) or b"unused"
        ),
    )

    assert rendered == []
    assert provider.requests == []
    assert result.evidence_items == ()
    assert (
        result.report.decisions[0].provider_status
        is VisualProviderStatus.SKIPPED
    )


def test_report_rejected_visual_claim_without_using_it() -> None:
    """A provider claim cannot detach its number from the visible value."""

    provider = FakeVisualProvider(
        (_claim(raw_value="72 percent", raw_number=27.0),)
    )
    result = VisualUnderstandingService(
        catalog=load_metric_catalog(CATALOG_PATH),
        provider=provider,
    ).analyze(
        document=_document(),
        pages=(_page(_region()),),
        render_region=lambda page, region: b"png",
    )

    assert result.evidence_items == ()
    decision = result.report.decisions[0]
    assert len(decision.rejected_claims) == 1
    assert "absent" in decision.rejected_claims[0].reason


def test_reject_visual_claim_with_unit_absent_from_raw_value() -> None:
    """A provider cannot attach a unit the copied value does not show."""

    provider = FakeVisualProvider(
        (_claim(raw_value="72", raw_unit="percent"),)
    )
    result = VisualUnderstandingService(
        catalog=load_metric_catalog(CATALOG_PATH),
        provider=provider,
    ).analyze(
        document=_document(),
        pages=(_page(_region()),),
        render_region=lambda page, region: b"png",
    )

    assert result.evidence_items == ()
    assert "unit is absent" in (
        result.report.decisions[0].rejected_claims[0].reason
    )


def test_relevant_chart_is_audited_when_provider_is_disabled() -> None:
    """Disabled multimodal processing should be explicit, not silent."""

    result = VisualUnderstandingService(
        catalog=load_metric_catalog(CATALOG_PATH),
    ).analyze(
        document=_document(),
        pages=(_page(_region()),),
        render_region=lambda page, region: b"unused",
    )

    assert result.evidence_items == ()
    assert (
        result.report.decisions[0].provider_status
        is VisualProviderStatus.DISABLED
    )
