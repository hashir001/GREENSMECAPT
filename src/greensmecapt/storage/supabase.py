"""Private Supabase object storage for original documents."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256 as calculate_sha256
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from greensmecapt.storage.documents import DocumentStorageError

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_BUCKET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StorageResponse:
    """Contain the bounded response needed by the storage adapter."""

    status: int
    body: bytes


class StorageTransport(Protocol):
    """Send one authenticated object-storage request."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_seconds: float,
    ) -> StorageResponse:
        """Return an HTTP status and response bytes."""
        ...


class UrllibStorageTransport:
    """Use the Python standard library for storage requests."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_seconds: float,
    ) -> StorageResponse:
        request = Request(
            url=url,
            data=content,
            headers=dict(headers),
            method=method,
        )

        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                return StorageResponse(
                    status=response.status,
                    body=response.read(),
                )
        except HTTPError as error:
            return StorageResponse(
                status=error.code,
                body=error.read(),
            )
        except (URLError, TimeoutError, OSError) as error:
            raise DocumentStorageError(
                "Supabase Storage could not be reached."
            ) from error


@dataclass(frozen=True)
class SupabaseStorageConfiguration:
    """Configure the private server-side storage connection."""

    project_url: str
    service_role_key: str
    bucket: str = "source-documents"
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        project_url = self.project_url.rstrip("/")
        parsed = urlsplit(project_url)

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(
                "Supabase project URL must be an HTTP or HTTPS URL."
            )

        if not self.service_role_key.strip():
            raise ValueError(
                "Supabase service-role key must not be blank."
            )

        if not _SAFE_BUCKET.fullmatch(self.bucket):
            raise ValueError("Supabase bucket name is invalid.")

        if self.timeout_seconds <= 0:
            raise ValueError("Storage timeout must be positive.")

        object.__setattr__(self, "project_url", project_url)


class SupabaseDocumentStorage:
    """Store original documents in a private Supabase bucket."""

    def __init__(
        self,
        configuration: SupabaseStorageConfiguration,
        *,
        transport: StorageTransport | None = None,
    ) -> None:
        self._configuration = configuration
        self._transport = transport or UrllibStorageTransport()

    def save(
        self,
        *,
        sme_id: str,
        document_id: str,
        sha256: str,
        content: bytes,
    ) -> str:
        """Store verified bytes at a deterministic private key."""

        storage_key = _build_storage_key(
            sme_id=sme_id,
            document_id=document_id,
            digest=sha256,
        )

        if not content:
            raise DocumentStorageError(
                "Document content must not be empty."
            )

        if calculate_sha256(content).hexdigest() != sha256:
            raise DocumentStorageError(
                "Document content does not match its SHA-256 digest."
            )

        response = self._request(
            method="POST",
            storage_key=storage_key,
            content=content,
            extra_headers={
                "Content-Type": "application/octet-stream",
                "x-upsert": "false",
            },
        )

        if response.status in {200, 201}:
            return storage_key

        if response.status == 409:
            existing = self.read(storage_key)

            if existing == content:
                return storage_key

            raise DocumentStorageError(
                "Stored content does not match its digest."
            )

        raise DocumentStorageError(
            "Document could not be stored in Supabase Storage."
        )

    def read(self, storage_key: str) -> bytes:
        """Read an object and verify its content-addressed digest."""

        expected_digest = _validate_storage_key(storage_key)
        response = self._request(
            method="GET",
            storage_key=storage_key,
        )

        if response.status != 200:
            raise DocumentStorageError(
                "Stored document could not be read."
            )

        if calculate_sha256(response.body).hexdigest() != expected_digest:
            raise DocumentStorageError(
                "Stored document failed its integrity check."
            )

        return response.body

    def delete(self, storage_key: str) -> None:
        """Delete one validated storage object."""

        _validate_storage_key(storage_key)
        response = self._request(
            method="DELETE",
            storage_key=storage_key,
        )

        if response.status not in {200, 204, 404}:
            raise DocumentStorageError(
                "Stored document could not be removed."
            )

    def _request(
        self,
        *,
        method: str,
        storage_key: str,
        content: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> StorageResponse:
        configuration = self._configuration
        encoded_bucket = quote(configuration.bucket, safe="")
        encoded_key = quote(storage_key, safe="/")
        headers = {
            "apikey": configuration.service_role_key,
            "Authorization": (
                f"Bearer {configuration.service_role_key}"
            ),
        }
        headers.update(extra_headers or {})

        return self._transport.request(
            method=method,
            url=(
                f"{configuration.project_url}/storage/v1/object/"
                f"{encoded_bucket}/{encoded_key}"
            ),
            headers=headers,
            content=content,
            timeout_seconds=configuration.timeout_seconds,
        )


def _build_storage_key(
    *,
    sme_id: str,
    document_id: str,
    digest: str,
) -> str:
    _validate_identifier("SME", sme_id)
    _validate_identifier("document", document_id)
    _validate_digest(digest)
    return f"{sme_id}/{document_id}/{digest}"


def _validate_storage_key(storage_key: str) -> str:
    parts = storage_key.split("/")

    if len(parts) != 3:
        raise DocumentStorageError(
            "Storage key has an invalid structure."
        )

    sme_id, document_id, digest = parts
    _validate_identifier("SME", sme_id)
    _validate_identifier("document", document_id)
    _validate_digest(digest)
    return digest


def _validate_identifier(name: str, value: str) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise DocumentStorageError(
            f"{name} identifier is unsafe for storage."
        )


def _validate_digest(value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise DocumentStorageError(
            "Storage requires a valid SHA-256 digest."
        )
