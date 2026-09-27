"""Tests for explicit MCDM calibration provenance."""

from pathlib import Path

from greensmecapt.assessment.calibration import (
    CalibrationBasis,
    CalibrationStatus,
    load_calibration_manifest,
)
from greensmecapt.assessment.electre_iii import load_electre_configuration
from greensmecapt.assessment.normalization import load_normalization_policy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    PROJECT_ROOT
    / "config"
    / "mcdm_calibration.development.json"
)


def test_load_development_calibration_manifest() -> None:
    manifest = load_calibration_manifest(MANIFEST_PATH)

    assert manifest.status is CalibrationStatus.DEVELOPMENT
    assert all(item.review_required for item in manifest.artifacts)
    assert {
        item.basis for item in manifest.artifacts
    } == {CalibrationBasis.MODEL_INFORMED}
    assert {item.artifact_id for item in manifest.artifacts} == {
        "normalization_policy",
        "electre_iii",
    }


def test_manifest_versions_match_live_configurations() -> None:
    manifest = load_calibration_manifest(MANIFEST_PATH)
    versions = {
        item.artifact_id: item.artifact_version
        for item in manifest.artifacts
    }

    assert versions["normalization_policy"] == load_normalization_policy(
        PROJECT_ROOT / "config/normalization_policy.development.json"
    ).version
    assert versions["electre_iii"] == load_electre_configuration(
        PROJECT_ROOT / "config/electre_iii.development.json"
    ).version
