"""Build reviewer-editable assessment inputs from accepted evidence."""

from collections import defaultdict
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.financial import (
    FinancialAssessmentPolicy,
    FinancialMetricRole,
    FinancialObservation,
    FinancialObservationState,
)
from greensmecapt.assessment.fuzzy_dematel import DematelSpecification
from greensmecapt.assessment.performance_context import MetricComparisonContext
from greensmecapt.assessment.readiness import (
    ReadinessObservation,
    readiness_observations_from_evidence,
)
from greensmecapt.document_intelligence.semantics import (
    MetricCatalog,
    MetricDimension,
    MetricValueNature,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
    StructuredInvestmentRecord,
)

NonBlank = Annotated[str, Field(min_length=1)]


class AutofillModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AutofillGap(AutofillModel):
    code: NonBlank
    field_id: NonBlank
    message: NonBlank
    source_ids: tuple[NonBlank, ...] = ()


class SectorProposal(AutofillModel):
    sector_id: NonBlank
    source_ids: tuple[NonBlank, ...]


class AssessmentAutofillResponse(AutofillModel):
    sme_id: NonBlank
    activity_description: NonBlank
    activity_description_source_ids: tuple[NonBlank, ...] = ()
    stage: str | None = None
    stage_source_ids: tuple[NonBlank, ...] = ()
    funding_purpose: str | None = None
    funding_purpose_source_ids: tuple[NonBlank, ...] = ()
    facts: dict[str, bool] = Field(default_factory=dict)
    fact_source_ids: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    financial_observations: tuple[FinancialObservation, ...] = ()
    readiness_observations: tuple[ReadinessObservation, ...] = ()
    metric_contexts: tuple[MetricComparisonContext, ...] = ()
    sector_proposals: tuple[SectorProposal, ...] = ()
    gaps: tuple[AutofillGap, ...] = ()


def build_assessment_autofill(
    *,
    record: StructuredInvestmentRecord,
    financial_policy: FinancialAssessmentPolicy,
    metric_catalog: MetricCatalog,
    readiness_specification: DematelSpecification,
) -> AssessmentAutofillResponse:
    """Convert accepted, non-conflicting evidence into editable form values."""

    accepted = tuple(
        item
        for item in record.evidence_items
        if item.validation_status is EvidenceValidationStatus.ACCEPTED
    )
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in accepted:
        grouped[item.indicator_id].append(item)

    gaps: list[AutofillGap] = []
    facts: dict[str, bool] = {}
    fact_sources: dict[str, tuple[str, ...]] = {}
    for indicator_id, items in grouped.items():
        if not indicator_id.startswith("activity_fact:"):
            continue
        fact_id = indicator_id.removeprefix("activity_fact:")
        values = {item.normalized_value for item in items}
        source_ids = _source_ids(items)
        if len(values) == 1 and isinstance(next(iter(values)), bool):
            facts[fact_id] = next(iter(values))
            fact_sources[fact_id] = source_ids
        else:
            gaps.append(_conflict_gap(fact_id, source_ids, "activity fact"))

    description, description_sources = _activity_description(record, grouped, gaps)
    stage, stage_sources = _single_text_claim(
        grouped, "business_stage", "business stage", gaps
    )
    funding_purpose, funding_sources = _single_text_claim(
        grouped, "funding_purpose", "funding purpose", gaps
    )
    financial = _financial_observations(
        record.sme.sme_id, grouped, financial_policy, gaps
    )
    contexts = _metric_contexts(record.sme.sme_id, grouped, metric_catalog, gaps)
    sectors = tuple(
        SectorProposal(
            sector_id=indicator_id.removeprefix("sector_activity:"),
            source_ids=_source_ids(items),
        )
        for indicator_id, items in sorted(grouped.items())
        if indicator_id.startswith("sector_activity:")
    )

    return AssessmentAutofillResponse(
        sme_id=record.sme.sme_id,
        activity_description=description,
        activity_description_source_ids=description_sources,
        stage=stage,
        stage_source_ids=stage_sources,
        funding_purpose=funding_purpose,
        funding_purpose_source_ids=funding_sources,
        facts=facts,
        fact_source_ids=fact_sources,
        financial_observations=financial,
        readiness_observations=readiness_observations_from_evidence(
            sme_id=record.sme.sme_id,
            specification=readiness_specification,
            evidence_items=record.evidence_items,
        ),
        metric_contexts=contexts,
        sector_proposals=sectors,
        gaps=tuple(gaps),
    )


def _activity_description(
    record: StructuredInvestmentRecord,
    grouped: dict[str, list[EvidenceItem]],
    gaps: list[AutofillGap],
) -> tuple[str, tuple[str, ...]]:
    claims: list[EvidenceItem] = []
    for field_id in ("products_and_services", "green_value_proposition"):
        items = grouped.get(f"company_profile:{field_id}", [])
        values = {str(item.normalized_value).strip() for item in items}
        if len(values) == 1:
            claims.append(items[0])
        elif len(values) > 1:
            gaps.append(
                _conflict_gap(field_id, _source_ids(items), "company context")
            )
    if claims:
        return " ".join(str(item.normalized_value).strip() for item in claims), _source_ids(claims)
    return (
        f"{record.sme.legal_name} operates in {record.sme.sector}.",
        (),
    )


def _single_text_claim(
    grouped: dict[str, list[EvidenceItem]],
    field_id: str,
    label: str,
    gaps: list[AutofillGap],
) -> tuple[str | None, tuple[str, ...]]:
    items = grouped.get(f"company_profile:{field_id}", [])
    if not items:
        return None, ()
    values = {str(item.normalized_value).strip() for item in items}
    sources = _source_ids(items)
    if len(values) != 1:
        gaps.append(_conflict_gap(field_id, sources, "company context"))
        return None, sources
    return next(iter(values)), sources


def _financial_observations(
    sme_id: str,
    grouped: dict[str, list[EvidenceItem]],
    policy: FinancialAssessmentPolicy,
    gaps: list[AutofillGap],
) -> tuple[FinancialObservation, ...]:
    observations: list[FinancialObservation] = []
    for metric in policy.metrics:
        if metric.role is FinancialMetricRole.DERIVED_INDICATOR:
            continue
        items = grouped.get(metric.metric_id, [])
        numeric = [item for item in items if _is_number(item.normalized_value)]
        if not numeric:
            continue
        signatures = {
            (float(item.normalized_value), item.unit, item.reporting_period)
            for item in numeric
        }
        sources = _source_ids(numeric)
        if len(signatures) != 1:
            gaps.append(_conflict_gap(metric.metric_id, sources, "financial value"))
            continue
        value, unit, period = next(iter(signatures))
        if not unit or unit not in metric.allowed_units:
            gaps.append(
                AutofillGap(
                    code="unsupported_unit",
                    field_id=metric.metric_id,
                    message="Accepted evidence uses a unit not allowed by the financial policy.",
                    source_ids=sources,
                )
            )
            continue
        observations.append(
            FinancialObservation(
                observation_id=f"autofill:{sme_id}:{metric.metric_id}",
                sme_id=sme_id,
                metric_id=metric.metric_id,
                state=FinancialObservationState.REPORTED,
                value=value,
                unit=unit,
                reporting_period=period,
                source_ids=sources,
            )
        )
    return tuple(observations)


def _metric_contexts(
    sme_id: str,
    grouped: dict[str, list[EvidenceItem]],
    catalog: MetricCatalog,
    gaps: list[AutofillGap],
) -> tuple[MetricComparisonContext, ...]:
    contexts: list[MetricComparisonContext] = []
    for metric in catalog.metrics:
        if (
            metric.dimension is not MetricDimension.ENVIRONMENTAL_PERFORMANCE
            or metric.value_nature is MetricValueNature.ACTIVITY_DENOMINATOR
        ):
            continue
        numeric = [
            item for item in grouped.get(metric.indicator_id, [])
            if _is_number(item.normalized_value)
        ]
        if not numeric:
            continue
        signatures = {(item.reporting_period, item.scope) for item in numeric}
        sources = _source_ids(numeric)
        if len(signatures) != 1:
            gaps.append(_conflict_gap(metric.indicator_id, sources, "measurement context"))
            continue
        period, scope = next(iter(signatures))
        contexts.append(
            MetricComparisonContext(
                context_id=f"autofill:{sme_id}:{metric.indicator_id}",
                sme_id=sme_id,
                indicator_id=metric.indicator_id,
                reporting_period=period,
                operational_scope=scope,
                source_ids=sources,
            )
        )
    return tuple(contexts)


def _source_ids(items: list[EvidenceItem] | tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    return tuple(sorted({item.evidence_id for item in items}))


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _conflict_gap(
    field_id: str,
    source_ids: tuple[str, ...],
    label: Literal[
        "activity fact",
        "financial value",
        "measurement context",
        "company context",
    ],
) -> AutofillGap:
    return AutofillGap(
        code="conflicting_accepted_evidence",
        field_id=field_id,
        message=f"Accepted evidence conflicts for this {label}; reviewer input is required.",
        source_ids=source_ids,
    )
