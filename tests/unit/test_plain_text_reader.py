"""Tests for the plain-text document reader."""

from hashlib import sha256

import pytest

from greensmecapt.document_intelligence import (
    DocumentReadError,
    PlainTextDocumentReader,
    UnsupportedMimeTypeError,
)
from greensmecapt.domain import SourceDocument

DOCUMENT_CONTENT = b"Renewable energy contribution: 72%"


def _make_document(
    mime_type: str = "text/plain",
    content: bytes = DOCUMENT_CONTENT,
) -> SourceDocument:
    return SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name="sustainability_statement.txt",
        mime_type=mime_type,
        sha256=sha256(content).hexdigest(),
    )


def test_read_plain_text_document() -> None:
    """Valid UTF-8 document content should become extracted text."""

    reader = PlainTextDocumentReader()

    extracted_document = reader.read(
        document=_make_document(),
        content=DOCUMENT_CONTENT,
    )

    assert extracted_document.document_id == "doc_001"
    assert extracted_document.pages[0].page_number == 1
    assert extracted_document.pages[0].text == (
        "Renewable energy contribution: 72%"
    )


def test_reject_unsupported_mime_type() -> None:
    """The text reader should reject non-text documents."""

    reader = PlainTextDocumentReader()

    with pytest.raises(UnsupportedMimeTypeError):
        reader.read(
            document=_make_document(mime_type="application/pdf"),
            content=DOCUMENT_CONTENT,
        )


def test_reject_invalid_utf8() -> None:
    """Invalid UTF-8 bytes should produce a controlled error."""

    invalid_content = b"\xff\xfe"
    reader = PlainTextDocumentReader()

    with pytest.raises(DocumentReadError):
        reader.read(
            document=_make_document(content=invalid_content),
            content=invalid_content,
        )