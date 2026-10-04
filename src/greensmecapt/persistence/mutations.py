"""Destructive persistence operations with explicit dependency checks."""

import json

from sqlalchemy import inspect, text
from sqlmodel import Session, select

from greensmecapt.domain import DocumentJobStatus, DocumentProcessingStatus
from greensmecapt.persistence.applications import (
    ApplicationStatus,
    SMEApplicationRow,
)
from greensmecapt.persistence.assessment_profiles import SMEAssessmentProfileRevisionRow
from greensmecapt.persistence.assessment_runs import AssessmentRunRow
from greensmecapt.persistence.repository import (
    PersistenceConflictError,
    PersistenceNotFoundError,
    StoredDocumentRegistration,
    _document_from_row,
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


class DestructiveMutationRepository:
    """Delete governed records only after dependency validation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def delete_document(
        self,
        *,
        sme_id: str,
        document_id: str,
        actor_id: str,
        reason: str,
        commit: bool = True,
    ) -> StoredDocumentRegistration:
        """Delete one inactive document and all of its derived data."""

        row = self._session.get(DocumentRow, document_id)

        if row is None or row.sme_id != sme_id or row.storage_key is None:
            raise PersistenceNotFoundError(f"Document {document_id!r} was not found.")

        processing = self._session.get(
            DocumentProcessingRow,
            document_id,
        )
        if (
            processing is not None
            and processing.status == DocumentProcessingStatus.PROCESSING.value
        ):
            raise PersistenceConflictError(
                "A document cannot be deleted while processing is active."
            )

        jobs = self._session.exec(
            select(DocumentProcessingJobRow).where(
                DocumentProcessingJobRow.document_id == document_id
            )
        ).all()
        if any(
            job.status
            in {
                DocumentJobStatus.QUEUED.value,
                DocumentJobStatus.RUNNING.value,
            }
            for job in jobs
        ):
            raise PersistenceConflictError("A document cannot be deleted while a job is active.")

        registration = StoredDocumentRegistration(
            document=_document_from_row(row),
            storage_key=row.storage_key,
        )
        checkpoints = self._session.exec(
            select(DocumentBatchCheckpointRow).where(
                DocumentBatchCheckpointRow.document_id == document_id
            )
        ).all()
        evidence = self._session.exec(
            select(EvidenceRow).where(EvidenceRow.document_id == document_id)
        ).all()

        for item in checkpoints:
            self._session.delete(item)
        for item in jobs:
            self._session.delete(item)
        for item in evidence:
            self._session.delete(item)
        if processing is not None:
            self._session.delete(processing)
        self._session.delete(row)
        self._session.add(
            AuditEventRow(
                sme_id=sme_id,
                entity_type="document",
                entity_id=document_id,
                action="document_deleted",
                actor_id=actor_id,
                reason=reason,
                previous_value_json=json.dumps(
                    {
                        "file_name": registration.document.file_name,
                        "sha256": registration.document.sha256,
                        "storage_key": registration.storage_key,
                        "deleted_evidence_count": len(evidence),
                        "deleted_job_count": len(jobs),
                    },
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return registration

    def delete_empty_sme(
        self,
        *,
        sme_id: str,
        actor_id: str,
        expected_revision: int,
        reason: str,
        commit: bool = True,
    ) -> None:
        """Hard-delete only an empty draft or withdrawn workspace."""

        sme = self._session.get(SMERow, sme_id)
        application = self._session.exec(
            select(SMEApplicationRow).where(SMEApplicationRow.sme_id == sme_id)
        ).first()

        if sme is None or application is None:
            raise PersistenceNotFoundError(f"SME {sme_id!r} was not found.")
        if application.revision != expected_revision:
            raise PersistenceConflictError("The application changed after it was loaded.")
        if ApplicationStatus(application.status) not in {
            ApplicationStatus.DRAFT,
            ApplicationStatus.WITHDRAWN,
        }:
            raise PersistenceConflictError(
                "Only a draft or withdrawn SME workspace can be deleted."
            )
        if (
            self._session.exec(select(DocumentRow).where(DocumentRow.sme_id == sme_id)).first()
            is not None
        ):
            raise PersistenceConflictError(
                "Delete the SME documents before deleting its workspace."
            )
        if (
            self._session.exec(
                select(SMEAssessmentProfileRevisionRow).where(
                    SMEAssessmentProfileRevisionRow.sme_id == sme_id
                )
            ).first()
            is not None
        ):
            raise PersistenceConflictError(
                "An SME with approved profile history cannot be deleted; archive it instead."
            )

        self._session.delete(application)
        self._session.delete(sme)
        self._session.add(
            AuditEventRow(
                sme_id=sme_id,
                entity_type="sme",
                entity_id=sme_id,
                action="sme_deleted",
                actor_id=actor_id,
                reason=reason,
                previous_value_json=json.dumps(
                    {
                        "legal_name": sme.legal_name,
                        "sector": sme.sector,
                        "jurisdiction": sme.jurisdiction,
                        "application_status": application.status,
                        "application_revision": application.revision,
                    },
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)

    def purge_sme(
        self,
        *,
        sme_id: str,
        actor_id: str,
        expected_revision: int,
        reason: str,
        commit: bool = True,
    ) -> tuple[StoredDocumentRegistration, ...]:
        """Permanently remove one SME and every dependent platform record."""

        sme = self._session.get(SMERow, sme_id)
        application = self._session.exec(
            select(SMEApplicationRow).where(SMEApplicationRow.sme_id == sme_id)
        ).first()
        if sme is None or application is None:
            raise PersistenceNotFoundError(f"SME {sme_id!r} was not found.")
        if application.revision != expected_revision:
            raise PersistenceConflictError("The application changed after it was loaded.")

        documents = self._session.exec(
            select(DocumentRow).where(DocumentRow.sme_id == sme_id)
        ).all()
        registrations = tuple(
            StoredDocumentRegistration(
                document=_document_from_row(row),
                storage_key=row.storage_key,
            )
            for row in documents
            if row.storage_key is not None
        )

        affected_run_ids: list[str] = []
        for run in self._session.exec(select(AssessmentRunRow)).all():
            try:
                run_sme_ids = json.loads(run.sme_ids_json)
            except (TypeError, json.JSONDecodeError):
                run_sme_ids = []
            if sme_id in run_sme_ids:
                affected_run_ids.append(run.run_id)

        # Use direct statements in child-to-parent order. This is deliberate:
        # older Supabase projects may contain tables or foreign keys created by
        # earlier schema versions that are not represented by today's ORM.
        bind = self._session.get_bind()
        existing_tables = set(inspect(bind).get_table_names())

        def delete_rows(table: str, predicate: str, parameters: dict[str, object]) -> int:
            if table not in existing_tables:
                return 0
            result = self._session.execute(
                text(f"delete from {table} where {predicate}"),
                parameters,
            )
            return result.rowcount or 0

        for run_id in affected_run_ids:
            delete_rows("assessment_runs", "run_id = :run_id", {"run_id": run_id})
            delete_rows(
                "audit_events",
                "entity_type = 'assessment_run' and entity_id = :run_id",
                {"run_id": run_id},
            )

        deleted_publications = delete_rows(
            "sme_assessment_profile_publications",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        deleted_revisions = delete_rows(
            "sme_assessment_profile_revisions",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        deleted_legacy_profiles = delete_rows(
            "sme_assessment_profiles",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        deleted_financial_submissions = delete_rows(
            "financial_submissions",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )

        # Batch checkpoints reference jobs/documents but do not carry sme_id.
        # Resolve them through the document IDs before deleting either parent.
        document_ids = [document.document_id for document in documents]
        deleted_checkpoints = 0
        for document_id in document_ids:
            deleted_checkpoints += delete_rows(
                "document_batch_checkpoints",
                "document_id = :document_id",
                {"document_id": document_id},
            )

        deleted_evidence = delete_rows(
            "evidence_items",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        deleted_jobs = delete_rows(
            "document_processing_jobs",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        deleted_processing = delete_rows(
            "document_processing",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        deleted_documents = delete_rows(
            "documents",
            "sme_id = :sme_id",
            {"sme_id": sme_id},
        )
        delete_rows("audit_events", "sme_id = :sme_id", {"sme_id": sme_id})
        delete_rows("sme_applications", "sme_id = :sme_id", {"sme_id": sme_id})
        delete_rows("smes", "sme_id = :sme_id", {"sme_id": sme_id})

        self._session.add(
            AuditEventRow(
                entity_type="sme_purge",
                entity_id=sme_id,
                action="sme_purged",
                actor_id=actor_id,
                reason=reason,
                previous_value_json=json.dumps(
                    {
                        "legal_name": sme.legal_name,
                        "deleted_documents": deleted_documents,
                        "deleted_evidence": deleted_evidence,
                        "deleted_jobs": deleted_jobs,
                        "deleted_processing_rows": deleted_processing,
                        "deleted_checkpoints": deleted_checkpoints,
                        "deleted_profile_publications": deleted_publications,
                        "deleted_profile_revisions": deleted_revisions,
                        "deleted_legacy_profiles": deleted_legacy_profiles,
                        "deleted_financial_submissions": deleted_financial_submissions,
                        "deleted_assessment_runs": affected_run_ids,
                    },
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return registrations

    def purge_platform_data(
        self,
        *,
        commit: bool = True,
    ) -> tuple[tuple[StoredDocumentRegistration, ...], dict[str, int]]:
        """Remove all application data while preserving identities and schema."""

        documents = self._session.exec(select(DocumentRow)).all()
        registrations = tuple(
            StoredDocumentRegistration(
                document=_document_from_row(row),
                storage_key=row.storage_key,
            )
            for row in documents
            if row.storage_key is not None
        )

        bind = self._session.get_bind()
        existing_tables = set(inspect(bind).get_table_names())
        # Child-to-parent ordering keeps this portable across current and older
        # Supabase schemas without touching auth.users or migration metadata.
        deletion_order = (
            "assessment_runs",
            "sme_assessment_profile_publications",
            "sme_assessment_profile_revisions",
            "sme_assessment_profiles",
            "financial_submissions",
            "document_batch_checkpoints",
            "evidence_items",
            "document_processing_jobs",
            "document_processing",
            "documents",
            "sme_applications",
            "audit_events",
            "smes",
        )
        deleted: dict[str, int] = {}

        for table in deletion_order:
            if table not in existing_tables:
                continue
            result = self._session.execute(text(f"delete from {table}"))
            deleted[table] = result.rowcount or 0

        self._finish(commit)
        return registrations, deleted

    def _finish(self, commit: bool) -> None:
        try:
            if commit:
                self._session.commit()
            else:
                self._session.flush()
        except Exception:
            if commit:
                self._session.rollback()
            raise
