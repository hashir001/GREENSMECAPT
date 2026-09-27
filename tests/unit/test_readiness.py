"""Tests for applicant-specific readiness interpretation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from greensmecapt.assessment.fuzzy_dematel import (
    load_dematel_specification,
)
from greensmecapt.assessment.readiness import (
    ReadinessError,
    ReadinessObservation,
    ReadinessState,
    build_readiness_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION_PATH = (
    PROJECT_ROOT
    / "config"
    / "dematel_specification.development.json"
)


def test_build_complete_non_scoring_readiness_profile() -> None:
    specification = load_dematel_specification(SPECIFICATION_PATH)
    observation = ReadinessObservation(
        observation_id="obs-1",
        sme_id="sme-1",
        factor_id="regulation_compliance_standards_and_certifications",
        state=ReadinessState.CONSTRAINING_EVIDENCE,
        source_ids=("document-1",),
        narrative="A required environmental permit is still pending.",
    )

    profile = build_readiness_profile(
        "sme-1",
        specification,
        (observation,),
    )

    assert len(profile.factors) == len(specification.factor_ids)
    assert profile.calibration_status == "requires_expert_calibration"
    assert profile.causal_results_available is False
    assert next(
        item
        for item in profile.factors
        if item.factor_id == observation.factor_id
    ).state is ReadinessState.CONSTRAINING_EVIDENCE
    assert any(
        item.state is ReadinessState.UNKNOWN
        for item in profile.factors
    )
    assert "score" not in profile.model_fields


def test_evidence_state_requires_source() -> None:
    with pytest.raises(ValidationError, match="require at least one source"):
        ReadinessObservation(
            observation_id="obs-1",
            sme_id="sme-1",
            factor_id="leadership_and_organisational_commitment",
            state=ReadinessState.ENABLING_EVIDENCE,
        )


def test_unknown_factor_is_rejected() -> None:
    specification = load_dematel_specification(SPECIFICATION_PATH)
    observation = ReadinessObservation(
        observation_id="obs-1",
        sme_id="sme-1",
        factor_id="not_in_taxonomy",
        state=ReadinessState.UNKNOWN,
    )

    with pytest.raises(ReadinessError, match="Unknown readiness factor"):
        build_readiness_profile("sme-1", specification, (observation,))
