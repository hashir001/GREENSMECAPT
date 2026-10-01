"""Policy and profile contracts; these do not assign performance scores."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

NonBlank = Annotated[str, Field(min_length=1)]


class ProfileModel(BaseModel):
    """Validate fields and prevent accidental attribute reassignment."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNCERTAIN = "uncertain"


class Requirement(StrEnum):
    """Prompt priority, not automatic company rejection or permission to score."""

    CORE = "core"
    CONDITIONAL = "conditional"
    OPTIONAL = "optional"
    INFORMATIONAL = "informational"


class Rule(ProfileModel):
    """All configured groups must hold; missing fact values remain unknown."""

    all_true: tuple[NonBlank, ...] = ()
    any_true: tuple[NonBlank, ...] = ()
    all_false: tuple[NonBlank, ...] = ()


class ModuleRule(ProfileModel):
    module_id: NonBlank
    title: NonBlank
    when: Rule


class CriterionPolicy(ProfileModel):
    criterion_id: NonBlank
    title: NonBlank
    output: Literal["green", "financial", "context"]
    dimension: Literal[
        "environmental_performance",
        "financial_health",
        "investment_case",
        "readiness_context",
    ]
    scoring_role: Literal[
        "performance_criterion",
        "separate_financial_assessment",
        "non_scoring_context",
    ]
    requires_evidence_confirmation: StrictBool = True
    requirement: Requirement
    module_ids: tuple[NonBlank, ...] = ()
    indicator_ids: tuple[NonBlank, ...] = ()
    when: Rule
    question: NonBlank
    evidence_routes: tuple[NonBlank, ...] = Field(min_length=1)
    assessment_note: NonBlank


class AssessmentPolicy(ProfileModel):
    policy_id: NonBlank
    version: NonBlank
    status: Literal["development", "approved"] = "development"
    description: NonBlank
    fact_questions: dict[NonBlank, NonBlank] = Field(min_length=1)
    modules: tuple[ModuleRule, ...] = ()
    criteria: tuple[CriterionPolicy, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        for name, identifiers in (
            ("module", [item.module_id for item in self.modules]),
            ("criterion", [item.criterion_id for item in self.criteria]),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"Duplicate {name} IDs are not allowed.")

        module_ids = {item.module_id for item in self.modules}
        for item in (*self.modules, *self.criteria):
            rule = item.when
            references = set((*rule.all_true, *rule.any_true, *rule.all_false))
            unknown = references - self.fact_questions.keys()
            if unknown:
                raise ValueError(f"Undefined activity facts: {sorted(unknown)}")
            if set(rule.all_true) & set(rule.all_false):
                raise ValueError("A fact cannot be required both true and false.")
            if rule.any_true and set(rule.any_true) <= set(rule.all_false):
                raise ValueError("Rule requires a true fact from an all-false group.")

        for criterion in self.criteria:
            unknown_modules = set(criterion.module_ids) - module_ids
            if unknown_modules:
                raise ValueError(f"Undefined modules: {sorted(unknown_modules)}")
        return self


class AssessmentContext(ProfileModel):
    sme_id: NonBlank
    activity_description: NonBlank
    sector: str | None = None
    stage: str | None = None
    funding_purpose: str | None = None
    # Only explicit activity answers drive rules; sector labels do not.
    facts: dict[NonBlank, StrictBool | None] = Field(default_factory=dict)


class ApplicabilityOverride(ProfileModel):
    """An internal reviewed decision, never an applicant's self-approved claim."""

    criterion_id: NonBlank
    status: Applicability
    decided_by: NonBlank
    reason: NonBlank
    basis: tuple[NonBlank, ...] = Field(min_length=1)


class CriterionDecision(ProfileModel):
    criterion_id: NonBlank
    title: NonBlank
    output: Literal["green", "financial", "context"]
    dimension: Literal[
        "environmental_performance",
        "financial_health",
        "investment_case",
        "readiness_context",
    ]
    scoring_role: Literal[
        "performance_criterion",
        "separate_financial_assessment",
        "non_scoring_context",
    ]
    requires_evidence_confirmation: bool
    requirement: Requirement
    indicator_ids: tuple[str, ...] = ()
    rule_status: Applicability
    status: Applicability
    reason: NonBlank
    missing_facts: tuple[str, ...] = ()
    matched_facts: tuple[str, ...] = ()
    override: ApplicabilityOverride | None = None


class FollowUp(ProfileModel):
    request_id: NonBlank
    kind: Literal["activity_question", "evidence_question"]
    question: NonBlank
    criterion_ids: tuple[NonBlank, ...] = Field(min_length=1)
    response_routes: tuple[NonBlank, ...] = Field(min_length=1)


class AssessmentProfile(ProfileModel):
    sme_id: NonBlank
    policy_id: NonBlank
    policy_version: NonBlank
    policy_sha256: str
    context_sha256: str
    # Snapshots permit reconstruction even if a configuration file changes.
    policy_snapshot: AssessmentPolicy
    context_snapshot: AssessmentContext
    active_modules: tuple[str, ...]
    uncertain_modules: tuple[str, ...]
    decisions: tuple[CriterionDecision, ...]
    follow_ups: tuple[FollowUp, ...]

    @property
    def applicable_criteria(self) -> tuple[str, ...]:
        return tuple(
            item.criterion_id for item in self.decisions
            if item.status is Applicability.APPLICABLE
        )

    @property
    def applicability_resolved(self) -> bool:
        """This describes applicability only, not MCDM readiness."""
        return all(
            item.status is not Applicability.UNCERTAIN for item in self.decisions
        )
