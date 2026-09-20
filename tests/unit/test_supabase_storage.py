"""Tests for private Supabase original-document storage."""

from hashlib import sha256

import pytest

from greensmecapt.storage import (
    DocumentStorageError,
    StorageResponse,
    SupabaseDocumentStorage,
    SupabaseStorageConfiguration,
    storage_from_environment,
)


class FakeTransport:
    """Store objects in memory while preserving HTTP semantics."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[dict[str, object]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers,
        content: bytes | None,
        timeout_seconds: float,
    ) -> StorageResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )

        if method == "POST":
            if url in self.objects:
                return StorageResponse(409, b"already exists")

            self.objects[url] = content or b""
            return StorageResponse(200, b"stored")

        if method == "GET":
            if url not in self.objects:
                return StorageResponse(404, b"missing")

            return StorageResponse(200, self.objects[url])

        if method == "DELETE":
            self.objects.pop(url, None)
            return StorageResponse(200, b"deleted")

        raise AssertionError(f"Unexpected method: {method}")


def _storage() -> tuple[SupabaseDocumentStorage, FakeTransport]:
    transport = FakeTransport()
    storage = SupabaseDocumentStorage(
        SupabaseStorageConfiguration(
            project_url="https://project.supabase.co",
            service_role_key="server-secret",
        ),
        transport=transport,
    )
    return storage, transport


def test_store_read_and_delete_private_object() -> None:
    content = b"Renewable energy share: 72 percent."
    digest = sha256(content).hexdigest()
    storage, transport = _storage()

    key = storage.save(
        sme_id="sme_001",
        document_id="doc_001",
        sha256=digest,
        content=content,
    )

    assert key == f"sme_001/doc_001/{digest}"
    assert storage.read(key) == content
    assert (
        transport.requests[0]["headers"]["Authorization"]
        == "Bearer server-secret"
    )
    assert transport.requests[0]["headers"]["x-upsert"] == "false"

    storage.delete(key)

    with pytest.raises(DocumentStorageError):
        storage.read(key)


def test_retry_identical_upload_idempotently() -> None:
    content = b"document"
    digest = sha256(content).hexdigest()
    storage, _ = _storage()

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


def test_detect_remote_content_tampering() -> None:
    content = b"document"
    digest = sha256(content).hexdigest()
    storage, transport = _storage()
    key = storage.save(
        sme_id="sme_001",
        document_id="doc_001",
        sha256=digest,
        content=content,
    )
    object_url = next(iter(transport.objects))
    transport.objects[object_url] = b"tampered"

    with pytest.raises(
        DocumentStorageError,
        match="integrity check",
    ):
        storage.read(key)


def test_reject_invalid_storage_configuration() -> None:
    with pytest.raises(ValueError):
        SupabaseStorageConfiguration(
            project_url="not-a-url",
            service_role_key="secret",
        )


def test_supabase_factory_requires_server_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GREENSMECAPT_STORAGE_BACKEND",
        "supabase",
    )
    monkeypatch.delenv(
        "GREENSMECAPT_SUPABASE_URL",
        raising=False,
    )
    monkeypatch.delenv(
        "GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY",
        raising=False,
    )

    with pytest.raises(
        DocumentStorageError,
        match="GREENSMECAPT_SUPABASE_URL",
    ):
        storage_from_environment()
