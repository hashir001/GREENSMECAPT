"""Interpret SME readiness evidence through a calibrated causal model."""

from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.evidence_eligibility import (
    is_current_reviewed_evidence,
)
from greensmecapt.assessment.fuzzy_dematel import (
    DematelFactorResult,
    DematelSpecification,
    FuzzyDematelResult,
)
from greensmecapt.domain import EvidenceItem


class ReadinessError(ValueError):
    """Raised when readiness evidence cannot be interpreted consistently."""


class ReadinessModel(BaseModel):
    """Provide immutable readiness contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ReadinessState(StrEnum):
    """Represent evidence state without inventing a readiness score."""

    ENABLING_EVIDENCE = "enabling_evidence"
    CONSTRAINING_EVIDENCE = "constraining_evidence"
    MIXED_EVIDENCE = "mixed_evidence"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_REVIEW = "needs_review"


class ReadinessObservation(ReadinessModel):
    """Record SME-specific evidence for one readiness factor."""

    observation_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    factor_id: str = Field(min_length=1)
    state: ReadinessState
    source_ids: tuple[str, ...] = ()
    narrative: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Readiness source IDs must be unique.")

        evidence_states = {
            ReadinessState.ENABLING_EVIDENCE,
            ReadinessState.CONSTRAINING_EVIDENCE,
            ReadinessState.MIXED_EVIDENCE,
        }

        if self.state in evidence_states and not self.source_ids:
            raise ValueError(
                "Evidence-based readiness states require at least one source."
            )

        return self


class ReadinessCausalLink(ReadinessModel):
    """Expose a calibrated total-relation link without turning it into a score."""

    target_factor_id: str = Field(min_length=1)
    influence_strength: float = Field(ge=0.0)


class ReadinessFactorInterpretation(ReadinessModel):
    """Join one SME observation to optional DEMATEL influence results."""

    factor_id: str = Field(min_length=1)
    domain_id: str = Field(min_length=1)
    state: ReadinessState
    source_ids: tuple[str, ...] = ()
    narrative: str | None = Field(default=None, min_length=1)
    influence: DematelFactorResult | None = None
    interpretation: str = Field(min_length=1)
    downstream_influences: tuple[ReadinessCausalLink, ...] = ()


class SMEReadinessProfile(ReadinessModel):
    """Store contextual readiness interpretation, never performance scoring."""

    sme_id: str = Field(min_length=1)
    dematel_specification_id: str = Field(min_length=1)
    dematel_specification_version: str = Field(min_length=1)
    calibration_status: str = Field(min_length=1)
    causal_results_available: bool
    factors: tuple[ReadinessFactorInterpretation, ...] = Field(min_length=2)


def build_readiness_profile(
    sme_id: str,
    specification: DematelSpecification,
    observations: tuple[ReadinessObservation, ...] = (),
    dematel_result: FuzzyDematelResult | None = None,
) -> SMEReadinessProfile:
    """Build a complete non-scoring SME readiness profile."""

    if not specification.domains or not specification.factors:
        raise ReadinessError(
            "Readiness interpretation requires factor and domain metadata."
        )

    observations_by_factor: dict[str, ReadinessObservation] = {}

    for observation in observations:
        if observation.sme_id != sme_id:
            raise ReadinessError(
                "Every readiness observation must belong to the requested SME."
            )

        if observation.factor_id not in specification.factor_ids:
            raise ReadinessError(
                f"Unknown readiness factor: {observation.factor_id}"
            )

        if observation.factor_id in observations_by_factor:
            raise ReadinessError(
                f"Duplicate readiness observation: {observation.factor_id}"
            )

        observations_by_factor[observation.factor_id] = observation

    influence_by_factor: dict[str, DematelFactorResult] = {}

    if dematel_result is not None:
        if (
            dematel_result.specification_id != specification.specification_id
            or dematel_result.specification_version != specification.version
        ):
            raise ReadinessError(
                "DEMATEL result and readiness specification must match."
            )

        influence_by_factor = {
            factor.factor_id: factor for factor in dematel_result.factors
        }

        if set(influence_by_factor) != set(specification.factor_ids):
            raise ReadinessError(
                "DEMATEL result factors must match the readiness taxonomy."
            )

    downstream_by_factor = _downstream_influences(dematel_result)
    factors = tuple(
        ReadinessFactorInterpretation(
            factor_id=factor.factor_id,
            domain_id=factor.domain_id,
            state=(
                observations_by_factor[factor.factor_id].state
                if factor.factor_id in observations_by_factor
                else ReadinessState.UNKNOWN
            ),
            source_ids=(
                observations_by_factor[factor.factor_id].source_ids
                if factor.factor_id in observations_by_factor
                else ()
            ),
            narrative=(
                observations_by_factor[factor.factor_id].narrative
                if factor.factor_id in observations_by_factor
                else None
            ),
            influence=influence_by_factor.get(factor.factor_id),
            interpretation=_factor_interpretation(
                state=(
                    observations_by_factor[factor.factor_id].state
                    if factor.factor_id in observations_by_factor
                    else ReadinessState.UNKNOWN
                ),
                influence=influence_by_factor.get(factor.factor_id),
                calibration_status=specification.calibration_status,
            ),
            downstream_influences=downstream_by_factor.get(factor.factor_id, ()),
        )
        for factor in specification.factors
    )

    return SMEReadinessProfile(
        sme_id=sme_id,
        dematel_specification_id=specification.specification_id,
        dematel_specification_version=specification.version,
        calibration_status=specification.calibration_status,
        causal_results_available=dematel_result is not None,
        factors=factors,
    )


def readiness_observations_from_evidence(
    *,
    sme_id: str,
    specification: DematelSpecification,
    evidence_items: Sequence[EvidenceItem],
) -> tuple[ReadinessObservation, ...]:
    """Consolidate accepted Gemini readiness evidence by governed factor."""

    prefix = "readiness_factor:"
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for evidence in evidence_items:
        if (
            is_current_reviewed_evidence(evidence)
            and evidence.indicator_id.startswith(prefix)
        ):
            grouped[evidence.indicator_id.removeprefix(prefix)].append(evidence)

    observations: list[ReadinessObservation] = []
    evidence_states = {
        ReadinessState.ENABLING_EVIDENCE,
        ReadinessState.CONSTRAINING_EVIDENCE,
        ReadinessState.MIXED_EVIDENCE,
    }
    for factor_id, items in sorted(grouped.items()):
        if factor_id not in specification.factor_ids:
            raise ReadinessError(f"Unknown accepted readiness factor: {factor_id}")
        try:
            states = {ReadinessState(str(item.normalized_value)) for item in items}
        except ValueError as error:
            raise ReadinessError(
                f"Accepted readiness evidence has an invalid state for {factor_id}."
            ) from error
        if not states <= evidence_states:
            raise ReadinessError(
                f"Accepted readiness evidence has an invalid state for {factor_id}."
            )
        state = next(iter(states)) if len(states) == 1 else ReadinessState.MIXED_EVIDENCE
        observations.append(
            ReadinessObservation(
                observation_id=f"accepted_evidence:{sme_id}:{factor_id}",
                sme_id=sme_id,
                factor_id=factor_id,
                state=state,
                source_ids=tuple(sorted(item.evidence_id for item in items)),
                narrative=(
                    "Accepted sources contain both enabling and constraining evidence."
                    if state is ReadinessState.MIXED_EVIDENCE
                    else "Consolidated from accepted document evidence."
                ),
            )
        )
    return tuple(observations)


def merge_readiness_observations(
    *,
    supplied: Sequence[ReadinessObservation],
    extracted: Sequence[ReadinessObservation],
) -> tuple[ReadinessObservation, ...]:
    """Merge reviewer input with accepted evidence without hiding conflicts."""

    supplied_by_factor = {item.factor_id: item for item in supplied}
    if len(supplied_by_factor) != len(supplied):
        raise ReadinessError("Duplicate supplied readiness observations.")
    extracted_by_factor = {item.factor_id: item for item in extracted}
    merged: list[ReadinessObservation] = []
    for factor_id in sorted(set(supplied_by_factor) | set(extracted_by_factor)):
        reviewer = supplied_by_factor.get(factor_id)
        evidence = extracted_by_factor.get(factor_id)
        if evidence is None:
            if reviewer is not None:
                merged.append(reviewer)
            continue
        if reviewer is not None and reviewer.state not in {
            ReadinessState.UNKNOWN,
            evidence.state,
        }:
            raise ReadinessError(
                f"Reviewer readiness state conflicts with accepted evidence for {factor_id}."
            )
        merged.append(
            evidence.model_copy(
                update={
                    "narrative": (
                        reviewer.narrative
                        if reviewer is not None and reviewer.narrative
                        else evidence.narrative
                    )
                }
            )
        )
    return tuple(merged)


def _factor_interpretation(
    *,
    state: ReadinessState,
    influence: DematelFactorResult | None,
    calibration_status: str,
) -> str:
    state_text = {
        ReadinessState.ENABLING_EVIDENCE: "Accepted evidence indicates an enabling condition.",
        ReadinessState.CONSTRAINING_EVIDENCE: "Accepted evidence indicates a readiness bottleneck.",
        ReadinessState.MIXED_EVIDENCE: (
            "Accepted evidence contains both enabling and constraining signals."
        ),
        ReadinessState.UNKNOWN: "No accepted evidence establishes this readiness condition.",
        ReadinessState.NOT_APPLICABLE: "A reviewer marked this factor not applicable.",
        ReadinessState.NEEDS_REVIEW: "The available observation requires reviewer resolution.",
    }[state]
    if influence is None:
        return f"{state_text} Causal interpretation awaits expert DEMATEL calibration."
    model_label = (
        "calibrated DEMATEL model"
        if calibration_status == "calibrated"
        else "development DEMATEL scenario"
    )
    return (
        f"{state_text} The {model_label} identifies this factor as "
        f"{influence.role.value} with prominence {influence.prominence:.3f}."
    )


def _downstream_influences(
    result: FuzzyDematelResult | None,
) -> dict[str, tuple[ReadinessCausalLink, ...]]:
    if result is None:
        return {}
    factor_ids = result.total_relation_matrix.factor_ids
    output: dict[str, tuple[ReadinessCausalLink, ...]] = {}
    for row_index, source_id in enumerate(factor_ids):
        links = [
            ReadinessCausalLink(
                target_factor_id=target_id,
                influence_strength=(value.lower + value.modal + value.upper) / 3.0,
            )
            for target_id, value in zip(
                factor_ids,
                result.total_relation_matrix.values[row_index],
                strict=True,
            )
            if target_id != source_id
        ]
        output[source_id] = tuple(
            sorted(links, key=lambda item: item.influence_strength, reverse=True)[:2]
        )
    return output
