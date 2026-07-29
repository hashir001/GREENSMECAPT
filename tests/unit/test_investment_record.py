"""Tests for the structured investment record."""

import pytest
from pydantic import ValidationError

from greensmecapt.domain import (
    SME,
    DocumentType,
    EvidenceItem,
    SourceDocument,
    StructuredInvestmentRecord,
)


def _make_sme() -> SME:
    return SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )


def _make_document(
    document_id: str = "doc_001",
    sme_id: str = "sme_001",
) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        sme_id=sme_id,
        file_name="electricity_bill_2026.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
        document_type=DocumentType.UTILITY_BILL,
    )


def _make_evidence(
    document_id: str = "doc_001",
    sme_id: str = "sme_001",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="evidence_001",
        sme_id=sme_id,
        document_id=document_id,
        indicator_id="renewable_energy_percentage",
        criterion_id="renewable_energy",
        raw_value="72%",
        normalized_value=72.0,
        unit="percent",
        source_locator="page 2, table 1, row 6",
        extraction_method="table_extraction",
        extractor_name="table_transformer",
        confidence=0.94,
    )


def test_create_structured_investment_record() -> None:
    """Documents and evidence from one SME should form a valid record."""

    record = StructuredInvestmentRecord(
        sme=_make_sme(),
        documents=(_make_document(),),
        evidence_items=(_make_evidence(),),
    )

    assert record.sme.sme_id == "sme_001"
    assert len(record.documents) == 1
    assert len(record.evidence_items) == 1


def test_reject_document_from_another_sme() -> None:
    """A record must not contain another SME's document."""

    with pytest.raises(ValidationError):
        StructuredInvestmentRecord(
            sme=_make_sme(),
            documents=(_make_document(sme_id="sme_002"),),
        )


def test_reject_evidence_from_another_sme() -> None:
    """A record must not contain another SME's evidence."""

    with pytest.raises(ValidationError):
        StructuredInvestmentRecord(
            sme=_make_sme(),
            documents=(_make_document(),),
            evidence_items=(_make_evidence(sme_id="sme_002"),),
        )


def test_reject_evidence_with_unknown_document() -> None:
    """Evidence must reference a document contained in the record."""

    with pytest.raises(ValidationError):
        StructuredInvestmentRecord(
            sme=_make_sme(),
            documents=(_make_document(),),
            evidence_items=(
                _make_evidence(document_id="missing_document"),
            ),
        )


def test_reject_duplicate_document_ids() -> None:
    """Two documents in one record must not share an identifier."""

    with pytest.raises(ValidationError):
        StructuredInvestmentRecord(
            sme=_make_sme(),
            documents=(
                _make_document(),
                _make_document(),
            ),
        )