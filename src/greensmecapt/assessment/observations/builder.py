"""Resolve applicant responses and document evidence into observations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from greensmecapt.assessment.evidence_eligibility import (
    describes_current_state,
    is_reviewed_evidence,
)
from greensmecapt.assessment.observations.models import (
    CriterionObservation,
    CriterionResponse,
    ObservationCoverage,
    ObservationSet,
    ObservationStatus,
    ResponseKind,
)
from greensmecapt.assessment.profiles.models import (
    Applicability,
    AssessmentProfile,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
)

if TYPE_CHECKING:
    from greensmecapt.assessment.normalization.models import NumericScale


@dataclass(frozen=True)
class _Number:
    value: float
    unit: str | None
    period: str | None
    scope: str | None


def build_observations(
    profile: AssessmentProfile,
    *,
    responses: Sequence[CriterionResponse] = (),
    evidence_items: Sequence[EvidenceItem] = (),
    numeric_scoring_scales: Mapping[str, NumericScale] | None = None,
) -> ObservationSet:
    """Build observations without converting unknowns into scores."""

    _validate_unique(
        "response",
        [item.response_id for item in responses],
    )
    _validate_unique(
        "evidence",
        [item.evidence_id for item in evidence_items],
    )

    if any(
        item.sme_id != profile.sme_id
        for item in responses
    ):
        raise ValueError(
            "Every response must belong to the profile SME."
        )

    if any(
        item.sme_id != profile.sme_id
        for item in evidence_items
    ):
        raise ValueError(
            "Every evidence item must belong to the profile SME."
        )

    supplied_evidence_ids = {
        item.evidence_id for item in evidence_items
    }
    missing_support = {
        evidence_id
        for response in responses
        for evidence_id in response.supporting_evidence_ids
        if evidence_id not in supplied_evidence_ids
    }

    if missing_support:
        raise ValueError(
            "Responses reference evidence that was not supplied: "
            f"{sorted(missing_support)}"
        )

    decisions = {
        item.criterion_id: item
        for item in profile.decisions
    }
    responses_by_criterion: dict[
        str,
        list[CriterionResponse],
    ] = defaultdict(list)
    unused_response_ids: list[str] = []

    for response in responses:
        if response.criterion_id not in decisions:
            unused_response_ids.append(
                response.response_id
            )
        else:
            responses_by_criterion[
                response.criterion_id
            ].append(response)

    indicators_to_criteria: dict[
        str,
        list[str],
    ] = defaultdict(list)

    for decision in profile.decisions:
        for indicator_id in decision.indicator_ids:
            indicators_to_criteria[
                indicator_id
            ].append(decision.criterion_id)

    evidence_by_criterion: dict[
        str,
        list[EvidenceItem],
    ] = defaultdict(list)
    unmapped_evidence_ids: list[str] = []

    for evidence in evidence_items:
        mapped = set(
            indicators_to_criteria.get(
                evidence.indicator_id,
                (),
            )
        )

        if evidence.criterion_id in decisions:
            mapped.add(evidence.criterion_id)

        if not mapped:
            unmapped_evidence_ids.append(
                evidence.evidence_id
            )

        for criterion_id in mapped:
            evidence_by_criterion[
                criterion_id
            ].append(evidence)

    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    observations = tuple(
        _attach_response_support(
            _build_one(
                decision,
                responses_by_criterion.get(decision.criterion_id, ()),
                evidence_by_criterion.get(decision.criterion_id, ()),
                (
                    numeric_scoring_scales.get(decision.criterion_id)
                    if numeric_scoring_scales is not None
                    else None
                ),
                numeric_scoring_scales is not None,
            ),
            responses_by_criterion.get(decision.criterion_id, ()),
            evidence_by_id,
        )
        for decision in profile.decisions
    )

    applicable = [
        observation
        for observation, decision in zip(
            observations,
            profile.decisions,
            strict=True,
        )
        if decision.status is Applicability.APPLICABLE
    ]
    ready = {
        ObservationStatus.READY_NUMERIC,
        ObservationStatus.READY_RANGE,
        ObservationStatus.READY_LINGUISTIC,
    }
    resolved_count = sum(
        item.status in ready
        for item in applicable
    )

    return ObservationSet(
        sme_id=profile.sme_id,
        policy_id=profile.policy_id,
        policy_version=profile.policy_version,
        observations=observations,
        coverage=ObservationCoverage(
            applicable_count=len(applicable),
            resolved_count=resolved_count,
            document_supported_count=sum(
                item.status in ready
                and bool(item.evidence_ids)
                for item in applicable
            ),
            coverage_ratio=(
                resolved_count / len(applicable)
                if applicable
                else 0.0
            ),
        ),
        unused_response_ids=tuple(
            sorted(unused_response_ids)
        ),
        unmapped_evidence_ids=tuple(
            sorted(unmapped_evidence_ids)
        ),
    )


def _build_one(
    decision,
    responses,
    evidence_items,
    numeric_scale,
    enforce_numeric_scale,
) -> CriterionObservation:
    if decision.status is Applicability.NOT_APPLICABLE:
        if responses or any(
            is_reviewed_evidence(item)
            for item in evidence_items
        ):
            return _state(
                decision.criterion_id,
                ObservationStatus.APPLICABILITY_REVIEW,
                responses,
                evidence_items,
                (
                    "Information was supplied for a criterion "
                    "marked not applicable."
                ),
            )

        return CriterionObservation(
            criterion_id=decision.criterion_id,
            status=ObservationStatus.NOT_APPLICABLE,
        )

    if decision.status is Applicability.UNCERTAIN:
        return _state(
            decision.criterion_id,
            ObservationStatus.APPLICABILITY_REVIEW,
            responses,
            evidence_items,
            (
                "Applicability must be resolved before "
                "interpreting evidence."
            ),
        )

    if any(
        item.kind
        is ResponseKind.CLAIMED_NOT_APPLICABLE
        for item in responses
    ):
        return _state(
            decision.criterion_id,
            ObservationStatus.APPLICABILITY_REVIEW,
            responses,
            evidence_items,
            (
                "The applicant's non-applicability claim "
                "requires review."
            ),
        )

    accepted = [
        item
        for item in evidence_items
        if is_reviewed_evidence(item)
        and (
            decision.scoring_role != "performance_criterion"
            or describes_current_state(item)
        )
    ]
    pending = [
        item
        for item in evidence_items
        if (
            item.validation_status
            is EvidenceValidationStatus.UNVALIDATED
        )
    ]

    accepted_numbers = [
        _Number(
            value=float(item.normalized_value),
            unit=item.unit,
            period=item.reporting_period,
            scope=item.scope,
        )
        for item in accepted
        if isinstance(
            item.normalized_value,
            (int, float),
        )
        and not isinstance(
            item.normalized_value,
            bool,
        )
        and (
            not enforce_numeric_scale
            or _numeric_evidence_is_score_ready(item, numeric_scale)
        )
    ]
    response_numbers = [
        _Number(
            value=item.exact_value,
            unit=item.unit,
            period=item.reporting_period,
            scope=item.scope,
        )
        for item in responses
        if item.kind is ResponseKind.EXACT_NUMBER
    ]
    ranges = [
        item
        for item in responses
        if item.kind is ResponseKind.NUMBER_RANGE
    ]
    linguistic = [
        item
        for item in responses
        if item.kind is ResponseKind.LINGUISTIC
    ]
    accepted_qualitative = [
        item
        for item in accepted
        if isinstance(
            item.normalized_value,
            (str, bool),
        )
    ]

    # A reviewed measurement is more authoritative than a redundant
    # linguistic estimate. Deliberate overrides require an explicit
    # override contract; a generic rating must never silently compete
    # with accepted numeric evidence.
    evidence_numeric_is_authoritative = (
        bool(accepted_numbers)
        and bool(linguistic)
        and not response_numbers
        and not ranges
        and not accepted_qualitative
    )

    if evidence_numeric_is_authoritative:
        linguistic = []
        scoring_responses = [
            item
            for item in responses
            if item.kind is not ResponseKind.LINGUISTIC
        ]
    else:
        scoring_responses = list(responses)

    numbers = [*accepted_numbers, *response_numbers]

    response_ids = tuple(
        sorted(
            item.response_id
            for item in scoring_responses
        )
    )
    evidence_ids = tuple(
        sorted(
            item.evidence_id
            for item in accepted
        )
    )

    modes = sum(
        bool(items)
        for items in (
            numbers,
            ranges,
            (
                *linguistic,
                *accepted_qualitative,
            ),
        )
    )

    if modes > 1:
        return CriterionObservation(
            criterion_id=decision.criterion_id,
            status=ObservationStatus.NEEDS_SELECTION,
            response_ids=response_ids,
            evidence_ids=evidence_ids,
            source_indicator_ids=_indicator_ids(
                accepted
            ),
            issues=(
                "Multiple response types need an explicit "
                "scoring selection.",
            ),
        )

    if numbers:
        signatures = {
            (
                item.unit,
                item.period,
                item.scope,
            )
            for item in numbers
        }
        values = {
            item.value for item in numbers
        }

        if len(signatures) > 1:
            return CriterionObservation(
                criterion_id=decision.criterion_id,
                status=(
                    ObservationStatus.NEEDS_SELECTION
                ),
                response_ids=response_ids,
                evidence_ids=evidence_ids,
                source_indicator_ids=_indicator_ids(
                    accepted
                ),
                issues=(
                    "Numeric values have different units, "
                    "periods or scopes.",
                ),
            )

        if len(values) > 1:
            return CriterionObservation(
                criterion_id=decision.criterion_id,
                status=ObservationStatus.CONFLICT,
                response_ids=response_ids,
                evidence_ids=evidence_ids,
                source_indicator_ids=_indicator_ids(
                    accepted
                ),
                issues=(
                    "Accepted numeric sources contain "
                    "different values.",
                ),
            )

        number = numbers[0]

        return CriterionObservation(
            criterion_id=decision.criterion_id,
            status=ObservationStatus.READY_NUMERIC,
            exact_value=number.value,
            unit=number.unit,
            reporting_period=number.period,
            scope=number.scope,
            response_ids=response_ids,
            evidence_ids=evidence_ids,
            source_indicator_ids=_indicator_ids(
                accepted
            ),
        )

    if ranges:
        signatures = {
            (
                item.unit,
                item.reporting_period,
                item.scope,
            )
            for item in ranges
        }

        if len(signatures) > 1:
            return CriterionObservation(
                criterion_id=decision.criterion_id,
                status=(
                    ObservationStatus.NEEDS_SELECTION
                ),
                response_ids=response_ids,
                issues=(
                    "Ranges have different units, periods "
                    "or scopes.",
                ),
            )

        lower = max(
            item.lower_value
            for item in ranges
        )
        upper = min(
            item.upper_value
            for item in ranges
        )

        if lower > upper:
            return CriterionObservation(
                criterion_id=decision.criterion_id,
                status=ObservationStatus.CONFLICT,
                response_ids=response_ids,
                issues=(
                    "Submitted numeric ranges do not overlap.",
                ),
            )

        first = ranges[0]

        return CriterionObservation(
            criterion_id=decision.criterion_id,
            status=ObservationStatus.READY_RANGE,
            lower_value=lower,
            upper_value=upper,
            unit=first.unit,
            reporting_period=(
                first.reporting_period
            ),
            scope=first.scope,
            response_ids=response_ids,
        )

    if linguistic or accepted_qualitative:
        response_values = [
            item.linguistic_value
            for item in linguistic
        ]
        evidence_values = [
            str(item.normalized_value)
            for item in accepted_qualitative
        ]
        values = {
            value.casefold()
            for value in (
                *response_values,
                *evidence_values,
            )
            if value is not None
        }

        if len(values) > 1:
            return CriterionObservation(
                criterion_id=decision.criterion_id,
                status=ObservationStatus.CONFLICT,
                response_ids=response_ids,
                evidence_ids=evidence_ids,
                source_indicator_ids=_indicator_ids(
                    accepted
                ),
                issues=(
                    "Linguistic responses disagree.",
                ),
            )

        selected_value = (
            *response_values,
            *evidence_values,
        )[0]

        return CriterionObservation(
            criterion_id=decision.criterion_id,
            status=(
                ObservationStatus.READY_LINGUISTIC
            ),
            linguistic_value=selected_value,
            response_ids=response_ids,
            evidence_ids=evidence_ids,
            source_indicator_ids=_indicator_ids(
                accepted
            ),
        )

    if any(
        item.kind is ResponseKind.NOT_MEASURED
        for item in responses
    ):
        return _state(
            decision.criterion_id,
            ObservationStatus.NOT_MEASURED,
            responses,
            evidence_items,
            "The applicable topic is not measured.",
        )

    if pending:
        return CriterionObservation(
            criterion_id=decision.criterion_id,
            status=ObservationStatus.PENDING_REVIEW,
            response_ids=response_ids,
            evidence_ids=tuple(
                sorted(
                    item.evidence_id
                    for item in pending
                )
            ),
            source_indicator_ids=_indicator_ids(
                pending
            ),
            issues=(
                "Extracted evidence is awaiting acceptance.",
            ),
        )

    return _state(
        decision.criterion_id,
        ObservationStatus.UNKNOWN,
        responses,
        evidence_items,
        (
            "No usable response or accepted evidence "
            "is available."
        ),
    )


def _attach_response_support(
    observation: CriterionObservation,
    responses: Sequence[CriterionResponse],
    evidence_by_id: dict[str, EvidenceItem],
) -> CriterionObservation:
    """Trace cited accepted evidence without treating narrative as a score."""

    cited = {
        evidence_id
        for response in responses
        for evidence_id in response.supporting_evidence_ids
        if is_reviewed_evidence(evidence_by_id[evidence_id])
    }
    if not cited:
        return observation
    return observation.model_copy(
        update={"evidence_ids": tuple(sorted({*observation.evidence_ids, *cited}))}
    )


def _state(
    criterion_id,
    status,
    responses,
    evidence_items,
    issue,
):
    return CriterionObservation(
        criterion_id=criterion_id,
        status=status,
        response_ids=tuple(
            sorted(
                item.response_id
                for item in responses
            )
        ),
        evidence_ids=tuple(
            sorted(
                item.evidence_id
                for item in evidence_items
            )
        ),
        issues=(issue,),
    )


def _validate_unique(
    name: str,
    identifiers: Sequence[str],
) -> None:
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(
            f"{name.title()} IDs must be unique."
        )


def _indicator_ids(
    evidence_items: Sequence[EvidenceItem],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item.indicator_id
                for item in evidence_items
            }
        )
    )


def _numeric_evidence_is_score_ready(
    evidence: EvidenceItem,
    scale: NumericScale | None,
) -> bool:
    """Keep raw totals contextual unless policy explicitly permits scoring."""

    if scale is None or evidence.unit is None:
        return False
    if evidence.unit.casefold() not in {
        unit.casefold() for unit in scale.allowed_units
    }:
        return False
    return (
        not scale.allowed_indicator_ids
        or evidence.indicator_id in scale.allowed_indicator_ids
    )
