"""Tests for environmental metric comparison requirements."""

from pathlib import Path

from greensmecapt.document_intelligence.semantics import (
    MetricAssessmentUse,
    load_metric_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    PROJECT_ROOT
    / "config"
    / "metric_catalog.development.json"
)


def test_absolute_environmental_values_require_context() -> None:
    catalog = load_metric_catalog(CATALOG_PATH)
    metrics = {
        metric.indicator_id: metric for metric in catalog.metrics
    }

    for indicator_id in (
        "electricity_consumption_kwh",
        "water_consumption_m3",
        "total_ghg_emissions_tco2e",
    ):
        metric = metrics[indicator_id]
        assert metric.requires_comparison_context
        assert "reporting_period" in metric.comparison_requirements
        assert any(
            "denominator" in requirement
            for requirement in metric.comparison_requirements
        )


def test_ratio_metric_still_declares_scope_and_period() -> None:
    catalog = load_metric_catalog(CATALOG_PATH)
    renewable = next(
        metric
        for metric in catalog.metrics
        if metric.indicator_id == "renewable_energy_percentage"
    )

    assert renewable.assessment_use is MetricAssessmentUse.DIRECT_RATIO
    assert set(renewable.comparison_requirements) == {
        "reporting_period",
        "operational_scope",
    }
