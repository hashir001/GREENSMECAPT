"""Prepare fair shared-criterion cohorts for the existing TOPSIS engine."""

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.input_models import (
    IndicatorDefinition,
    InputStatus,
    NumericDirection,
    ResolvedIndicator,
    SMEAssessmentInput,
)
from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    NormalizedAssessmentInputs,
    NormalizedCriterionInput,
)
from greensmecapt.assessment.topsis import (
    IndicatorWeight,
    TopsisConfiguration,
    TopsisResult,
    run_topsis,
)


class CohortComparisonError(ValueError):
    """Raised when SMEs cannot be compared fairly."""


class CohortComparisonStatus(StrEnum):
    """Describe the completeness of a completed comparison."""

    READY = "ready"
    PROVISIONAL = "provisional"


class FuzzyProjection(StrEnum):
    """Describe how fuzzy inputs enter the current crisp TOPSIS engine."""

    MODAL = "modal"


class CohortModel(BaseModel):
    """Provide immutable cohort contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class CohortConfiguration(CohortModel):
    """Configure minimum comparability requirements."""

    cohort_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    minimum_shared_criteria: int = Field(default=2, ge=1)
    minimum_shared_weight_ratio: float = Field(
        default=0.6,
        gt=0.0,
        le=1.0,
    )
    projection: FuzzyProjection = FuzzyProjection.MODAL


class SMECohortCoverage(CohortModel):
    """Explain how much of one SME's available assessment was compared."""

    sme_id: str = Field(min_length=1)
    available_criterion_ids: tuple[str, ...]
    shared_criterion_ids: tuple[str, ...]
    excluded_criterion_ids: tuple[str, ...]
    shared_weight_ratio: float = Field(ge=0.0, le=1.0)


class ComparableTopsisResult(CohortModel):
    """Store cohort preparation decisions and the resulting ranking."""

    cohort_id: str = Field(min_length=1)
    cohort_version: str = Field(min_length=1)
    normalization_policy_id: str = Field(min_length=1)
    normalization_policy_version: str = Field(min_length=1)
    comparison_status: CohortComparisonStatus
    projection: FuzzyProjection
    shared_criterion_ids: tuple[str, ...] = Field(min_length=1)
    coverage: tuple[SMECohortCoverage, ...] = Field(min_length=2)
    topsis_result: TopsisResult


def run_comparable_topsis(
    inputs: Sequence[NormalizedAssessmentInputs],
    configuration: CohortConfiguration,
) -> ComparableTopsisResult:
    """Select shared normalized criteria and run the existing TOPSIS."""

    if len(inputs) < 2:
        raise CohortComparisonError(
            "A cohort comparison requires at least two SMEs."
        )

    sme_ids = [item.sme_id for item in inputs]

    if len(sme_ids) != len(set(sme_ids)):
        raise CohortComparisonError(
            "SME IDs must be unique within a cohort."
        )

    blocked = [
        item
        for item in inputs
        if item.readiness is AssessmentReadiness.BLOCKED
    ]

    if blocked:
        details = "; ".join(
            (
                f"{item.sme_id}: "
                + (
                    " | ".join(
                        (
                            f"{issue.criterion_id} "
                            f"[{issue.code}]: {issue.message}"
                        )
                        for issue in item.issues
                    )
                    or "assessment coverage is insufficient"
                )
            )
            for item in blocked
        )
        raise CohortComparisonError(
            "Assessment inputs are not ready for comparison. "
            + details
        )

    policy_references = {
        (
            item.normalization_policy_id,
            item.normalization_policy_version,
        )
        for item in inputs
    }

    if len(policy_references) != 1:
        raise CohortComparisonError(
            "Every SME must use the same normalization policy."
        )

    criterion_maps = [
        {
            criterion.criterion_id: criterion
            for criterion in item.criteria
        }
        for item in inputs
    ]

    for mapping, item in zip(
        criterion_maps,
        inputs,
        strict=True,
    ):
        if len(mapping) != len(item.criteria):
            raise CohortComparisonError(
                f"SME {item.sme_id!r} contains duplicate criteria."
            )

    shared_ids = set(criterion_maps[0])

    for mapping in criterion_maps[1:]:
        shared_ids &= mapping.keys()

    ordered_shared_ids = tuple(sorted(shared_ids))

    if (
        len(ordered_shared_ids)
        < configuration.minimum_shared_criteria
    ):
        raise CohortComparisonError(
            "The cohort does not have enough shared ready criteria. "
            f"Required: {configuration.minimum_shared_criteria}; "
            f"available: {len(ordered_shared_ids)}."
        )

    shared_weights = _resolve_shared_weights(
        criterion_maps,
        ordered_shared_ids,
    )

    coverage = _build_coverage(
        inputs,
        criterion_maps,
        ordered_shared_ids,
        shared_weights,
    )

    insufficient_coverage = [
        item.sme_id
        for item in coverage
        if (
            item.shared_weight_ratio
            < configuration.minimum_shared_weight_ratio
        )
    ]

    if insufficient_coverage:
        raise CohortComparisonError(
            "The shared criteria cover too little of the available "
            f"assessment for SMEs: {insufficient_coverage}."
        )

    definitions = tuple(
        IndicatorDefinition(
            indicator_id=f"normalized:{criterion_id}",
            criterion_id=criterion_id,
            name=criterion_id.replace("_", " ").title(),
            unit="normalized_0_1",
            direction=NumericDirection.BENEFIT,
            required=True,
            minimum=0.0,
            maximum=1.0,
        )
        for criterion_id in ordered_shared_ids
    )

    assessment_inputs = tuple(
        _build_sme_input(
            normalized_input,
            criterion_map,
            definitions,
            configuration,
        )
        for normalized_input, criterion_map in zip(
            inputs,
            criterion_maps,
            strict=True,
        )
    )

    topsis_configuration = TopsisConfiguration(
        configuration_id=f"{configuration.cohort_id}:weights",
        version=configuration.version,
        weights=tuple(
            IndicatorWeight(
                indicator_id=f"normalized:{criterion_id}",
                weight=shared_weights[criterion_id],
            )
            for criterion_id in ordered_shared_ids
        ),
    )

    topsis_result = run_topsis(
        assessment_inputs,
        topsis_configuration,
    )

    is_provisional = (
        any(
            item.readiness is AssessmentReadiness.PROVISIONAL
            for item in inputs
        )
        or any(item.excluded_criterion_ids for item in coverage)
    )

    policy_id, policy_version = next(iter(policy_references))

    return ComparableTopsisResult(
        cohort_id=configuration.cohort_id,
        cohort_version=configuration.version,
        normalization_policy_id=policy_id,
        normalization_policy_version=policy_version,
        comparison_status=(
            CohortComparisonStatus.PROVISIONAL
            if is_provisional
            else CohortComparisonStatus.READY
        ),
        projection=configuration.projection,
        shared_criterion_ids=ordered_shared_ids,
        coverage=coverage,
        topsis_result=topsis_result,
    )


def _resolve_shared_weights(
    criterion_maps: Sequence[
        dict[str, NormalizedCriterionInput]
    ],
    shared_ids: tuple[str, ...],
) -> dict[str, float]:
    weights: dict[str, float] = {}

    for criterion_id in shared_ids:
        candidate_weights = {
            mapping[criterion_id].base_weight
            for mapping in criterion_maps
        }

        if len(candidate_weights) != 1:
            raise CohortComparisonError(
                f"Criterion {criterion_id!r} has inconsistent weights."
            )

        weights[criterion_id] = next(iter(candidate_weights))

    return weights


def _build_coverage(
    inputs: Sequence[NormalizedAssessmentInputs],
    criterion_maps: Sequence[
        dict[str, NormalizedCriterionInput]
    ],
    shared_ids: tuple[str, ...],
    shared_weights: dict[str, float],
) -> tuple[SMECohortCoverage, ...]:
    shared_weight = sum(shared_weights.values())
    coverage: list[SMECohortCoverage] = []

    for item, criterion_map in zip(
        inputs,
        criterion_maps,
        strict=True,
    ):
        available_ids = tuple(sorted(criterion_map))
        excluded_ids = tuple(
            criterion_id
            for criterion_id in available_ids
            if criterion_id not in shared_ids
        )
        available_weight = sum(
            criterion.base_weight
            for criterion in criterion_map.values()
        )

        coverage.append(
            SMECohortCoverage(
                sme_id=item.sme_id,
                available_criterion_ids=available_ids,
                shared_criterion_ids=shared_ids,
                excluded_criterion_ids=excluded_ids,
                shared_weight_ratio=(
                    shared_weight / available_weight
                ),
            )
        )

    return tuple(coverage)


def _build_sme_input(
    normalized_input: NormalizedAssessmentInputs,
    criterion_map: dict[str, NormalizedCriterionInput],
    definitions: tuple[IndicatorDefinition, ...],
    configuration: CohortConfiguration,
) -> SMEAssessmentInput:
    resolved: list[ResolvedIndicator] = []

    for definition in definitions:
        criterion = criterion_map[definition.criterion_id]

        if not criterion.evidence_ids and not criterion.response_ids:
            raise CohortComparisonError(
                f"SME {normalized_input.sme_id!r}, criterion "
                f"{criterion.criterion_id!r} has no provenance."
            )

        value = _project_value(
            criterion,
            configuration.projection,
        )

        resolved.append(
            ResolvedIndicator(
                definition=definition,
                status=InputStatus.READY,
                value=value,
                evidence_ids=criterion.evidence_ids,
                response_ids=criterion.response_ids,
            )
        )

    return SMEAssessmentInput(
        sme_id=normalized_input.sme_id,
        specification_id=f"{configuration.cohort_id}:shared",
        specification_version=configuration.version,
        indicators=tuple(resolved),
    )


def _project_value(
    criterion: NormalizedCriterionInput,
    projection: FuzzyProjection,
) -> float:
    if projection is FuzzyProjection.MODAL:
        return criterion.fuzzy_value.modal

    raise CohortComparisonError(
        f"Unsupported fuzzy projection: {projection}."
    )