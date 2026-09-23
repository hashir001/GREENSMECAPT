"""Test honest resolution of SME answers and extracted evidence."""

import unittest
from pathlib import Path

from pydantic import ValidationError

from greensmecapt.assessment.observations import (
    CriterionResponse,
    ObservationStatus,
    build_observations,
)
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    build_profile,
    load_policy,
)
from greensmecapt.domain import EvidenceItem, EvidenceValidationStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "config" / "assessment_profiles.development.json"
EXAMPLE_DIR = PROJECT_ROOT / "examples" / "assessment_profiles"


class TestCriterionObservations(unittest.TestCase):
    def setUp(self) -> None:
        policy = load_policy(POLICY_PATH)
        context = AssessmentContext.model_validate_json(
            (EXAMPLE_DIR / "small_manufacturer.json").read_text(encoding="utf-8")
        )
        self.profile = build_profile(context, policy)

    def response(self, **changes: object) -> CriterionResponse:
        data: dict[str, object] = {
            "response_id": "response_001",
            "sme_id": self.profile.sme_id,
            "criterion_id": "green_contribution",
            "kind": "linguistic",
            "linguistic_value": "high",
            "submitted_by": "applicant_001",
        }
        data.update(changes)
        return CriterionResponse.model_validate(data)

    def evidence(self, **changes: object) -> EvidenceItem:
        data: dict[str, object] = {
            "evidence_id": "evidence_001",
            "sme_id": self.profile.sme_id,
            "document_id": "document_001",
            "indicator_id": "renewable_energy_percentage",
            "criterion_id": "purchased_energy_management",
            "raw_value": "72%",
            "normalized_value": 72.0,
            "unit": "percent",
            "source_locator": "page 1",
            "extraction_method": "regular_expression",
            "extractor_name": "renewable_energy_percentage_regex",
            "validation_status": EvidenceValidationStatus.ACCEPTED,
        }
        data.update(changes)
        return EvidenceItem.model_validate(data)

    @staticmethod
    def find(result, criterion_id: str):
        return next(
            item for item in result.observations if item.criterion_id == criterion_id
        )

    def test_unknown_is_not_converted_to_zero_or_neutral(self) -> None:
        result = build_observations(self.profile)
        item = self.find(result, "green_contribution")
        self.assertEqual(item.status, ObservationStatus.UNKNOWN)
        self.assertIsNone(item.exact_value)
        self.assertIsNone(item.linguistic_value)

    def test_not_measured_remains_distinct_from_not_applicable(self) -> None:
        response = self.response(
            criterion_id="direct_operational_emissions",
            kind="not_measured",
            linguistic_value=None,
        )
        result = build_observations(self.profile, responses=(response,))
        item = self.find(result, "direct_operational_emissions")
        self.assertEqual(item.status, ObservationStatus.NOT_MEASURED)

    def test_claimed_not_applicable_requires_review(self) -> None:
        response = self.response(
            criterion_id="direct_operational_emissions",
            kind="claimed_not_applicable",
            linguistic_value=None,
            narrative="All production equipment is electric.",
        )
        result = build_observations(self.profile, responses=(response,))
        item = self.find(result, "direct_operational_emissions")
        self.assertEqual(item.status, ObservationStatus.APPLICABILITY_REVIEW)

    def test_accepted_document_metric_is_available_but_not_scored(self) -> None:
        result = build_observations(self.profile, evidence_items=(self.evidence(),))
        item = self.find(result, "purchased_energy_management")
        self.assertEqual(item.status, ObservationStatus.READY_NUMERIC)
        self.assertEqual(item.exact_value, 72.0)
        self.assertEqual(item.source_indicator_ids, ("renewable_energy_percentage",))
        self.assertFalse(hasattr(item, "criterion_score"))

    def test_accepted_numeric_evidence_replaces_redundant_rating(
        self,
    ) -> None:
        """Reviewed measurements should outrank generic manual ratings."""

        response = self.response(
            response_id="response_energy_rating",
            criterion_id="purchased_energy_management",
            linguistic_value="low",
        )

        result = build_observations(
            self.profile,
            responses=(response,),
            evidence_items=(self.evidence(),),
        )
        item = self.find(
            result,
            "purchased_energy_management",
        )

        self.assertEqual(
            item.status,
            ObservationStatus.READY_NUMERIC,
        )
        self.assertEqual(item.exact_value, 72.0)
        self.assertEqual(item.response_ids, ())
        self.assertEqual(
            item.evidence_ids,
            ("evidence_001",),
        )

    def test_unvalidated_extraction_waits_for_acceptance(self) -> None:
        evidence = self.evidence(validation_status=EvidenceValidationStatus.UNVALIDATED)
        result = build_observations(self.profile, evidence_items=(evidence,))
        item = self.find(result, "purchased_energy_management")
        self.assertEqual(item.status, ObservationStatus.PENDING_REVIEW)
        self.assertEqual(item.evidence_ids, ("evidence_001",))

    def test_different_accepted_values_are_not_silently_averaged(self) -> None:
        evidence_items = (
            self.evidence(),
            self.evidence(evidence_id="evidence_002", normalized_value=64.0),
        )
        result = build_observations(self.profile, evidence_items=evidence_items)
        item = self.find(result, "purchased_energy_management")
        self.assertEqual(item.status, ObservationStatus.CONFLICT)
        self.assertIsNone(item.exact_value)

    def test_overlapping_ranges_are_narrowed_without_inventing_a_point(self) -> None:
        responses = (
            self.response(
                response_id="range_001",
                criterion_id="investment_context",
                kind="number_range",
                linguistic_value=None,
                lower_value=900000,
                upper_value=1100000,
                unit="AED annual revenue",
                reporting_period="FY2025",
            ),
            self.response(
                response_id="range_002",
                criterion_id="investment_context",
                kind="number_range",
                linguistic_value=None,
                lower_value=950000,
                upper_value=1200000,
                unit="AED annual revenue",
                reporting_period="FY2025",
            ),
        )
        result = build_observations(self.profile, responses=responses)
        item = self.find(result, "investment_context")
        self.assertEqual(item.status, ObservationStatus.READY_RANGE)
        self.assertEqual((item.lower_value, item.upper_value), (950000, 1100000))
        self.assertIsNone(item.exact_value)

    def test_non_overlapping_ranges_become_a_conflict(self) -> None:
        responses = (
            self.response(
                response_id="range_001",
                criterion_id="investment_context",
                kind="number_range",
                linguistic_value=None,
                lower_value=1,
                upper_value=2,
                unit="AED",
            ),
            self.response(
                response_id="range_002",
                criterion_id="investment_context",
                kind="number_range",
                linguistic_value=None,
                lower_value=3,
                upper_value=4,
                unit="AED",
            ),
        )
        result = build_observations(self.profile, responses=responses)
        self.assertEqual(
            self.find(result, "investment_context").status,
            ObservationStatus.CONFLICT,
        )

    def test_uncertain_applicability_is_not_missing_performance(self) -> None:
        context = AssessmentContext(
            sme_id="uncertain_sme",
            activity_description="A small company with incomplete activity answers.",
        )
        profile = build_profile(context, load_policy(POLICY_PATH))
        result = build_observations(profile)
        item = self.find(result, "direct_operational_emissions")
        self.assertEqual(item.status, ObservationStatus.APPLICABILITY_REVIEW)

    def test_response_payloads_cannot_mix_meanings(self) -> None:
        with self.assertRaises(ValidationError):
            self.response(kind="unknown", linguistic_value="medium")

    def test_referenced_evidence_must_be_supplied(self) -> None:
        response = self.response(supporting_evidence_ids=("missing_evidence",))
        with self.assertRaisesRegex(ValueError, "was not supplied"):
            build_observations(self.profile, responses=(response,))

    def test_wrong_sme_and_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "profile SME"):
            build_observations(
                self.profile,
                responses=(self.response(sme_id="another_sme"),),
            )
        duplicate = self.response()
        with self.assertRaisesRegex(ValueError, "Response IDs"):
            build_observations(self.profile, responses=(duplicate, duplicate))


if __name__ == "__main__":
    unittest.main()
