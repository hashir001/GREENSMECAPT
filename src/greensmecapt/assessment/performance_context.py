"""Qualify raw environmental measures before performance comparison."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.evidence_eligibility import (
    is_current_reviewed_evidence,
)
from greensmecapt.document_intelligence.semantics import (
    MetricCatalog,
    MetricDimension,
    MetricValueNature,
)
from greensmecapt.domain import EvidenceItem

NonBlank = Annotated[str, Field(min_length=1)]


class PerformanceContextModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ComparisonContextState(StrEnum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    NEEDS_REVIEW = "needs_review"
    NO_MEASUREMENT = "no_measurement"


class MetricComparisonContext(PerformanceContextModel):
    context_id: NonBlank
    sme_id: NonBlank
    indicator_id: NonBlank
    reporting_period: str | None = Field(default=None, min_length=1)
    operational_scope: str | None = Field(default=None, min_length=1)
    denominator_value: float | None = Field(default=None, gt=0.0)
    denominator_unit: str | None = Field(default=None, min_length=1)
    baseline_value: float | None = Field(default=None, ge=0.0)
    benchmark_value: float | None = Field(default=None, ge=0.0)
    target_value: float | None = Field(default=None, ge=0.0)
    reference_unit: str | None = Field(default=None, min_length=1)
    source_ids: tuple[NonBlank, ...] = ()
    narrative: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if (self.denominator_value is None) != (self.denominator_unit is None):
            raise ValueError("A denominator requires both value and unit.")
        references = (self.baseline_value, self.benchmark_value, self.target_value)
        if any(value is not None for value in references) and not self.reference_unit:
            raise ValueError("Baseline, benchmark or target values require a unit.")
        quantitative = self.denominator_value is not None or any(
            value is not None for value in references
        )
        if quantitative and not self.source_ids:
            raise ValueError("Quantitative comparison context requires a source.")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Comparison-context source IDs must be unique.")
        return self


class MetricContextAssessment(PerformanceContextModel):
    indicator_id: NonBlank
    metric_name: NonBlank
    state: ComparisonContextState
    measurement_value: float | None = None
    measurement_unit: str | None = None
    reporting_period: str | None = None
    operational_scope: str | None = None
    denominator_value: float | None = None
    denominator_unit: str | None = None
    intensity_value: float | None = None
    intensity_unit: str | None = None
    baseline_value: float | None = None
    benchmark_value: float | None = None
    target_value: float | None = None
    reference_unit: str | None = None
    source_ids: tuple[str, ...] = ()
    missing_requirements: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


class EnvironmentalPerformanceContextProfile(PerformanceContextModel):
    sme_id: NonBlank
    metric_catalog_id: NonBlank
    metric_catalog_version: NonBlank
    metrics: tuple[MetricContextAssessment, ...] = Field(min_length=1)

    @property
    def comparison_ready_count(self) -> int:
        return sum(item.state is ComparisonContextState.READY for item in self.metrics)


def build_performance_context_profile(
    *,
    sme_id: str,
    catalog: MetricCatalog,
    evidence_items: Sequence[EvidenceItem] = (),
    contexts: Sequence[MetricComparisonContext] = (),
) -> EnvironmentalPerformanceContextProfile:
    """Assess context sufficiency; never treat an absolute total as performance."""

    if any(item.sme_id != sme_id for item in contexts):
        raise ValueError("Every metric context must belong to the SME.")
    context_by_metric: dict[str, MetricComparisonContext] = {}
    known_ids = {metric.indicator_id for metric in catalog.metrics}
    for context in contexts:
        if context.indicator_id not in known_ids:
            raise ValueError(f"Unknown metric context: {context.indicator_id}")
        if context.indicator_id in context_by_metric:
            raise ValueError(f"Duplicate metric context: {context.indicator_id}")
        context_by_metric[context.indicator_id] = context

    accepted = [
        item
        for item in evidence_items
        if is_current_reviewed_evidence(item)
    ]
    return EnvironmentalPerformanceContextProfile(
        sme_id=sme_id,
        metric_catalog_id=catalog.catalog_id,
        metric_catalog_version=catalog.version,
        metrics=tuple(
            _assess_metric(
                metric,
                [item for item in accepted if item.indicator_id == metric.indicator_id],
                context_by_metric.get(metric.indicator_id),
            )
            for metric in catalog.metrics
            if metric.dimension is MetricDimension.ENVIRONMENTAL_PERFORMANCE
            and metric.value_nature is not MetricValueNature.ACTIVITY_DENOMINATOR
        ),
    )


def _assess_metric(metric, evidence, context):
    numeric = [
        item for item in evidence
        if isinstance(item.normalized_value, (int, float))
        and not isinstance(item.normalized_value, bool)
    ]
    signatures = {
        (float(item.normalized_value), item.unit, item.reporting_period, item.scope)
        for item in numeric
    }
    source_ids = tuple(sorted({
        *(item.evidence_id for item in numeric),
        *(context.source_ids if context else ()),
    }))
    if len(signatures) > 1:
        return MetricContextAssessment(
            indicator_id=metric.indicator_id,
            metric_name=metric.name,
            state=ComparisonContextState.NEEDS_REVIEW,
            source_ids=source_ids,
            issues=("Accepted measurements conflict or cover different periods/scopes.",),
        )
    if not numeric:
        return MetricContextAssessment(
            indicator_id=metric.indicator_id,
            metric_name=metric.name,
            state=ComparisonContextState.NO_MEASUREMENT,
            source_ids=source_ids,
            missing_requirements=metric.comparison_requirements,
        )

    item = numeric[0]
    period = (
        context.reporting_period
        if context and context.reporting_period
        else item.reporting_period
    )
    scope = (
        context.operational_scope
        if context and context.operational_scope
        else item.scope
    )
    missing: list[str] = []
    for requirement in metric.comparison_requirements:
        has_denominator = bool(context and context.denominator_value is not None)
        has_reference = bool(
            context
            and any(
                value is not None
                for value in (
                    context.baseline_value,
                    context.benchmark_value,
                    context.target_value,
                )
            )
        )
        if requirement == "reporting_period" and not period:
            missing.append(requirement)
        elif "scope" in requirement and not scope:
            missing.append(requirement)
        elif (
            "denominator" in requirement
            and any(token in requirement for token in ("baseline", "benchmark"))
            and not (has_denominator or has_reference)
        ):
            missing.append(requirement)
        elif "denominator" in requirement and not has_denominator:
            missing.append(requirement)
        elif (
            any(token in requirement for token in ("baseline", "benchmark"))
            and "denominator" not in requirement
            and not has_reference
        ):
            missing.append(requirement)
        elif "sector_applicability" in requirement and not (context and context.narrative):
            missing.append(requirement)

    intensity = None
    intensity_unit = None
    if context and context.denominator_value is not None:
        intensity = float(item.normalized_value) / context.denominator_value
        intensity_unit = f"{item.unit}_per_{context.denominator_unit}"

    return MetricContextAssessment(
        indicator_id=metric.indicator_id,
        metric_name=metric.name,
        state=(ComparisonContextState.INCOMPLETE if missing else ComparisonContextState.READY),
        measurement_value=float(item.normalized_value),
        measurement_unit=item.unit,
        reporting_period=period,
        operational_scope=scope,
        denominator_value=context.denominator_value if context else None,
        denominator_unit=context.denominator_unit if context else None,
        intensity_value=intensity,
        intensity_unit=intensity_unit,
        baseline_value=context.baseline_value if context else None,
        benchmark_value=context.benchmark_value if context else None,
        target_value=context.target_value if context else None,
        reference_unit=context.reference_unit if context else None,
        source_ids=source_ids,
        missing_requirements=tuple(missing),
    )
