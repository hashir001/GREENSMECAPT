"""Tests for relational domain persistence."""

from hashlib import sha256

import pytest

from greensmecapt.domain import (
    SME,
    EvidenceItem,
    EvidenceValidationStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence import (
    Database,
    GreenSMERepository,
    PersistenceConflictError,
)


def _record() -> StructuredInvestmentRecord:
    content = b"Renewable energy share was 72 percent."

    sme = SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )

    document = SourceDocument(
        document_id="doc_001",
        sme_id=sme.sme_id,
        file_name="environmental-report.txt",
        mime_type="text/plain",
        sha256=sha256(content).hexdigest(),
    )

    evidence = EvidenceItem(
        evidence_id="evidence_001",
        sme_id=sme.sme_id,
        document_id=document.document_id,
        indicator_id="renewable_energy_percentage",
        criterion_id="renewable_energy",
        raw_value="72 percent",
        normalized_value=72.0,
        unit="percent",
        reporting_period="2025",
        source_locator="page 1",
        source_excerpt=(
            "Renewable energy share was 72 percent."
        ),
        extraction_method="semantic_rule_page_text",
        extractor_name="semantic_metric_rules",
        extractor_version="1.0.0",
    )

    return StructuredInvestmentRecord(
        sme=sme,
        documents=(document,),
        evidence_items=(evidence,),
    )


def _database(tmp_path) -> Database:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.create_schema()

    return database


def test_round_trip_structured_record(tmp_path) -> None:
    """A complete record should survive persistence."""

    database = _database(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        repository.save_record(_record())

    with database.session() as session:
        restored = GreenSMERepository(
            session
        ).get_record("sme_001")

    assert restored == _record()


def test_save_same_record_idempotently(tmp_path) -> None:
    """Retrying the same write should not duplicate data."""

    database = _database(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        repository.save_record(_record())
        repository.save_record(_record())

        restored = repository.get_record("sme_001")

    assert len(restored.documents) == 1
    assert len(restored.evidence_items) == 1


def test_reject_conflicting_sme_identity(tmp_path) -> None:
    """One SME ID cannot represent different companies."""

    database = _database(tmp_path)
    original = _record()

    conflicting = StructuredInvestmentRecord(
        sme=original.sme.model_copy(
            update={"legal_name": "Different Company LLC"}
        )
    )

    with database.session() as session:
        repository = GreenSMERepository(session)
        repository.save_record(original)

        with pytest.raises(PersistenceConflictError):
            repository.save_record(conflicting)


def test_validation_update_creates_audit_event(
    tmp_path,
) -> None:
    """Human evidence decisions should remain auditable."""

    database = _database(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        repository.save_record(_record())

        updated = repository.set_evidence_validation(
            evidence_id="evidence_001",
            status=EvidenceValidationStatus.ACCEPTED,
            actor_id="reviewer_001",
            reason="Matched the source document.",
        )

        events = repository.list_audit_events(
            sme_id="sme_001"
        )

    assert (
        updated.validation_status
        is EvidenceValidationStatus.ACCEPTED
    )
    assert len(events) == 1
    assert events[0].actor_id == "reviewer_001"
    assert (
        events[0].action
        == "validation_status_changed"
    )