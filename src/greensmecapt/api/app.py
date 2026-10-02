"""FastAPI application for GREENSMECAPT."""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Self
from urllib.parse import quote
from uuid import uuid4

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session

from greensmecapt.api.assessment import build_assessment_router
from greensmecapt.api.configuration import (
    cors_origins_from_environment,
    validate_deployment_environment,
)
from greensmecapt.assessment.financial import (
    FinancialAssessmentPolicy,
    FinancialObservation,
)
from greensmecapt.assessment.workflow import AssessmentWorkflow
from greensmecapt.document_intelligence.semantics.intelligence import (
    SemanticProviderConnection,
    SemanticProviderError,
)
from greensmecapt.document_intelligence.understanding import (
    HybridSemanticExtractionError,
)
from greensmecapt.domain import (
    SME,
    DocumentBatchCheckpoint,
    DocumentJobStatus,
    DocumentProcessingJob,
    DocumentType,
    EvidenceItem,
    EvidenceValidationStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence import (
    ApplicationRepository,
    ApplicationStatus,
    ApplicationTransition,
    AssessmentProfileRepository,
    Database,
    DestructiveMutationRepository,
    FinancialSubmission,
    FinancialSubmissionRepository,
    FinancialSubmissionStatus,
    GreenSMERepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
    SMEApplication,
    StoredDocumentRegistration,
)
from greensmecapt.security import (
    ApplicationPermission,
    ApplicationRole,
    AuthPrincipal,
    IdentityAdmin,
    IdentityAdministrationError,
    ManagedUser,
    TokenVerifier,
    get_current_principal,
    identity_admin_from_environment,
    require_permission,
    require_roles,
    require_sme_permission,
    verifier_from_environment,
)
from greensmecapt.services import (
    DocumentProcessingError,
    DocumentProcessingJobService,
    DocumentProcessingResult,
    StoredDocumentProcessingService,
    build_document_processing_service,
)
from greensmecapt.storage import (
    DocumentStorage,
    DocumentStorageError,
    storage_from_environment,
)

_MAXIMUM_UPLOAD_BYTES = 20 * 1024 * 1024
_ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "image/jpeg",
        "image/png",
        "image/tiff",
    }
)


class EvidenceValidationRequest(BaseModel):
    """Request a traceable evidence-validation decision."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: EvidenceValidationStatus
    reason: str | None = Field(
        default=None,
        min_length=1,
    )


class BulkEvidenceValidationRequest(BaseModel):
    """Apply one traceable decision to a bounded evidence selection."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=500)
    status: EvidenceValidationStatus
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_bulk_decision(self) -> Self:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Bulk evidence IDs must be unique.")
        if self.status is EvidenceValidationStatus.UNVALIDATED:
            raise ValueError("Bulk review must accept or reject evidence.")
        if self.status is EvidenceValidationStatus.REJECTED and not self.reason:
            raise ValueError("Bulk rejection requires a reason.")
        return self


class ApplicationTransitionRequest(BaseModel):
    """Request one revision-checked SME application transition."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    expected_revision: int = Field(ge=1)
    target_status: ApplicationStatus
    reason: str | None = Field(default=None, min_length=1)


class SMEUpdateRequest(BaseModel):
    """Patch mutable SME metadata against an application revision."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    expected_application_revision: int = Field(ge=1)
    legal_name: str | None = Field(default=None, min_length=1)
    sector: str | None = Field(default=None, min_length=1)
    jurisdiction: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if all(
            value is None
            for value in (
                self.legal_name,
                self.sector,
                self.jurisdiction,
            )
        ):
            raise ValueError("At least one SME field must be supplied.")
        return self


class DestructiveMutationRequest(BaseModel):
    """Require an optimistic revision and human-readable deletion reason."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    expected_application_revision: int = Field(ge=1)
    reason: str = Field(min_length=1)


class SMEUpdateResponse(BaseModel):
    """Return updated metadata and the resulting lifecycle revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sme: SME
    application: SMEApplication


class DocumentDeletionResponse(BaseModel):
    """Confirm removal and return the resulting lifecycle revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    application: SMEApplication


class DocumentUploadResponse(BaseModel):
    """Return registered metadata for an uploaded document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document: SourceDocument
    storage_key: str = Field(min_length=1)
    processing_status: str = "stored"
    application: SMEApplication


class SystemCapabilities(BaseModel):
    """Expose operational feature wiring without revealing secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    native_pdf_reading: bool = True
    ocr_routing: bool = True
    table_extraction: bool = True
    semantic_provider_configured: bool
    visual_provider_configured: bool
    identity_admin_configured: bool
    human_validation_required: bool = True


class UserAccessRequest(BaseModel):
    """Assign one server-controlled application role."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    role: ApplicationRole
    sme_ids: tuple[str, ...] = ()


class UserInvitationRequest(UserAccessRequest):
    """Invite one user with their initial application access."""

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )


class FinancialSubmissionWriteRequest(BaseModel):
    """Save the SME's current financial observations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int | None = Field(default=None, ge=1)
    observations: tuple[FinancialObservation, ...]


class FinancialSubmissionTransitionRequest(BaseModel):
    """Revision-check a financial submit or review decision."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    expected_revision: int = Field(ge=1)
    decision: FinancialSubmissionStatus | None = None
    note: str | None = Field(default=None, min_length=1, max_length=2000)


def create_app(
    *,
    database_url: str | None = None,
    token_verifier: TokenVerifier | None = None,
    document_storage: DocumentStorage | None = None,
    document_processor: StoredDocumentProcessingService | None = None,
    identity_administrator: IdentityAdmin | None = None,
) -> FastAPI:
    """Create a secured database-bound application."""

    validate_deployment_environment()

    database = Database(database_url)
    verifier = token_verifier or verifier_from_environment()
    storage_backend = document_storage or storage_from_environment()
    processing_service = document_processor or build_document_processing_service(storage_backend)
    identity_service = identity_administrator or identity_admin_from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema()
        yield

    app = FastAPI(
        title="GREENSMECAPT API",
        version="0.6.0",
        description=("Evidence-aware assessment and decision-support platform for green SMEs."),
        lifespan=lifespan,
    )
    cors_origins = cors_origins_from_environment()

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=False,
            allow_methods=[
                "GET",
                "POST",
                "PATCH",
                "DELETE",
                "OPTIONS",
            ],
            allow_headers=[
                "Authorization",
                "Content-Type",
            ],
        )
    app.state.database = database
    app.state.token_verifier = verifier
    app.state.document_storage = storage_backend
    app.state.document_processor = processing_service
    app.state.identity_administrator = identity_service
    app.state.assessment_workflow = AssessmentWorkflow.from_environment()

    def get_session() -> Iterator[Session]:
        with database.session() as session:
            yield session

    def run_document_job(job_id: str) -> None:
        """Execute queued work in an independent database session."""

        with database.session() as worker_session:
            DocumentProcessingJobService(processing_service).run(
                repository=GreenSMERepository(worker_session),
                job_id=job_id,
            )

    app.include_router(
        build_assessment_router(
            get_session=get_session,
            workflow=app.state.assessment_workflow,
        )
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready"}

    @app.get(
        "/system/capabilities",
        response_model=SystemCapabilities,
    )
    def system_capabilities(
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> SystemCapabilities:
        """Report which processing paths are configured in this runtime."""

        del principal
        return SystemCapabilities(
            semantic_provider_configured=(processing_service.semantic_provider_configured),
            visual_provider_configured=(processing_service.visual_provider_configured),
            identity_admin_configured=identity_service.configured,
        )

    @app.get("/financial/configuration", response_model=FinancialAssessmentPolicy)
    def get_financial_configuration(
        principal: Annotated[AuthPrincipal, Depends(get_current_principal)],
    ) -> FinancialAssessmentPolicy:
        """Expose the versioned fields without inventing a financial score."""

        del principal
        return app.state.assessment_workflow.financial_policy

    @app.get(
        "/financial/submissions",
        response_model=tuple[FinancialSubmission, ...],
    )
    def list_financial_submissions(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.VALIDATE_EVIDENCE)),
        ],
    ) -> tuple[FinancialSubmission, ...]:
        del principal
        return FinancialSubmissionRepository(session).list_for_review()

    @app.get(
        "/smes/{sme_id}/financial-submission",
        response_model=FinancialSubmission | None,
    )
    def get_financial_submission(
        sme_id: str,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[AuthPrincipal, Depends(get_current_principal)],
    ) -> FinancialSubmission | None:
        _require_sme_access(principal, sme_id)
        try:
            return FinancialSubmissionRepository(session).get(sme_id)
        except PersistenceNotFoundError:
            return None

    @app.put(
        "/smes/{sme_id}/financial-submission",
        response_model=FinancialSubmission,
    )
    def save_financial_submission(
        sme_id: str,
        request: FinancialSubmissionWriteRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.EDIT_SME)),
        ],
    ) -> FinancialSubmission:
        try:
            application = ApplicationRepository(session).get(sme_id)
            if application.status in {
                ApplicationStatus.APPROVED,
                ApplicationStatus.PUBLISHED,
                ApplicationStatus.ARCHIVED,
                ApplicationStatus.WITHDRAWN,
            }:
                raise PersistenceConflictError(
                    "Financial information cannot be changed after final "
                    "approval, publication, archival or withdrawal."
                )
            return FinancialSubmissionRepository(session).save_draft(
                sme_id=sme_id,
                observations=request.observations,
                actor_id=principal.user_id,
                expected_revision=request.expected_revision,
            )
        except PersistenceConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @app.post(
        "/smes/{sme_id}/financial-submission/submit",
        response_model=FinancialSubmission,
    )
    def submit_financial_submission(
        sme_id: str,
        request: FinancialSubmissionTransitionRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.EDIT_SME)),
        ],
    ) -> FinancialSubmission:
        try:
            return FinancialSubmissionRepository(session).submit(
                sme_id=sme_id,
                actor_id=principal.user_id,
                expected_revision=request.expected_revision,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except PersistenceConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @app.post(
        "/smes/{sme_id}/financial-submission/review",
        response_model=FinancialSubmission,
    )
    def review_financial_submission(
        sme_id: str,
        request: FinancialSubmissionTransitionRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.VALIDATE_EVIDENCE)),
        ],
    ) -> FinancialSubmission:
        if request.decision is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A financial review decision is required.",
            )
        try:
            return FinancialSubmissionRepository(session).review(
                sme_id=sme_id,
                actor_id=principal.user_id,
                expected_revision=request.expected_revision,
                decision=request.decision,
                note=request.note,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except PersistenceConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @app.get(
        "/admin/users",
        response_model=tuple[ManagedUser, ...],
    )
    def list_managed_users(
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.MANAGE_USERS)),
        ],
    ) -> tuple[ManagedUser, ...]:
        """List users through the server-only Supabase admin boundary."""

        del principal

        try:
            return identity_service.list_users()
        except IdentityAdministrationError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    @app.post(
        "/admin/users/invitations",
        response_model=ManagedUser,
        status_code=status.HTTP_201_CREATED,
    )
    def invite_managed_user(
        request: UserInvitationRequest,
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.MANAGE_USERS)),
        ],
    ) -> ManagedUser:
        """Invite a user with validated role and SME access claims."""

        del principal

        try:
            return identity_service.invite_user(
                email=request.email,
                role=request.role,
                sme_ids=request.sme_ids,
            )
        except IdentityAdministrationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @app.patch(
        "/admin/users/{user_id}/access",
        response_model=ManagedUser,
    )
    def update_managed_user_access(
        user_id: str,
        request: UserAccessRequest,
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.MANAGE_USERS)),
        ],
    ) -> ManagedUser:
        """Replace role claims while preventing accidental self-lockout."""

        if user_id == principal.user_id and request.role is not ApplicationRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Administrators cannot remove their own admin access."),
            )

        try:
            return identity_service.update_access(
                user_id=user_id,
                role=request.role,
                sme_ids=request.sme_ids,
            )
        except IdentityAdministrationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @app.post(
        "/system/providers/semantic/check",
        response_model=SemanticProviderConnection,
    )
    def check_semantic_provider(
        principal: Annotated[
            AuthPrincipal,
            Depends(require_roles(ApplicationRole.ADMIN)),
        ],
    ) -> SemanticProviderConnection:
        """Verify key, endpoint, model access and structured output."""

        del principal

        try:
            return processing_service.check_semantic_provider()
        except HybridSemanticExtractionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except SemanticProviderError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    @app.post(
        "/smes",
        response_model=SME,
        status_code=status.HTTP_201_CREATED,
    )
    def create_sme(
        sme: SME,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.CREATE_SME)),
        ],
    ) -> SME:
        repository = GreenSMERepository(session)

        try:
            repository.save_record(
                StructuredInvestmentRecord(sme=sme),
                commit=False,
            )
            ApplicationRepository(session).create(
                sme_id=sme.sme_id,
                actor_id=principal.user_id,
                commit=False,
            )
            session.commit()
        except PersistenceConflictError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except Exception:
            session.rollback()
            raise

        return repository.get_sme(sme.sme_id)

    @app.get(
        "/smes",
        response_model=tuple[SME, ...],
    )
    def list_smes(
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> tuple[SME, ...]:
        smes = GreenSMERepository(session).list_smes()

        if principal.role is ApplicationRole.INVESTOR:
            return tuple(
                profile.record_snapshot.sme
                for profile in AssessmentProfileRepository(session).list_published_profiles()
            )

        return tuple(sme for sme in smes if principal.can_access_sme(sme.sme_id))

    @app.get(
        "/smes/{sme_id}/application",
        response_model=SMEApplication,
    )
    def get_sme_application(
        sme_id: str,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> SMEApplication:
        """Return lifecycle state only to raw-record participants."""

        _require_sme_access(principal, sme_id)

        try:
            return ApplicationRepository(session).get(sme_id)
        except PersistenceNotFoundError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.patch(
        "/smes/{sme_id}/application",
        response_model=SMEApplication,
    )
    def transition_sme_application(
        sme_id: str,
        request: ApplicationTransitionRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(
                require_roles(
                    ApplicationRole.ADMIN,
                    ApplicationRole.REVIEWER,
                    ApplicationRole.SME_USER,
                )
            ),
        ],
    ) -> SMEApplication:
        """Apply a role-aware, revision-checked lifecycle transition."""

        _require_sme_access(principal, sme_id)
        _require_application_transition_role(
            principal.role,
            request.target_status,
        )

        try:
            applications = ApplicationRepository(session)
            current = applications.get(sme_id)
            if (
                current.status is ApplicationStatus.PUBLISHED
                and request.target_status is not ApplicationStatus.PUBLISHED
            ):
                AssessmentProfileRepository(session).withdraw(
                    sme_id=sme_id,
                    actor_id=principal.user_id,
                    reason=(request.reason or "Application publication status changed"),
                    commit=False,
                )
            updated = applications.transition(
                sme_id=sme_id,
                transition=ApplicationTransition(
                    target_status=request.target_status,
                    reason=request.reason,
                ),
                actor_id=principal.user_id,
                expected_revision=request.expected_revision,
                commit=False,
            )
            session.commit()
            return updated
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

    @app.get(
        "/smes/{sme_id}",
        response_model=SME,
    )
    def get_sme(
        sme_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> SME:
        _require_sme_access(principal, sme_id)

        try:
            return GreenSMERepository(session).get_sme(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.patch(
        "/smes/{sme_id}",
        response_model=SMEUpdateResponse,
    )
    def update_sme(
        sme_id: str,
        request: SMEUpdateRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.EDIT_SME)),
        ],
    ) -> SMEUpdateResponse:
        """Update editable application metadata in one transaction."""

        repository = GreenSMERepository(session)
        applications = ApplicationRepository(session)

        try:
            current = repository.get_sme(sme_id)
            application = applications.get(sme_id)
            _require_application_data_mutable(
                principal=principal,
                application=application,
                allow_reviewer=False,
            )
            reason = request.reason or "SME metadata updated"
            updated = repository.update_sme(
                sme_id=sme_id,
                legal_name=request.legal_name or current.legal_name,
                sector=request.sector or current.sector,
                jurisdiction=(request.jurisdiction or current.jurisdiction),
                actor_id=principal.user_id,
                reason=reason,
                commit=False,
            )
            application = applications.record_change(
                sme_id=sme_id,
                actor_id=principal.user_id,
                expected_revision=request.expected_application_revision,
                reason=reason,
                commit=False,
            )
            session.commit()
            return SMEUpdateResponse(
                sme=updated,
                application=application,
            )
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
        except Exception:
            session.rollback()
            raise

    @app.delete(
        "/smes/{sme_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_sme(
        sme_id: str,
        request: DestructiveMutationRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.DELETE_SME)),
        ],
    ) -> Response:
        """Permanently purge an SME and all associated platform data."""

        repository = GreenSMERepository(session)
        backups: list[tuple[StoredDocumentRegistration, bytes | None]] = []
        storage_deleted: list[StoredDocumentRegistration] = []
        try:
            record = repository.get_record(sme_id)
            for document in record.documents:
                registration = repository.get_stored_document(document.document_id)
                try:
                    content = storage_backend.read(registration.storage_key)
                except DocumentStorageError:
                    # Legacy rows may point to an already-missing object or an
                    # old key format. That must not make the database record
                    # impossible to purge.
                    content = None
                backups.append((registration, content))
            registrations = DestructiveMutationRepository(session).purge_sme(
                sme_id=sme_id,
                actor_id=principal.user_id,
                expected_revision=request.expected_application_revision,
                reason=request.reason,
                commit=False,
            )
            for registration in registrations:
                try:
                    storage_backend.delete(registration.storage_key)
                    storage_deleted.append(registration)
                except DocumentStorageError:
                    # Hard deletion remains possible for legacy/orphaned
                    # storage metadata. Current valid objects are still
                    # removed normally.
                    pass
            session.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except PersistenceNotFoundError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (PersistenceConflictError, DocumentStorageError) as error:
            session.rollback()
            deleted_keys = {registration.storage_key for registration in storage_deleted}
            for registration, content in backups:
                if content is not None and registration.storage_key in deleted_keys:
                    _restore_deleted_document(
                        storage_backend=storage_backend,
                        registration=registration,
                        content=content,
                        storage_deleted=True,
                    )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except Exception:
            session.rollback()
            deleted_keys = {registration.storage_key for registration in storage_deleted}
            for registration, content in backups:
                if content is not None and registration.storage_key in deleted_keys:
                    _restore_deleted_document(
                        storage_backend=storage_backend,
                        registration=registration,
                        content=content,
                        storage_deleted=True,
                    )
            raise

    @app.get(
        "/smes/{sme_id}/record",
        response_model=StructuredInvestmentRecord,
    )
    def get_record(
        sme_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> StructuredInvestmentRecord:
        _require_sme_access(principal, sme_id)

        try:
            return GreenSMERepository(session).get_record(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.post(
        "/smes/{sme_id}/documents",
        response_model=DocumentUploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(
        sme_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.MANAGE_DOCUMENTS)),
        ],
        file: Annotated[UploadFile, File()],
        document_type: Annotated[
            DocumentType,
            Form(),
        ] = DocumentType.UNKNOWN,
        expected_application_revision: Annotated[int, Form()] = 1,
    ) -> DocumentUploadResponse:
        _require_sme_access(principal, sme_id)

        repository = GreenSMERepository(session)
        applications = ApplicationRepository(session)

        try:
            repository.get_sme(sme_id)
            application = applications.get(sme_id)
            _require_application_data_mutable(
                principal=principal,
                application=application,
                allow_reviewer=True,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

        mime_type = file.content_type or ""

        if mime_type not in _ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(f"Unsupported document MIME type: {mime_type!r}."),
            )

        content = await file.read(_MAXIMUM_UPLOAD_BYTES + 1)

        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded document is empty.",
            )

        if len(content) > _MAXIMUM_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Uploaded document exceeds 20 MiB.",
            )

        original_name = file.filename or "uploaded-document"
        safe_name = Path(original_name.replace("\\", "/")).name

        if not safe_name:
            safe_name = "uploaded-document"

        document = SourceDocument(
            document_id=f"doc_{uuid4().hex}",
            sme_id=sme_id,
            file_name=safe_name,
            mime_type=mime_type,
            sha256=sha256(content).hexdigest(),
            document_type=document_type,
        )

        try:
            storage_key = storage_backend.save(
                sme_id=sme_id,
                document_id=document.document_id,
                sha256=document.sha256,
                content=content,
            )

            repository.attach_document(
                document=document,
                storage_key=storage_key,
                actor_id=principal.user_id,
                commit=False,
            )
            application = applications.record_change(
                sme_id=sme_id,
                actor_id=principal.user_id,
                expected_revision=expected_application_revision,
                reason=f"Document uploaded: {safe_name}",
                commit=False,
            )
            session.commit()
        except (
            DocumentStorageError,
            PersistenceConflictError,
        ) as error:
            session.rollback()
            if "storage_key" in locals():
                storage_backend.delete(storage_key)

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except Exception:
            session.rollback()
            if "storage_key" in locals():
                storage_backend.delete(storage_key)
            raise

        return DocumentUploadResponse(
            document=document,
            storage_key=storage_key,
            application=application,
        )

    @app.delete(
        "/smes/{sme_id}/documents/{document_id}",
        response_model=DocumentDeletionResponse,
    )
    def delete_document(
        sme_id: str,
        document_id: str,
        request: DestructiveMutationRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.MANAGE_DOCUMENTS)),
        ],
    ) -> DocumentDeletionResponse:
        """Delete a source, its derived data and its private stored object."""

        applications = ApplicationRepository(session)
        storage_deleted = False
        registration: StoredDocumentRegistration | None = None
        original_content: bytes | None = None

        try:
            application = applications.get(sme_id)
            _require_application_data_mutable(
                principal=principal,
                application=application,
                allow_reviewer=True,
            )
            registration = _require_document_for_sme(
                repository=GreenSMERepository(session),
                document_id=document_id,
                sme_id=sme_id,
            )
            original_content = storage_backend.read(registration.storage_key)
            DestructiveMutationRepository(session).delete_document(
                sme_id=sme_id,
                document_id=document_id,
                actor_id=principal.user_id,
                reason=request.reason,
                commit=False,
            )
            application = applications.record_change(
                sme_id=sme_id,
                actor_id=principal.user_id,
                expected_revision=request.expected_application_revision,
                reason=request.reason,
                commit=False,
            )
            storage_deleted = True
            storage_backend.delete(registration.storage_key)
            session.commit()
            return DocumentDeletionResponse(
                document_id=document_id,
                application=application,
            )
        except PersistenceNotFoundError as error:
            session.rollback()
            _restore_deleted_document(
                storage_backend=storage_backend,
                registration=registration,
                content=original_content,
                storage_deleted=storage_deleted,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (PersistenceConflictError, DocumentStorageError) as error:
            session.rollback()
            _restore_deleted_document(
                storage_backend=storage_backend,
                registration=registration,
                content=original_content,
                storage_deleted=storage_deleted,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except Exception:
            session.rollback()
            _restore_deleted_document(
                storage_backend=storage_backend,
                registration=registration,
                content=original_content,
                storage_deleted=storage_deleted,
            )
            raise

    @app.get(
        "/smes/{sme_id}/documents/{document_id}/content",
        response_class=Response,
    )
    def get_document_content(
        sme_id: str,
        document_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> Response:
        """Return authorized original bytes for source inspection."""

        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)
        registration = _require_document_for_sme(
            repository=repository,
            document_id=document_id,
            sme_id=sme_id,
        )

        try:
            content = storage_backend.read(registration.storage_key)
        except DocumentStorageError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

        return Response(
            content=content,
            media_type=registration.document.mime_type,
            headers={
                "Content-Disposition": (
                    "inline; filename*=UTF-8''" + quote(registration.document.file_name)
                ),
                "Cache-Control": "private, no-store",
            },
        )

    @app.get(
        "/smes/{sme_id}/documents/{document_id}/processing",
        response_model=DocumentProcessingResult,
    )
    def get_document_processing(
        sme_id: str,
        document_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> DocumentProcessingResult:
        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)
        _require_document_for_sme(
            repository=repository,
            document_id=document_id,
            sme_id=sme_id,
        )

        try:
            return processing_service.get_result(
                repository=repository,
                document_id=document_id,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.post(
        "/smes/{sme_id}/documents/{document_id}/process",
        response_model=DocumentProcessingResult,
    )
    def process_document(
        sme_id: str,
        document_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.MANAGE_DOCUMENTS)),
        ],
    ) -> DocumentProcessingResult:
        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)
        _require_document_for_sme(
            repository=repository,
            document_id=document_id,
            sme_id=sme_id,
        )

        try:
            return processing_service.process(
                repository=repository,
                document_id=document_id,
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
        except DocumentProcessingError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": error.code,
                    "message": error.message,
                },
            ) from error

    @app.post(
        "/smes/{sme_id}/documents/{document_id}/processing-jobs",
        response_model=DocumentProcessingJob,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def queue_document_processing(
        sme_id: str,
        document_id: str,
        background_tasks: BackgroundTasks,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.MANAGE_DOCUMENTS)),
        ],
    ) -> DocumentProcessingJob:
        """Queue heavy processing and return a durable polling handle."""

        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)
        _require_document_for_sme(
            repository=repository,
            document_id=document_id,
            sme_id=sme_id,
        )

        try:
            job = repository.enqueue_document_processing(
                document_id=document_id,
                actor_id=principal.user_id,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

        if job.status is not DocumentJobStatus.RUNNING:
            background_tasks.add_task(
                run_document_job,
                job.job_id,
            )
        return job

    @app.get(
        "/smes/{sme_id}/documents/{document_id}/processing-jobs/{job_id}/batches",
        response_model=tuple[DocumentBatchCheckpoint, ...],
    )
    def list_document_processing_batches(
        sme_id: str,
        document_id: str,
        job_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> tuple[DocumentBatchCheckpoint, ...]:
        """Return durable page progress for one authorized job."""

        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)

        try:
            job = repository.get_document_processing_job(job_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

        if job.document_id != document_id or job.sme_id != sme_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document processing job was not found.",
            )

        return repository.list_document_batch_checkpoints(job_id)

    @app.get(
        ("/smes/{sme_id}/documents/{document_id}/processing-jobs/latest"),
        response_model=DocumentProcessingJob | None,
    )
    def get_latest_document_processing_job(
        sme_id: str,
        document_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> DocumentProcessingJob | None:
        """Return resumable progress for the newest document job."""

        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)
        _require_document_for_sme(
            repository=repository,
            document_id=document_id,
            sme_id=sme_id,
        )
        return repository.get_latest_document_processing_job(document_id)

    @app.get(
        "/smes/{sme_id}/documents/{document_id}/processing-jobs/{job_id}",
        response_model=DocumentProcessingJob,
    )
    def get_document_processing_job(
        sme_id: str,
        document_id: str,
        job_id: str,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> DocumentProcessingJob:
        """Return durable progress for one background job."""

        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)
        _require_document_for_sme(
            repository=repository,
            document_id=document_id,
            sme_id=sme_id,
        )

        try:
            job = repository.get_document_processing_job(job_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

        if job.document_id != document_id or job.sme_id != sme_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document processing job was not found.",
            )

        return job

    @app.post(
        "/smes/{sme_id}/documents/{document_id}/processing-jobs/{job_id}/retry",
        response_model=DocumentProcessingJob,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def retry_document_processing_job(
        sme_id: str,
        document_id: str,
        job_id: str,
        background_tasks: BackgroundTasks,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_sme_permission(ApplicationPermission.MANAGE_DOCUMENTS)),
        ],
    ) -> DocumentProcessingJob:
        """Retry failed work without creating an unbounded job chain."""

        _require_sme_access(principal, sme_id)
        repository = GreenSMERepository(session)

        try:
            job = repository.get_document_processing_job(job_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

        if job.document_id != document_id or job.sme_id != sme_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document processing job was not found.",
            )

        if job.status is not DocumentJobStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a failed document processing job can be retried.",
            )

        if job.attempt_count >= job.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document processing job exhausted its retry limit.",
            )

        background_tasks.add_task(
            run_document_job,
            job.job_id,
        )
        return job

    @app.patch(
        "/evidence/{evidence_id}/validation",
        response_model=EvidenceItem,
    )
    def validate_evidence(
        evidence_id: str,
        request: EvidenceValidationRequest,
        session: Annotated[
            Session,
            Depends(get_session),
        ],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.VALIDATE_EVIDENCE)),
        ],
    ) -> EvidenceItem:
        try:
            evidence = GreenSMERepository(session).get_evidence(evidence_id)

            _require_sme_access(
                principal,
                evidence.sme_id,
            )

            return GreenSMERepository(session).set_evidence_validation(
                evidence_id=evidence_id,
                status=request.status,
                actor_id=principal.user_id,
                reason=request.reason,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.patch(
        "/evidence/validation/bulk",
        response_model=tuple[EvidenceItem, ...],
    )
    def validate_evidence_bulk(
        request: BulkEvidenceValidationRequest,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[
            AuthPrincipal,
            Depends(require_permission(ApplicationPermission.VALIDATE_EVIDENCE)),
        ],
    ) -> tuple[EvidenceItem, ...]:
        """Save one atomic review decision across selected evidence items."""

        repository = GreenSMERepository(session)
        try:
            evidence_items = tuple(
                repository.get_evidence(evidence_id)
                for evidence_id in request.evidence_ids
            )
            for evidence in evidence_items:
                _require_sme_access(principal, evidence.sme_id)
            return repository.set_evidence_validations(
                evidence_ids=request.evidence_ids,
                status=request.status,
                actor_id=principal.user_id,
                reason=request.reason,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    return app


def _require_application_transition_role(
    role: ApplicationRole,
    target_status: ApplicationStatus,
) -> None:
    """Prevent actors from selecting lifecycle states they do not own."""

    allowed_targets = {
        ApplicationRole.ADMIN: set(ApplicationStatus) - {ApplicationStatus.PUBLISHED},
        ApplicationRole.REVIEWER: {
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.CHANGES_REQUESTED,
            ApplicationStatus.APPROVED,
        },
        ApplicationRole.SME_USER: {
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.WITHDRAWN,
        },
    }

    if target_status not in allowed_targets.get(role, set()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("The authenticated role cannot select this application status."),
        )


def _require_application_data_mutable(
    *,
    principal: AuthPrincipal,
    application: SMEApplication,
    allow_reviewer: bool,
) -> None:
    """Prevent silent changes to approved or published application data."""

    allowed = {
        ApplicationRole.ADMIN: {
            ApplicationStatus.DRAFT,
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.CHANGES_REQUESTED,
            ApplicationStatus.WITHDRAWN,
        },
        ApplicationRole.SME_USER: {
            ApplicationStatus.DRAFT,
            ApplicationStatus.CHANGES_REQUESTED,
        },
        ApplicationRole.REVIEWER: (
            {
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.UNDER_REVIEW,
                ApplicationStatus.CHANGES_REQUESTED,
            }
            if allow_reviewer
            else set()
        ),
    }

    if application.status not in allowed.get(principal.role, set()):
        raise PersistenceConflictError(
            "Approved or published application data cannot be changed "
            "silently. Move the application to changes requested first."
        )


def _restore_deleted_document(
    *,
    storage_backend: DocumentStorage,
    registration: StoredDocumentRegistration | None,
    content: bytes | None,
    storage_deleted: bool,
) -> None:
    """Compensate storage deletion if the database transaction fails."""

    if not storage_deleted or registration is None or content is None:
        return

    restored_key = storage_backend.save(
        sme_id=registration.document.sme_id,
        document_id=registration.document.document_id,
        sha256=registration.document.sha256,
        content=content,
    )
    if restored_key != registration.storage_key:
        raise DocumentStorageError("Deleted document storage could not be restored consistently.")


def _require_sme_access(
    principal: AuthPrincipal,
    sme_id: str,
) -> None:
    """Reject access outside an SME user's assignment."""

    if not principal.can_access_sme(sme_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("The authenticated user cannot access this SME."),
        )


def _require_document_for_sme(
    *,
    repository: GreenSMERepository,
    document_id: str,
    sme_id: str,
) -> StoredDocumentRegistration:
    """Reject missing documents and cross-SME path mismatches."""

    try:
        registration = repository.get_stored_document(document_id)
    except PersistenceNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if registration.document.sme_id != sme_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id!r} was not found.",
        )

    return registration


app = create_app()
