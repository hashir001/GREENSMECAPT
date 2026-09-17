"""End-to-end preparation and multi-method SME comparison workflow."""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.assessment.calibration import (
    MCDMCalibrationManifest,
    load_calibration_manifest,
)
from greensmecapt.assessment.cohort import (
    CohortConfiguration,
    ComparableTopsisResult,
    run_comparable_topsis,
)
from greensmecapt.assessment.electre_iii import (
    ElectreIIIConfiguration,
    ElectreIIIResult,
    load_electre_configuration,
    run_electre_iii,
)
from greensmecapt.assessment.fuzzy_topsis import (
    FuzzyTopsisResult,
    run_fuzzy_topsis,
)
from greensmecapt.assessment.normalization import (
    NormalizationPolicy,
    NormalizedAssessmentInputs,
    load_normalization_policy,
    normalize_observations,
)
from greensmecapt.assessment.observations import (
    CriterionResponse,
    ObservationSet,
    build_observations,
)
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    AssessmentPolicy,
    AssessmentProfile,
    build_profile,
    load_policy,
)
from greensmecapt.assessment.robustness import (
    RankingRobustnessResult,
    RobustnessConfiguration,
    analyze_ranking_robustness,
)
from greensmecapt.domain import StructuredInvestmentRecord


class AssessmentWorkflowError(ValueError):
    """Raised when an assessment workflow request is inconsistent."""


class AssessmentWorkflowModel(BaseModel):
    """Provide immutable assessment workflow contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class PreparedAssessment(AssessmentWorkflowModel):
    """Contain the complete traceable preparation result for one SME."""

    profile: AssessmentProfile
    observations: ObservationSet
    normalized_inputs: NormalizedAssessmentInputs


class CohortAssessmentResult(AssessmentWorkflowModel):
    """Contain complementary cohort rankings from one shared input set."""

    preparations: tuple[PreparedAssessment, ...] = Field(min_length=2)
    comparable_topsis: ComparableTopsisResult
    fuzzy_topsis: FuzzyTopsisResult
    electre_iii: ElectreIIIResult
    robustness: RankingRobustnessResult | None = None
    calibration: MCDMCalibrationManifest | None = None


class AssessmentWorkflow:
    """Prepare SME evidence and run reproducible comparison methods."""

    def __init__(
        self,
        *,
        assessment_policy: AssessmentPolicy,
        normalization_policy: NormalizationPolicy,
        electre_configuration: ElectreIIIConfiguration,
        robustness_configuration: RobustnessConfiguration | None = None,
        calibration_manifest: MCDMCalibrationManifest | None = None,
    ) -> None:
        self._assessment_policy = assessment_policy
        self._normalization_policy = normalization_policy
        self._electre_configuration = electre_configuration
        self._robustness_configuration = (
            robustness_configuration or RobustnessConfiguration()
        )
        self._calibration_manifest = calibration_manifest

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "AssessmentWorkflow":
        """Load versioned assessment policy from configured JSON files."""

        configured = environment if environment is not None else os.environ

        return cls(
            assessment_policy=load_policy(
                Path(
                    configured.get(
                        "GREENSMECAPT_ASSESSMENT_POLICY",
                        "config/assessment_profiles.development.json",
                    )
                )
            ),
            normalization_policy=load_normalization_policy(
                Path(
                    configured.get(
                        "GREENSMECAPT_NORMALIZATION_POLICY",
                        "config/normalization_policy.development.json",
                    )
                )
            ),
            electre_configuration=load_electre_configuration(
                Path(
                    configured.get(
                        "GREENSMECAPT_ELECTRE_CONFIGURATION",
                        "config/electre_iii.development.json",
                    )
                )
            ),
            calibration_manifest=load_calibration_manifest(
                Path(
                    configured.get(
                        "GREENSMECAPT_MCDM_CALIBRATION",
                        "config/mcdm_calibration.development.json",
                    )
                )
            ),
        )

    def prepare(
        self,
        *,
        record: StructuredInvestmentRecord,
        context: AssessmentContext,
        responses: Sequence[CriterionResponse] = (),
    ) -> PreparedAssessment:
        """Resolve applicability, observations and normalized inputs."""

        if record.sme.sme_id != context.sme_id:
            raise AssessmentWorkflowError(
                "The assessment context belongs to a different SME."
            )

        profile = build_profile(context, self._assessment_policy)
        observations = build_observations(
            profile,
            responses=responses,
            evidence_items=record.evidence_items,
        )
        normalized = normalize_observations(
            profile,
            observations,
            self._normalization_policy,
        )

        return PreparedAssessment(
            profile=profile,
            observations=observations,
            normalized_inputs=normalized,
        )

    def compare(
        self,
        preparations: Sequence[PreparedAssessment],
        configuration: CohortConfiguration,
    ) -> CohortAssessmentResult:
        """Run crisp TOPSIS, fuzzy TOPSIS and ELECTRE III together."""

        if len(preparations) < 2:
            raise AssessmentWorkflowError(
                "A cohort assessment requires at least two SMEs."
            )

        sme_ids = [
            item.normalized_inputs.sme_id
            for item in preparations
        ]

        if len(sme_ids) != len(set(sme_ids)):
            raise AssessmentWorkflowError(
                "A cohort assessment cannot contain duplicate SMEs."
            )

        normalized_inputs = tuple(
            item.normalized_inputs for item in preparations
        )
        comparable_topsis = run_comparable_topsis(
            normalized_inputs,
            configuration,
        )

        fuzzy_topsis = run_fuzzy_topsis(
            normalized_inputs,
            comparable_topsis,
        )
        electre_iii = run_electre_iii(
            normalized_inputs,
            comparable_topsis,
            self._electre_configuration,
        )
        robustness = analyze_ranking_robustness(
            inputs=normalized_inputs,
            cohort_configuration=configuration,
            electre_configuration=self._electre_configuration,
            baseline_topsis=comparable_topsis,
            baseline_fuzzy_topsis=fuzzy_topsis,
            baseline_electre=electre_iii,
            configuration=self._robustness_configuration,
        )

        return CohortAssessmentResult(
            preparations=tuple(preparations),
            comparable_topsis=comparable_topsis,
            fuzzy_topsis=fuzzy_topsis,
            electre_iii=electre_iii,
            robustness=robustness,
            calibration=self._calibration_manifest,
        )
