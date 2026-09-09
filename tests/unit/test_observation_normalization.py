"""Tests for observation normalization and MCDM readiness."""

from pathlib import Path

from greensmecapt.assessment.normalization import (
    AssessmentReadiness,
    load_normalization_policy,
    normalize_observations,
)
from greensmecapt.assessment.observations import (
    CriterionResponse,
    build_observations,
)
from greensmecapt.assessment.profiles import (
    Applicability,
    AssessmentContext,
    build_profile,
    load_policy,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "assessment_profiles.development.json"
)
NORMALIZATION_POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "normalization_policy.development.json"
)
EXAMPLE_DIR = PROJECT_ROOT / "examples" / "assessment_profiles"


def _profile(example: str = "small_manufacturer"):
    context = AssessmentContext.model_validate_json(
        (EXAMPLE_DIR / f"{example}.json").read_text(
            encoding="utf-8"
        )
    )
    return build_profile(
        context,
        load_policy(PROFILE_POLICY_PATH),
    )


def _linguistic_responses(profile, omitted: set[str] | None = None):
    omitted = omitted or set()
    responses = []

    for decision in profile.decisions:
        if (
            decision.output == "green"
            and decision.status is Applicability.APPLICABLE
            and decision.criterion_id not in omitted
        ):
            responses.append(
                CriterionResponse(
                    response_id=(
                        f"response_{decision.criterion_id}"
                    ),
                    sme_id=profile.sme_id,
                    criterion_id=decision.criterion_id,
                    kind="linguistic",
                    linguistic_value="high",
                    narrative="Development assessment response.",
                    submitted_by="applicant_001",
                )
            )

    return tuple(responses)


def test_complete_inputs_are_ready() -> None:
    profile = _profile()
    observations = build_observations(
        profile,
        responses=_linguistic_responses(profile),
    )

    result = normalize_observations(
        profile,
        observations,
        load_normalization_policy(
            NORMALIZATION_POLICY_PATH
        ),
    )

    assert result.readiness is AssessmentReadiness.READY
    assert result.coverage_ratio == 1.0
    assert not hasattr(result, "green_score")


def test_missing_input_can_remain_provisional() -> None:
    profile = _profile()
    applicable = [
        decision.criterion_id
        for decision in profile.decisions
        if (
            decision.output == "green"
            and decision.status is Applicability.APPLICABLE
        )
    ]

    observations = build_observations(
        profile,
        responses=_linguistic_responses(
            profile,
            omitted={applicable[-1]},
        ),
    )

    result = normalize_observations(
        profile,
        observations,
        load_normalization_policy(
            NORMALIZATION_POLICY_PATH
        ),
    )

    assert result.readiness is AssessmentReadiness.PROVISIONAL
    assert 0.6 <= result.coverage_ratio < 1.0


def test_low_coverage_blocks_mcdm_preparation() -> None:
    profile = _profile()
    applicable = [
        decision.criterion_id
        for decision in profile.decisions
        if (
            decision.output == "green"
            and decision.status is Applicability.APPLICABLE
        )
    ]

    observations = build_observations(
        profile,
        responses=_linguistic_responses(
            profile,
            omitted=set(applicable[1:]),
        ),
    )

    result = normalize_observations(
        profile,
        observations,
        load_normalization_policy(
            NORMALIZATION_POLICY_PATH
        ),
    )

    assert result.readiness is AssessmentReadiness.BLOCKED


def test_accepted_renewable_percentage_becomes_point_72() -> None:
    profile = _profile()
    responses = tuple(
        response
        for response in _linguistic_responses(profile)
        if response.criterion_id != "purchased_energy_management"
    )

    evidence = EvidenceItem(
        evidence_id="evidence_energy_001",
        sme_id=profile.sme_id,
        document_id="document_001",
        indicator_id="renewable_energy_percentage",
        criterion_id="purchased_energy_management",
        raw_value="72%",
        normalized_value=72.0,
        unit="percent",
        source_locator="page 1",
        extraction_method="regular_expression",
        extractor_name="renewable_energy_percentage_regex",
        validation_status=EvidenceValidationStatus.ACCEPTED,
    )

    observations = build_observations(
        profile,
        responses=responses,
        evidence_items=(evidence,),
    )

    result = normalize_observations(
        profile,
        observations,
        load_normalization_policy(
            NORMALIZATION_POLICY_PATH
        ),
    )

    energy = next(
        item
        for item in result.criteria
        if item.criterion_id
        == "purchased_energy_management"
    )

    assert energy.fuzzy_value.lower == 0.72
    assert energy.fuzzy_value.modal == 0.72
    assert energy.fuzzy_value.upper == 0.72
    assert energy.source_indicator_ids == (
        "renewable_energy_percentage",
    )


def test_out_of_range_metric_is_not_silently_clamped() -> None:
    profile = _profile()
    responses = tuple(
        response
        for response in _linguistic_responses(profile)
        if response.criterion_id != "purchased_energy_management"
    )

    evidence = EvidenceItem(
        evidence_id="evidence_energy_001",
        sme_id=profile.sme_id,
        document_id="document_001",
        indicator_id="renewable_energy_percentage",
        criterion_id="purchased_energy_management",
        raw_value="120%",
        normalized_value=120.0,
        unit="percent",
        source_locator="page 1",
        extraction_method="regular_expression",
        extractor_name="renewable_energy_percentage_regex",
        validation_status=EvidenceValidationStatus.ACCEPTED,
    )

    observations = build_observations(
        profile,
        responses=responses,
        evidence_items=(evidence,),
    )

    result = normalize_observations(
        profile,
        observations,
        load_normalization_policy(
            NORMALIZATION_POLICY_PATH
        ),
    )

    assert "purchased_energy_management" not in (
        result.criterion_ids
    )
    assert any(
        issue.criterion_id
        == "purchased_energy_management"
        and issue.code == "input_not_normalizable"
        for issue in result.issues
    )


def test_unresolved_applicability_blocks_preparation() -> None:
    profile = _profile("activity_incomplete")
    observations = build_observations(
        profile,
        responses=_linguistic_responses(profile),
    )

    result = normalize_observations(
        profile,
        observations,
        load_normalization_policy(
            NORMALIZATION_POLICY_PATH
        ),
    )

    assert result.readiness is AssessmentReadiness.BLOCKED
    assert any(
        issue.code == "applicability_unresolved"
        for issue in result.issues
    )