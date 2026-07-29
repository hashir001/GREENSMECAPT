"""Tests for the evidence-item domain model."""

import pytest
from pydantic import ValidationError

from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
)


def test_create_evidence_item() -> None:
    """A valid evidence item should preserve value and provenance."""

    evidence = EvidenceItem(
        evidence_id="evidence_001",
        sme_id="sme_001",
        document_id="doc_001",
        indicator_id="renewable_energy_percentage",
        criterion_id="renewable_energy",
        raw_value="72%",
        normalized_value=72.0,
        unit="percent",
        source_locator="page 2, table 1, row 6",
        source_excerpt="Renewable energy contribution: 72%",
        extraction_method="table_extraction",
        extractor_name="table_transformer",
        extractor_version="1.0",
        confidence=0.94,
    )

    assert evidence.raw_value == "72%"
    assert evidence.normalized_value == 72.0
    assert evidence.confidence == 0.94
    assert (
        evidence.validation_status
        is EvidenceValidationStatus.UNVALIDATED
    )


def test_reject_invalid_confidence() -> None:
    """Extraction confidence must remain between zero and one."""

    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="evidence_001",
            sme_id="sme_001",
            document_id="doc_001",
            indicator_id="renewable_energy_percentage",
            raw_value="72%",
            normalized_value=72.0,
            unit="percent",
            source_locator="page 2",
            extraction_method="table_extraction",
            extractor_name="table_transformer",
            confidence=1.2,
        )


def test_reject_blank_source_locator() -> None:
    """Evidence must identify where it came from."""

    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="evidence_001",
            sme_id="sme_001",
            document_id="doc_001",
            indicator_id="renewable_energy_percentage",
            raw_value="72%",
            normalized_value=72.0,
            unit="percent",
            source_locator="   ",
            extraction_method="table_extraction",
            extractor_name="table_transformer",
            confidence=0.94,
        )