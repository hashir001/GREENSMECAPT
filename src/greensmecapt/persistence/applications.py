"""Versioned SME application lifecycle persistence."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, select

from greensmecapt.persistence.repository import (
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from greensmecapt.persistence.tables import AuditEventRow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationStatus(StrEnum):
    """Describe the governed lifecycle of one SME application."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


_ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: frozenset(
        {ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.SUBMITTED: frozenset(
        {
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.CHANGES_REQUESTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.UNDER_REVIEW: frozenset(
        {
            ApplicationStatus.CHANGES_REQUESTED,
            ApplicationStatus.APPROVED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.CHANGES_REQUESTED: frozenset(
        {ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.APPROVED: frozenset(
        {ApplicationStatus.PUBLISHED, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.PUBLISHED: frozenset(
        {ApplicationStatus.APPROVED, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.WITHDRAWN: frozenset(
        {ApplicationStatus.DRAFT, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.ARCHIVED: frozenset(),
}


class SMEApplicationRow(SQLModel, table=True):
    """Persist the current application state and revision number."""

    __tablename__ = "sme_applications"
    __table_args__ = (
        UniqueConstraint("sme_id", name="uq_sme_applications_sme_id"),
    )

    application_id: str = SQLField(primary_key=True)
    sme_id: str = SQLField(foreign_key="smes.sme_id", index=True)
    status: str = SQLField(default=ApplicationStatus.DRAFT.value, index=True)
    revision: int = SQLField(default=1, ge=1)
    created_by: str = SQLField(index=True)
    updated_by: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=_utc_now)
    updated_at: datetime = SQLField(default_factory=_utc_now)


class SMEApplication(BaseModel):
    """Return a governed application lifecycle record."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    application_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    status: ApplicationStatus
    revision: int = Field(ge=1)
    created_by: str = Field(min_length=1)
    updated_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime


class ApplicationTransition(BaseModel):
    """Request one audited state transition."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    target_status: ApplicationStatus
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_reason_for_adverse_transition(self) -> Self:
        if (
            self.target_status
            in {
                ApplicationStatus.CHANGES_REQUESTED,
                ApplicationStatus.WITHDRAWN,
                ApplicationStatus.ARCHIVED,
            }
            and self.reason is None
        ):
            raise ValueError(
                "Changes requested, withdrawal and archival require a reason."
            )
        return self


class ApplicationRepository:
    """Persist lifecycle changes with optimistic revision checks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        sme_id: str,
        actor_id: str,
        commit: bool = True,
    ) -> SMEApplication:
        existing = self._session.exec(
            select(SMEApplicationRow).where(
                SMEApplicationRow.sme_id == sme_id
            )
        ).first()

        if existing is not None:
            raise PersistenceConflictError(
                f"SME {sme_id!r} already has an application."
            )

        now = _utc_now()
        row = SMEApplicationRow(
            application_id=f"application_{uuid4().hex}",
            sme_id=sme_id,
            status=ApplicationStatus.DRAFT.value,
            revision=1,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.add(
            AuditEventRow(
                sme_id=sme_id,
                entity_type="sme_application",
                entity_id=row.application_id,
                action="application_created",
                actor_id=actor_id,
                new_value_json=json.dumps(
                    {"status": row.status, "revision": row.revision},
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return _application_from_row(row)

    def get(self, sme_id: str) -> SMEApplication:
        row = self._session.exec(
            select(SMEApplicationRow).where(
                SMEApplicationRow.sme_id == sme_id
            )
        ).first()

        if row is None:
            raise PersistenceNotFoundError(
                f"SME {sme_id!r} has no application."
            )

        return _application_from_row(row)

    def transition(
        self,
        *,
        sme_id: str,
        transition: ApplicationTransition,
        actor_id: str,
        expected_revision: int,
        commit: bool = True,
    ) -> SMEApplication:
        row = self._session.exec(
            select(SMEApplicationRow).where(
                SMEApplicationRow.sme_id == sme_id
            )
        ).first()

        if row is None:
            raise PersistenceNotFoundError(
                f"SME {sme_id!r} has no application."
            )

        current = ApplicationStatus(row.status)

        if row.revision != expected_revision:
            raise PersistenceConflictError(
                "The application changed after it was loaded."
            )

        if transition.target_status not in _ALLOWED_TRANSITIONS[current]:
            raise PersistenceConflictError(
                f"Application cannot move from {current.value!r} "
                f"to {transition.target_status.value!r}."
            )

        previous = {"status": row.status, "revision": row.revision}
        row.status = transition.target_status.value
        row.revision += 1
        row.updated_by = actor_id
        row.updated_at = _utc_now()
        self._session.add(row)
        self._session.add(
            AuditEventRow(
                sme_id=sme_id,
                entity_type="sme_application",
                entity_id=row.application_id,
                action="application_status_changed",
                actor_id=actor_id,
                reason=transition.reason,
                previous_value_json=json.dumps(previous, sort_keys=True),
                new_value_json=json.dumps(
                    {"status": row.status, "revision": row.revision},
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return _application_from_row(row)

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


def _application_from_row(row: SMEApplicationRow) -> SMEApplication:
    return SMEApplication(
        application_id=row.application_id,
        sme_id=row.sme_id,
        status=ApplicationStatus(row.status),
        revision=row.revision,
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )

