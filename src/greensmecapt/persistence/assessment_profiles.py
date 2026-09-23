"""Durable governed inputs reused by automatic investor comparisons."""

import json
from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel

from greensmecapt.assessment.observations import CriterionResponse
from greensmecapt.assessment.profiles import AssessmentContext
from greensmecapt.persistence.repository import (
    PersistenceNotFoundError,
)
from greensmecapt.persistence.tables import AuditEventRow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SMEAssessmentProfileRow(SQLModel, table=True):
    """Persist the latest internally approved inputs for one SME."""

    __tablename__ = "sme_assessment_profiles"

    sme_id: str = SQLField(
        primary_key=True,
        foreign_key="smes.sme_id",
    )
    profile_version: int = SQLField(default=1, ge=1)
    context_json: str
    responses_json: str
    approved_by: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=_utc_now)
    updated_at: datetime = SQLField(default_factory=_utc_now)


class StoredAssessmentProfile(BaseModel):
    """Return one reusable governed assessment profile."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    sme_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    context: AssessmentContext
    responses: tuple[CriterionResponse, ...]
    approved_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_ownership(self) -> Self:
        if self.context.sme_id != self.sme_id:
            raise ValueError(
                "Stored assessment context belongs to another SME."
            )

        if any(
            response.sme_id != self.sme_id
            for response in self.responses
        ):
            raise ValueError(
                "Stored assessment responses belong to another SME."
            )

        return self


class AssessmentProfileRepository:
    """Store inputs once so investors never supply scoring judgements."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        *,
        context: AssessmentContext,
        responses: tuple[CriterionResponse, ...],
        actor_id: str,
    ) -> StoredAssessmentProfile:
        """Create or replace the approved profile for one SME."""

        sme_id = context.sme_id

        if any(response.sme_id != sme_id for response in responses):
            raise ValueError(
                "Every assessment response must belong to the context SME."
            )

        now = _utc_now()
        row = self._session.get(
            SMEAssessmentProfileRow,
            sme_id,
        )

        if row is None:
            row = SMEAssessmentProfileRow(
                sme_id=sme_id,
                profile_version=1,
                context_json=context.model_dump_json(),
                responses_json=_serialize_responses(responses),
                approved_by=actor_id,
                created_at=now,
                updated_at=now,
            )
            action = "assessment_profile_created"
        else:
            row.profile_version += 1
            row.context_json = context.model_dump_json()
            row.responses_json = _serialize_responses(responses)
            row.approved_by = actor_id
            row.updated_at = now
            action = "assessment_profile_updated"

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=sme_id,
                    entity_type="assessment_profile",
                    entity_id=sme_id,
                    action=action,
                    actor_id=actor_id,
                    new_value_json=json.dumps(
                        {
                            "profile_version": row.profile_version,
                            "response_count": len(responses),
                        },
                        sort_keys=True,
                    ),
                )
            )
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise

        return _profile_from_row(row)

    def get(self, sme_id: str) -> StoredAssessmentProfile:
        row = self._session.get(
            SMEAssessmentProfileRow,
            sme_id,
        )

        if row is None:
            raise PersistenceNotFoundError(
                f"SME {sme_id!r} has no approved assessment profile."
            )

        return _profile_from_row(row)


def _serialize_responses(
    responses: tuple[CriterionResponse, ...],
) -> str:
    return json.dumps(
        [
            response.model_dump(mode="json")
            for response in responses
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _profile_from_row(
    row: SMEAssessmentProfileRow,
) -> StoredAssessmentProfile:
    response_data = json.loads(row.responses_json)

    return StoredAssessmentProfile(
        sme_id=row.sme_id,
        profile_version=row.profile_version,
        context=AssessmentContext.model_validate_json(
            row.context_json
        ),
        responses=tuple(
            CriterionResponse.model_validate(item)
            for item in response_data
        ),
        approved_by=row.approved_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
