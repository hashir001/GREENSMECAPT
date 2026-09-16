"""FastAPI application for GREENSMECAPT."""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from greensmecapt.domain import (
    SME,
    EvidenceItem,
    EvidenceValidationStatus,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence import (
    Database,
    GreenSMERepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
)


class EvidenceValidationRequest(BaseModel):
    """Request a traceable evidence-validation decision."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: EvidenceValidationStatus
    actor_id: str = Field(min_length=1)
    reason: str | None = Field(
        default=None,
        min_length=1,
    )


def create_app(
    *,
    database_url: str | None = None,
) -> FastAPI:
    """Create a database-bound application."""

    database = Database(database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema()
        yield

    app = FastAPI(
        title="GREENSMECAPT API",
        version="0.1.0",
        description=(
            "Evidence-aware assessment and decision-support "
            "platform for green SMEs."
        ),
        lifespan=lifespan,
    )
    app.state.database = database

    def get_session() -> Iterator[Session]:
        with database.session() as session:
            yield session

    

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report API availability."""

        return {"status": "ready"}

    @app.post(
        "/smes",
        response_model=SME,
        status_code=status.HTTP_201_CREATED,
    )
    def create_sme(
        sme: SME,
        session: Annotated[Session, Depends(get_session)],
    ) -> SME:
        """Persist one SME."""

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
        session: Annotated[Session, Depends(get_session)],
    ) -> tuple[SME, ...]:
        """List registered SMEs."""

        return GreenSMERepository(
            session
        ).list_smes()

    @app.get(
        "/smes/{sme_id}",
        response_model=SME,
    )
    def get_sme(
        sme_id: str,
        session: Annotated[Session, Depends(get_session)],
    ) -> SME:
        """Return one SME."""

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
        session: Annotated[Session, Depends(get_session)],
    ) -> StructuredInvestmentRecord:
        """Return documents and evidence for one SME."""

        try:
            return GreenSMERepository(
                session
            ).get_record(sme_id)
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.patch(
        "/evidence/{evidence_id}/validation",
        response_model=EvidenceItem,
    )
    def validate_evidence(
        evidence_id: str,
        request: EvidenceValidationRequest,
        session: Annotated[Session, Depends(get_session)],
    ) -> EvidenceItem:
        """Accept or reject extracted evidence."""

        try:
            return GreenSMERepository(
                session
            ).set_evidence_validation(
                evidence_id=evidence_id,
                status=request.status,
                actor_id=request.actor_id,
                reason=request.reason,
            )
        except PersistenceNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    return app


app = create_app()