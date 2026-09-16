"""Reconcile equivalent and conflicting document evidence."""

from collections import defaultdict
from collections.abc import Sequence
from hashlib import sha256
from math import isclose

from greensmecapt.document_intelligence.reconciliation.models import (
    EvidenceCluster,
    EvidenceReconciliationReport,
    ReconciledValue,
    ReconciliationConfiguration,
    ReconciliationStatus,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
)


class EvidenceReconciliationError(ValueError):
    """Raised when evidence cannot be reconciled safely."""


class EvidenceReconciliationService:
    """Compare evidence without averaging contradictory values."""

    def __init__(
        self,
        configuration: (
            ReconciliationConfiguration | None
        ) = None,
    ) -> None:
        self._configuration = (
            configuration
            or ReconciliationConfiguration()
        )

    def reconcile(
        self,
        evidence_items: Sequence[EvidenceItem],
    ) -> EvidenceReconciliationReport:
        """Reconcile one SME's evidence across its documents."""

        if not evidence_items:
            raise EvidenceReconciliationError(
                "At least one evidence item is required."
            )

        _validate_unique_evidence_ids(evidence_items)
        sme_id = _validate_single_sme(evidence_items)
        _validate_indicator_criteria(evidence_items)

        rejected = tuple(
            sorted(
                evidence.evidence_id
                for evidence in evidence_items
                if (
                    evidence.validation_status
                    is EvidenceValidationStatus.REJECTED
                )
            )
        )

        usable = tuple(
            evidence
            for evidence in evidence_items
            if (
                evidence.validation_status
                is not EvidenceValidationStatus.REJECTED
            )
        )

        groups: dict[
            tuple[
                str,
                str | None,
                str | None,
                str | None,
                str | None,
            ],
            list[EvidenceItem],
        ] = defaultdict(list)

        for evidence in usable:
            key = (
                evidence.indicator_id,
                evidence.criterion_id,
                evidence.unit,
                evidence.reporting_period,
                evidence.scope,
            )
            groups[key].append(evidence)

        clusters = tuple(
            self._build_cluster(
                sme_id=sme_id,
                key=key,
                evidence_items=items,
            )
            for key, items in sorted(
                groups.items(),
                key=lambda item: tuple(
                    value or ""
                    for value in item[0]
                ),
            )
        )

        return EvidenceReconciliationReport(
            sme_id=sme_id,
            clusters=clusters,
            rejected_evidence_ids=rejected,
            unit_mismatch_indicator_ids=(
                _unit_mismatch_indicator_ids(usable)
            ),
        )

    def _build_cluster(
        self,
        *,
        sme_id: str,
        key: tuple[
            str,
            str | None,
            str | None,
            str | None,
            str | None,
        ],
        evidence_items: Sequence[EvidenceItem],
    ) -> EvidenceCluster:
        """Build one context-specific evidence cluster."""

        (
            indicator_id,
            criterion_id,
            unit,
            reporting_period,
            scope,
        ) = key

        ordered = tuple(
            sorted(
                evidence_items,
                key=lambda evidence: evidence.evidence_id,
            )
        )

        candidate_values = self._unique_values(
            tuple(
                evidence.normalized_value
                for evidence in ordered
            )
        )

        document_ids = tuple(
            sorted(
                {
                    evidence.document_id
                    for evidence in ordered
                }
            )
        )
        extraction_methods = tuple(
            sorted(
                {
                    evidence.extraction_method
                    for evidence in ordered
                }
            )
        )

        status, issues = _cluster_status(
            evidence_count=len(ordered),
            document_count=len(document_ids),
            value_count=len(candidate_values),
            reporting_period=reporting_period,
        )

        cluster_fingerprint = sha256(
            (
                f"{sme_id}:"
                f"{indicator_id}:"
                f"{criterion_id}:"
                f"{unit}:"
                f"{reporting_period}:"
                f"{scope}"
            ).encode()
        ).hexdigest()[:20]

        return EvidenceCluster(
            cluster_id=f"cluster_{cluster_fingerprint}",
            sme_id=sme_id,
            indicator_id=indicator_id,
            criterion_id=criterion_id,
            unit=unit,
            reporting_period=reporting_period,
            scope=scope,
            status=status,
            candidate_values=candidate_values,
            evidence_ids=tuple(
                evidence.evidence_id
                for evidence in ordered
            ),
            document_ids=document_ids,
            extraction_methods=extraction_methods,
            accepted_evidence_ids=tuple(
                evidence.evidence_id
                for evidence in ordered
                if (
                    evidence.validation_status
                    is EvidenceValidationStatus.ACCEPTED
                )
            ),
            unvalidated_evidence_ids=tuple(
                evidence.evidence_id
                for evidence in ordered
                if (
                    evidence.validation_status
                    is EvidenceValidationStatus.UNVALIDATED
                )
            ),
            issues=issues,
        )

    def _unique_values(
        self,
        values: Sequence[ReconciledValue],
    ) -> tuple[ReconciledValue, ...]:
        """Collapse equivalent values without averaging them."""

        unique: list[ReconciledValue] = []

        for value in values:
            if not any(
                self._values_equivalent(
                    value,
                    existing,
                )
                for existing in unique
            ):
                unique.append(value)

        return tuple(unique)

    def _values_equivalent(
        self,
        left: ReconciledValue,
        right: ReconciledValue,
    ) -> bool:
        """Compare numeric and qualitative values safely."""

        if isinstance(left, bool) or isinstance(right, bool):
            return (
                isinstance(left, bool)
                and isinstance(right, bool)
                and left is right
            )

        if isinstance(left, (int, float)) and isinstance(
            right,
            (int, float),
        ):
            return isclose(
                float(left),
                float(right),
                rel_tol=(
                    self._configuration.relative_tolerance
                ),
                abs_tol=(
                    self._configuration.absolute_tolerance
                ),
            )

        if isinstance(left, str) and isinstance(right, str):
            return (
                " ".join(left.casefold().split())
                == " ".join(right.casefold().split())
            )

        return False


def _cluster_status(
    *,
    evidence_count: int,
    document_count: int,
    value_count: int,
    reporting_period: str | None,
) -> tuple[ReconciliationStatus, tuple[str, ...]]:
    """Classify agreement without manufacturing a value."""

    if value_count > 1:
        if reporting_period is None:
            return (
                ReconciliationStatus.CONTEXT_REQUIRED,
                (
                    "Different values were found, but their "
                    "reporting period is not known.",
                ),
            )

        return (
            ReconciliationStatus.CONFLICT,
            (
                "Different values were reported for the same "
                "metric, period and scope.",
            ),
        )

    if document_count > 1:
        return (
            ReconciliationStatus.CORROBORATED,
            (
                "Equivalent values occur in independent "
                "documents.",
            ),
        )

    if evidence_count > 1:
        return (
            ReconciliationStatus.DUPLICATE_EXTRACTION,
            (
                "Equivalent values were extracted more than "
                "once from the same document.",
            ),
        )

    return (
        ReconciliationStatus.SINGLE_SOURCE,
        (
            "Only one usable source currently supports this "
            "value.",
        ),
    )


def _validate_unique_evidence_ids(
    evidence_items: Sequence[EvidenceItem],
) -> None:
    """Prevent ambiguous evidence identity."""

    evidence_ids = [
        evidence.evidence_id
        for evidence in evidence_items
    ]

    if len(evidence_ids) != len(set(evidence_ids)):
        raise EvidenceReconciliationError(
            "Evidence IDs must be unique."
        )


def _validate_single_sme(
    evidence_items: Sequence[EvidenceItem],
) -> str:
    """Prevent evidence leakage between SMEs."""

    sme_ids = {
        evidence.sme_id
        for evidence in evidence_items
    }

    if len(sme_ids) != 1:
        raise EvidenceReconciliationError(
            "All reconciled evidence must belong to one SME."
        )

    return next(iter(sme_ids))


def _validate_indicator_criteria(
    evidence_items: Sequence[EvidenceItem],
) -> None:
    """Require one criterion mapping per indicator."""

    criteria_by_indicator: dict[
        str,
        set[str | None],
    ] = defaultdict(set)

    for evidence in evidence_items:
        criteria_by_indicator[
            evidence.indicator_id
        ].add(evidence.criterion_id)

    ambiguous = sorted(
        indicator_id
        for indicator_id, criterion_ids
        in criteria_by_indicator.items()
        if len(criterion_ids) > 1
    )

    if ambiguous:
        raise EvidenceReconciliationError(
            "Indicators map to multiple criteria: "
            f"{ambiguous}."
        )


def _unit_mismatch_indicator_ids(
    evidence_items: Sequence[EvidenceItem],
) -> tuple[str, ...]:
    """Identify indicators that escaped unit normalization."""

    units_by_indicator: dict[
        str,
        set[str | None],
    ] = defaultdict(set)

    for evidence in evidence_items:
        units_by_indicator[
            evidence.indicator_id
        ].add(evidence.unit)

    return tuple(
        sorted(
            indicator_id
            for indicator_id, units
            in units_by_indicator.items()
            if len(units) > 1
        )
    )