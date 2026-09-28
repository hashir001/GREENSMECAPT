"""Destructive persistence operations with explicit dependency checks."""

import json

from sqlmodel import Session, select

from greensmecapt.domain import DocumentJobStatus, DocumentProcessingStatus
from greensmecapt.persistence.applications import (
    ApplicationStatus,
    SMEApplicationRow,
)
from greensmecapt.persistence.assessment_profiles import (
    SMEAssessmentProfilePublicationRow,
    SMEAssessmentProfileRevisionRow,
)
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
            if sme_id in json.loads(run.sme_ids_json):
                affected_run_ids.append(run.run_id)
                self._session.delete(run)

        publications = self._session.exec(
            select(SMEAssessmentProfilePublicationRow).where(
                SMEAssessmentProfilePublicationRow.sme_id == sme_id
            )
        ).all()
        revisions = self._session.exec(
            select(SMEAssessmentProfileRevisionRow).where(
                SMEAssessmentProfileRevisionRow.sme_id == sme_id
            )
        ).all()
        for row in publications:
            self._session.delete(row)
        for row in revisions:
            self._session.delete(row)

        deleted_evidence = 0
        deleted_jobs = 0
        for document in documents:
            checkpoints = self._session.exec(
                select(DocumentBatchCheckpointRow).where(
                    DocumentBatchCheckpointRow.document_id == document.document_id
                )
            ).all()
            jobs = self._session.exec(
                select(DocumentProcessingJobRow).where(
                    DocumentProcessingJobRow.document_id == document.document_id
                )
            ).all()
            evidence = self._session.exec(
                select(EvidenceRow).where(EvidenceRow.document_id == document.document_id)
            ).all()
            processing = self._session.get(DocumentProcessingRow, document.document_id)
            for row in checkpoints:
                self._session.delete(row)
            for row in jobs:
                self._session.delete(row)
            for row in evidence:
                self._session.delete(row)
            if processing is not None:
                self._session.delete(processing)
            self._session.delete(document)
            deleted_evidence += len(evidence)
            deleted_jobs += len(jobs)

        old_audit_events = self._session.exec(
            select(AuditEventRow).where(AuditEventRow.sme_id == sme_id)
        ).all()
        run_audit_events = self._session.exec(
            select(AuditEventRow).where(AuditEventRow.entity_type == "assessment_run")
        ).all()
        for row in old_audit_events:
            self._session.delete(row)
        for row in run_audit_events:
            if row.entity_id in affected_run_ids:
                self._session.delete(row)

        self._session.delete(application)
        self._session.delete(sme)
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
                        "deleted_documents": len(documents),
                        "deleted_evidence": deleted_evidence,
                        "deleted_jobs": deleted_jobs,
                        "deleted_profile_revisions": len(revisions),
                        "deleted_assessment_runs": affected_run_ids,
                    },
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return registrations

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
