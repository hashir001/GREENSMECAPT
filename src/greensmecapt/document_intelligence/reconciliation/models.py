"""Models for reconciling evidence across SME documents."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

type ReconciledValue = str | int | float | bool


class ReconciliationModel(BaseModel):
    """Strict base model for evidence reconciliation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ReconciliationStatus(StrEnum):
    """Describe agreement within one contextual evidence group."""

    SINGLE_SOURCE = "single_source"
    DUPLICATE_EXTRACTION = "duplicate_extraction"
    CORROBORATED = "corroborated"
    CONTEXT_REQUIRED = "context_required"
    CONFLICT = "conflict"


class ReconciliationConfiguration(ReconciliationModel):
    """Configure numeric-equivalence tolerances."""

    absolute_tolerance: float = Field(
        default=1e-9,
        ge=0,
    )
    relative_tolerance: float = Field(
        default=1e-9,
        ge=0,
    )


class EvidenceCluster(ReconciliationModel):
    """Group evidence describing one metric and context."""

    cluster_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    indicator_id: str = Field(min_length=1)
    criterion_id: str | None = Field(
        default=None,
        min_length=1,
    )
    unit: str | None = Field(default=None, min_length=1)
    reporting_period: str | None = Field(
        default=None,
        min_length=1,
    )
    scope: str | None = Field(
        default=None,
        min_length=1,
    )

    status: ReconciliationStatus
    candidate_values: tuple[
        ReconciledValue, ...
    ] = Field(min_length=1)

    evidence_ids: tuple[str, ...] = Field(min_length=1)
    document_ids: tuple[str, ...] = Field(min_length=1)
    extraction_methods: tuple[str, ...] = Field(
        min_length=1
    )

    accepted_evidence_ids: tuple[str, ...] = ()
    unvalidated_evidence_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


class EvidenceReconciliationReport(ReconciliationModel):
    """Summarize reconciled evidence for one SME."""

    sme_id: str = Field(min_length=1)
    clusters: tuple[EvidenceCluster, ...]
    rejected_evidence_ids: tuple[str, ...] = ()
    unit_mismatch_indicator_ids: tuple[str, ...] = ()

    @property
    def conflicts(self) -> tuple[EvidenceCluster, ...]:
        """Return genuine same-context contradictions."""

        return tuple(
            cluster
            for cluster in self.clusters
            if cluster.status is ReconciliationStatus.CONFLICT
        )

    @property
    def context_questions(
        self,
    ) -> tuple[EvidenceCluster, ...]:
        """Return groups requiring period clarification."""

        return tuple(
            cluster
            for cluster in self.clusters
            if (
                cluster.status
                is ReconciliationStatus.CONTEXT_REQUIRED
            )
        )