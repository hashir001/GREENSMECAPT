"""Safe local storage for original submitted documents."""

import os
import re
from hashlib import sha256 as calculate_sha256
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DocumentStorageError(ValueError):
    """Raised when document bytes cannot be stored safely."""


class DocumentStorage(Protocol):
    """Persist and retrieve original document bytes."""

    def save(
        self,
        *,
        sme_id: str,
        document_id: str,
        sha256: str,
        content: bytes,
    ) -> str:
        """Store content and return an opaque storage key."""
        ...

    def read(self, storage_key: str) -> bytes:
        """Return bytes for an opaque storage key."""
        ...

    def delete(self, storage_key: str) -> None:
        """Delete a stored object when a transaction fails."""
        ...


class LocalDocumentStorage:
    """Store content-addressed documents outside the database."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        sme_id: str,
        document_id: str,
        sha256: str,
        content: bytes,
    ) -> str:
        """Store bytes without trusting identifiers or digests."""

        if not content:
            raise DocumentStorageError(
                "Document content must not be empty."
            )

        _validate_identifier("SME", sme_id)
        _validate_identifier("document", document_id)
        _validate_digest(sha256)

        actual_sha256 = calculate_sha256(content).hexdigest()

        if actual_sha256 != sha256:
            raise DocumentStorageError(
                "Document content does not match its SHA-256 digest."
            )

        relative_path = PurePosixPath(
            sme_id,
            document_id,
            sha256,
        )
        destination = (
            self._root / Path(*relative_path.parts)
        ).resolve()

        _ensure_within_root(
            root=self._root,
            target=destination,
        )

        temporary = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp"
        )

        try:
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if destination.exists():
                existing_content = destination.read_bytes()

                if existing_content != content:
                    raise DocumentStorageError(
                        "Stored content does not match its digest."
                    )

                return relative_path.as_posix()

            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temporary, destination)
        except DocumentStorageError:
            _remove_temporary_file(temporary)
            raise
        except OSError as error:
            _remove_temporary_file(temporary)

            raise DocumentStorageError(
                "Document could not be stored."
            ) from error

        return relative_path.as_posix()

    def read(self, storage_key: str) -> bytes:
        """Return bytes after verifying their stored digest."""

        target = self._resolve_key(storage_key)

        try:
            content = target.read_bytes()
        except OSError as error:
            raise DocumentStorageError(
                "Stored document could not be read."
            ) from error

        actual_sha256 = calculate_sha256(content).hexdigest()
        expected_sha256 = target.name

        if actual_sha256 != expected_sha256:
            raise DocumentStorageError(
                "Stored document failed its integrity check."
            )

        return content

    def delete(self, storage_key: str) -> None:
        """Remove an object without accepting arbitrary paths."""

        target = self._resolve_key(storage_key)

        try:
            target.unlink(missing_ok=True)
        except OSError as error:
            raise DocumentStorageError(
                "Stored document could not be removed."
            ) from error

    def _resolve_key(self, storage_key: str) -> Path:
        if not storage_key.strip():
            raise DocumentStorageError(
                "Storage key must not be blank."
            )

        key = PurePosixPath(storage_key)

        if key.is_absolute() or len(key.parts) != 3:
            raise DocumentStorageError(
                "Storage key has an invalid structure."
            )

        sme_id, document_id, digest = key.parts

        _validate_identifier("SME", sme_id)
        _validate_identifier("document", document_id)
        _validate_digest(digest)

        target = (
            self._root / Path(*key.parts)
        ).resolve()

        _ensure_within_root(
            root=self._root,
            target=target,
        )

        return target


def _validate_identifier(
    name: str,
    value: str,
) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise DocumentStorageError(
            f"{name} identifier is unsafe for storage."
        )


def _validate_digest(value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise DocumentStorageError(
            "Storage requires a valid SHA-256 digest."
        )


def _ensure_within_root(
    *,
    root: Path,
    target: Path,
) -> None:
    if root not in target.parents:
        raise DocumentStorageError(
            "Resolved document path escapes storage."
        )


def _remove_temporary_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass