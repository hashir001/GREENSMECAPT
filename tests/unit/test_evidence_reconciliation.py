"""Tests for cross-document evidence reconciliation."""

import pytest

from greensmecapt.document_intelligence.reconciliation import (
    EvidenceReconciliationError,
    EvidenceReconciliationService,
    ReconciliationStatus,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
)


def _evidence(
    *,
    evidence_id: str,
    document_id: str,
    value: float = 72.0,
    period: str | None = None,
    unit: str = "percent",
    sme_id: str = "sme_001",
    validation_status: EvidenceValidationStatus = (
        EvidenceValidationStatus.UNVALIDATED
    ),
    extraction_method: str = "semantic_rule_text_block",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        sme_id=sme_id,
        document_id=document_id,
        indicator_id="renewable_energy_percentage",
        criterion_id="renewable_energy",
        raw_value=f"{value} percent",
        normalized_value=value,
        unit=unit,
        reporting_period=period,
        source_locator="page 1",
        source_excerpt=(
            f"Renewable energy share was {value} percent."
        ),
        extraction_method=extraction_method,
        extractor_name="test_extractor",
        extractor_version="1.0",
        validation_status=validation_status,
    )


def test_identify_single_source() -> None:
    """One candidate should remain explicitly single-source."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_001",
                document_id="doc_001",
            ),
        )
    )

    assert len(report.clusters) == 1
    assert (
        report.clusters[0].status
        is ReconciliationStatus.SINGLE_SOURCE
    )


def test_identify_duplicate_extraction() -> None:
    """Two extractors reading one source are not corroboration."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_rule",
                document_id="doc_001",
            ),
            _evidence(
                evidence_id="evidence_llm",
                document_id="doc_001",
                extraction_method=(
                    "language_model_structured_extraction"
                ),
            ),
        )
    )

    cluster = report.clusters[0]

    assert (
        cluster.status
        is ReconciliationStatus.DUPLICATE_EXTRACTION
    )
    assert cluster.document_ids == ("doc_001",)
    assert len(cluster.evidence_ids) == 2


def test_identify_independent_corroboration() -> None:
    """Equivalent values in separate documents corroborate."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_001",
                document_id="doc_001",
                period="2025",
            ),
            _evidence(
                evidence_id="evidence_002",
                document_id="doc_002",
                period="2025",
            ),
        )
    )

    cluster = report.clusters[0]

    assert (
        cluster.status
        is ReconciliationStatus.CORROBORATED
    )
    assert cluster.document_ids == (
        "doc_001",
        "doc_002",
    )
    assert cluster.candidate_values == (72.0,)


def test_request_context_for_unscoped_different_values() -> None:
    """Different values without periods require clarification."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_001",
                document_id="doc_001",
                value=72,
            ),
            _evidence(
                evidence_id="evidence_002",
                document_id="doc_002",
                value=80,
            ),
        )
    )

    cluster = report.clusters[0]

    assert (
        cluster.status
        is ReconciliationStatus.CONTEXT_REQUIRED
    )
    assert cluster.candidate_values == (72.0, 80.0)
    assert report.context_questions == (cluster,)
    assert report.conflicts == ()


def test_identify_same_period_conflict() -> None:
    """Different values for one known period are contradictory."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_001",
                document_id="doc_001",
                value=72,
                period="2025",
            ),
            _evidence(
                evidence_id="evidence_002",
                document_id="doc_002",
                value=80,
                period="2025",
            ),
        )
    )

    cluster = report.clusters[0]

    assert (
        cluster.status
        is ReconciliationStatus.CONFLICT
    )
    assert report.conflicts == (cluster,)


def test_keep_different_periods_separate() -> None:
    """Annual values must not be treated as contradictions."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_2024",
                document_id="doc_001",
                value=60,
                period="2024",
            ),
            _evidence(
                evidence_id="evidence_2025",
                document_id="doc_002",
                value=72,
                period="2025",
            ),
        )
    )

    assert len(report.clusters) == 2
    assert {
        cluster.reporting_period
        for cluster in report.clusters
    } == {"2024", "2025"}

    assert all(
        cluster.status
        is ReconciliationStatus.SINGLE_SOURCE
        for cluster in report.clusters
    )


def test_ignore_rejected_evidence() -> None:
    """Rejected claims must not influence reconciliation."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_valid",
                document_id="doc_001",
                value=72,
            ),
            _evidence(
                evidence_id="evidence_rejected",
                document_id="doc_002",
                value=99,
                validation_status=(
                    EvidenceValidationStatus.REJECTED
                ),
            ),
        )
    )

    assert (
        report.clusters[0].candidate_values
        == (72.0,)
    )
    assert report.rejected_evidence_ids == (
        "evidence_rejected",
    )


def test_reject_evidence_from_multiple_smes() -> None:
    """Evidence from different companies must never mix."""

    with pytest.raises(EvidenceReconciliationError):
        EvidenceReconciliationService().reconcile(
            (
                _evidence(
                    evidence_id="evidence_001",
                    document_id="doc_001",
                    sme_id="sme_001",
                ),
                _evidence(
                    evidence_id="evidence_002",
                    document_id="doc_002",
                    sme_id="sme_002",
                ),
            )
        )


def test_report_unit_normalization_failure() -> None:
    """One indicator with multiple units should be flagged."""

    report = EvidenceReconciliationService().reconcile(
        (
            _evidence(
                evidence_id="evidence_001",
                document_id="doc_001",
                unit="percent",
            ),
            _evidence(
                evidence_id="evidence_002",
                document_id="doc_002",
                unit="ratio",
            ),
        )
    )

    assert report.unit_mismatch_indicator_ids == (
        "renewable_energy_percentage",
    )