"""Evidence-grounded financial and investment assessment without scoring."""

import json
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.domain import EvidenceItem, EvidenceValidationStatus

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
    allowed_units: tuple[NonBlank, ...] = Field(min_length=1)
    requires_reporting_period: bool = False
    description: NonBlank


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
    state: FinancialObservationState
    value: float | None = None
    unit: str | None = None
    reporting_period: str | None = None
    comparison_basis: str | None = None
    source_ids: tuple[str, ...] = ()
    narrative: str | None = None
    issues: tuple[str, ...] = ()


class FinancialDerivedIndicator(FinancialModel):
    indicator_id: NonBlank
    value: float
    unit: NonBlank
    source_metric_ids: tuple[NonBlank, ...] = Field(min_length=2)
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
        if (
            evidence.validation_status is EvidenceValidationStatus.ACCEPTED
            and evidence.indicator_id in definitions
        ):
            evidence_by_metric[evidence.indicator_id].append(evidence)

    results = tuple(
        _resolve_metric(
            definition,
            supplied.get(definition.metric_id),
            evidence_by_metric.get(definition.metric_id, ()),
        )
        for definition in policy.metrics
    )
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
            state=state,
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
            state=FinancialObservationState.REPORTED,
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
    if definition.metric_id == "revenue_growth_percentage" and not observation.comparison_basis:
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
        state=state,
        source_ids=source_ids,
        issues=issues,
    )


def _derive_indicators(
    results: Sequence[FinancialMetricResult],
) -> tuple[FinancialDerivedIndicator, ...]:
    by_id = {item.metric_id: item for item in results}
    requested = by_id.get("requested_amount")
    project_cost = by_id.get("project_cost")
    savings = by_id.get("expected_annual_savings")
    derived: list[FinancialDerivedIndicator] = []

    if _compatible_amounts(requested, project_cost) and project_cost.value:
        derived.append(
            FinancialDerivedIndicator(
                indicator_id="requested_share_of_project_cost",
                value=requested.value / project_cost.value,
                unit="ratio",
                source_metric_ids=("requested_amount", "project_cost"),
                interpretation=(
                    "Funding-request coverage only; it is not a viability score."
                ),
            )
        )
    if _compatible_annual_savings(project_cost, savings) and savings.value and savings.value > 0:
        derived.append(
            FinancialDerivedIndicator(
                indicator_id="simple_payback_years",
                value=project_cost.value / savings.value,
                unit="years",
                source_metric_ids=("project_cost", "expected_annual_savings"),
                interpretation=(
                    "Undiscounted screening estimate; financing and investment "
                    "approval remain outside the platform."
                ),
            )
        )
    return tuple(derived)


def _compatible_amounts(
    left: FinancialMetricResult | None,
    right: FinancialMetricResult | None,
) -> bool:
    return bool(
        left
        and right
        and left.state is FinancialObservationState.REPORTED
        and right.state is FinancialObservationState.REPORTED
        and left.unit
        and left.unit.casefold() == (right.unit or "").casefold()
        and left.value is not None
        and right.value is not None
    )


def _compatible_annual_savings(
    cost: FinancialMetricResult | None,
    savings: FinancialMetricResult | None,
) -> bool:
    if not cost or not savings or not cost.unit or not savings.unit:
        return False
    return bool(
        cost.state is FinancialObservationState.REPORTED
        and savings.state is FinancialObservationState.REPORTED
        and savings.unit.casefold() == f"{cost.unit.casefold()}_per_year"
        and cost.value is not None
        and savings.value is not None
    )
