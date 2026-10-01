"""Versioned evidence-strength policy kept separate from SME performance."""

import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonBlank = Annotated[str, Field(min_length=1)]


class EvidenceStrengthModel(BaseModel):
    """Provide strict immutable evidence-governance contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class EvidenceSourceClass(StrEnum):
    """Describe evidence origin without treating it as performance."""

    AUDITED_OR_REGULATORY = "audited_or_regulatory"
    THIRD_PARTY_TRANSACTIONAL = "third_party_transactional"
    INTERNALLY_GENERATED = "internally_generated"
    SELF_DECLARED = "self_declared"
    MODEL_INFERRED = "model_inferred"


class EvidenceStrengthBand(StrEnum):
    """Qualitative evidence-strength outputs pending final calibration."""

    STRONG = "strong"
    ADEQUATE = "adequate"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


class EvidenceBandCondition(StrEnum):
    """Name deterministic development rules without numeric scoring."""

    CONFLICT = "conflict"
    NO_CONFIRMED_SOURCES = "no_confirmed_sources"
    MISSING_ATTRIBUTES_OR_WEAK_ONLY = "missing_attributes_or_weak_only"
    COMPLETE_INTERNAL_SUPPORT = "complete_internal_support"
    COMPLETE_INDEPENDENT_SUPPORT = "complete_independent_support"


class SourceClassDefinition(EvidenceStrengthModel):
    source_class: EvidenceSourceClass
    title: NonBlank
    description: NonBlank
    requires_human_acceptance: bool = True


class EvidenceDimensionRequirement(EvidenceStrengthModel):
    dimension_id: Literal[
        "environmental_performance",
        "financial_health",
        "investment_case",
        "readiness_context",
    ]
    required_attributes: tuple[NonBlank, ...] = Field(min_length=1)
    notes: NonBlank


class EvidenceBandRule(EvidenceStrengthModel):
    band: EvidenceStrengthBand
    condition: EvidenceBandCondition
    description: NonBlank


class EvidenceStrengthPolicy(EvidenceStrengthModel):
    """Govern evidence quality as an overlay, never a Green Score criterion."""

    policy_id: NonBlank
    version: NonBlank
    status: Literal["development", "approved"] = "development"
    calibration_status: Literal[
        "requires_evidence_calibration",
        "calibrated",
    ] = "requires_evidence_calibration"
    missing_information_rule: Literal["unknown_not_zero"] = "unknown_not_zero"
    performance_separation: Literal[True] = True
    source_classes: tuple[SourceClassDefinition, ...] = Field(min_length=1)
    dimension_requirements: tuple[EvidenceDimensionRequirement, ...] = Field(
        min_length=1
    )
    bands: tuple[EvidenceStrengthBand, ...] = Field(min_length=1)
    band_rules: tuple[EvidenceBandRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        source_ids = [item.source_class for item in self.source_classes]
        dimension_ids = [item.dimension_id for item in self.dimension_requirements]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Evidence source classes must be unique.")
        if len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError("Evidence dimension requirements must be unique.")
        if len(self.bands) != len(set(self.bands)):
            raise ValueError("Evidence-strength bands must be unique.")
        rule_bands = [item.band for item in self.band_rules]
        conditions = [item.condition for item in self.band_rules]
        if set(rule_bands) != set(self.bands):
            raise ValueError("Every evidence-strength band requires one rule.")
        if len(conditions) != len(set(conditions)):
            raise ValueError("Evidence-strength rule conditions must be unique.")
        return self


class EvidenceSourceClassification(EvidenceStrengthModel):
    """Retain how one source was classified for evidence-strength purposes."""

    source_id: NonBlank
    source_class: EvidenceSourceClass
    confirmed: bool
    classification_basis: NonBlank


class EvidenceDimensionInput(EvidenceStrengthModel):
    """Supply transparent coverage facts for one assessment dimension."""

    dimension_id: Literal[
        "environmental_performance",
        "financial_health",
        "investment_case",
        "readiness_context",
    ]
    source_ids: tuple[NonBlank, ...] = ()
    missing_attributes: tuple[NonBlank, ...] = ()
    conflicting: bool = False
    issues: tuple[NonBlank, ...] = ()

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Evidence-strength source IDs must be unique.")
        if len(self.missing_attributes) != len(set(self.missing_attributes)):
            raise ValueError("Missing evidence attributes must be unique.")
        return self


class EvidenceDimensionResult(EvidenceStrengthModel):
    dimension_id: NonBlank
    band: EvidenceStrengthBand
    sources: tuple[EvidenceSourceClassification, ...] = ()
    missing_attributes: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    rationale: NonBlank


class EvidenceStrengthAssessment(EvidenceStrengthModel):
    """Qualify evidence without changing any performance result."""

    policy_id: NonBlank
    policy_version: NonBlank
    calibration_status: NonBlank
    performance_separation: Literal[True] = True
    dimensions: tuple[EvidenceDimensionResult, ...] = Field(min_length=1)


def load_evidence_strength_policy(
    path: str | Path,
) -> EvidenceStrengthPolicy:
    """Load the versioned evidence-strength policy."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvidenceStrengthPolicy.model_validate(data)


def assess_evidence_strength(
    *,
    policy: EvidenceStrengthPolicy,
    dimension_inputs: Sequence[EvidenceDimensionInput],
    source_classifications: Mapping[str, EvidenceSourceClassification],
) -> EvidenceStrengthAssessment:
    """Apply versioned qualitative rules and retain their full provenance."""

    supplied = {item.dimension_id: item for item in dimension_inputs}
    required = {
        requirement.dimension_id for requirement in policy.dimension_requirements
    }
    if len(supplied) != len(dimension_inputs) or set(supplied) != required:
        raise ValueError(
            "Evidence-strength inputs must cover every governed dimension once."
        )
    unknown = {
        source_id
        for item in dimension_inputs
        for source_id in item.source_ids
        if source_id not in source_classifications
    }
    if unknown:
        raise ValueError(f"Evidence sources are not classified: {sorted(unknown)}")

    rules = {item.condition: item for item in policy.band_rules}
    dimensions = tuple(
        _assess_dimension(supplied[dimension], source_classifications, rules)
        for dimension in sorted(required)
    )
    return EvidenceStrengthAssessment(
        policy_id=policy.policy_id,
        policy_version=policy.version,
        calibration_status=policy.calibration_status,
        dimensions=dimensions,
    )


def _assess_dimension(
    item: EvidenceDimensionInput,
    classifications: Mapping[str, EvidenceSourceClassification],
    rules: Mapping[EvidenceBandCondition, EvidenceBandRule],
) -> EvidenceDimensionResult:
    sources = tuple(classifications[source_id] for source_id in item.source_ids)
    confirmed = tuple(source for source in sources if source.confirmed)
    source_classes = {source.source_class for source in confirmed}
    independent = {
        EvidenceSourceClass.AUDITED_OR_REGULATORY,
        EvidenceSourceClass.THIRD_PARTY_TRANSACTIONAL,
    }
    weak = {
        EvidenceSourceClass.SELF_DECLARED,
        EvidenceSourceClass.MODEL_INFERRED,
    }
    if item.conflicting:
        condition = EvidenceBandCondition.CONFLICT
    elif not confirmed:
        condition = EvidenceBandCondition.NO_CONFIRMED_SOURCES
    elif item.missing_attributes or source_classes <= weak:
        condition = EvidenceBandCondition.MISSING_ATTRIBUTES_OR_WEAK_ONLY
    elif source_classes & independent:
        condition = EvidenceBandCondition.COMPLETE_INDEPENDENT_SUPPORT
    else:
        condition = EvidenceBandCondition.COMPLETE_INTERNAL_SUPPORT
    rule = rules[condition]
    return EvidenceDimensionResult(
        dimension_id=item.dimension_id,
        band=rule.band,
        sources=sources,
        missing_attributes=item.missing_attributes,
        issues=item.issues,
        rationale=rule.description,
    )
