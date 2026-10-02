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
    readiness_observations_from_evidence,
)
from greensmecapt.domain import EvidenceItem, EvidenceValidationStatus

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


def test_accepted_conflicting_readiness_evidence_becomes_mixed() -> None:
    specification = load_dematel_specification(SPECIFICATION_PATH)
    factor_id = "leadership_and_organisational_commitment"
    evidence = tuple(
        EvidenceItem(
            evidence_id=f"evidence-{index}",
            sme_id="sme-1",
            document_id=f"document-{index}",
            indicator_id=f"readiness_factor:{factor_id}",
            raw_value=state,
            normalized_value=state,
            source_locator=f"page {index}",
            source_excerpt=f"Readiness evidence {index}",
            extraction_method="language_model_grounded_context_extraction",
            extractor_name="test",
            validation_status=EvidenceValidationStatus.ACCEPTED,
        )
        for index, state in enumerate(
            ("enabling_evidence", "constraining_evidence"), start=1
        )
    )

    observations = readiness_observations_from_evidence(
        sme_id="sme-1",
        specification=specification,
        evidence_items=evidence,
    )

    assert observations[0].state is ReadinessState.MIXED_EVIDENCE
    assert observations[0].source_ids == ("evidence-1", "evidence-2")
