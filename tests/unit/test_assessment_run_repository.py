"""Tests for immutable assessment-run persistence."""

from pathlib import Path

import pytest

from greensmecapt.assessment.cohort import CohortConfiguration
from greensmecapt.assessment.observations import (
    CriterionResponse,
    ResponseKind,
)
from greensmecapt.assessment.profiles import AssessmentContext
from greensmecapt.assessment.workflow import AssessmentWorkflow
from greensmecapt.domain import SME, StructuredInvestmentRecord
from greensmecapt.persistence import (
    AssessmentRunRepository,
    Database,
    PersistenceConflictError,
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


def _result(strong_value: str = "very_high"):
    workflow = AssessmentWorkflow.from_environment(
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

    def prepare(sme_id: str, value: str):
        record = StructuredInvestmentRecord(
            sme=SME(
                sme_id=sme_id,
                legal_name=f"Company {sme_id}",
                sector="Green services",
                jurisdiction="United Arab Emirates",
            )
        )
        facts = {
            fact_id: False
            for fact_id in FACT_IDS
        }

        return workflow.prepare(
            record=record,
            context=AssessmentContext(
                sme_id=sme_id,
                activity_description=(
                    "Environmental service provider."
                ),
                facts=facts,
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

    return workflow.compare(
        (
            prepare("sme_a", strong_value),
            prepare("sme_b", "low"),
        ),
        CohortConfiguration(
            cohort_id="cohort_001",
            version="1.0",
            minimum_shared_criteria=1,
        ),
    )


def test_save_and_reconstruct_complete_run(
    tmp_path: Path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'runs.db'}"
    )
    database.create_schema()

    with database.session() as session:
        repository = AssessmentRunRepository(session)

        saved = repository.save(
            run_id="run_001",
            result=_result(),
            actor_id="reviewer_001",
        )
        retrieved = repository.get("run_001")

    assert retrieved == saved
    assert retrieved.sme_ids == ("sme_a", "sme_b")
    assert (
        retrieved.result.fuzzy_topsis.ranking[0].sme_id
        == "sme_a"
    )


def test_identical_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'runs.db'}"
    )
    database.create_schema()
    result = _result()

    with database.session() as session:
        repository = AssessmentRunRepository(session)

        first = repository.save(
            run_id="run_001",
            result=result,
            actor_id="reviewer_001",
        )
        second = repository.save(
            run_id="run_001",
            result=result,
            actor_id="reviewer_001",
        )

    assert first == second


def test_reject_replacement_of_completed_run(
    tmp_path: Path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'runs.db'}"
    )
    database.create_schema()

    with database.session() as session:
        repository = AssessmentRunRepository(session)

        repository.save(
            run_id="run_001",
            result=_result(),
            actor_id="reviewer_001",
        )

        with pytest.raises(
            PersistenceConflictError,
            match="different result",
        ):
            repository.save(
                run_id="run_001",
                result=_result("high"),
                actor_id="reviewer_001",
            )