"""Tests for end-to-end assessment preparation and comparison."""

from pathlib import Path

import pytest

from greensmecapt.assessment.cohort import CohortConfiguration
from greensmecapt.assessment.observations import (
    CriterionResponse,
    ResponseKind,
)
from greensmecapt.assessment.profiles import AssessmentContext
from greensmecapt.assessment.workflow import (
    AssessmentWorkflow,
    AssessmentWorkflowError,
)
from greensmecapt.domain import SME, StructuredInvestmentRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _workflow() -> AssessmentWorkflow:
    return AssessmentWorkflow.from_environment(
        {
            "GREENSMECAPT_ASSESSMENT_POLICY": str(
                PROJECT_ROOT
                / "config/assessment_profiles.development.json"
            ),
            "GREENSMECAPT_NORMALIZATION_POLICY": str(
                PROJECT_ROOT
                / "config/normalization_policy.development.json"
            ),
            "GREENSMECAPT_ELECTRE_CONFIGURATION": str(
                PROJECT_ROOT
                / "config/electre_iii.development.json"
            ),
        }
    )


def _record(sme_id: str) -> StructuredInvestmentRecord:
    return StructuredInvestmentRecord(
        sme=SME(
            sme_id=sme_id,
            legal_name=f"Company {sme_id}",
            sector="Green services",
            jurisdiction="United Arab Emirates",
        )
    )


def _prepare(sme_id: str, value: str):
    return _workflow().prepare(
        record=_record(sme_id),
        context=AssessmentContext(
            sme_id=sme_id,
            activity_description="Environmental service provider.",
            facts={
                "manufactures_or_processes": False,
                "burns_fuel_on_site": False,
                "operates_vehicle_fleet": False,
                "operates_facility": False,
                "uses_cloud_services": False,
                "handles_materials_or_waste": False,
                "provides_clean_energy": False,
                "provides_circular_services": False,
                "works_on_buildings": False,
                "works_in_agriculture_food_land": False,
                "provides_digital_services": False,
                "offers_environmental_solution": False,
                "operates_retail_or_hospitality": False,
                "plans_operational_transition": False,
            },
        ),
        responses=(
            CriterionResponse(
                response_id=f"response_{sme_id}",
                sme_id=sme_id,
                criterion_id="green_contribution",
                kind=ResponseKind.LINGUISTIC,
                linguistic_value=value,
                submitted_by="reviewer_001",
            ),
        ),
    )


def test_prepare_traceable_assessment() -> None:
    prepared = _prepare("sme_001", "high")

    assert prepared.profile.applicable_criteria == (
        "green_contribution",
        "investment_context",
    )
    assert prepared.normalized_inputs.readiness == "ready"
    assert prepared.normalized_inputs.criteria[0].response_ids == (
        "response_sme_001",
    )


def test_compare_with_three_complementary_methods() -> None:
    workflow = _workflow()
    result = workflow.compare(
        (
            _prepare("sme_strong", "very_high"),
            _prepare("sme_weaker", "low"),
        ),
        CohortConfiguration(
            cohort_id="cohort_001",
            version="1.0",
            minimum_shared_criteria=1,
        ),
    )

    assert (
        result.comparable_topsis.topsis_result.ranking[0].sme_id
        == "sme_strong"
    )
    assert result.fuzzy_topsis.ranking[0].sme_id == "sme_strong"
    assert result.electre_iii.rank_levels[0].sme_ids == (
        "sme_strong",
    )


def test_reject_duplicate_smes() -> None:
    prepared = _prepare("sme_001", "high")

    with pytest.raises(
        AssessmentWorkflowError,
        match="duplicate SMEs",
    ):
        _workflow().compare(
            (prepared, prepared),
            CohortConfiguration(
                cohort_id="cohort_001",
                version="1.0",
                minimum_shared_criteria=1,
            ),
        )
