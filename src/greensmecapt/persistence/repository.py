"""Transactional persistence for GREENSMECAPT domain records."""

import json
from datetime import UTC, datetime

from sqlmodel import Session, select

from greensmecapt.domain import (
    SME,
    DocumentType,
    EvidenceItem,
    EvidenceValidationStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence.tables import (
    AuditEventRow,
    DocumentRow,
    EvidenceRow,
    SMERow,
)


class PersistenceConflictError(ValueError):
    """Raised when an identifier already represents different data."""


class PersistenceNotFoundError(LookupError):
    """Raised when a requested persistent entity is absent."""


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