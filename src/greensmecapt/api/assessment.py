"""Assessment preparation and cohort-comparison API routes."""

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from greensmecapt.assessment.cohort import (
    CohortComparisonError,
    CohortConfiguration,
)
from greensmecapt.assessment.electre_iii import ElectreIIIError
from greensmecapt.assessment.fuzzy_topsis import FuzzyTopsisError
from greensmecapt.assessment.normalization import NormalizationPolicy
from greensmecapt.assessment.observations import CriterionResponse
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    AssessmentPolicy,
)
from greensmecapt.assessment.workflow import (
    AssessmentWorkflow,
    AssessmentWorkflowError,
    PreparedAssessment,
)
from greensmecapt.persistence import (
    AssessmentProfileRepository,
    AssessmentRunRecord,
    AssessmentRunRepository,
    AssessmentRunSummary,
    GreenSMERepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from greensmecapt.security import (
    ApplicationRole,
    AuthPrincipal,
    require_roles,
)


class AssessmentSubmission(BaseModel):
    """Supply reviewed context and criterion responses for one SME."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    context: AssessmentContext
    responses: tuple[CriterionResponse, ...] = ()


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
    submissions: tuple[AssessmentSubmission, ...] = Field(
        min_length=2
    )


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


def build_assessment_router(
    *,
    get_session: Callable[[], Iterator[Session]],
    workflow: AssessmentWorkflow,
) -> APIRouter:
    """Build assessment routes with application-owned dependencies."""

    router = APIRouter(prefix="/assessments", tags=["assessments"])
    reviewer_dependency = require_roles(
        ApplicationRole.ADMIN,
        ApplicationRole.REVIEWER,
    )
    results_dependency = require_roles(
        ApplicationRole.ADMIN,
        ApplicationRole.REVIEWER,
        ApplicationRole.INVESTOR,
    )

    @router.get(
        "/configuration",
        response_model=AssessmentConfigurationResponse,
    )
    def get_assessment_configuration(
        principal: Annotated[
            AuthPrincipal,
            Depends(reviewer_dependency),
        ],
    ) -> AssessmentConfigurationResponse:
        """Describe the authoritative questions, criteria and rating scale."""

        del principal
        return AssessmentConfigurationResponse(
            assessment_policy=workflow.assessment_policy,
            normalization_policy=workflow.normalization_policy,
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
            Depends(reviewer_dependency),
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
        "/compare",
        response_model=AssessmentRunRecord,
    )
    def compare_assessments(
        request: CohortAssessmentRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(reviewer_dependency),
        ],
    ) -> AssessmentRunRecord:
        """Prepare and compare SMEs from one consistent policy snapshot."""

        repository = GreenSMERepository(session)

        try:
            preparations = tuple(
                workflow.prepare(
                    record=repository.get_record(
                        submission.context.sme_id
                    ),
                    context=submission.context,
                    responses=submission.responses,
                )
                for submission in request.submissions
            )

            result = workflow.compare(
                preparations,
                CohortConfiguration(
                    cohort_id=request.cohort_id,
                    version=request.version,
                    minimum_shared_criteria=(
                        request.minimum_shared_criteria
                    ),
                    minimum_shared_weight_ratio=(
                        request.minimum_shared_weight_ratio
                    ),
                ),
            )

            profile_repository = AssessmentProfileRepository(
                session
            )

            for submission in request.submissions:
                profile_repository.save(
                    context=submission.context,
                    responses=submission.responses,
                    actor_id=principal.user_id,
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

        record_repository = GreenSMERepository(session)
        profile_repository = AssessmentProfileRepository(session)

        try:
            profiles = tuple(
                profile_repository.get(sme_id)
                for sme_id in request.sme_ids
            )
            preparations = tuple(
                workflow.prepare(
                    record=record_repository.get_record(
                        profile.sme_id
                    ),
                    context=profile.context,
                    responses=profile.responses,
                )
                for profile in profiles
            )
            result = workflow.compare(
                preparations,
                CohortConfiguration(
                    cohort_id=request.cohort_id,
                    version=request.version,
                    minimum_shared_criteria=(
                        request.minimum_shared_criteria
                    ),
                    minimum_shared_weight_ratio=(
                        request.minimum_shared_weight_ratio
                    ),
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

        del principal
        return AssessmentRunRepository(session).list()

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

        del principal

        try:
            return AssessmentRunRepository(session).get(run_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    return router
