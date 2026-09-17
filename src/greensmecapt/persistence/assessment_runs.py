"""Durable storage for completed multi-method assessment runs."""

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, select

from greensmecapt.assessment.workflow import CohortAssessmentResult
from greensmecapt.persistence.repository import (
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from greensmecapt.persistence.tables import AuditEventRow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AssessmentRunRow(SQLModel, table=True):
    """Persist one immutable completed comparison."""

    __tablename__ = "assessment_runs"

    run_id: str = SQLField(primary_key=True)
    cohort_id: str = SQLField(index=True)
    cohort_version: str
    requested_by: str = SQLField(index=True)
    sme_ids_json: str
    comparison_status: str = SQLField(index=True)
    result_json: str
    created_at: datetime = SQLField(default_factory=_utc_now)


class AssessmentRunModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class AssessmentRunSummary(AssessmentRunModel):
    """Describe a stored run without returning its full matrices."""

    run_id: str = Field(min_length=1)
    cohort_id: str = Field(min_length=1)
    cohort_version: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    sme_ids: tuple[str, ...] = Field(min_length=2)
    comparison_status: str = Field(min_length=1)
    created_at: datetime


class AssessmentRunRecord(AssessmentRunSummary):
    """Return one stored run with every reproducible result."""

    result: CohortAssessmentResult


class AssessmentRunRepository:
    """Persist immutable assessment outputs and audit their creation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        *,
        run_id: str,
        result: CohortAssessmentResult,
        actor_id: str,
    ) -> AssessmentRunRecord:
        """Save once; allow identical retries but reject replacement."""

        serialized = _serialize_result(result)
        existing = self._session.get(AssessmentRunRow, run_id)

        if existing is not None:
            if existing.result_json != serialized:
                raise PersistenceConflictError(
                    f"Assessment run {run_id!r} already exists "
                    "with a different result."
                )

            return _record_from_row(existing)

        sme_ids = tuple(
            item.profile.sme_id for item in result.preparations
        )
        row = AssessmentRunRow(
            run_id=run_id,
            cohort_id=result.comparable_topsis.cohort_id,
            cohort_version=result.comparable_topsis.cohort_version,
            requested_by=actor_id,
            sme_ids_json=json.dumps(sme_ids),
            comparison_status=(
                result.comparable_topsis.comparison_status.value
            ),
            result_json=serialized,
        )

        try:
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    entity_type="assessment_run",
                    entity_id=run_id,
                    action="assessment_completed",
                    actor_id=actor_id,
                    new_value_json=json.dumps(
                        {
                            "cohort_id": row.cohort_id,
                            "cohort_version": row.cohort_version,
                            "sme_ids": sme_ids,
                            "comparison_status": (
                                row.comparison_status
                            ),
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

        return _record_from_row(row)

    def get(self, run_id: str) -> AssessmentRunRecord:
        row = self._session.get(AssessmentRunRow, run_id)

        if row is None:
            raise PersistenceNotFoundError(
                f"Assessment run {run_id!r} was not found."
            )

        return _record_from_row(row)

    def list(self) -> tuple[AssessmentRunSummary, ...]:
        rows = self._session.exec(select(AssessmentRunRow)).all()
        ordered = sorted(
            rows,
            key=lambda row: (row.created_at, row.run_id),
            reverse=True,
        )
        return tuple(_summary_from_row(row) for row in ordered)


def _serialize_result(result: CohortAssessmentResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _summary_from_row(row: AssessmentRunRow) -> AssessmentRunSummary:
    return AssessmentRunSummary(
        run_id=row.run_id,
        cohort_id=row.cohort_id,
        cohort_version=row.cohort_version,
        requested_by=row.requested_by,
        sme_ids=tuple(json.loads(row.sme_ids_json)),
        comparison_status=row.comparison_status,
        created_at=row.created_at,
    )


def _record_from_row(row: AssessmentRunRow) -> AssessmentRunRecord:
    summary = _summary_from_row(row)

    return AssessmentRunRecord(
        **summary.model_dump(),
        result=CohortAssessmentResult.model_validate_json(
            row.result_json
        ),
    )