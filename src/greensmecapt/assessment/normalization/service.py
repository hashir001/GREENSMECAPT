"""Convert resolved observations into honest fuzzy assessment inputs."""

import json
from pathlib import Path

from greensmecapt.assessment.normalization.models import (
    AssessmentReadiness,
    CriterionDirection,
    CriterionNormalizationRule,
    NormalizationIssue,
    NormalizationPolicy,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
    NumericScale,
    TriangularFuzzyNumber,
)
from greensmecapt.assessment.observations import (
    CriterionObservation,
    ObservationSet,
    ObservationStatus,
)
from greensmecapt.assessment.profiles import (
    Applicability,
    AssessmentProfile,
)


def _unique_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value

    return result


def load_normalization_policy(
    path: str | Path,
) -> NormalizationPolicy:
    """Load a strict versioned normalization policy."""

    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )
    return NormalizationPolicy.model_validate(data)


def normalize_observations(
    profile: AssessmentProfile,
    observations: ObservationSet,
    policy: NormalizationPolicy,
) -> NormalizedAssessmentInputs:
    """Convert available observations without inventing missing values."""

    if profile.sme_id != observations.sme_id:
        raise ValueError(
            "The profile and observations must belong to the same SME."
        )

    if (
        profile.policy_id != observations.policy_id
        or profile.policy_version != observations.policy_version
    ):
        raise ValueError(
            "The observation set was built from a different profile policy."
        )

    observation_by_id = {
        item.criterion_id: item
        for item in observations.observations
    }

    if len(observation_by_id) != len(observations.observations):
        raise ValueError("Observation criterion IDs must be unique.")

    rules = {
        item.criterion_id: item
        for item in policy.rules
    }

    applicable_green_decisions = [
        item
        for item in profile.decisions
        if (
            item.output == "green"
            and item.status is Applicability.APPLICABLE
        )
    ]

    unresolved_green_decisions = [
        item
        for item in profile.decisions
        if (
            item.output == "green"
            and item.status is Applicability.UNCERTAIN
        )
    ]

    normalized: list[NormalizedCriterionInput] = []
    issues: list[NormalizationIssue] = []
    total_weight = 0.0
    resolved_weight = 0.0
    policy_gap = False

    for decision in applicable_green_decisions:
        rule = rules.get(decision.criterion_id)

        if rule is None:
            policy_gap = True
            issues.append(
                NormalizationIssue(
                    criterion_id=decision.criterion_id,
                    code="normalization_rule_missing",
                    message=(
                        "The applicable criterion has no configured "
                        "normalization rule."
                    ),
                )
            )
            continue

        total_weight += rule.base_weight
        observation = observation_by_id.get(decision.criterion_id)

        if observation is None:
            issues.append(
                NormalizationIssue(
                    criterion_id=decision.criterion_id,
                    code="observation_missing",
                    message=(
                        "No observation record exists for the "
                        "applicable criterion."
                    ),
                )
            )
            continue

        try:
            normalized_input = _normalize_one(
                observation,
                rule,
                policy,
            )
        except ValueError as error:
            issues.append(
                NormalizationIssue(
                    criterion_id=decision.criterion_id,
                    code="input_not_normalizable",
                    message=str(error),
                )
            )
            continue

        normalized.append(normalized_input)
        resolved_weight += rule.base_weight

    for decision in unresolved_green_decisions:
        issues.append(
            NormalizationIssue(
                criterion_id=decision.criterion_id,
                code="applicability_unresolved",
                message=(
                    "Applicability must be resolved before this "
                    "criterion enters MCDM preparation."
                ),
            )
        )

    coverage_ratio = (
        resolved_weight / total_weight
        if total_weight
        else 0.0
    )

    if (
        policy_gap
        or unresolved_green_decisions
        or not normalized
        or coverage_ratio < policy.minimum_coverage_ratio
    ):
        readiness = AssessmentReadiness.BLOCKED
    elif coverage_ratio < 1.0:
        readiness = AssessmentReadiness.PROVISIONAL
    else:
        readiness = AssessmentReadiness.READY

    return NormalizedAssessmentInputs(
        sme_id=profile.sme_id,
        normalization_policy_id=policy.policy_id,
        normalization_policy_version=policy.version,
        readiness=readiness,
        coverage_ratio=coverage_ratio,
        criteria=tuple(normalized),
        issues=tuple(issues),
    )


def _normalize_one(
    observation: CriterionObservation,
    rule: CriterionNormalizationRule,
    policy: NormalizationPolicy,
) -> NormalizedCriterionInput:
    if observation.status is ObservationStatus.READY_NUMERIC:
        if observation.exact_value is None:
            raise ValueError(
                "The numeric observation contains no exact value."
            )

        fuzzy_value = _normalize_numeric(
            observation.exact_value,
            observation.exact_value,
            observation,
            rule,
        )

    elif observation.status is ObservationStatus.READY_RANGE:
        if (
            observation.lower_value is None
            or observation.upper_value is None
        ):
            raise ValueError(
                "The range observation is missing a boundary."
            )

        fuzzy_value = _normalize_numeric(
            observation.lower_value,
            observation.upper_value,
            observation,
            rule,
        )

    elif observation.status is ObservationStatus.READY_LINGUISTIC:
        if not rule.allow_linguistic:
            raise ValueError(
                "This criterion does not permit linguistic input."
            )

        if observation.linguistic_value is None:
            raise ValueError(
                "The linguistic observation contains no value."
            )

        scale = {
            label.casefold(): value
            for label, value in (
                policy.default_linguistic_scale.items()
            )
        }

        try:
            fuzzy_value = scale[
                observation.linguistic_value.casefold()
            ]
        except KeyError as error:
            raise ValueError(
                "The linguistic value is not present in the "
                "normalization policy."
            ) from error

    else:
        raise ValueError(
            f"Observation status '{observation.status}' is not "
            "ready for normalization."
        )

    return NormalizedCriterionInput(
        criterion_id=observation.criterion_id,
        fuzzy_value=fuzzy_value,
        base_weight=rule.base_weight,
        source_status=observation.status,
        response_ids=observation.response_ids,
        evidence_ids=observation.evidence_ids,
        source_indicator_ids=(
            observation.source_indicator_ids
        ),
    )


def _normalize_numeric(
    lower_value: float,
    upper_value: float,
    observation: CriterionObservation,
    rule: CriterionNormalizationRule,
) -> TriangularFuzzyNumber:
    scale = rule.numeric_scale

    if scale is None:
        raise ValueError(
            "This criterion has no quantitative normalization scale."
        )

    _validate_numeric_source(observation, scale)

    for value in (lower_value, upper_value):
        if not scale.lower_bound <= value <= scale.upper_bound:
            raise ValueError(
                f"Value {value} falls outside the configured range "
                f"{scale.lower_bound}–{scale.upper_bound}."
            )

    normalized_lower = _normalize_value(lower_value, scale)
    normalized_upper = _normalize_value(upper_value, scale)

    final_lower = min(normalized_lower, normalized_upper)
    final_upper = max(normalized_lower, normalized_upper)

    return TriangularFuzzyNumber(
        lower=final_lower,
        modal=(final_lower + final_upper) / 2.0,
        upper=final_upper,
    )


def _validate_numeric_source(
    observation: CriterionObservation,
    scale: NumericScale,
) -> None:
    if observation.unit is None:
        raise ValueError(
            "A quantitative observation requires a unit."
        )

    allowed_units = {
        unit.casefold()
        for unit in scale.allowed_units
    }

    if observation.unit.casefold() not in allowed_units:
        raise ValueError(
            f"Unit '{observation.unit}' is not allowed by this rule."
        )

    if (
        observation.source_indicator_ids
        and scale.allowed_indicator_ids
    ):
        unexpected = (
            set(observation.source_indicator_ids)
            - set(scale.allowed_indicator_ids)
        )

        if unexpected:
            raise ValueError(
                "The observation contains an unsupported indicator: "
                f"{sorted(unexpected)}."
            )


def _normalize_value(
    value: float,
    scale: NumericScale,
) -> float:
    span = scale.upper_bound - scale.lower_bound
    benefit_value = (
        value - scale.lower_bound
    ) / span

    if scale.direction is CriterionDirection.BENEFIT:
        return benefit_value

    return 1.0 - benefit_value