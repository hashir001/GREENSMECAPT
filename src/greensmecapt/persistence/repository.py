"""Transactional persistence for GREENSMECAPT domain records."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlmodel import Session, select

from greensmecapt.domain import (
    SME,
    DocumentBatchCheckpoint,
    DocumentBatchStatus,
    DocumentJobStatus,
    DocumentProcessingJob,
    DocumentProcessingState,
    DocumentProcessingStatus,
    DocumentType,
    EvidenceItem,
    EvidenceValidationStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence.tables import (
    AuditEventRow,
    DocumentBatchCheckpointRow,
    DocumentProcessingJobRow,
    DocumentProcessingRow,
    DocumentRow,
    EvidenceRow,
    SMERow,
)


class PersistenceConflictError(ValueError):
    """Raised when an identifier already represents different data."""


class PersistenceNotFoundError(LookupError):
    """Raised when a requested persistent entity is absent."""


@dataclass(frozen=True)
class StoredDocumentRegistration:
    """Join source metadata to its opaque storage reference."""

    document: SourceDocument
    storage_key: str


class GreenSMERepository:
    """Persist and reconstruct GREENSMECAPT domain objects."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_record(
        self,
        record: StructuredInvestmentRecord,
    ) -> None:
        """Persist a record atomically and idempotently."""

        try:
            self._save_sme(record.sme)

            for document in record.documents:
                self._save_document(document)

            for evidence in record.evidence_items:
                self._save_evidence(evidence)

            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def attach_document(
        self,
        *,
        document: SourceDocument,
        storage_key: str,
        actor_id: str,
    ) -> SourceDocument:
        """Persist uploaded metadata and its storage reference."""

        if self._session.get(SMERow, document.sme_id) is None:
            raise PersistenceNotFoundError(
                f"SME {document.sme_id!r} was not found."
            )

        try:
            self._save_document(document)
            self._session.flush()

            row = self._session.get(
                DocumentRow,
                document.document_id,
            )

            if row is None:
                raise PersistenceNotFoundError(
                    "Uploaded document could not be persisted."
                )

            if (
                row.storage_key is not None
                and row.storage_key != storage_key
            ):
                raise PersistenceConflictError(
                    "Document already references another "
                    "stored object."
                )

            row.storage_key = storage_key
            self._session.add(row)

            processing_row = self._session.get(
                DocumentProcessingRow,
                document.document_id,
            )

            if processing_row is None:
                self._session.add(
                    DocumentProcessingRow(
                        document_id=document.document_id,
                        sme_id=document.sme_id,
                    )
                )

            self._session.add(
                AuditEventRow(
                    sme_id=document.sme_id,
                    entity_type="document",
                    entity_id=document.document_id,
                    action="document_uploaded",
                    actor_id=actor_id,
                    reason=document.file_name,
                    new_value_json=json.dumps(
                        {
                            "storage_key": storage_key,
                            "sha256": document.sha256,
                        }
                    ),
                )
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return document

    def get_stored_document(
        self,
        document_id: str,
    ) -> StoredDocumentRegistration:
        """Return document metadata and its storage reference."""

        row = self._session.get(DocumentRow, document_id)

        if row is None:
            raise PersistenceNotFoundError(
                f"Document {document_id!r} was not found."
            )

        if row.storage_key is None:
            raise PersistenceNotFoundError(
                f"Document {document_id!r} has no stored content."
            )

        return StoredDocumentRegistration(
            document=_document_from_row(row),
            storage_key=row.storage_key,
        )

    def enqueue_document_processing(
        self,
        *,
        document_id: str,
        actor_id: str,
        max_attempts: int = 3,
    ) -> DocumentProcessingJob:
        """Persist a job, reusing any active job for the document."""

        document = self._session.get(DocumentRow, document_id)

        if document is None or document.storage_key is None:
            raise PersistenceNotFoundError(
                f"Stored document {document_id!r} was not found."
            )

        self.recover_stale_document_processing_jobs()

        latest = self._session.exec(
            select(DocumentProcessingJobRow)
            .where(DocumentProcessingJobRow.document_id == document_id)
            .order_by(DocumentProcessingJobRow.created_at.desc())
        ).first()

        if latest is not None:
            latest_status = DocumentJobStatus(latest.status)

            if latest_status in {
                DocumentJobStatus.QUEUED,
                DocumentJobStatus.RUNNING,
            } or (
                latest_status is DocumentJobStatus.FAILED
                and latest.attempt_count < latest.max_attempts
            ):
                return _document_job_from_row(latest)

        now = datetime.now(UTC)
        row = DocumentProcessingJobRow(
            job_id=f"job_{uuid4().hex}",
            document_id=document.document_id,
            sme_id=document.sme_id,
            requested_by=actor_id,
            max_attempts=max_attempts,
            created_at=now,
            updated_at=now,
        )

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=document.sme_id,
                    entity_type="document_processing_job",
                    entity_id=row.job_id,
                    action="document_processing_queued",
                    actor_id=actor_id,
                    new_value_json=json.dumps(
                        {
                            "document_id": document_id,
                            "max_attempts": max_attempts,
                        }
                    ),
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_job_from_row(row)

    def get_document_processing_job(
        self,
        job_id: str,
    ) -> DocumentProcessingJob:
        """Return one durable processing job."""

        row = self._session.get(DocumentProcessingJobRow, job_id)

        if row is None:
            raise PersistenceNotFoundError(
                f"Document processing job {job_id!r} was not found."
            )

        return _document_job_from_row(row)

    def initialize_document_batch_checkpoints(
        self,
        *,
        job_id: str,
        checkpoints: Sequence[DocumentBatchCheckpoint],
    ) -> tuple[DocumentBatchCheckpoint, ...]:
        """Persist a complete, non-overlapping page plan idempotently."""

        job = self._require_document_job_row(job_id)

        if not checkpoints:
            raise ValueError("At least one page checkpoint is required.")

        checkpoint_ids = [item.checkpoint_id for item in checkpoints]
        batch_ids = [item.batch_id for item in checkpoints]
        page_numbers = [
            page_number
            for item in checkpoints
            for page_number in item.page_numbers
        ]

        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise PersistenceConflictError(
                "Checkpoint IDs must be unique within a job."
            )

        if len(batch_ids) != len(set(batch_ids)):
            raise PersistenceConflictError(
                "Batch IDs must be unique within a job."
            )

        if len(page_numbers) != len(set(page_numbers)):
            raise PersistenceConflictError(
                "A source page may belong to only one checkpoint."
            )

        try:
            for checkpoint in checkpoints:
                if (
                    checkpoint.job_id != job.job_id
                    or checkpoint.document_id != job.document_id
                    or checkpoint.status
                    is not DocumentBatchStatus.PLANNED
                ):
                    raise PersistenceConflictError(
                        "Checkpoint plan does not match its processing job."
                    )

                candidate = _document_batch_row(checkpoint)
                existing = self._session.get(
                    DocumentBatchCheckpointRow,
                    checkpoint.checkpoint_id,
                )

                if existing is None:
                    self._session.add(candidate)
                elif _document_batch_signature(existing) != (
                    _document_batch_signature(candidate)
                ):
                    raise PersistenceConflictError(
                        "Checkpoint ID already represents different pages."
                    )

            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return self.list_document_batch_checkpoints(job_id)

    def list_document_batch_checkpoints(
        self,
        job_id: str,
    ) -> tuple[DocumentBatchCheckpoint, ...]:
        """Return all page checkpoints in source order."""

        self._require_document_job_row(job_id)
        rows = self._session.exec(
            select(DocumentBatchCheckpointRow).where(
                DocumentBatchCheckpointRow.job_id == job_id
            )
        ).all()
        rows.sort(
            key=lambda row: min(
                json.loads(row.page_numbers_json)
            )
        )
        return tuple(
            _document_batch_from_row(row)
            for row in rows
        )

    def start_document_batch_checkpoint(
        self,
        *,
        checkpoint_id: str,
        worker_id: str,
    ) -> DocumentBatchCheckpoint:
        """Claim one unfinished page batch for the job's active worker."""

        row = self._require_document_batch_row(checkpoint_id)
        status = DocumentBatchStatus(row.status)

        if status is DocumentBatchStatus.COMPLETED:
            return _document_batch_from_row(row)

        if status is DocumentBatchStatus.RUNNING:
            if row.worker_id == worker_id:
                return _document_batch_from_row(row)

            raise PersistenceConflictError(
                "Page checkpoint is owned by another worker."
            )

        if row.attempt_count >= row.max_attempts:
            raise PersistenceConflictError(
                "Page checkpoint exhausted its retry limit."
            )

        job = self._require_document_job_row(row.job_id)

        if (
            DocumentJobStatus(job.status) is not DocumentJobStatus.RUNNING
            or job.worker_id != worker_id
        ):
            raise PersistenceConflictError(
                "The active job worker must own every page checkpoint."
            )

        now = datetime.now(UTC)
        row.status = DocumentBatchStatus.RUNNING.value
        row.attempt_count += 1
        row.worker_id = worker_id
        row.failure_message = None
        row.result_json = None
        row.started_at = now
        row.completed_at = None
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_batch_from_row(row)

    def complete_document_batch_checkpoint(
        self,
        *,
        checkpoint_id: str,
        worker_id: str,
        result_json: str,
    ) -> DocumentBatchCheckpoint:
        """Save one successful page-batch output as a durable checkpoint."""

        if not result_json.strip():
            raise ValueError("Checkpoint output JSON must not be blank.")

        row = self._require_document_batch_row(checkpoint_id)

        if (
            DocumentBatchStatus(row.status) is not DocumentBatchStatus.RUNNING
            or row.worker_id != worker_id
        ):
            raise PersistenceConflictError(
                "Only the active worker can complete a page checkpoint."
            )

        now = datetime.now(UTC)
        row.status = DocumentBatchStatus.COMPLETED.value
        row.worker_id = None
        row.failure_message = None
        row.result_json = result_json
        row.completed_at = now
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_batch_from_row(row)

    def fail_document_batch_checkpoint(
        self,
        *,
        checkpoint_id: str,
        worker_id: str,
        failure_message: str,
    ) -> DocumentBatchCheckpoint:
        """Keep a failed batch retryable without discarding other output."""

        row = self._require_document_batch_row(checkpoint_id)

        if (
            DocumentBatchStatus(row.status) is not DocumentBatchStatus.RUNNING
            or row.worker_id != worker_id
        ):
            raise PersistenceConflictError(
                "Only the active worker can fail a page checkpoint."
            )

        now = datetime.now(UTC)
        row.status = DocumentBatchStatus.FAILED.value
        row.worker_id = None
        row.failure_message = failure_message
        row.result_json = None
        row.completed_at = now
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_batch_from_row(row)

    def start_document_processing_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> DocumentProcessingJob:
        """Claim queued or retryable failed work exactly once."""

        if lease_seconds < 1:
            raise ValueError("Job lease duration must be positive.")

        row = self._require_document_job_row(job_id)
        status = DocumentJobStatus(row.status)

        if status is DocumentJobStatus.COMPLETED:
            return _document_job_from_row(row)

        if status is DocumentJobStatus.RUNNING:
            if row.worker_id == worker_id:
                return _document_job_from_row(row)

            if not _lease_expired(row.lease_expires_at):
                raise PersistenceConflictError(
                    f"Processing job {job_id!r} is already running."
                )

        if row.attempt_count >= row.max_attempts:
            raise PersistenceConflictError(
                f"Processing job {job_id!r} exhausted its retry limit."
            )

        now = datetime.now(UTC)
        row.status = DocumentJobStatus.RUNNING.value
        row.attempt_count += 1
        row.failure_code = None
        row.failure_message = None
        row.worker_id = worker_id
        row.lease_expires_at = _seconds_after(
            now,
            lease_seconds,
        )
        row.last_heartbeat_at = now
        row.started_at = now
        row.completed_at = None
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_job_from_row(row)

    def heartbeat_document_processing_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> DocumentProcessingJob:
        """Extend a running job lease owned by the calling worker."""

        if lease_seconds < 1:
            raise ValueError("Job lease duration must be positive.")

        row = self._require_document_job_row(job_id)

        if (
            DocumentJobStatus(row.status) is not DocumentJobStatus.RUNNING
            or row.worker_id != worker_id
        ):
            raise PersistenceConflictError(
                "Only the active worker may heartbeat a running job."
            )

        now = datetime.now(UTC)
        row.last_heartbeat_at = now
        row.lease_expires_at = _seconds_after(now, lease_seconds)
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_job_from_row(row)

    def recover_stale_document_processing_jobs(
        self,
        *,
        as_of: datetime | None = None,
    ) -> tuple[DocumentProcessingJob, ...]:
        """Fail abandoned running jobs so their bounded retry can resume."""

        effective_now = as_of or datetime.now(UTC)
        rows = self._session.exec(
            select(DocumentProcessingJobRow).where(
                DocumentProcessingJobRow.status
                == DocumentJobStatus.RUNNING.value
            )
        ).all()
        recovered: list[DocumentProcessingJob] = []

        for row in rows:
            if not _lease_expired(
                row.lease_expires_at,
                as_of=effective_now,
            ):
                continue

            row.status = DocumentJobStatus.FAILED.value
            row.failure_code = "worker_lease_expired"
            row.failure_message = (
                "The processing worker stopped before completing the job."
            )
            row.worker_id = None
            row.lease_expires_at = None
            row.last_heartbeat_at = None
            row.completed_at = effective_now
            row.updated_at = effective_now
            self._session.add(row)

            checkpoint_rows = self._session.exec(
                select(DocumentBatchCheckpointRow).where(
                    DocumentBatchCheckpointRow.job_id == row.job_id,
                    DocumentBatchCheckpointRow.status
                    == DocumentBatchStatus.RUNNING.value,
                )
            ).all()

            for checkpoint_row in checkpoint_rows:
                checkpoint_row.status = DocumentBatchStatus.FAILED.value
                checkpoint_row.worker_id = None
                checkpoint_row.failure_message = (
                    "The processing worker lease expired."
                )
                checkpoint_row.completed_at = effective_now
                checkpoint_row.updated_at = effective_now
                self._session.add(checkpoint_row)

            processing_row = self._session.get(
                DocumentProcessingRow,
                row.document_id,
            )

            if (
                processing_row is not None
                and DocumentProcessingStatus(processing_row.status)
                is DocumentProcessingStatus.PROCESSING
            ):
                processing_row.status = (
                    DocumentProcessingStatus.FAILED.value
                )
                processing_row.failure_code = "worker_lease_expired"
                processing_row.failure_message = (
                    "The processing worker stopped before completion."
                )
                processing_row.completed_at = effective_now
                processing_row.updated_at = effective_now
                self._session.add(processing_row)

            recovered.append(_document_job_from_row(row))

        if recovered:
            try:
                self._session.commit()
            except Exception:
                self._session.rollback()
                raise

        return tuple(recovered)

    def complete_document_processing_job(
        self,
        *,
        job_id: str,
        worker_id: str,
    ) -> DocumentProcessingJob:
        """Mark claimed work complete."""

        row = self._require_document_job_row(job_id)

        if (
            DocumentJobStatus(row.status) is not DocumentJobStatus.RUNNING
            or row.worker_id != worker_id
        ):
            raise PersistenceConflictError(
                "Only the active worker can complete a running job."
            )

        now = datetime.now(UTC)
        row.status = DocumentJobStatus.COMPLETED.value
        row.failure_code = None
        row.failure_message = None
        row.worker_id = None
        row.lease_expires_at = None
        row.last_heartbeat_at = None
        row.completed_at = now
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=row.sme_id,
                    entity_type="document_processing_job",
                    entity_id=row.job_id,
                    action="document_processing_job_completed",
                    actor_id=row.requested_by,
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_job_from_row(row)

    def fail_document_processing_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        failure_code: str,
        failure_message: str,
    ) -> DocumentProcessingJob:
        """Persist controlled failure details so the job can be retried."""

        row = self._require_document_job_row(job_id)

        if (
            DocumentJobStatus(row.status) is not DocumentJobStatus.RUNNING
            or row.worker_id != worker_id
        ):
            raise PersistenceConflictError(
                "Only the active worker can fail a running job."
            )

        now = datetime.now(UTC)
        row.status = DocumentJobStatus.FAILED.value
        row.failure_code = failure_code
        row.failure_message = failure_message
        row.worker_id = None
        row.lease_expires_at = None
        row.last_heartbeat_at = None
        row.completed_at = now
        row.updated_at = now

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=row.sme_id,
                    entity_type="document_processing_job",
                    entity_id=row.job_id,
                    action="document_processing_job_failed",
                    actor_id=row.requested_by,
                    reason=failure_message,
                    new_value_json=json.dumps(
                        {"failure_code": failure_code}
                    ),
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _document_job_from_row(row)

    def get_document_processing_state(
        self,
        document_id: str,
    ) -> DocumentProcessingState:
        """Return durable processing progress for one document."""

        document = self._session.get(DocumentRow, document_id)

        if document is None:
            raise PersistenceNotFoundError(
                f"Document {document_id!r} was not found."
            )

        row = self._session.get(
            DocumentProcessingRow,
            document_id,
        )

        if row is None:
            return _processing_state_from_row(
                DocumentProcessingRow(
                    document_id=document.document_id,
                    sme_id=document.sme_id,
                    updated_at=document.created_at,
                )
            )

        return _processing_state_from_row(row)

    def begin_document_processing(
        self,
        *,
        document_id: str,
        actor_id: str,
    ) -> DocumentProcessingState:
        """Start or retry processing without duplicating completed work."""

        document = self._session.get(DocumentRow, document_id)

        if document is None:
            raise PersistenceNotFoundError(
                f"Document {document_id!r} was not found."
            )

        row = self._session.get(
            DocumentProcessingRow,
            document_id,
        )

        if row is None:
            row = DocumentProcessingRow(
                document_id=document.document_id,
                sme_id=document.sme_id,
            )

        current_status = DocumentProcessingStatus(row.status)

        if current_status is DocumentProcessingStatus.COMPLETED:
            return _processing_state_from_row(row)

        if current_status is DocumentProcessingStatus.PROCESSING:
            raise PersistenceConflictError(
                f"Document {document_id!r} is already being processed."
            )

        started_at = datetime.now(UTC)
        row.status = DocumentProcessingStatus.PROCESSING.value
        row.attempt_count += 1
        row.evidence_count = 0
        row.deterministic_evidence_count = 0
        row.intelligent_evidence_count = 0
        row.rejected_intelligent_claim_count = 0
        row.intelligent_provider_status = None
        row.failure_code = None
        row.failure_message = None
        row.report_json = None
        row.started_at = started_at
        row.completed_at = None
        row.updated_at = started_at

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=document.sme_id,
                    entity_type="document",
                    entity_id=document.document_id,
                    action="document_processing_started",
                    actor_id=actor_id,
                    new_value_json=json.dumps(
                        {
                            "attempt_count": row.attempt_count,
                            "status": row.status,
                        }
                    ),
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _processing_state_from_row(row)

    def complete_document_processing(
        self,
        *,
        document_id: str,
        evidence_items: tuple[EvidenceItem, ...],
        deterministic_evidence_count: int,
        intelligent_evidence_count: int,
        rejected_intelligent_claim_count: int,
        intelligent_provider_status: str,
        report_json: str,
        actor_id: str,
    ) -> DocumentProcessingState:
        """Persist extracted evidence and mark processing complete."""

        row = self._require_processing_row(document_id)

        if (
            DocumentProcessingStatus(row.status)
            is not DocumentProcessingStatus.PROCESSING
        ):
            raise PersistenceConflictError(
                "Only an active processing attempt can be completed."
            )

        for evidence in evidence_items:
            if (
                evidence.document_id != row.document_id
                or evidence.sme_id != row.sme_id
            ):
                raise PersistenceConflictError(
                    "Extracted evidence does not belong to the "
                    "processing document."
                )

        completed_at = datetime.now(UTC)

        try:
            for evidence in evidence_items:
                self._save_evidence(evidence)

            row.status = DocumentProcessingStatus.COMPLETED.value
            row.evidence_count = len(evidence_items)
            row.deterministic_evidence_count = (
                deterministic_evidence_count
            )
            row.intelligent_evidence_count = intelligent_evidence_count
            row.rejected_intelligent_claim_count = (
                rejected_intelligent_claim_count
            )
            row.intelligent_provider_status = intelligent_provider_status
            row.failure_code = None
            row.failure_message = None
            row.report_json = report_json
            row.completed_at = completed_at
            row.updated_at = completed_at

            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=row.sme_id,
                    entity_type="document",
                    entity_id=row.document_id,
                    action="document_processing_completed",
                    actor_id=actor_id,
                    new_value_json=json.dumps(
                        {
                            "evidence_count": len(evidence_items),
                            "status": row.status,
                        }
                    ),
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _processing_state_from_row(row)

    def fail_document_processing(
        self,
        *,
        document_id: str,
        failure_code: str,
        failure_message: str,
        actor_id: str,
    ) -> DocumentProcessingState:
        """Record a controlled failure while keeping the file retryable."""

        row = self._require_processing_row(document_id)

        if (
            DocumentProcessingStatus(row.status)
            is DocumentProcessingStatus.COMPLETED
        ):
            return _processing_state_from_row(row)

        if (
            DocumentProcessingStatus(row.status)
            is not DocumentProcessingStatus.PROCESSING
        ):
            raise PersistenceConflictError(
                "Only an active processing attempt can fail."
            )

        completed_at = datetime.now(UTC)
        row.status = DocumentProcessingStatus.FAILED.value
        row.failure_code = failure_code
        row.failure_message = failure_message
        row.completed_at = completed_at
        row.updated_at = completed_at

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=row.sme_id,
                    entity_type="document",
                    entity_id=row.document_id,
                    action="document_processing_failed",
                    actor_id=actor_id,
                    reason=failure_message,
                    new_value_json=json.dumps(
                        {
                            "failure_code": failure_code,
                            "status": row.status,
                        }
                    ),
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _processing_state_from_row(row)

    def get_document_processing_report(
        self,
        document_id: str,
    ) -> str | None:
        """Return the stored semantic diagnostics JSON, when available."""

        row = self._session.get(
            DocumentProcessingRow,
            document_id,
        )

        if row is None:
            self.get_stored_document(document_id)
            return None

        return row.report_json

    def list_document_evidence(
        self,
        document_id: str,
    ) -> tuple[EvidenceItem, ...]:
        """Return evidence from one document in stable order."""

        if self._session.get(DocumentRow, document_id) is None:
            raise PersistenceNotFoundError(
                f"Document {document_id!r} was not found."
            )

        rows = self._session.exec(
            select(EvidenceRow)
            .where(EvidenceRow.document_id == document_id)
            .order_by(EvidenceRow.evidence_id)
        ).all()

        return tuple(_evidence_from_row(row) for row in rows)

    def get_sme(self, sme_id: str) -> SME:
        """Return one SME or raise a controlled error."""

        row = self._session.get(SMERow, sme_id)

        if row is None:
            raise PersistenceNotFoundError(
                f"SME {sme_id!r} was not found."
            )

        return _sme_from_row(row)

    def list_smes(self) -> tuple[SME, ...]:
        """Return all SMEs in stable name order."""

        rows = self._session.exec(
            select(SMERow).order_by(
                SMERow.legal_name,
                SMERow.sme_id,
            )
        ).all()

        return tuple(
            _sme_from_row(row)
            for row in rows
        )

    def get_record(
        self,
        sme_id: str,
    ) -> StructuredInvestmentRecord:
        """Reconstruct one structured investment record."""

        sme = self.get_sme(sme_id)

        document_rows = self._session.exec(
            select(DocumentRow)
            .where(DocumentRow.sme_id == sme_id)
            .order_by(DocumentRow.document_id)
        ).all()

        evidence_rows = self._session.exec(
            select(EvidenceRow)
            .where(EvidenceRow.sme_id == sme_id)
            .order_by(EvidenceRow.evidence_id)
        ).all()

        return StructuredInvestmentRecord(
            sme=sme,
            documents=tuple(
                _document_from_row(row)
                for row in document_rows
            ),
            evidence_items=tuple(
                _evidence_from_row(row)
                for row in evidence_rows
            ),
        )

    def get_evidence(
        self,
        evidence_id: str,
    ) -> EvidenceItem:
        """Return one evidence item."""

        row = self._session.get(
            EvidenceRow,
            evidence_id,
        )

        if row is None:
            raise PersistenceNotFoundError(
                f"Evidence {evidence_id!r} was not found."
            )

        return _evidence_from_row(row)

    def set_evidence_validation(
        self,
        *,
        evidence_id: str,
        status: EvidenceValidationStatus,
        actor_id: str,
        reason: str | None = None,
    ) -> EvidenceItem:
        """Update evidence status and create an audit event."""

        row = self._session.get(
            EvidenceRow,
            evidence_id,
        )

        if row is None:
            raise PersistenceNotFoundError(
                f"Evidence {evidence_id!r} was not found."
            )

        previous_status = row.validation_status
        row.validation_status = status.value
        row.updated_at = datetime.now(UTC)

        audit_event = AuditEventRow(
            sme_id=row.sme_id,
            entity_type="evidence",
            entity_id=row.evidence_id,
            action="validation_status_changed",
            actor_id=actor_id,
            reason=reason,
            previous_value_json=json.dumps(
                {"validation_status": previous_status}
            ),
            new_value_json=json.dumps(
                {"validation_status": status.value}
            ),
        )

        try:
            self._session.add(row)
            self._session.add(audit_event)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _evidence_from_row(row)

    def list_audit_events(
        self,
        *,
        sme_id: str | None = None,
    ) -> tuple[AuditEventRow, ...]:
        """Return audit events in chronological order."""

        statement = select(AuditEventRow)

        if sme_id is not None:
            statement = statement.where(
                AuditEventRow.sme_id == sme_id
            )

        rows = self._session.exec(
            statement.order_by(
                AuditEventRow.created_at,
                AuditEventRow.event_id,
            )
        ).all()

        return tuple(rows)

    def _save_sme(self, sme: SME) -> None:
        existing = self._session.get(
            SMERow,
            sme.sme_id,
        )
        candidate = _sme_row(sme)

        if existing is None:
            self._session.add(candidate)
            self._session.flush()
            return

        if (
            existing.legal_name != candidate.legal_name
            or existing.sector != candidate.sector
            or existing.jurisdiction
            != candidate.jurisdiction
        ):
            raise PersistenceConflictError(
                f"SME ID {sme.sme_id!r} already represents "
                "different data."
            )

    def _save_document(
        self,
        document: SourceDocument,
    ) -> None:
        existing = self._session.get(
            DocumentRow,
            document.document_id,
        )
        candidate = _document_row(document)

        if existing is None:
            self._session.add(candidate)
            self._session.flush()
            return

        comparable_existing = (
            existing.sme_id,
            existing.file_name,
            existing.mime_type,
            existing.sha256,
            existing.document_type,
        )
        comparable_candidate = (
            candidate.sme_id,
            candidate.file_name,
            candidate.mime_type,
            candidate.sha256,
            candidate.document_type,
        )

        if comparable_existing != comparable_candidate:
            raise PersistenceConflictError(
                "Document ID "
                f"{document.document_id!r} already represents "
                "different data."
            )

    def _save_evidence(
        self,
        evidence: EvidenceItem,
    ) -> None:
        existing = self._session.get(
            EvidenceRow,
            evidence.evidence_id,
        )
        candidate = _evidence_row(evidence)

        if existing is None:
            self._session.add(candidate)
            self._session.flush()
            return

        if _evidence_signature(existing) != (
            _evidence_signature(candidate)
        ):
            raise PersistenceConflictError(
                "Evidence ID "
                f"{evidence.evidence_id!r} already represents "
                "different data."
            )

    def _require_processing_row(
        self,
        document_id: str,
    ) -> DocumentProcessingRow:
        row = self._session.get(
            DocumentProcessingRow,
            document_id,
        )

        if row is None:
            raise PersistenceNotFoundError(
                f"Document {document_id!r} has no processing state."
            )

        return row

    def _require_document_job_row(
        self,
        job_id: str,
    ) -> DocumentProcessingJobRow:
        row = self._session.get(DocumentProcessingJobRow, job_id)

        if row is None:
            raise PersistenceNotFoundError(
                f"Document processing job {job_id!r} was not found."
            )

        return row

    def _require_document_batch_row(
        self,
        checkpoint_id: str,
    ) -> DocumentBatchCheckpointRow:
        row = self._session.get(
            DocumentBatchCheckpointRow,
            checkpoint_id,
        )

        if row is None:
            raise PersistenceNotFoundError(
                f"Document batch checkpoint {checkpoint_id!r} was not found."
            )

        return row


def _sme_row(sme: SME) -> SMERow:
    return SMERow(
        sme_id=sme.sme_id,
        legal_name=sme.legal_name,
        sector=sme.sector,
        jurisdiction=sme.jurisdiction,
    )


def _sme_from_row(row: SMERow) -> SME:
    return SME(
        sme_id=row.sme_id,
        legal_name=row.legal_name,
        sector=row.sector,
        jurisdiction=row.jurisdiction,
    )


def _document_row(
    document: SourceDocument,
) -> DocumentRow:
    return DocumentRow(
        document_id=document.document_id,
        sme_id=document.sme_id,
        file_name=document.file_name,
        mime_type=document.mime_type,
        sha256=document.sha256,
        document_type=document.document_type.value,
    )


def _document_from_row(
    row: DocumentRow,
) -> SourceDocument:
    return SourceDocument(
        document_id=row.document_id,
        sme_id=row.sme_id,
        file_name=row.file_name,
        mime_type=row.mime_type,
        sha256=row.sha256,
        document_type=DocumentType(row.document_type),
    )


def _evidence_row(
    evidence: EvidenceItem,
) -> EvidenceRow:
    return EvidenceRow(
        evidence_id=evidence.evidence_id,
        sme_id=evidence.sme_id,
        document_id=evidence.document_id,
        indicator_id=evidence.indicator_id,
        criterion_id=evidence.criterion_id,
        raw_value=evidence.raw_value,
        normalized_value_json=json.dumps(
            evidence.normalized_value
        ),
        unit=evidence.unit,
        reporting_period=evidence.reporting_period,
        scope=evidence.scope,
        source_locator=evidence.source_locator,
        source_excerpt=evidence.source_excerpt,
        extraction_method=evidence.extraction_method,
        extractor_name=evidence.extractor_name,
        extractor_version=evidence.extractor_version,
        confidence=evidence.confidence,
        validation_status=(
            evidence.validation_status.value
        ),
    )


def _evidence_from_row(
    row: EvidenceRow,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=row.evidence_id,
        sme_id=row.sme_id,
        document_id=row.document_id,
        indicator_id=row.indicator_id,
        criterion_id=row.criterion_id,
        raw_value=row.raw_value,
        normalized_value=json.loads(
            row.normalized_value_json
        ),
        unit=row.unit,
        reporting_period=row.reporting_period,
        scope=row.scope,
        source_locator=row.source_locator,
        source_excerpt=row.source_excerpt,
        extraction_method=row.extraction_method,
        extractor_name=row.extractor_name,
        extractor_version=row.extractor_version,
        confidence=row.confidence,
        validation_status=EvidenceValidationStatus(
            row.validation_status
        ),
    )


def _evidence_signature(
    row: EvidenceRow,
) -> tuple[object, ...]:
    return (
        row.sme_id,
        row.document_id,
        row.indicator_id,
        row.criterion_id,
        row.raw_value,
        row.normalized_value_json,
        row.unit,
        row.reporting_period,
        row.scope,
        row.source_locator,
        row.source_excerpt,
        row.extraction_method,
        row.extractor_name,
        row.extractor_version,
        row.confidence,
        row.validation_status,
    )


def _processing_state_from_row(
    row: DocumentProcessingRow,
) -> DocumentProcessingState:
    return DocumentProcessingState(
        document_id=row.document_id,
        sme_id=row.sme_id,
        status=DocumentProcessingStatus(row.status),
        attempt_count=row.attempt_count,
        evidence_count=row.evidence_count,
        deterministic_evidence_count=(
            row.deterministic_evidence_count
        ),
        intelligent_evidence_count=row.intelligent_evidence_count,
        rejected_intelligent_claim_count=(
            row.rejected_intelligent_claim_count
        ),
        intelligent_provider_status=row.intelligent_provider_status,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        updated_at=row.updated_at,
    )


def _seconds_after(value: datetime, seconds: int) -> datetime:
    return value + timedelta(seconds=seconds)


def _lease_expired(
    value: datetime | None,
    *,
    as_of: datetime | None = None,
) -> bool:
    if value is None:
        return True

    normalized = (
        value.replace(tzinfo=UTC)
        if value.tzinfo is None
        else value.astimezone(UTC)
    )
    effective_now = as_of or datetime.now(UTC)
    effective_now = (
        effective_now.replace(tzinfo=UTC)
        if effective_now.tzinfo is None
        else effective_now.astimezone(UTC)
    )
    return normalized <= effective_now


def _document_job_from_row(
    row: DocumentProcessingJobRow,
) -> DocumentProcessingJob:
    return DocumentProcessingJob(
        job_id=row.job_id,
        document_id=row.document_id,
        sme_id=row.sme_id,
        requested_by=row.requested_by,
        status=DocumentJobStatus(row.status),
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
        worker_id=row.worker_id,
        lease_expires_at=row.lease_expires_at,
        last_heartbeat_at=row.last_heartbeat_at,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        updated_at=row.updated_at,
    )


def _document_batch_row(
    checkpoint: DocumentBatchCheckpoint,
) -> DocumentBatchCheckpointRow:
    return DocumentBatchCheckpointRow(
        checkpoint_id=checkpoint.checkpoint_id,
        job_id=checkpoint.job_id,
        document_id=checkpoint.document_id,
        batch_id=checkpoint.batch_id,
        page_numbers_json=json.dumps(checkpoint.page_numbers),
        status=checkpoint.status.value,
        attempt_count=checkpoint.attempt_count,
        max_attempts=checkpoint.max_attempts,
        worker_id=checkpoint.worker_id,
        failure_message=checkpoint.failure_message,
        result_json=checkpoint.result_json,
        created_at=checkpoint.created_at,
        started_at=checkpoint.started_at,
        completed_at=checkpoint.completed_at,
        updated_at=checkpoint.updated_at,
    )


def _document_batch_from_row(
    row: DocumentBatchCheckpointRow,
) -> DocumentBatchCheckpoint:
    return DocumentBatchCheckpoint(
        checkpoint_id=row.checkpoint_id,
        job_id=row.job_id,
        document_id=row.document_id,
        batch_id=row.batch_id,
        page_numbers=tuple(json.loads(row.page_numbers_json)),
        status=DocumentBatchStatus(row.status),
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        worker_id=row.worker_id,
        failure_message=row.failure_message,
        result_json=row.result_json,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        updated_at=row.updated_at,
    )


def _document_batch_signature(
    row: DocumentBatchCheckpointRow,
) -> tuple[object, ...]:
    return (
        row.job_id,
        row.document_id,
        row.batch_id,
        row.page_numbers_json,
        row.status,
        row.attempt_count,
        row.max_attempts,
    )
