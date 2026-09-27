"""Tests for contextualizing raw environmental measurements."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.assessment.performance_context import (
    MetricComparisonContext,
    build_performance_context_profile,
)
from greensmecapt.document_intelligence.semantics import load_metric_catalog
from greensmecapt.domain import EvidenceItem, EvidenceValidationStatus

CATALOG = load_metric_catalog(Path("config/metric_catalog.development.json"))


def _evidence(value: float, period: str | None = "FY2025") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"evidence_{sha256(str(value).encode()).hexdigest()[:10]}",
        sme_id="sme_001",
        document_id="document_utility",
        indicator_id="electricity_consumption_kwh",
        criterion_id="energy_efficiency",
        raw_value=f"{value} kWh",
        normalized_value=value,
        unit="kwh",
        reporting_period=period,
        source_locator="page 1",
        extraction_method="test",
        extractor_name="test",
        validation_status=EvidenceValidationStatus.ACCEPTED,
    )


def test_raw_total_is_not_performance_without_context() -> None:
    profile = build_performance_context_profile(
        sme_id="sme_001",
        catalog=CATALOG,
        evidence_items=(_evidence(20_000),),
    )
    electricity = next(
        item for item in profile.metrics
        if item.indicator_id == "electricity_consumption_kwh"
    )

    assert electricity.state == "incomplete"
    assert electricity.measurement_value == 20_000
    assert "operational_scope" in electricity.missing_requirements
    assert "denominator_or_activity_level" in electricity.missing_requirements


def test_denominator_and_reference_make_measurement_comparison_ready() -> None:
    context = MetricComparisonContext(
        context_id="context_electricity",
        sme_id="sme_001",
        indicator_id="electricity_consumption_kwh",
        operational_scope="Abu Dhabi production facility",
        denominator_value=1_000,
        denominator_unit="units_produced",
        baseline_value=23_000,
        reference_unit="kwh",
        source_ids=("document_utility",),
    )
    profile = build_performance_context_profile(
        sme_id="sme_001",
        catalog=CATALOG,
        evidence_items=(_evidence(20_000),),
        contexts=(context,),
    )
    electricity = next(
        item for item in profile.metrics
        if item.indicator_id == "electricity_consumption_kwh"
    )

    assert electricity.state == "ready"
    assert electricity.intensity_value == 20.0
    assert electricity.intensity_unit == "kwh_per_units_produced"


def test_conflicting_measurements_require_review() -> None:
    profile = build_performance_context_profile(
        sme_id="sme_001",
        catalog=CATALOG,
        evidence_items=(_evidence(20_000), _evidence(25_000)),
    )
    electricity = next(
        item for item in profile.metrics
        if item.indicator_id == "electricity_consumption_kwh"
    )

    assert electricity.state == "needs_review"
    assert electricity.issues
