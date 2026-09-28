"""Persist the SME financial submission and human review workflow."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, select

from greensmecapt.assessment.financial import FinancialObservation
from greensmecapt.persistence.repository import (
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from greensmecapt.persistence.tables import AuditEventRow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FinancialSubmissionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"


class FinancialSubmissionRow(SQLModel, table=True):
    __tablename__ = "financial_submissions"

    submission_id: str = SQLField(primary_key=True)
    sme_id: str = SQLField(foreign_key="smes.sme_id", unique=True, index=True)
    status: str = SQLField(default=FinancialSubmissionStatus.DRAFT.value, index=True)
    revision: int = SQLField(default=1, ge=1)
    observations_json: str = SQLField(default="[]")
    submitted_by: str | None = SQLField(default=None)
    reviewed_by: str | None = SQLField(default=None)
    review_note: str | None = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=_utc_now)
    updated_at: datetime = SQLField(default_factory=_utc_now)
    submitted_at: datetime | None = SQLField(default=None)
    reviewed_at: datetime | None = SQLField(default=None)


class FinancialSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    submission_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    status: FinancialSubmissionStatus
    revision: int = Field(ge=1)
    observations: tuple[FinancialObservation, ...] = ()
    submitted_by: str | None = None
    reviewed_by: str | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None


class FinancialSubmissionRepository:
    """Store a revision-checked current submission for each SME."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, sme_id: str) -> FinancialSubmission:
        row = self._row(sme_id)
        if row is None:
            raise PersistenceNotFoundError(
                f"SME {sme_id!r} has no financial submission."
            )
        return _submission_from_row(row)

    def list_for_review(self) -> tuple[FinancialSubmission, ...]:
        rows = self._session.exec(
            select(FinancialSubmissionRow).where(
                FinancialSubmissionRow.status.in_(
                    [
                        FinancialSubmissionStatus.SUBMITTED.value,
                        FinancialSubmissionStatus.UNDER_REVIEW.value,
                        FinancialSubmissionStatus.CHANGES_REQUESTED.value,
                        FinancialSubmissionStatus.APPROVED.value,
                    ]
                )
            ).order_by(FinancialSubmissionRow.updated_at.desc())
        ).all()
        return tuple(_submission_from_row(row) for row in rows)

    def save_draft(
        self,
        *,
        sme_id: str,
        observations: tuple[FinancialObservation, ...],
        actor_id: str,
        expected_revision: int | None,
    ) -> FinancialSubmission:
        if any(item.sme_id != sme_id for item in observations):
            raise ValueError("Every financial observation must belong to the SME.")
        metric_ids = [item.metric_id for item in observations]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("Financial metric observations must be unique.")

        row = self._row(sme_id)
        now = _utc_now()
        if row is None:
            if expected_revision is not None:
                raise PersistenceConflictError("The financial submission no longer matches.")
            row = FinancialSubmissionRow(
                submission_id=f"financial_{uuid4().hex}",
                sme_id=sme_id,
                status=FinancialSubmissionStatus.DRAFT.value,
                observations_json=_serialize(observations),
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            if expected_revision != row.revision:
                raise PersistenceConflictError("The financial submission changed after it was loaded.")
            if row.status not in {
                FinancialSubmissionStatus.DRAFT.value,
                FinancialSubmissionStatus.CHANGES_REQUESTED.value,
            }:
                raise PersistenceConflictError(
                    "Only a draft or changes-requested submission can be edited."
                )
            row.observations_json = _serialize(observations)
            row.status = FinancialSubmissionStatus.DRAFT.value
            row.revision += 1
            row.updated_at = now
            row.reviewed_by = None
            row.reviewed_at = None
            row.review_note = None

        self._audit(row, "financial_draft_saved", actor_id)
        self._session.commit()
        self._session.refresh(row)
        return _submission_from_row(row)

    def submit(
        self, *, sme_id: str, actor_id: str, expected_revision: int
    ) -> FinancialSubmission:
        row = self._require_revision(sme_id, expected_revision)
        if row.status not in {
            FinancialSubmissionStatus.DRAFT.value,
            FinancialSubmissionStatus.CHANGES_REQUESTED.value,
        }:
            raise PersistenceConflictError("Only an editable financial submission can be submitted.")
        if not _deserialize(row.observations_json):
            raise ValueError("Add at least one financial observation before submitting.")
        now = _utc_now()
        row.status = FinancialSubmissionStatus.SUBMITTED.value
        row.revision += 1
        row.submitted_by = actor_id
        row.submitted_at = now
        row.updated_at = now
        self._audit(row, "financial_submission_submitted", actor_id)
        self._session.commit()
        self._session.refresh(row)
        return _submission_from_row(row)

    def review(
        self,
        *,
        sme_id: str,
        actor_id: str,
        expected_revision: int,
        decision: FinancialSubmissionStatus,
        note: str | None,
    ) -> FinancialSubmission:
        if decision not in {
            FinancialSubmissionStatus.APPROVED,
            FinancialSubmissionStatus.CHANGES_REQUESTED,
        }:
            raise ValueError("A financial review must approve or request changes.")
        row = self._require_revision(sme_id, expected_revision)
        if row.status not in {
            FinancialSubmissionStatus.SUBMITTED.value,
            FinancialSubmissionStatus.UNDER_REVIEW.value,
        }:
            raise PersistenceConflictError("This financial submission is not awaiting review.")
        if decision is FinancialSubmissionStatus.CHANGES_REQUESTED and not note:
            raise ValueError("A change request requires a review note.")
        now = _utc_now()
        row.status = decision.value
        row.revision += 1
        row.reviewed_by = actor_id
        row.reviewed_at = now
        row.review_note = note
        row.updated_at = now
        self._audit(row, f"financial_submission_{decision.value}", actor_id, note)
        self._session.commit()
        self._session.refresh(row)
        return _submission_from_row(row)

    def approved_observations(self, sme_id: str) -> tuple[FinancialObservation, ...]:
        row = self._row(sme_id)
        if row is None or row.status != FinancialSubmissionStatus.APPROVED.value:
            return ()
        return _deserialize(row.observations_json)

    def _row(self, sme_id: str) -> FinancialSubmissionRow | None:
        return self._session.exec(
            select(FinancialSubmissionRow).where(FinancialSubmissionRow.sme_id == sme_id)
        ).first()

    def _require_revision(self, sme_id: str, revision: int) -> FinancialSubmissionRow:
        row = self._row(sme_id)
        if row is None:
            raise PersistenceNotFoundError(f"SME {sme_id!r} has no financial submission.")
        if row.revision != revision:
            raise PersistenceConflictError("The financial submission changed after it was loaded.")
        return row

    def _audit(
        self, row: FinancialSubmissionRow, action: str, actor_id: str, reason: str | None = None
    ) -> None:
        self._session.add(
            AuditEventRow(
                sme_id=row.sme_id,
                entity_type="financial_submission",
                entity_id=row.submission_id,
                action=action,
                actor_id=actor_id,
                reason=reason,
                new_value_json=json.dumps(
                    {"status": row.status, "revision": row.revision}, sort_keys=True
                ),
            )
        )


def _serialize(observations: tuple[FinancialObservation, ...]) -> str:
    return json.dumps(
        [item.model_dump(mode="json") for item in observations],
        sort_keys=True,
        separators=(",", ":"),
    )


def _deserialize(value: str) -> tuple[FinancialObservation, ...]:
    return tuple(FinancialObservation.model_validate(item) for item in json.loads(value))


def _submission_from_row(row: FinancialSubmissionRow) -> FinancialSubmission:
    return FinancialSubmission(
        submission_id=row.submission_id,
        sme_id=row.sme_id,
        status=FinancialSubmissionStatus(row.status),
        revision=row.revision,
        observations=_deserialize(row.observations_json),
        submitted_by=row.submitted_by,
        reviewed_by=row.reviewed_by,
        review_note=row.review_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
        submitted_at=row.submitted_at,
        reviewed_at=row.reviewed_at,
    )
