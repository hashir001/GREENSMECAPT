"""Interpret SME readiness evidence through a calibrated causal model."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.assessment.fuzzy_dematel import (
    DematelFactorResult,
    DematelSpecification,
    FuzzyDematelResult,
)


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


class ReadinessFactorInterpretation(ReadinessModel):
    """Join one SME observation to optional DEMATEL influence results."""

    factor_id: str = Field(min_length=1)
    domain_id: str = Field(min_length=1)
    state: ReadinessState
    source_ids: tuple[str, ...] = ()
    narrative: str | None = Field(default=None, min_length=1)
    influence: DematelFactorResult | None = None


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
