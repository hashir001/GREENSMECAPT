"""FastAPI application for GREENSMECAPT."""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Annotated
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
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from greensmecapt.api.assessment import build_assessment_router
from greensmecapt.api.configuration import cors_origins_from_environment
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
    Database,
    GreenSMERepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
    StoredDocumentRegistration,
)
from greensmecapt.security import (
    ApplicationRole,
    AuthPrincipal,
    TokenVerifier,
    get_current_principal,
    require_roles,
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


class DocumentUploadResponse(BaseModel):
    """Return registered metadata for an uploaded document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document: SourceDocument
    storage_key: str = Field(min_length=1)
    processing_status: str = "stored"


class SystemCapabilities(BaseModel):
    """Expose operational feature wiring without revealing secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    native_pdf_reading: bool = True
    ocr_routing: bool = True
    table_extraction: bool = True
    semantic_provider_configured: bool
    visual_provider_configured: bool
    human_validation_required: bool = True


def create_app(
    *,
    database_url: str | None = None,
    token_verifier: TokenVerifier | None = None,
    document_storage: DocumentStorage | None = None,
    document_processor: StoredDocumentProcessingService | None = None,
) -> FastAPI:
    """Create a secured database-bound application."""

    database = Database(database_url)
    verifier = (
        token_verifier
        or verifier_from_environment()
    )
    storage_backend = (
        document_storage
        or storage_from_environment()
    )
    processing_service = (
        document_processor
        or build_document_processing_service(storage_backend)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema()
        yield

    app = FastAPI(
        title="GREENSMECAPT API",
        version="0.3.0",
        description=(
            "Evidence-aware assessment and decision-support "
            "platform for green SMEs."
        ),
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
    app.state.assessment_workflow = AssessmentWorkflow.from_environment()

    def get_session() -> Iterator[Session]:
        with database.session() as session:
            yield session

    def run_document_job(job_id: str) -> None:
        """Execute queued work in an independent database session."""

        with database.session() as worker_session:
            DocumentProcessingJobService(
                processing_service
            ).run(
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
            semantic_provider_configured=(
                processing_service.semantic_provider_configured
            ),
            visual_provider_configured=(
                processing_service.visual_provider_configured
            ),
        )

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
            Depends(
                require_roles(ApplicationRole.ADMIN)
            ),
        ],
    ) -> SME:
        repository = GreenSMERepository(session)

        try:
            repository.save_record(
                StructuredInvestmentRecord(sme=sme)
            )
        except PersistenceConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

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
        smes = GreenSMERepository(
            session
        ).list_smes()

        return tuple(
            sme
            for sme in smes
            if principal.can_access_sme(sme.sme_id)
        )

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
            return GreenSMERepository(
                session
            ).get_sme(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

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
            return GreenSMERepository(
                session
            ).get_record(sme_id)
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
            Depends(
                require_roles(
                    ApplicationRole.ADMIN,
                    ApplicationRole.REVIEWER,
                    ApplicationRole.SME_USER,
                )
            ),
        ],
        file: Annotated[UploadFile, File()],
        document_type: Annotated[
            DocumentType,
            Form(),
        ] = DocumentType.UNKNOWN,
    ) -> DocumentUploadResponse:
        _require_sme_access(principal, sme_id)

        repository = GreenSMERepository(session)

        try:
            repository.get_sme(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

        mime_type = file.content_type or ""

        if mime_type not in _ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Unsupported document MIME type: "
                    f"{mime_type!r}."
                ),
            )

        content = await file.read(
            _MAXIMUM_UPLOAD_BYTES + 1
        )

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

        original_name = (
            file.filename or "uploaded-document"
        )
        safe_name = Path(
            original_name.replace("\\", "/")
        ).name

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
            )
        except (
            DocumentStorageError,
            PersistenceConflictError,
        ) as error:
            if "storage_key" in locals():
                storage_backend.delete(storage_key)

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

        return DocumentUploadResponse(
            document=document,
            storage_key=storage_key,
        )

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
                    "inline; filename*=UTF-8''"
                    + quote(registration.document.file_name)
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
            Depends(
                require_roles(
                    ApplicationRole.ADMIN,
                    ApplicationRole.REVIEWER,
                    ApplicationRole.SME_USER,
                )
            ),
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
            Depends(
                require_roles(
                    ApplicationRole.ADMIN,
                    ApplicationRole.REVIEWER,
                    ApplicationRole.SME_USER,
                )
            ),
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
        (
            "/smes/{sme_id}/documents/{document_id}"
            "/processing-jobs/latest"
        ),
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
        return repository.get_latest_document_processing_job(
            document_id
        )

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
            Depends(
                require_roles(
                    ApplicationRole.ADMIN,
                    ApplicationRole.REVIEWER,
                    ApplicationRole.SME_USER,
                )
            ),
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

        if (
            job.attempt_count >= job.max_attempts
        ):
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
            Depends(
                require_roles(
                    ApplicationRole.ADMIN,
                    ApplicationRole.REVIEWER,
                )
            ),
        ],
    ) -> EvidenceItem:
        try:
            evidence = GreenSMERepository(
                session
            ).get_evidence(evidence_id)

            _require_sme_access(
                principal,
                evidence.sme_id,
            )

            return GreenSMERepository(
                session
            ).set_evidence_validation(
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

    return app


def _require_sme_access(
    principal: AuthPrincipal,
    sme_id: str,
) -> None:
    """Reject access outside an SME user's assignment."""

    if not principal.can_access_sme(sme_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "The authenticated user cannot access this SME."
            ),
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
