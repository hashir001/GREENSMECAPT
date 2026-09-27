"""Tests for immutable profile approval and explicit publication."""

from pathlib import Path

from greensmecapt.assessment.observations import (
    CriterionResponse,
    ResponseKind,
)
from greensmecapt.assessment.profiles import AssessmentContext
from greensmecapt.assessment.workflow import AssessmentWorkflow
from greensmecapt.domain import SME, StructuredInvestmentRecord
from greensmecapt.persistence import (
    AssessmentProfileRepository,
    Database,
    GreenSMERepository,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FACT_IDS = (
    "manufactures_or_processes",
    "burns_fuel_on_site",
    "operates_vehicle_fleet",
    "operates_facility",
    "uses_cloud_services",
    "handles_materials_or_waste",
    "provides_clean_energy",
    "provides_circular_services",
    "works_on_buildings",
    "works_in_agriculture_food_land",
    "provides_digital_services",
    "offers_environmental_solution",
    "operates_retail_or_hospitality",
    "plans_operational_transition",
)


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
                PROJECT_ROOT / "config/electre_iii.development.json"
            ),
        }
    )


def _context(description: str) -> AssessmentContext:
    return AssessmentContext(
        sme_id="sme_001",
        activity_description=description,
        facts={fact_id: False for fact_id in FACT_IDS},
    )


def _responses(value: str) -> tuple[CriterionResponse, ...]:
    return (
        CriterionResponse(
            response_id=f"response_{value}",
            sme_id="sme_001",
            criterion_id="green_contribution",
            kind=ResponseKind.LINGUISTIC,
            linguistic_value=value,
            submitted_by="reviewer_001",
        ),
    )


def test_revisions_are_immutable_and_publication_is_explicit(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'profiles.db'}")
    database.create_schema()
    workflow = _workflow()
    record = StructuredInvestmentRecord(
        sme=SME(
            sme_id="sme_001",
            legal_name="Green SME",
            sector="Green services",
            jurisdiction="United Arab Emirates",
        )
    )

    with database.session() as session:
        GreenSMERepository(session).save_record(record)
        repository = AssessmentProfileRepository(session)
        first = repository.approve(
            context=_context("First approved description."),
            responses=_responses("high"),
            record_snapshot=record,
            assessment_policy=workflow.assessment_policy,
            normalization_policy=workflow.normalization_policy,
            actor_id="reviewer_001",
        )
        duplicate = repository.approve(
            context=_context("First approved description."),
            responses=_responses("high"),
            record_snapshot=record,
            assessment_policy=workflow.assessment_policy,
            normalization_policy=workflow.normalization_policy,
            actor_id="reviewer_001",
        )
        second = repository.approve(
            context=_context("Revised approved description."),
            responses=_responses("very_high"),
            record_snapshot=record,
            assessment_policy=workflow.assessment_policy,
            normalization_policy=workflow.normalization_policy,
            actor_id="reviewer_001",
        )
        repository.publish(
            sme_id="sme_001",
            revision_id=first.revision_id,
            actor_id="reviewer_001",
        )
        initially_published = repository.get_published("sme_001")
        repository.publish(
            sme_id="sme_001",
            revision_id=second.revision_id,
            actor_id="reviewer_001",
        )
        currently_published = repository.get_published("sme_001")

    assert duplicate.revision_id == first.revision_id
    assert first.profile_version == 1
    assert second.profile_version == 2
    assert initially_published.revision_id == first.revision_id
    assert currently_published.revision_id == second.revision_id
    assert (
        initially_published.context.activity_description
        == "First approved description."
    )
