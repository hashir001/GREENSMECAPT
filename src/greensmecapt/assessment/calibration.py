"""Auditable metadata for development and approved MCDM calibration."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CalibrationStatus(StrEnum):
    """Describe the governance state of calibration values."""

    DEVELOPMENT = "development"
    APPROVED = "approved"
    RETIRED = "retired"


class CalibrationBasis(StrEnum):
    """Describe where a calibrated artifact came from."""

    MODEL_INFORMED = "model_informed"
    EXPERT_ELICITATION = "expert_elicitation"
    EMPIRICAL_VALIDATION = "empirical_validation"


class CalibrationModel(BaseModel):
    """Provide immutable calibration contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class CalibrationArtifact(CalibrationModel):
    """Describe one versioned configuration used by the MCDM system."""

    artifact_id: str = Field(min_length=1)
    artifact_version: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    basis: CalibrationBasis
    review_required: bool


class MCDMCalibrationManifest(CalibrationModel):
    """Record the provenance and approval state of MCDM choices."""

    calibration_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: CalibrationStatus
    created_for: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    artifacts: tuple[CalibrationArtifact, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        artifact_ids = [item.artifact_id for item in self.artifacts]

        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Calibration artifact IDs must be unique.")

        if self.status is CalibrationStatus.APPROVED and any(
            item.review_required for item in self.artifacts
        ):
            raise ValueError(
                "An approved manifest cannot contain unreviewed artifacts."
            )

        return self


def load_calibration_manifest(
    path: str | Path,
) -> MCDMCalibrationManifest:
    """Load strict MCDM calibration provenance."""

    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )
    return MCDMCalibrationManifest.model_validate(data)


def _unique_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value

    return result
