"""Assessment preparation and cohort-comparison API routes."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Literal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from greensmecapt.assessment.autofill import (
    AssessmentAutofillResponse,
    build_assessment_autofill,
)
from greensmecapt.assessment.cohort import (
    CohortComparisonError,
    CohortConfiguration,
)
from greensmecapt.assessment.electre_iii import ElectreIIIError
from greensmecapt.assessment.evidence_strength import EvidenceStrengthPolicy
from greensmecapt.assessment.financial import (
    FinancialAssessmentPolicy,
    FinancialObservation,
)
from greensmecapt.assessment.fuzzy_dematel import DematelSpecification
from greensmecapt.assessment.fuzzy_topsis import FuzzyTopsisError
from greensmecapt.assessment.green_score import GreenScoreStatus
from greensmecapt.assessment.normalization import NormalizationPolicy
from greensmecapt.assessment.observations import CriterionResponse
from greensmecapt.assessment.performance_context import MetricComparisonContext
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    AssessmentPolicy,
)
from greensmecapt.assessment.readiness import ReadinessObservation
from greensmecapt.assessment.workflow import (
    AssessmentWorkflow,
    AssessmentWorkflowError,
    PreparedAssessment,
)
from greensmecapt.document_intelligence.semantics import MetricCatalog
from greensmecapt.domain import SME
from greensmecapt.persistence import (
    ApplicationRepository,
    ApplicationStatus,
    ApplicationTransition,
    AssessmentProfilePublication,
    AssessmentProfileRepository,
    AssessmentRunRecord,
    AssessmentRunRepository,
    AssessmentRunSummary,
    FinancialSubmissionRepository,
    GreenSMERepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
    SMEApplication,
    StoredAssessmentProfileRevision,
)
from greensmecapt.security import (
    ApplicationPermission,
    ApplicationRole,
    AuthPrincipal,
    require_permission,
)


class AssessmentSubmission(BaseModel):
    """Supply reviewed context and criterion responses for one SME."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    context: AssessmentContext
    responses: tuple[CriterionResponse, ...] = ()
    financial_observations: tuple[FinancialObservation, ...] = ()
    readiness_observations: tuple[ReadinessObservation, ...] = ()
    metric_contexts: tuple[MetricComparisonContext, ...] = ()


class CohortAssessmentRequest(BaseModel):
    """Request one governed multi-method cohort comparison."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    run_id: str = Field(min_length=1)
    cohort_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    minimum_shared_criteria: int = Field(default=2, ge=1)
    minimum_shared_weight_ratio: float = Field(
        default=0.6,
        gt=0.0,
        le=1.0,
    )
    submissions: tuple[AssessmentSubmission, ...] = Field(min_length=2)


class AutomaticCohortAssessmentRequest(BaseModel):
    """Compare SMEs using centrally approved profiles only."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    run_id: str = Field(min_length=1)
    cohort_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    sme_ids: tuple[str, ...] = Field(min_length=2)
    minimum_shared_criteria: int = Field(default=2, ge=1)
    minimum_shared_weight_ratio: float = Field(
        default=0.6,
        gt=0.0,
        le=1.0,
    )


class AssessmentConfigurationResponse(BaseModel):
    """Return the exact versioned policies that drive assessment forms."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    assessment_policy: AssessmentPolicy
    normalization_policy: NormalizationPolicy
    financial_policy: FinancialAssessmentPolicy
    readiness_specification: DematelSpecification
    metric_catalog: MetricCatalog
    evidence_strength_policy: EvidenceStrengthPolicy


class ProfilePublicationRequest(BaseModel):
    """Publish one approved revision with an optimistic lifecycle check."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    revision_id: str = Field(min_length=1)
    expected_application_revision: int = Field(ge=1)


class AssessmentProfileStatusResponse(BaseModel):
    """Expose profile readiness without leaking mutable assessment inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sme_id: str = Field(min_length=1)
    legal_name: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    application_status: ApplicationStatus
    application_revision: int = Field(ge=1)
    lifecycle_status: Literal[
        "not_prepared",
        "approved",
        "published",
        "approved_changes",
        "reapproval_required",
        "published_outdated",
    ]
    latest_revision_id: str | None = None
    latest_profile_version: int | None = Field(default=None, ge=1)
    latest_approved_at: datetime | None = None
    latest_policy_current: bool = False
    active_publication_id: str | None = None
    active_revision_id: str | None = None
    published_at: datetime | None = None
    active_policy_current: bool = False
    comparison_eligible: bool = False


class AssessmentRunDeletionRequest(BaseModel):
    """Require an explicit reason for permanent run deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=1000)


def build_assessment_router(
    *,
    get_session: Callable[[], Iterator[Session]],
    workflow: AssessmentWorkflow,
) -> APIRouter:
    """Build assessment routes with application-owned dependencies."""

    router = APIRouter(prefix="/assessments", tags=["assessments"])
    assessment_dependency = require_permission(ApplicationPermission.RUN_ASSESSMENTS)
    approval_dependency = require_permission(ApplicationPermission.APPROVE_PROFILES)
    publication_dependency = require_permission(ApplicationPermission.PUBLISH_PROFILES)
    results_dependency = require_permission(ApplicationPermission.VIEW_PUBLISHED_PROFILES)
    run_deletion_dependency = require_permission(ApplicationPermission.DELETE_ASSESSMENT_RUN)

    @router.get(
        "/configuration",
        response_model=AssessmentConfigurationResponse,
    )
    def get_assessment_configuration(
        principal: Annotated[
            AuthPrincipal,
            Depends(assessment_dependency),
        ],
    ) -> AssessmentConfigurationResponse:
        """Describe the authoritative questions, criteria and rating scale."""

        del principal
        return AssessmentConfigurationResponse(
            assessment_policy=workflow.assessment_policy,
            normalization_policy=workflow.normalization_policy,
            financial_policy=workflow.financial_policy,
            readiness_specification=workflow.readiness_specification,
            metric_catalog=workflow.metric_catalog,
            evidence_strength_policy=workflow.evidence_strength_policy,
        )

    @router.get(
        "/autofill/{sme_id}",
        response_model=AssessmentAutofillResponse,
    )
    def get_assessment_autofill(
        sme_id: str,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[AuthPrincipal, Depends(assessment_dependency)],
    ) -> AssessmentAutofillResponse:
        """Prefill editable assessment inputs from accepted evidence only."""

        del principal
        try:
            record = GreenSMERepository(session).get_record(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return build_assessment_autofill(
            record=record,
            financial_policy=workflow.financial_policy,
            metric_catalog=workflow.metric_catalog,
            readiness_specification=workflow.readiness_specification,
        )

    @router.get(
        "/profiles",
        response_model=tuple[AssessmentProfileStatusResponse, ...],
    )
    def list_assessment_profile_statuses(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[AuthPrincipal, Depends(assessment_dependency)],
    ) -> tuple[AssessmentProfileStatusResponse, ...]:
        """List every accessible SME's governed profile lifecycle state."""

        smes = GreenSMERepository(session).list_smes()
        return tuple(
            _profile_status(
                sme=sme,
                application=ApplicationRepository(session).get(sme.sme_id),
                repository=AssessmentProfileRepository(session),
                workflow=workflow,
            )
            for sme in smes
            if principal.can_access_sme(sme.sme_id)
        )

    @router.get(
        "/profiles/{sme_id}/status",
        response_model=AssessmentProfileStatusResponse,
    )
    def get_assessment_profile_status(
        sme_id: str,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[AuthPrincipal, Depends(assessment_dependency)],
    ) -> AssessmentProfileStatusResponse:
        """Return status needed to prepare, approve or publish one profile."""

        del principal
        try:
            sme = GreenSMERepository(session).get_sme(sme_id)
            application = ApplicationRepository(session).get(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return _profile_status(
            sme=sme,
            application=application,
            repository=AssessmentProfileRepository(session),
            workflow=workflow,
        )

    @router.post(
        "/prepare",
        response_model=PreparedAssessment,
    )
    def prepare_assessment(
        submission: AssessmentSubmission,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(assessment_dependency),
        ],
    ) -> PreparedAssessment:
        """Prepare one reviewer-controlled assessment without ranking it."""

        del principal
        repository = GreenSMERepository(session)

        try:
            record = repository.get_record(submission.context.sme_id)
            return workflow.prepare(
                record=record,
                context=submission.context,
                responses=submission.responses,
                financial_observations=submission.financial_observations,
                readiness_observations=submission.readiness_observations,
                metric_contexts=submission.metric_contexts,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (AssessmentWorkflowError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @router.post(
        "/profiles/{sme_id}/approve",
        response_model=StoredAssessmentProfileRevision,
    )
    def approve_assessment_profile(
        sme_id: str,
        submission: AssessmentSubmission,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(approval_dependency),
        ],
    ) -> StoredAssessmentProfileRevision:
        """Approve an immutable snapshot after validating all inputs."""

        if submission.context.sme_id != sme_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The path and assessment context SME IDs must match.",
            )

        try:
            application = ApplicationRepository(session).get(sme_id)
            if application.status is not ApplicationStatus.APPROVED:
                raise ValueError(
                    "The SME application must be approved before its "
                    "assessment profile can be approved."
                )
            record = GreenSMERepository(session).get_record(sme_id)
            approved_financial = FinancialSubmissionRepository(
                session
            ).approved_observations(sme_id)
            financial_observations = (
                approved_financial
                if approved_financial
                else submission.financial_observations
            )
            prepared = workflow.prepare(
                record=record,
                context=submission.context,
                responses=submission.responses,
                financial_observations=financial_observations,
                readiness_observations=submission.readiness_observations,
                metric_contexts=submission.metric_contexts,
            )
            if (
                prepared.green_score is None
                or prepared.green_score.status is not GreenScoreStatus.FINAL
            ):
                raise ValueError(
                    "The Green Score must be final before the assessment "
                    "profile can be approved. Resolve applicability and every "
                    "applicable environmental criterion first."
                )
            revision = AssessmentProfileRepository(session).approve(
                context=submission.context,
                responses=submission.responses,
                record_snapshot=record,
                assessment_policy=workflow.assessment_policy,
                normalization_policy=workflow.normalization_policy,
                financial_policy=workflow.financial_policy,
                readiness_specification=workflow.readiness_specification,
                metric_catalog=workflow.metric_catalog,
                evidence_strength_policy=workflow.evidence_strength_policy,
                financial_observations=financial_observations,
                readiness_observations=submission.readiness_observations,
                metric_contexts=submission.metric_contexts,
                actor_id=principal.user_id,
                commit=False,
            )
            session.commit()
            return revision
        except PersistenceNotFoundError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except PersistenceConflictError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except (AssessmentWorkflowError, ValueError) as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        except Exception:
            session.rollback()
            raise

    @router.post(
        "/profiles/{sme_id}/publish",
        response_model=AssessmentProfilePublication,
    )
    def publish_assessment_profile(
        sme_id: str,
        request: ProfilePublicationRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(publication_dependency),
        ],
    ) -> AssessmentProfilePublication:
        """Atomically publish a revision and advance the application."""

        try:
            publication = AssessmentProfileRepository(session).publish(
                sme_id=sme_id,
                revision_id=request.revision_id,
                actor_id=principal.user_id,
                commit=False,
            )
            ApplicationRepository(session).transition(
                sme_id=sme_id,
                transition=ApplicationTransition(target_status=ApplicationStatus.PUBLISHED),
                actor_id=principal.user_id,
                expected_revision=request.expected_application_revision,
                commit=False,
            )
            session.commit()
            return publication
        except PersistenceNotFoundError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except PersistenceConflictError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ValueError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        except Exception:
            session.rollback()
            raise

    @router.post(
        "/compare",
        response_model=AssessmentRunRecord,
    )
    def compare_assessments(
        request: CohortAssessmentRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(assessment_dependency),
        ],
    ) -> AssessmentRunRecord:
        """Prepare and compare SMEs from one consistent policy snapshot."""

        repository = GreenSMERepository(session)

        try:
            preparations = tuple(
                workflow.prepare(
                    record=repository.get_record(submission.context.sme_id),
                    context=submission.context,
                    responses=submission.responses,
                    financial_observations=submission.financial_observations,
                    readiness_observations=submission.readiness_observations,
                    metric_contexts=submission.metric_contexts,
                )
                for submission in request.submissions
            )

            result = workflow.compare(
                preparations,
                CohortConfiguration(
                    cohort_id=request.cohort_id,
                    version=request.version,
                    minimum_shared_criteria=(request.minimum_shared_criteria),
                    minimum_shared_weight_ratio=(request.minimum_shared_weight_ratio),
                ),
            )

            return AssessmentRunRepository(session).save(
                run_id=request.run_id,
                result=result,
                actor_id=principal.user_id,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except PersistenceConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except (
            AssessmentWorkflowError,
            CohortComparisonError,
            ElectreIIIError,
            FuzzyTopsisError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @router.post(
        "/compare/automatic",
        response_model=AssessmentRunRecord,
    )
    def compare_approved_profiles(
        request: AutomaticCohortAssessmentRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(results_dependency),
        ],
    ) -> AssessmentRunRecord:
        """Compare approved profiles without accepting investor judgements."""

        if len(request.sme_ids) != len(set(request.sme_ids)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="SME IDs must be unique within a comparison.",
            )

        profile_repository = AssessmentProfileRepository(session)

        try:
            profiles = tuple(profile_repository.get_published(sme_id) for sme_id in request.sme_ids)
            for profile in profiles:
                if not _profile_matches_workflow(profile, workflow):
                    raise ValueError(
                        f"Published profile for SME {profile.sme_id!r} "
                        "uses an older policy and requires reapproval."
                    )
            preparations = tuple(
                workflow.prepare(
                    record=profile.record_snapshot,
                    context=profile.context,
                    responses=profile.responses,
                    financial_observations=profile.financial_observations,
                    readiness_observations=profile.readiness_observations,
                    metric_contexts=profile.metric_contexts,
                )
                for profile in profiles
            )
            result = workflow.compare(
                preparations,
                CohortConfiguration(
                    cohort_id=request.cohort_id,
                    version=request.version,
                    minimum_shared_criteria=(request.minimum_shared_criteria),
                    minimum_shared_weight_ratio=(request.minimum_shared_weight_ratio),
                ),
            )

            return AssessmentRunRepository(session).save(
                run_id=request.run_id,
                result=result,
                actor_id=principal.user_id,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        except PersistenceConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except (
            AssessmentWorkflowError,
            CohortComparisonError,
            ElectreIIIError,
            FuzzyTopsisError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @router.get(
        "/runs",
        response_model=tuple[AssessmentRunSummary, ...],
    )
    def list_assessment_runs(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(results_dependency),
        ],
    ) -> tuple[AssessmentRunSummary, ...]:
        """List completed comparisons without returning large matrices."""

        requested_by = principal.user_id if principal.role is ApplicationRole.INVESTOR else None
        return AssessmentRunRepository(session).list(requested_by=requested_by)

    @router.get(
        "/runs/{run_id}",
        response_model=AssessmentRunRecord,
    )
    def get_assessment_run(
        run_id: str,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(results_dependency),
        ],
    ) -> AssessmentRunRecord:
        """Return a complete immutable comparison for inspection."""

        try:
            record = AssessmentRunRepository(session).get(run_id)
            if (
                principal.role is ApplicationRole.INVESTOR
                and record.requested_by != principal.user_id
            ):
                raise PersistenceNotFoundError(f"Assessment run {run_id!r} was not found.")
            return record
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @router.delete(
        "/runs/{run_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_assessment_run(
        run_id: str,
        request: AssessmentRunDeletionRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(run_deletion_dependency),
        ],
    ) -> None:
        """Allow an administrator to permanently remove a completed run."""

        try:
            AssessmentRunRepository(session).delete(
                run_id=run_id,
                actor_id=principal.user_id,
                reason=request.reason,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    return router


def _profile_matches_workflow(
    profile: StoredAssessmentProfileRevision,
    workflow: AssessmentWorkflow,
) -> bool:
    """Require every governed policy snapshot to match the active model."""

    return (
        profile.assessment_policy.policy_id == workflow.assessment_policy.policy_id
        and profile.assessment_policy.version == workflow.assessment_policy.version
        and profile.normalization_policy.policy_id
        == workflow.normalization_policy.policy_id
        and profile.normalization_policy.version
        == workflow.normalization_policy.version
        and profile.financial_policy is not None
        and profile.financial_policy.policy_id == workflow.financial_policy.policy_id
        and profile.financial_policy.version == workflow.financial_policy.version
        and profile.readiness_specification is not None
        and profile.readiness_specification.specification_id
        == workflow.readiness_specification.specification_id
        and profile.readiness_specification.version
        == workflow.readiness_specification.version
        and profile.metric_catalog is not None
        and profile.metric_catalog.catalog_id == workflow.metric_catalog.catalog_id
        and profile.metric_catalog.version == workflow.metric_catalog.version
        and profile.evidence_strength_policy is not None
        and profile.evidence_strength_policy.policy_id
        == workflow.evidence_strength_policy.policy_id
        and profile.evidence_strength_policy.version
        == workflow.evidence_strength_policy.version
    )


def _profile_status(
    *,
    sme: SME,
    application: SMEApplication,
    repository: AssessmentProfileRepository,
    workflow: AssessmentWorkflow,
) -> AssessmentProfileStatusResponse:
    latest = repository.get_latest(sme.sme_id)
    publication = repository.get_active_publication(sme.sme_id)
    active = (
        repository.get_revision(publication.revision_id)
        if publication is not None
        else None
    )
    latest_current = latest is not None and _profile_matches_workflow(latest, workflow)
    active_current = active is not None and _profile_matches_workflow(active, workflow)

    if publication is not None and active_current:
        lifecycle_status = (
            "published"
            if latest is not None and latest.revision_id == active.revision_id
            else "approved_changes"
        )
    elif publication is not None:
        lifecycle_status = "published_outdated"
    elif latest is not None and latest_current:
        lifecycle_status = "approved"
    elif latest is not None:
        lifecycle_status = "reapproval_required"
    else:
        lifecycle_status = "not_prepared"

    return AssessmentProfileStatusResponse(
        sme_id=sme.sme_id,
        legal_name=sme.legal_name,
        sector=sme.sector,
        application_status=application.status,
        application_revision=application.revision,
        lifecycle_status=lifecycle_status,
        latest_revision_id=latest.revision_id if latest is not None else None,
        latest_profile_version=latest.profile_version if latest is not None else None,
        latest_approved_at=latest.approved_at if latest is not None else None,
        latest_policy_current=latest_current,
        active_publication_id=(publication.publication_id if publication else None),
        active_revision_id=(publication.revision_id if publication else None),
        published_at=publication.published_at if publication else None,
        active_policy_current=active_current,
        comparison_eligible=active_current,
    )
