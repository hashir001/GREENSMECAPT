"""Exercise SME inclusion, applicability and editable-policy behaviour."""

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from greensmecapt.assessment.profiles import (
    Applicability,
    ApplicabilityOverride,
    AssessmentContext,
    AssessmentPolicy,
    build_profile,
    load_policy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "config" / "assessment_profiles.development.json"
EXAMPLE_DIR = PROJECT_ROOT / "examples" / "assessment_profiles"


class TestActivityProfiles(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(POLICY_PATH)

    def company(self, name: str) -> AssessmentContext:
        return AssessmentContext.model_validate_json(
            (EXAMPLE_DIR / f"{name}.json").read_text(encoding="utf-8")
        )

    def test_software_avoids_factory_requests_but_keeps_energy(self) -> None:
        profile = build_profile(self.company("green_software"), self.policy)
        statuses = {item.criterion_id: item.status for item in profile.decisions}
        self.assertEqual(
            statuses["direct_operational_emissions"], Applicability.NOT_APPLICABLE
        )
        self.assertEqual(
            statuses["purchased_energy_management"], Applicability.APPLICABLE
        )
        self.assertEqual(
            statuses["customer_environmental_effect"], Applicability.APPLICABLE
        )
        self.assertNotIn(
            "evidence:direct_operational_emissions",
            [item.request_id for item in profile.follow_ups],
        )
        self.assertTrue(profile.applicability_resolved)

    def test_manufacturer_without_carbon_inventory_gets_alternatives(self) -> None:
        profile = build_profile(self.company("small_manufacturer"), self.policy)
        request = next(
            item for item in profile.follow_ups
            if item.request_id == "evidence:direct_operational_emissions"
        )
        self.assertIn("fuel_or_process_records", request.response_routes)
        self.assertIn("bounded_activity_estimate", request.response_routes)
        self.assertIn("not_measured", request.response_routes)
        self.assertIn("direct_operational_emissions", profile.applicable_criteria)

    def test_unknown_activity_requests_clarification_without_excluding(self) -> None:
        profile = build_profile(self.company("activity_incomplete"), self.policy)
        decision = next(
            item for item in profile.decisions
            if item.criterion_id == "direct_operational_emissions"
        )
        self.assertEqual(decision.status, Applicability.UNCERTAIN)
        activity_ids = {
            item.request_id for item in profile.follow_ups
            if item.kind == "activity_question"
        }
        self.assertEqual(activity_ids, {
            "activity:burns_fuel_on_site", "activity:operates_vehicle_fleet",
        })
        self.assertIn("green_contribution", profile.applicable_criteria)
        self.assertFalse(profile.applicability_resolved)

    def test_absent_answers_are_unknown_not_false(self) -> None:
        context = AssessmentContext(
            sme_id="micro", activity_description="Repair workshop"
        )
        profile = build_profile(context, self.policy)
        statuses = {item.status for item in profile.decisions}
        self.assertIn(Applicability.UNCERTAIN, statuses)
        self.assertNotIn(Applicability.NOT_APPLICABLE, statuses)

    def test_sector_label_does_not_override_operating_facts(self) -> None:
        data = self.company("small_manufacturer").model_dump()
        data["sector"] = "Software"
        profile = build_profile(AssessmentContext.model_validate(data), self.policy)
        self.assertIn("direct_operational_emissions", profile.applicable_criteria)

    def test_one_true_alternative_is_enough_despite_unknowns(self) -> None:
        context = AssessmentContext(
            sme_id="micro", activity_description="Uses a diesel generator",
            facts={"burns_fuel_on_site": True},
        )
        profile = build_profile(context, self.policy)
        self.assertIn("direct_operational_emissions", profile.applicable_criteria)

    def test_unmet_all_condition_resolves_without_asking_unneeded_facts(self) -> None:
        data = self.policy.model_dump()
        data["criteria"][2]["when"] = {
            "all_true": ["manufactures_or_processes"],
            "any_true": ["burns_fuel_on_site", "operates_vehicle_fleet"],
        }
        policy = AssessmentPolicy.model_validate(data)
        context = AssessmentContext(
            sme_id="micro", activity_description="Services only",
            facts={"manufactures_or_processes": False},
        )
        profile = build_profile(context, policy)
        decision = next(
            item for item in profile.decisions
            if item.criterion_id == "direct_operational_emissions"
        )
        self.assertEqual(decision.status, Applicability.NOT_APPLICABLE)
        self.assertEqual(decision.missing_facts, ())

    def test_common_unknown_fact_creates_only_one_question(self) -> None:
        data = self.policy.model_dump()
        duplicate = dict(data["criteria"][2])
        duplicate["criterion_id"] = "additional_emissions_topic"
        data["criteria"] = (*data["criteria"], duplicate)
        profile = build_profile(
            self.company("activity_incomplete"), AssessmentPolicy.model_validate(data)
        )
        questions = [
            item for item in profile.follow_ups
            if item.request_id == "activity:burns_fuel_on_site"
        ]
        self.assertEqual(len(questions), 1)
        self.assertEqual(len(questions[0].criterion_ids), 2)

    def test_reviewed_override_preserves_original_rule_and_reason(self) -> None:
        override = ApplicabilityOverride(
            criterion_id="direct_operational_emissions",
            status=Applicability.NOT_APPLICABLE,
            decided_by="internal_reviewer_example",
            reason=(
                "Activity declaration was corrected: electric equipment, "
                "no combustion or process release."
            ),
            basis=("review_record_001",),
        )
        profile = build_profile(
            self.company("small_manufacturer"), self.policy, overrides=(override,)
        )
        decision = next(
            item for item in profile.decisions
            if item.criterion_id == override.criterion_id
        )
        self.assertEqual(decision.rule_status, Applicability.APPLICABLE)
        self.assertEqual(decision.status, Applicability.NOT_APPLICABLE)
        self.assertEqual(decision.override.basis, ("review_record_001",))

    def test_policy_typo_is_rejected(self) -> None:
        data = self.policy.model_dump()
        data["criteria"][2]["when"] = {"any_true": ["burns_fule_on_site"]}
        with self.assertRaisesRegex(ValidationError, "Undefined activity facts"):
            AssessmentPolicy.model_validate(data)

    def test_duplicate_criteria_and_broken_module_references_are_rejected(self) -> None:
        data = self.policy.model_dump()
        data["criteria"] = (*data["criteria"], data["criteria"][0])
        with self.assertRaisesRegex(ValidationError, "Duplicate criterion"):
            AssessmentPolicy.model_validate(data)
        data = self.policy.model_dump()
        data["criteria"][2]["module_ids"] = ("missing_module",)
        with self.assertRaisesRegex(ValidationError, "Undefined modules"):
            AssessmentPolicy.model_validate(data)

    def test_activity_answers_must_be_explicit_booleans_or_unknown(self) -> None:
        for value in ("false", "yes", 1, 0):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                AssessmentContext(
                    sme_id="micro", activity_description="Workshop",
                    facts={"burns_fuel_on_site": value},
                )

    def test_policy_change_changes_fingerprint_without_engine_change(self) -> None:
        context = self.company("green_software")
        original = build_profile(context, self.policy)
        data = self.policy.model_dump()
        data["criteria"][2]["when"] = {}
        changed = build_profile(context, AssessmentPolicy.model_validate(data))
        self.assertNotEqual(original.policy_sha256, changed.policy_sha256)
        self.assertIn("direct_operational_emissions", changed.applicable_criteria)
        self.assertNotIn("direct_operational_emissions", original.applicable_criteria)

    def test_profile_keeps_independent_context_snapshot(self) -> None:
        context = self.company("green_software")
        profile = build_profile(context, self.policy)
        context.facts["burns_fuel_on_site"] = True
        self.assertIs(profile.context_snapshot.facts["burns_fuel_on_site"], False)
        rebuilt = build_profile(profile.context_snapshot, profile.policy_snapshot)
        self.assertEqual(rebuilt.model_dump(), profile.model_dump())

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text('{"version":"1", "version":"2"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                load_policy(path)

    def test_unknown_context_and_override_references_are_rejected(self) -> None:
        data = self.company("green_software").model_dump()
        data["facts"]["burns_fule_on_site"] = True
        with self.assertRaisesRegex(ValueError, "Unrecognised activity facts"):
            build_profile(AssessmentContext.model_validate(data), self.policy)
        override = ApplicabilityOverride(
            criterion_id="missing", status=Applicability.NOT_APPLICABLE,
            decided_by="reviewer", reason="Test reason", basis=("test_record",),
        )
        with self.assertRaisesRegex(ValueError, "unknown criterion"):
            build_profile(
                self.company("green_software"), self.policy, overrides=(override,)
            )

    def test_serialized_profile_preserves_policy_and_no_invented_score(self) -> None:
        profile = build_profile(self.company("green_software"), self.policy)
        output = json.loads(profile.model_dump_json())
        self.assertEqual(output["policy_snapshot"]["status"], "development")
        self.assertNotIn("green_score", output)
        self.assertNotIn("mcdm_ready", output)

    def test_negative_condition_preserves_unknown_and_detects_contradiction(self) -> None:
        data = self.policy.model_dump()
        data["criteria"][2]["when"] = {"all_false": ["burns_fuel_on_site"]}
        policy = AssessmentPolicy.model_validate(data)
        for answer, expected in (
            (False, Applicability.APPLICABLE),
            (True, Applicability.NOT_APPLICABLE),
            (None, Applicability.UNCERTAIN),
        ):
            with self.subTest(answer=answer):
                context = AssessmentContext(
                    sme_id="example", activity_description="Example activity",
                    facts={"burns_fuel_on_site": answer},
                )
                profile = build_profile(context, policy)
                decision = next(
                    item for item in profile.decisions
                    if item.criterion_id == "direct_operational_emissions"
                )
                self.assertEqual(decision.status, expected)
        data["criteria"][2]["when"]["all_true"] = ["burns_fuel_on_site"]
        with self.assertRaisesRegex(ValidationError, "both true and false"):
            AssessmentPolicy.model_validate(data)
