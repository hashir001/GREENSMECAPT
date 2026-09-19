"""Relational persistence tables for GREENSMECAPT."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class SMERow(SQLModel, table=True):
    """Persist one SME."""

    __tablename__ = "smes"

    sme_id: str = Field(primary_key=True)
    legal_name: str = Field(index=True)
    sector: str = Field(index=True)
    jurisdiction: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class DocumentRow(SQLModel, table=True):
    """Persist source-document metadata."""

    __tablename__ = "documents"

    document_id: str = Field(primary_key=True)
    sme_id: str = Field(
        foreign_key="smes.sme_id",
        index=True,
    )
    file_name: str
    mime_type: str
    sha256: str = Field(index=True)
    document_type: str
    storage_key: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)


class DocumentProcessingRow(SQLModel, table=True):
    """Persist the processing lifecycle for one source document."""

    __tablename__ = "document_processing"

    document_id: str = Field(
        primary_key=True,
        foreign_key="documents.document_id",
    )
    sme_id: str = Field(
        foreign_key="smes.sme_id",
        index=True,
    )
    status: str = Field(default="stored", index=True)
    attempt_count: int = Field(default=0)

    evidence_count: int = Field(default=0)
    deterministic_evidence_count: int = Field(default=0)
    intelligent_evidence_count: int = Field(default=0)
    rejected_intelligent_claim_count: int = Field(default=0)
    intelligent_provider_status: str | None = Field(default=None)

    failure_code: str | None = Field(default=None)
    failure_message: str | None = Field(default=None)
    report_json: str | None = Field(default=None)

    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    updated_at: datetime = Field(default_factory=_utc_now)


class DocumentProcessingJobRow(SQLModel, table=True):
    """Persist one retryable request to process a document."""

    __tablename__ = "document_processing_jobs"

    job_id: str = Field(primary_key=True)
    document_id: str = Field(
        foreign_key="documents.document_id",
        index=True,
    )
    sme_id: str = Field(
        foreign_key="smes.sme_id",
        index=True,
    )
    requested_by: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    failure_code: str | None = Field(default=None)
    failure_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    updated_at: datetime = Field(default_factory=_utc_now)


class EvidenceRow(SQLModel, table=True):
    """Persist one traceable extracted fact."""

    __tablename__ = "evidence_items"

    evidence_id: str = Field(primary_key=True)
    sme_id: str = Field(
        foreign_key="smes.sme_id",
        index=True,
    )
    document_id: str = Field(
        foreign_key="documents.document_id",
        index=True,
    )
    indicator_id: str = Field(index=True)
    criterion_id: str | None = Field(
        default=None,
        index=True,
    )

    raw_value: str
    normalized_value_json: str
    unit: str | None = None
    reporting_period: str | None = None
    scope: str | None = None

    source_locator: str
    source_excerpt: str | None = None

    extraction_method: str
    extractor_name: str
    extractor_version: str | None = None
    confidence: float | None = None
    validation_status: str = Field(index=True)

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class AuditEventRow(SQLModel, table=True):
    """Persist a security and data-governance event."""

    __tablename__ = "audit_events"

    event_id: str = Field(
        default_factory=lambda: f"audit_{uuid4().hex}",
        primary_key=True,
    )
    sme_id: str | None = Field(default=None, index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    action: str = Field(index=True)
    actor_id: str = Field(index=True)
    reason: str | None = None
    previous_value_json: str | None = None
    new_value_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
