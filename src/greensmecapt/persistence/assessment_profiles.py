"""Immutable approved profile revisions and explicit publication."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import UniqueConstraint
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, select

from greensmecapt.assessment.financial import (
    FinancialAssessmentPolicy,
    FinancialObservation,
)
from greensmecapt.assessment.fuzzy_dematel import DematelSpecification
from greensmecapt.assessment.normalization import NormalizationPolicy
from greensmecapt.assessment.observations import CriterionResponse
from greensmecapt.assessment.performance_context import MetricComparisonContext
from greensmecapt.assessment.profiles import AssessmentContext, AssessmentPolicy
from greensmecapt.assessment.readiness import ReadinessObservation
from greensmecapt.document_intelligence.semantics import MetricCatalog
from greensmecapt.domain import StructuredInvestmentRecord
from greensmecapt.persistence.repository import PersistenceNotFoundError
from greensmecapt.persistence.tables import AuditEventRow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SMEAssessmentProfileRevisionRow(SQLModel, table=True):
    """Persist one immutable approved assessment-input snapshot."""

    __tablename__ = "sme_assessment_profile_revisions"
    __table_args__ = (
        UniqueConstraint(
            "sme_id",
            "profile_version",
            name="uq_profile_revision_sme_version",
        ),
    )

    revision_id: str = SQLField(primary_key=True)
    sme_id: str = SQLField(foreign_key="smes.sme_id", index=True)
    profile_version: int = SQLField(ge=1)
    context_json: str
    responses_json: str
    record_snapshot_json: str
    approval_fingerprint: str = SQLField(index=True)
    assessment_policy_json: str
    normalization_policy_json: str
    supplemental_inputs_json: str = SQLField(default="{}")
    approved_by: str = SQLField(index=True)
    approved_at: datetime = SQLField(default_factory=_utc_now)


class SMEAssessmentProfilePublicationRow(SQLModel, table=True):
    """Retain publication history while identifying the active revision."""

    __tablename__ = "sme_assessment_profile_publications"

    publication_id: str = SQLField(primary_key=True)
    sme_id: str = SQLField(foreign_key="smes.sme_id", index=True)
    revision_id: str = SQLField(
        foreign_key="sme_assessment_profile_revisions.revision_id",
        index=True,
    )
    active: bool = SQLField(default=True, index=True)
    published_by: str = SQLField(index=True)
    published_at: datetime = SQLField(default_factory=_utc_now)
    withdrawn_by: str | None = SQLField(default=None, index=True)
    withdrawn_at: datetime | None = SQLField(default=None)


class StoredAssessmentProfileRevision(BaseModel):
    """Return a complete immutable approved profile revision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    revision_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    context: AssessmentContext
    responses: tuple[CriterionResponse, ...]
    record_snapshot: StructuredInvestmentRecord
    approval_fingerprint: str = Field(min_length=64, max_length=64)
    assessment_policy: AssessmentPolicy
    normalization_policy: NormalizationPolicy
    financial_policy: FinancialAssessmentPolicy | None = None
    readiness_specification: DematelSpecification | None = None
    metric_catalog: MetricCatalog | None = None
    financial_observations: tuple[FinancialObservation, ...] = ()
    readiness_observations: tuple[ReadinessObservation, ...] = ()
    metric_contexts: tuple[MetricComparisonContext, ...] = ()
    approved_by: str = Field(min_length=1)
    approved_at: datetime


class AssessmentProfilePublication(BaseModel):
    """Return one publication event and the published revision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    publication_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    active: bool
    published_by: str = Field(min_length=1)
    published_at: datetime
    withdrawn_by: str | None = Field(default=None, min_length=1)
    withdrawn_at: datetime | None = None


class AssessmentProfileRepository:
    """Store immutable approvals and explicit investor publications."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def approve(
        self,
        *,
        context: AssessmentContext,
        responses: tuple[CriterionResponse, ...],
        record_snapshot: StructuredInvestmentRecord,
        assessment_policy: AssessmentPolicy,
        normalization_policy: NormalizationPolicy,
        financial_policy: FinancialAssessmentPolicy,
        readiness_specification: DematelSpecification,
        metric_catalog: MetricCatalog,
        financial_observations: tuple[FinancialObservation, ...] = (),
        readiness_observations: tuple[ReadinessObservation, ...] = (),
        metric_contexts: tuple[MetricComparisonContext, ...] = (),
        actor_id: str,
        commit: bool = True,
    ) -> StoredAssessmentProfileRevision:
        sme_id = context.sme_id

        if record_snapshot.sme.sme_id != sme_id or any(
            response.sme_id != sme_id for response in responses
        ):
            raise ValueError(
                "Approved profile inputs must belong to the same SME."
            )

        serialized = _serialize_approval(
            context=context,
            responses=responses,
            record_snapshot=record_snapshot,
            assessment_policy=assessment_policy,
            normalization_policy=normalization_policy,
            financial_policy=financial_policy,
            readiness_specification=readiness_specification,
            metric_catalog=metric_catalog,
            financial_observations=financial_observations,
            readiness_observations=readiness_observations,
            metric_contexts=metric_contexts,
        )
        fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        latest = self._latest_row(sme_id)

        if latest is not None and latest.approval_fingerprint == fingerprint:
            return _revision_from_row(latest)

        row = SMEAssessmentProfileRevisionRow(
            revision_id=f"profile_revision_{uuid4().hex}",
            sme_id=sme_id,
            profile_version=1 if latest is None else latest.profile_version + 1,
            context_json=context.model_dump_json(),
            responses_json=_serialize_responses(responses),
            record_snapshot_json=record_snapshot.model_dump_json(),
            approval_fingerprint=fingerprint,
            assessment_policy_json=assessment_policy.model_dump_json(),
            normalization_policy_json=normalization_policy.model_dump_json(),
            supplemental_inputs_json=_serialize_supplemental_inputs(
                financial_observations=financial_observations,
                readiness_observations=readiness_observations,
                metric_contexts=metric_contexts,
                financial_policy=financial_policy,
                readiness_specification=readiness_specification,
                metric_catalog=metric_catalog,
            ),
            approved_by=actor_id,
            approved_at=_utc_now(),
        )
        self._session.add(row)
        self._session.add(
            AuditEventRow(
                sme_id=sme_id,
                entity_type="assessment_profile_revision",
                entity_id=row.revision_id,
                action="assessment_profile_approved",
                actor_id=actor_id,
                new_value_json=json.dumps(
                    {
                        "profile_version": row.profile_version,
                        "approval_fingerprint": fingerprint,
                        "policy_version": assessment_policy.version,
                        "normalization_version": normalization_policy.version,
                    },
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return _revision_from_row(row)

    def publish(
        self,
        *,
        sme_id: str,
        revision_id: str,
        actor_id: str,
        commit: bool = True,
    ) -> AssessmentProfilePublication:
        revision = self._session.get(
            SMEAssessmentProfileRevisionRow,
            revision_id,
        )

        if revision is None or revision.sme_id != sme_id:
            raise PersistenceNotFoundError(
                f"Approved profile revision {revision_id!r} was not found."
            )

        active_rows = self._session.exec(
            select(SMEAssessmentProfilePublicationRow).where(
                SMEAssessmentProfilePublicationRow.sme_id == sme_id,
                SMEAssessmentProfilePublicationRow.active.is_(True),
            )
        ).all()
        now = _utc_now()

        for active in active_rows:
            if active.revision_id == revision_id:
                return _publication_from_row(active)
            active.active = False
            active.withdrawn_by = actor_id
            active.withdrawn_at = now
            self._session.add(active)

        row = SMEAssessmentProfilePublicationRow(
            publication_id=f"profile_publication_{uuid4().hex}",
            sme_id=sme_id,
            revision_id=revision_id,
            active=True,
            published_by=actor_id,
            published_at=now,
        )
        self._session.add(row)
        self._session.add(
            AuditEventRow(
                sme_id=sme_id,
                entity_type="assessment_profile_publication",
                entity_id=row.publication_id,
                action="assessment_profile_published",
                actor_id=actor_id,
                previous_value_json=json.dumps(
                    {
                        "revision_ids": [
                            item.revision_id for item in active_rows
                        ]
                    },
                    sort_keys=True,
                ),
                new_value_json=json.dumps(
                    {"revision_id": revision_id},
                    sort_keys=True,
                ),
            )
        )
        self._finish(commit)
        return _publication_from_row(row)

    def get_revision(
        self,
        revision_id: str,
    ) -> StoredAssessmentProfileRevision:
        row = self._session.get(
            SMEAssessmentProfileRevisionRow,
            revision_id,
        )

        if row is None:
            raise PersistenceNotFoundError(
                f"Approved profile revision {revision_id!r} was not found."
            )

        return _revision_from_row(row)

    def withdraw(
        self,
        *,
        sme_id: str,
        actor_id: str,
        reason: str,
        commit: bool = True,
    ) -> None:
        """Withdraw every active publication while retaining its history."""

        active_rows = self._session.exec(
            select(SMEAssessmentProfilePublicationRow).where(
                SMEAssessmentProfilePublicationRow.sme_id == sme_id,
                SMEAssessmentProfilePublicationRow.active.is_(True),
            )
        ).all()
        now = _utc_now()

        for row in active_rows:
            row.active = False
            row.withdrawn_by = actor_id
            row.withdrawn_at = now
            self._session.add(row)
            self._session.add(
                AuditEventRow(
                    sme_id=sme_id,
                    entity_type="assessment_profile_publication",
                    entity_id=row.publication_id,
                    action="assessment_profile_withdrawn",
                    actor_id=actor_id,
                    reason=reason,
                    previous_value_json=json.dumps(
                        {
                            "active": True,
                            "revision_id": row.revision_id,
                        },
                        sort_keys=True,
                    ),
                    new_value_json=json.dumps(
                        {
                            "active": False,
                            "revision_id": row.revision_id,
                        },
                        sort_keys=True,
                    ),
                )
            )

        self._finish(commit)

    def get_published(
        self,
        sme_id: str,
    ) -> StoredAssessmentProfileRevision:
        publication = self._session.exec(
            select(SMEAssessmentProfilePublicationRow).where(
                SMEAssessmentProfilePublicationRow.sme_id == sme_id,
                SMEAssessmentProfilePublicationRow.active.is_(True),
            )
        ).first()

        if publication is None:
            raise PersistenceNotFoundError(
                f"SME {sme_id!r} has no published assessment profile."
            )

        return self.get_revision(publication.revision_id)

    def list_published_sme_ids(self) -> tuple[str, ...]:
        rows = self._session.exec(
            select(SMEAssessmentProfilePublicationRow).where(
                SMEAssessmentProfilePublicationRow.active.is_(True)
            )
        ).all()
        return tuple(sorted({row.sme_id for row in rows}))

    def list_published_profiles(
        self,
    ) -> tuple[StoredAssessmentProfileRevision, ...]:
        """Return active frozen snapshots for investor-facing discovery."""

        return tuple(
            self.get_published(sme_id)
            for sme_id in self.list_published_sme_ids()
        )

    def _latest_row(
        self,
        sme_id: str,
    ) -> SMEAssessmentProfileRevisionRow | None:
        return self._session.exec(
            select(SMEAssessmentProfileRevisionRow)
            .where(SMEAssessmentProfileRevisionRow.sme_id == sme_id)
            .order_by(SMEAssessmentProfileRevisionRow.profile_version.desc())
        ).first()

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


def _serialize_responses(
    responses: tuple[CriterionResponse, ...],
) -> str:
    return json.dumps(
        [response.model_dump(mode="json") for response in responses],
        sort_keys=True,
        separators=(",", ":"),
    )


def _serialize_approval(
    *,
    context: AssessmentContext,
    responses: tuple[CriterionResponse, ...],
    record_snapshot: StructuredInvestmentRecord,
    assessment_policy: AssessmentPolicy,
    normalization_policy: NormalizationPolicy,
    financial_policy: FinancialAssessmentPolicy,
    readiness_specification: DematelSpecification,
    metric_catalog: MetricCatalog,
    financial_observations: tuple[FinancialObservation, ...],
    readiness_observations: tuple[ReadinessObservation, ...],
    metric_contexts: tuple[MetricComparisonContext, ...],
) -> str:
    return json.dumps(
        {
            "context": context.model_dump(mode="json"),
            "responses": [
                response.model_dump(mode="json") for response in responses
            ],
            "record_snapshot": record_snapshot.model_dump(mode="json"),
            "assessment_policy": assessment_policy.model_dump(mode="json"),
            "normalization_policy": normalization_policy.model_dump(mode="json"),
            "financial_policy": financial_policy.model_dump(mode="json"),
            "readiness_specification": readiness_specification.model_dump(mode="json"),
            "metric_catalog": metric_catalog.model_dump(mode="json"),
            "financial_observations": [
                item.model_dump(mode="json") for item in financial_observations
            ],
            "readiness_observations": [
                item.model_dump(mode="json") for item in readiness_observations
            ],
            "metric_contexts": [
                item.model_dump(mode="json") for item in metric_contexts
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _revision_from_row(
    row: SMEAssessmentProfileRevisionRow,
) -> StoredAssessmentProfileRevision:
    supplemental = json.loads(row.supplemental_inputs_json or "{}")
    return StoredAssessmentProfileRevision(
        revision_id=row.revision_id,
        sme_id=row.sme_id,
        profile_version=row.profile_version,
        context=AssessmentContext.model_validate_json(row.context_json),
        responses=tuple(
            CriterionResponse.model_validate(item)
            for item in json.loads(row.responses_json)
        ),
        record_snapshot=StructuredInvestmentRecord.model_validate_json(
            row.record_snapshot_json
        ),
        approval_fingerprint=row.approval_fingerprint,
        assessment_policy=AssessmentPolicy.model_validate_json(
            row.assessment_policy_json
        ),
        normalization_policy=NormalizationPolicy.model_validate_json(
            row.normalization_policy_json
        ),
        financial_policy=(
            FinancialAssessmentPolicy.model_validate(
                supplemental["financial_policy"]
            )
            if "financial_policy" in supplemental
            else None
        ),
        readiness_specification=(
            DematelSpecification.model_validate(
                supplemental["readiness_specification"]
            )
            if "readiness_specification" in supplemental
            else None
        ),
        metric_catalog=(
            MetricCatalog.model_validate(supplemental["metric_catalog"])
            if "metric_catalog" in supplemental
            else None
        ),
        financial_observations=tuple(
            FinancialObservation.model_validate(item)
            for item in supplemental.get("financial_observations", ())
        ),
        readiness_observations=tuple(
            ReadinessObservation.model_validate(item)
            for item in supplemental.get("readiness_observations", ())
        ),
        metric_contexts=tuple(
            MetricComparisonContext.model_validate(item)
            for item in supplemental.get("metric_contexts", ())
        ),
        approved_by=row.approved_by,
        approved_at=row.approved_at,
    )


def _serialize_supplemental_inputs(
    *,
    financial_observations: tuple[FinancialObservation, ...],
    readiness_observations: tuple[ReadinessObservation, ...],
    metric_contexts: tuple[MetricComparisonContext, ...],
    financial_policy: FinancialAssessmentPolicy,
    readiness_specification: DematelSpecification,
    metric_catalog: MetricCatalog,
) -> str:
    return json.dumps(
        {
            "financial_policy": financial_policy.model_dump(mode="json"),
            "readiness_specification": readiness_specification.model_dump(mode="json"),
            "metric_catalog": metric_catalog.model_dump(mode="json"),
            "financial_observations": [
                item.model_dump(mode="json") for item in financial_observations
            ],
            "readiness_observations": [
                item.model_dump(mode="json") for item in readiness_observations
            ],
            "metric_contexts": [
                item.model_dump(mode="json") for item in metric_contexts
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _publication_from_row(
    row: SMEAssessmentProfilePublicationRow,
) -> AssessmentProfilePublication:
    return AssessmentProfilePublication(
        publication_id=row.publication_id,
        sme_id=row.sme_id,
        revision_id=row.revision_id,
        active=row.active,
        published_by=row.published_by,
        published_at=row.published_at,
        withdrawn_by=row.withdrawn_by,
        withdrawn_at=row.withdrawn_at,
    )
