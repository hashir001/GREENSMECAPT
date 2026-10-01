"""Versioned evidence-strength policy kept separate from SME performance."""

import json
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
        return self


def load_evidence_strength_policy(
    path: str | Path,
) -> EvidenceStrengthPolicy:
    """Load the versioned evidence-strength policy."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvidenceStrengthPolicy.model_validate(data)
