"""Evidence-grounded financial and investment assessment without scoring."""

import json
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from math import isclose
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.evidence_eligibility import (
    describes_current_state,
    is_reviewed_evidence,
)
from greensmecapt.domain import EvidenceItem

NonBlank = Annotated[str, Field(min_length=1)]


class FinancialModel(BaseModel):
    """Provide strict immutable financial-assessment contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class FinancialMetricGroup(StrEnum):
    BUSINESS_HEALTH = "business_health"
    INVESTMENT_CASE = "investment_case"


class FinancialMetricImportance(StrEnum):
    CORE = "core"
    SUPPORTING = "supporting"


class FinancialMetricRole(StrEnum):
    """Separate statement inputs, derived indicators and project inputs."""

    SOURCE_INPUT = "source_input"
    DERIVED_INDICATOR = "derived_indicator"
    INVESTMENT_INPUT = "investment_input"


class FinancialMetricDirection(StrEnum):
    """Record preference without imposing an uncalibrated threshold."""

    BENEFIT = "benefit"
    COST = "cost"
    CONTEXT_ONLY = "context_only"


class FinancialCalculationMethod(StrEnum):
    """Name the transparent calculation intended for a derived indicator."""

    RATIO = "ratio"
    RATIO_PERCENTAGE = "ratio_percentage"
    GROWTH_PERCENTAGE = "growth_percentage"
    SIMPLE_PAYBACK_YEARS = "simple_payback_years"


class FinancialValueOrigin(StrEnum):
    """Distinguish submitted, extracted and transparently calculated values."""

    UNKNOWN = "unknown"
    REPORTED = "reported"
    EXTRACTED = "extracted"
    CALCULATED = "calculated"
    REPORTED_AND_CALCULATED = "reported_and_calculated"


class FinancialObservationState(StrEnum):
    REPORTED = "reported"
    UNKNOWN = "unknown"
    NOT_MEASURED = "not_measured"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_REVIEW = "needs_review"


class FinancialAssessmentStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class FinancialMetricDefinition(FinancialModel):
    metric_id: NonBlank
    title: NonBlank
    group: FinancialMetricGroup
    importance: FinancialMetricImportance
    role: FinancialMetricRole
    direction: FinancialMetricDirection
    allowed_units: tuple[NonBlank, ...] = Field(min_length=1)
    requires_reporting_period: bool = False
    requires_comparison_basis: bool = False
    calculation_method: FinancialCalculationMethod | None = None
    input_metric_ids: tuple[NonBlank, ...] = ()
    description: NonBlank

    @model_validator(mode="after")
    def validate_calculation_contract(self) -> Self:
        if self.role is FinancialMetricRole.DERIVED_INDICATOR:
            if self.calculation_method is None or len(self.input_metric_ids) < 2:
                raise ValueError(
                    "A derived financial indicator requires a calculation "
                    "method and at least two input metrics."
                )
        elif self.calculation_method is not None or self.input_metric_ids:
            raise ValueError(
                "Only derived financial indicators may declare calculations."
            )
        return self


class FinancialAssessmentPolicy(FinancialModel):
    policy_id: NonBlank
    version: NonBlank
    status: Literal["development", "approved"] = "development"
    calibration_status: Literal[
        "requires_financial_calibration",
        "calibrated",
    ] = "requires_financial_calibration"
    metrics: tuple[FinancialMetricDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> Self:
        metric_ids = [item.metric_id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("Financial metric IDs must be unique.")
        known = set(metric_ids)
        for metric in self.metrics:
            unknown = set(metric.input_metric_ids) - known
            if unknown:
                raise ValueError(
                    f"Financial calculation references unknown metrics: "
                    f"{sorted(unknown)}"
                )
            if metric.metric_id in metric.input_metric_ids:
                raise ValueError("A financial metric cannot depend on itself.")
        return self


class FinancialObservation(FinancialModel):
    observation_id: NonBlank
    sme_id: NonBlank
    metric_id: NonBlank
    state: FinancialObservationState
    value: float | None = None
    unit: str | None = Field(default=None, min_length=1)
    reporting_period: str | None = Field(default=None, min_length=1)
    comparison_basis: str | None = Field(default=None, min_length=1)
    source_ids: tuple[NonBlank, ...] = ()
    narrative: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Financial source IDs must be unique.")
        if self.state is FinancialObservationState.REPORTED:
            if self.value is None or self.unit is None or not self.source_ids:
                raise ValueError(
                    "A reported financial value requires a value, unit and source."
                )
        elif self.value is not None or self.unit is not None:
            raise ValueError(
                "An unresolved financial observation cannot contain a value or unit."
            )
        return self


class FinancialMetricResult(FinancialModel):
    metric_id: NonBlank
    title: NonBlank
    group: FinancialMetricGroup
    importance: FinancialMetricImportance
    role: FinancialMetricRole
    direction: FinancialMetricDirection
    state: FinancialObservationState
    origin: FinancialValueOrigin = FinancialValueOrigin.UNKNOWN
    value: float | None = None
    unit: str | None = None
    reporting_period: str | None = None
    comparison_basis: str | None = None
    source_ids: tuple[str, ...] = ()
    narrative: str | None = None
    issues: tuple[str, ...] = ()
    calculation_method: FinancialCalculationMethod | None = None
    calculation_formula: str | None = None
    calculation_input_metric_ids: tuple[str, ...] = ()


class FinancialDerivedIndicator(FinancialModel):
    indicator_id: NonBlank
    value: float
    unit: NonBlank
    source_metric_ids: tuple[NonBlank, ...] = Field(min_length=2)
    source_ids: tuple[NonBlank, ...] = Field(min_length=1)
    calculation_method: FinancialCalculationMethod
    formula: NonBlank
    input_values: dict[str, float] = Field(min_length=2)
    interpretation: NonBlank


class FinancialInvestmentAssessment(FinancialModel):
    sme_id: NonBlank
    policy_id: NonBlank
    policy_version: NonBlank
    calibration_status: NonBlank
    status: FinancialAssessmentStatus
    core_coverage_ratio: float = Field(ge=0.0, le=1.0)
    metrics: tuple[FinancialMetricResult, ...] = Field(min_length=1)
    derived_indicators: tuple[FinancialDerivedIndicator, ...] = ()
    aggregate_score: None = None


def load_financial_policy(path: str | Path) -> FinancialAssessmentPolicy:
    """Load a strict versioned financial-assessment policy."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return FinancialAssessmentPolicy.model_validate(data)


def build_financial_assessment(
    *,
    sme_id: str,
    policy: FinancialAssessmentPolicy,
    observations: Sequence[FinancialObservation] = (),
    evidence_items: Sequence[EvidenceItem] = (),
) -> FinancialInvestmentAssessment:
    """Resolve reviewed inputs while keeping finance separate from Green Score."""

    if any(item.sme_id != sme_id for item in observations):
        raise ValueError("Every financial observation must belong to the SME.")
    if any(item.sme_id != sme_id for item in evidence_items):
        raise ValueError("Every financial evidence item must belong to the SME.")

    definitions = {item.metric_id: item for item in policy.metrics}
    supplied: dict[str, FinancialObservation] = {}
    for observation in observations:
        if observation.metric_id not in definitions:
            raise ValueError(f"Unknown financial metric: {observation.metric_id}")
        if observation.metric_id in supplied:
            raise ValueError(
                f"Duplicate financial observation: {observation.metric_id}"
            )
        supplied[observation.metric_id] = observation

    evidence_by_metric: dict[str, list[EvidenceItem]] = defaultdict(list)
    for evidence in evidence_items:
        definition = definitions.get(evidence.indicator_id)
        if definition is None or not is_reviewed_evidence(evidence):
            continue
        if (
            definition.role is FinancialMetricRole.SOURCE_INPUT
            and not describes_current_state(evidence)
        ):
            continue
        evidence_by_metric[evidence.indicator_id].append(evidence)

    resolved = tuple(
        _resolve_metric(
            definition,
            supplied.get(definition.metric_id),
            evidence_by_metric.get(definition.metric_id, ()),
        )
        for definition in policy.metrics
    )
    results = _calculate_derived_metrics(policy, resolved)
    core = [
        item
        for item in results
        if item.importance is FinancialMetricImportance.CORE
    ]
    ready_core = sum(
        item.state is FinancialObservationState.REPORTED for item in core
    )
    coverage = ready_core / len(core) if core else 0.0
    if coverage == 1.0:
        status = FinancialAssessmentStatus.COMPLETE
    elif ready_core:
        status = FinancialAssessmentStatus.PARTIAL
    else:
        status = FinancialAssessmentStatus.INSUFFICIENT

    return FinancialInvestmentAssessment(
        sme_id=sme_id,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        calibration_status=policy.calibration_status,
        status=status,
        core_coverage_ratio=coverage,
        metrics=results,
        derived_indicators=_derive_indicators(results),
    )


def _resolve_metric(
    definition: FinancialMetricDefinition,
    supplied: FinancialObservation | None,
    evidence: Sequence[EvidenceItem],
) -> FinancialMetricResult:
    if supplied is not None:
        issues = _validate_reported(definition, supplied)
        state = (
            FinancialObservationState.NEEDS_REVIEW
            if issues
            else supplied.state
        )
        return FinancialMetricResult(
            metric_id=definition.metric_id,
            title=definition.title,
            group=definition.group,
            importance=definition.importance,
            role=definition.role,
            direction=definition.direction,
            state=state,
            origin=(
                FinancialValueOrigin.REPORTED
                if supplied.state is FinancialObservationState.REPORTED
                else FinancialValueOrigin.UNKNOWN
            ),
            value=supplied.value if not issues else None,
            unit=supplied.unit if not issues else None,
            reporting_period=supplied.reporting_period,
            comparison_basis=supplied.comparison_basis,
            source_ids=supplied.source_ids,
            narrative=supplied.narrative,
            issues=issues,
        )

    numeric = [
        item
        for item in evidence
        if isinstance(item.normalized_value, (int, float))
        and not isinstance(item.normalized_value, bool)
    ]
    signatures = {
        (float(item.normalized_value), item.unit, item.reporting_period)
        for item in numeric
    }
    if len(signatures) > 1:
        return _empty_result(
            definition,
            FinancialObservationState.NEEDS_REVIEW,
            tuple(sorted(item.evidence_id for item in numeric)),
            ("Accepted financial sources conflict or cover different periods.",),
        )
    if numeric:
        item = numeric[0]
        synthetic = FinancialObservation(
            observation_id=f"evidence:{item.evidence_id}",
            sme_id=item.sme_id,
            metric_id=definition.metric_id,
            state=FinancialObservationState.REPORTED,
            value=float(item.normalized_value),
            unit=item.unit,
            reporting_period=item.reporting_period,
            source_ids=tuple(sorted(source.evidence_id for source in numeric)),
        )
        issues = _validate_reported(definition, synthetic)
        if issues:
            return _empty_result(
                definition,
                FinancialObservationState.NEEDS_REVIEW,
                synthetic.source_ids,
                issues,
            )
        return FinancialMetricResult(
            metric_id=definition.metric_id,
            title=definition.title,
            group=definition.group,
            importance=definition.importance,
            role=definition.role,
            direction=definition.direction,
            state=FinancialObservationState.REPORTED,
            origin=FinancialValueOrigin.EXTRACTED,
            value=synthetic.value,
            unit=synthetic.unit,
            reporting_period=synthetic.reporting_period,
            source_ids=synthetic.source_ids,
        )
    return _empty_result(definition, FinancialObservationState.UNKNOWN)


def _validate_reported(
    definition: FinancialMetricDefinition,
    observation: FinancialObservation,
) -> tuple[str, ...]:
    if observation.state is not FinancialObservationState.REPORTED:
        return ()
    issues: list[str] = []
    allowed = {unit.casefold() for unit in definition.allowed_units}
    if observation.unit is None or observation.unit.casefold() not in allowed:
        issues.append("The reported unit is not allowed for this metric.")
    if definition.requires_reporting_period and not observation.reporting_period:
        issues.append("This metric requires a reporting period.")
    if definition.requires_comparison_basis and not observation.comparison_basis:
        issues.append("Revenue growth requires an explicit comparison basis.")
    return tuple(issues)


def _empty_result(
    definition: FinancialMetricDefinition,
    state: FinancialObservationState,
    source_ids: tuple[str, ...] = (),
    issues: tuple[str, ...] = (),
) -> FinancialMetricResult:
    return FinancialMetricResult(
        metric_id=definition.metric_id,
        title=definition.title,
        group=definition.group,
        importance=definition.importance,
        role=definition.role,
        direction=definition.direction,
        state=state,
        source_ids=source_ids,
        issues=issues,
    )


def _calculate_derived_metrics(
    policy: FinancialAssessmentPolicy,
    results: Sequence[FinancialMetricResult],
) -> tuple[FinancialMetricResult, ...]:
    by_id = {item.metric_id: item for item in results}
    for definition in policy.metrics:
        if definition.role is not FinancialMetricRole.DERIVED_INDICATOR:
            continue
        inputs = tuple(by_id[metric_id] for metric_id in definition.input_metric_ids)
        if not all(
            item.state is FinancialObservationState.REPORTED
            and item.value is not None
            and item.unit is not None
            for item in inputs
        ):
            continue
        calculated, issue = _calculate_value(definition, inputs)
        existing = by_id[definition.metric_id]
        if issue:
            by_id[definition.metric_id] = existing.model_copy(
                update={
                    "state": FinancialObservationState.NEEDS_REVIEW,
                    "value": None,
                    "unit": None,
                    "origin": FinancialValueOrigin.UNKNOWN,
                    "issues": (*existing.issues, issue),
                }
            )
            continue
        assert calculated is not None
        value, unit, formula = calculated
        if (
            existing.state is FinancialObservationState.REPORTED
            and existing.value is not None
            and not isclose(existing.value, value, rel_tol=1e-6, abs_tol=1e-6)
        ):
            by_id[definition.metric_id] = existing.model_copy(
                update={
                    "state": FinancialObservationState.NEEDS_REVIEW,
                    "value": None,
                    "unit": None,
                    "origin": FinancialValueOrigin.UNKNOWN,
                    "issues": (
                        *existing.issues,
                        "The reported indicator conflicts with its calculated value.",
                    ),
                }
            )
            continue
        source_ids = tuple(sorted({
            *existing.source_ids,
            *(source for item in inputs for source in item.source_ids),
        }))
        origin = (
            FinancialValueOrigin.REPORTED_AND_CALCULATED
            if existing.state is FinancialObservationState.REPORTED
            else FinancialValueOrigin.CALCULATED
        )
        by_id[definition.metric_id] = FinancialMetricResult(
            metric_id=definition.metric_id,
            title=definition.title,
            group=definition.group,
            importance=definition.importance,
            role=definition.role,
            direction=definition.direction,
            state=FinancialObservationState.REPORTED,
            origin=origin,
            value=value,
            unit=unit,
            reporting_period=inputs[0].reporting_period,
            comparison_basis=_calculation_basis(definition, inputs),
            source_ids=source_ids,
            calculation_method=definition.calculation_method,
            calculation_formula=formula,
            calculation_input_metric_ids=definition.input_metric_ids,
        )
    return tuple(by_id[item.metric_id] for item in results)


def _calculate_value(
    definition: FinancialMetricDefinition,
    inputs: tuple[FinancialMetricResult, ...],
) -> tuple[tuple[float, str, str] | None, str | None]:
    left, right = inputs
    assert left.value is not None and right.value is not None
    assert left.unit is not None and right.unit is not None
    method = definition.calculation_method
    if method is FinancialCalculationMethod.SIMPLE_PAYBACK_YEARS:
        expected = f"{left.unit.casefold()}_per_year"
        if right.unit.casefold() != expected:
            return None, "Project cost and annual savings use incompatible currencies."
    elif left.unit.casefold() != right.unit.casefold():
        return None, "Calculation inputs use incompatible units or currencies."
    if right.value == 0:
        return None, "The calculation denominator is zero."
    if method is FinancialCalculationMethod.GROWTH_PERCENTAGE:
        value = (left.value - right.value) / right.value * 100
        formula = f"(({left.metric_id} - {right.metric_id}) / {right.metric_id}) × 100"
    elif method is FinancialCalculationMethod.RATIO_PERCENTAGE:
        value = left.value / right.value * 100
        formula = f"({left.metric_id} / {right.metric_id}) × 100"
    else:
        value = left.value / right.value
        formula = f"{left.metric_id} / {right.metric_id}"
    return (value, definition.allowed_units[0], formula), None


def _calculation_basis(
    definition: FinancialMetricDefinition,
    inputs: tuple[FinancialMetricResult, ...],
) -> str | None:
    if definition.calculation_method is FinancialCalculationMethod.GROWTH_PERCENTAGE:
        return f"{inputs[0].reporting_period} compared with {inputs[1].reporting_period}"
    return None


def _derive_indicators(
    results: Sequence[FinancialMetricResult],
) -> tuple[FinancialDerivedIndicator, ...]:
    interpretations = {
        "roa_percentage": "Profitability indicator; no approval threshold is implied.",
        "revenue_growth_percentage": "Period-on-period growth; no approval threshold is implied.",
        "current_ratio": "Liquidity indicator; no approval threshold is implied.",
        "debt_to_assets_percentage": "Leverage indicator; no approval threshold is implied.",
        "requested_share_of_project_cost": (
            "Funding-request coverage only; it is not a viability score."
        ),
        "simple_payback_years": (
            "Undiscounted screening estimate; financing and investment approval "
            "remain outside the platform."
        ),
    }
    return tuple(
        FinancialDerivedIndicator(
            indicator_id=item.metric_id,
            value=item.value,
            unit=item.unit,
            source_metric_ids=item.calculation_input_metric_ids,
            source_ids=item.source_ids,
            calculation_method=item.calculation_method,
            formula=item.calculation_formula,
            input_values={
                input_id: next(
                    source.value
                    for source in results
                    if source.metric_id == input_id and source.value is not None
                )
                for input_id in item.calculation_input_metric_ids
            },
            interpretation=interpretations[item.metric_id],
        )
        for item in results
        if item.role is FinancialMetricRole.DERIVED_INDICATOR
        and item.state is FinancialObservationState.REPORTED
        and item.origin in {
            FinancialValueOrigin.CALCULATED,
            FinancialValueOrigin.REPORTED_AND_CALCULATED,
        }
        and item.value is not None
        and item.unit is not None
        and item.calculation_method is not None
        and item.calculation_formula is not None
    )
