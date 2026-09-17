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
from greensmecapt.assessment.observations import CriterionResponse
from greensmecapt.assessment.profiles import AssessmentContext
from greensmecapt.assessment.workflow import (
    AssessmentWorkflow,
    AssessmentWorkflowError,
    PreparedAssessment,
)
from greensmecapt.persistence import (
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


def build_assessment_router(
    *,
    get_session: Callable[[], Iterator[Session]],
    workflow: AssessmentWorkflow,
) -> APIRouter:
    """Build assessment routes with application-owned dependencies."""

    router = APIRouter(
        prefix="/assessments",
        tags=["assessments"],
    )
    reviewer_dependency = require_roles(
        ApplicationRole.ADMIN,
        ApplicationRole.REVIEWER,
    )
    results_dependency = require_roles(
        ApplicationRole.ADMIN,
        ApplicationRole.REVIEWER,
        ApplicationRole.INVESTOR,
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
            record = repository.get_record(
                submission.context.sme_id
            )

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
        except (
            AssessmentWorkflowError,
            ValueError,
        ) as error:
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
        """Prepare, compare and persist SMEs using one policy snapshot."""

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