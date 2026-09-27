"""Tests for the revision-checked SME application lifecycle."""

from pathlib import Path

import pytest
from sqlmodel import select

from greensmecapt.domain import SME, StructuredInvestmentRecord
from greensmecapt.persistence import (
    ApplicationRepository,
    ApplicationStatus,
    ApplicationTransition,
    AuditEventRow,
    Database,
    GreenSMERepository,
    PersistenceConflictError,
)


def test_transition_lifecycle_and_reject_stale_revision(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'applications.db'}")
    database.create_schema()

    with database.session() as session:
        GreenSMERepository(session).save_record(
            StructuredInvestmentRecord(
                sme=SME(
                    sme_id="sme_001",
                    legal_name="Green SME",
                    sector="Green services",
                    jurisdiction="United Arab Emirates",
                )
            )
        )
        repository = ApplicationRepository(session)
        draft = repository.create(
            sme_id="sme_001",
            actor_id="admin_001",
        )
        submitted = repository.transition(
            sme_id="sme_001",
            transition=ApplicationTransition(
                target_status=ApplicationStatus.SUBMITTED
            ),
            actor_id="sme_user_001",
            expected_revision=draft.revision,
        )

        with pytest.raises(
            PersistenceConflictError,
            match="changed after it was loaded",
        ):
            repository.transition(
                sme_id="sme_001",
                transition=ApplicationTransition(
                    target_status=ApplicationStatus.UNDER_REVIEW
                ),
                actor_id="reviewer_001",
                expected_revision=draft.revision,
            )

        events = session.exec(
            select(AuditEventRow).where(
                AuditEventRow.sme_id == "sme_001"
            )
        ).all()

    assert draft.status is ApplicationStatus.DRAFT
    assert submitted.status is ApplicationStatus.SUBMITTED
    assert submitted.revision == 2
    assert [event.action for event in events] == [
        "application_created",
        "application_status_changed",
    ]


def test_adverse_lifecycle_transition_requires_reason() -> None:
    with pytest.raises(ValueError, match="require a reason"):
        ApplicationTransition(
            target_status=ApplicationStatus.CHANGES_REQUESTED
        )
