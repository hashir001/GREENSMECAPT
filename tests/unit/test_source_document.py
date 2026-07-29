"""Tests for the source-document domain model."""

import pytest
from pydantic import ValidationError

from greensmecapt.domain import DocumentType, SourceDocument


def test_create_source_document() -> None:
    """A valid source document should be created."""

    document = SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name="electricity_bill_2026.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
        document_type=DocumentType.UTILITY_BILL,
    )

    assert document.document_id == "doc_001"
    assert document.sme_id == "sme_001"
    assert document.document_type is DocumentType.UTILITY_BILL


def test_reject_invalid_sha256() -> None:
    """A malformed document fingerprint should be rejected."""

    with pytest.raises(ValidationError):
        SourceDocument(
            document_id="doc_001",
            sme_id="sme_001",
            file_name="electricity_bill_2026.pdf",
            mime_type="application/pdf",
            sha256="not-a-valid-hash",
        )


def test_reject_path_inside_file_name() -> None:
    """A filename must not contain a directory path."""

    with pytest.raises(ValidationError):
        SourceDocument(
            document_id="doc_001",
            sme_id="sme_001",
            file_name="../electricity_bill_2026.pdf",
            mime_type="application/pdf",
            sha256="a" * 64,
        )