"""Tests for safe original-document storage."""

from hashlib import sha256
from pathlib import Path

import pytest

from greensmecapt.storage import (
    DocumentStorageError,
    LocalDocumentStorage,
)


def test_store_and_read_document(tmp_path: Path) -> None:
    """Stored bytes should retain their content and stable key."""

    content = b"Renewable energy share: 72 percent."
    digest = sha256(content).hexdigest()
    storage = LocalDocumentStorage(tmp_path)

    key = storage.save(
        sme_id="sme_001",
        document_id="doc_001",
        sha256=digest,
        content=content,
    )

    assert storage.read(key) == content
    assert key == f"sme_001/doc_001/{digest}"


def test_store_same_content_idempotently(
    tmp_path: Path,
) -> None:
    """Retrying the same storage operation should be safe."""

    content = b"document"
    digest = sha256(content).hexdigest()
    storage = LocalDocumentStorage(tmp_path)

    first = storage.save(
        sme_id="sme_001",
        document_id="doc_001",
        sha256=digest,
        content=content,
    )
    second = storage.save(
        sme_id="sme_001",
        document_id="doc_001",
        sha256=digest,
        content=content,
    )

    assert first == second
    assert storage.read(second) == content


def test_reject_unsafe_identifier(tmp_path: Path) -> None:
    """Identifiers must not manipulate storage paths."""

    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(DocumentStorageError):
        storage.save(
            sme_id="../another-company",
            document_id="doc_001",
            sha256=sha256(b"document").hexdigest(),
            content=b"document",
        )


def test_reject_path_escape(tmp_path: Path) -> None:
    """An external storage key must not escape the root."""

    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(DocumentStorageError):
        storage.read("../../private-key")


def test_reject_content_that_does_not_match_digest(
    tmp_path: Path,
) -> None:
    """The supplied digest must describe the supplied bytes."""

    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(DocumentStorageError):
        storage.save(
            sme_id="sme_001",
            document_id="doc_001",
            sha256=sha256(b"different").hexdigest(),
            content=b"document",
        )


def test_reject_malformed_storage_key(
    tmp_path: Path,
) -> None:
    """Storage reads must use a generated three-part key."""

    storage = LocalDocumentStorage(tmp_path)

    malformed_key = (
        "sme_001/another_directory/doc_001/"
        f"{sha256(b'document').hexdigest()}"
    )

    with pytest.raises(DocumentStorageError):
        storage.read(malformed_key)


def test_detect_stored_content_tampering(
    tmp_path: Path,
) -> None:
    """Content changed after storage must fail verification."""

    content = b"original document"
    digest = sha256(content).hexdigest()
    storage = LocalDocumentStorage(tmp_path)

    key = storage.save(
        sme_id="sme_001",
        document_id="doc_001",
        sha256=digest,
        content=content,
    )

    stored_path = tmp_path / Path(key)
    stored_path.write_bytes(b"tampered document")

    with pytest.raises(DocumentStorageError):
        storage.read(key)