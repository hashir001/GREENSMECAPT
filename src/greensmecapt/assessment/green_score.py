"""Calculate the distinct, traceable 0-100 Green Score."""

from enum import StrEnum
from math import isclose
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizationPolicy,
    NormalizedAssessmentInputs,
)
from greensmecapt.assessment.profiles import Applicability, AssessmentProfile

NonBlank = Annotated[str, Field(min_length=1)]


class GreenScoreModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class GreenScoreStatus(StrEnum):
    """Separate a complete score from a limited estimate or no score."""

    FINAL = "final"
    PROVISIONAL = "provisional"
    BLOCKED = "blocked"


class GreenCriterionScore(GreenScoreModel):
    """Expose every value used in one criterion's score contribution."""

    criterion_id: NonBlank
    title: NonBlank
    applicability: Applicability
    resolved: bool
    normalized_score: float | None = Field(default=None, ge=0.0, le=100.0)
    base_weight: float = Field(gt=0.0)
    applicable_weight: float = Field(ge=0.0, le=1.0)
    scoring_weight: float = Field(ge=0.0, le=1.0)
    weighted_contribution: float | None = Field(default=None, ge=0.0, le=100.0)
    source_status: str | None = None
    response_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_indicator_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


class GreenScoreResult(GreenScoreModel):
    """Return the Green Score independently from cohort rankings."""

    sme_id: NonBlank
    status: GreenScoreStatus
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    resolved_weight: float = Field(ge=0.0, le=1.0)
    method: Literal["weighted_centroid"] = "weighted_centroid"
    scale_min: float = 0.0
    scale_max: float = 100.0
    normalization_policy_id: NonBlank
    normalization_policy_version: NonBlank
    weight_source: NonBlank
    criteria: tuple[GreenCriterionScore, ...]
    issues: tuple[NonBlank, ...] = ()


def calculate_green_score(
    *,
    profile: AssessmentProfile,
    normalized: NormalizedAssessmentInputs,
    policy: NormalizationPolicy,
) -> GreenScoreResult:
    """Apply the approved weighted-sum structure without scoring unknowns."""

    if profile.sme_id != normalized.sme_id:
        raise ValueError("Green Score inputs must belong to the same SME.")
    if (
        normalized.normalization_policy_id != policy.policy_id
        or normalized.normalization_policy_version != policy.version
    ):
        raise ValueError("Green Score inputs use a different normalization policy.")

    decisions = {
        item.criterion_id: item
        for item in profile.decisions
        if item.output == "green" and item.scoring_role == "performance_criterion"
    }
    normalized_by_id = {item.criterion_id: item for item in normalized.criteria}
    issues_by_id: dict[str, list[str]] = {}
    for issue in normalized.issues:
        issues_by_id.setdefault(issue.criterion_id, []).append(issue.message)

    governed_rules = tuple(
        rule for rule in policy.rules if rule.criterion_id in decisions
    )
    applicable_rules = tuple(
        rule
        for rule in governed_rules
        if decisions[rule.criterion_id].status is Applicability.APPLICABLE
    )
    applicable_base_weight = sum(rule.base_weight for rule in applicable_rules)
    unresolved_applicability = tuple(
        rule.criterion_id
        for rule in governed_rules
        if decisions[rule.criterion_id].status is Applicability.UNCERTAIN
    )

    if applicable_base_weight <= 0.0:
        return GreenScoreResult(
            sme_id=profile.sme_id,
            status=GreenScoreStatus.BLOCKED,
            coverage_ratio=0.0,
            resolved_weight=0.0,
            normalization_policy_id=policy.policy_id,
            normalization_policy_version=policy.version,
            weight_source=policy.weight_source,
            criteria=(),
            issues=("No applicable environmental performance criterion is available.",),
        )

    applicable_weights = {
        rule.criterion_id: rule.base_weight / applicable_base_weight
        for rule in applicable_rules
    }
    resolved_weight = sum(
        applicable_weights[criterion_id]
        for criterion_id in normalized_by_id
        if criterion_id in applicable_weights
    )
    resolved_weight = min(1.0, max(0.0, resolved_weight))

    if unresolved_applicability or normalized.readiness is AssessmentReadiness.BLOCKED:
        status = GreenScoreStatus.BLOCKED
    elif isclose(resolved_weight, 1.0, abs_tol=1e-9):
        status = GreenScoreStatus.FINAL
    else:
        status = GreenScoreStatus.PROVISIONAL

    criteria: list[GreenCriterionScore] = []
    weighted_total = 0.0
    for rule in governed_rules:
        decision = decisions[rule.criterion_id]
        item = normalized_by_id.get(rule.criterion_id)
        applicable_weight = applicable_weights.get(rule.criterion_id, 0.0)
        scoring_weight = (
            applicable_weight / resolved_weight
            if item is not None
            and resolved_weight > 0.0
            and status is not GreenScoreStatus.BLOCKED
            else 0.0
        )
        normalized_score = None
        contribution = None
        if item is not None:
            fuzzy = item.fuzzy_value
            normalized_score = round(
                ((fuzzy.lower + fuzzy.modal + fuzzy.upper) / 3.0) * 100.0,
                6,
            )
            if scoring_weight > 0.0:
                raw_contribution = normalized_score * scoring_weight
                contribution = round(raw_contribution, 6)
                weighted_total += raw_contribution

        criteria.append(
            GreenCriterionScore(
                criterion_id=rule.criterion_id,
                title=decision.title,
                applicability=decision.status,
                resolved=item is not None,
                normalized_score=normalized_score,
                base_weight=rule.base_weight,
                applicable_weight=round(applicable_weight, 10),
                scoring_weight=round(scoring_weight, 10),
                weighted_contribution=contribution,
                source_status=str(item.source_status) if item is not None else None,
                response_ids=item.response_ids if item is not None else (),
                evidence_ids=item.evidence_ids if item is not None else (),
                source_indicator_ids=(
                    item.source_indicator_ids if item is not None else ()
                ),
                issues=tuple(issues_by_id.get(rule.criterion_id, ())),
            )
        )

    result_issues: list[str] = []
    if unresolved_applicability:
        result_issues.append(
            "Environmental criterion applicability remains unresolved: "
            f"{list(unresolved_applicability)}."
        )
    if status is GreenScoreStatus.PROVISIONAL:
        result_issues.append(
            "The score is provisional and uses only resolved applicable criteria; "
            "coverage is reported separately and missing performance is not "
            "scored as zero."
        )
    if status is GreenScoreStatus.BLOCKED:
        result_issues.append(
            "Green Score is withheld because applicability or minimum governed "
            "coverage is unresolved."
        )

    return GreenScoreResult(
        sme_id=profile.sme_id,
        status=status,
        score=(
            min(100.0, max(0.0, round(weighted_total, 4)))
            if status is not GreenScoreStatus.BLOCKED
            else None
        ),
        coverage_ratio=normalized.coverage_ratio,
        resolved_weight=round(resolved_weight, 10),
        normalization_policy_id=policy.policy_id,
        normalization_policy_version=policy.version,
        weight_source=policy.weight_source,
        criteria=tuple(criteria),
        issues=tuple(result_issues),
    )
