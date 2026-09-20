"""Integration tests for the GREENSMECAPT API."""

from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient

from greensmecapt.api import create_app
from greensmecapt.security import (
    ApplicationRole,
    AuthenticationError,
    AuthPrincipal,
)
from greensmecapt.storage import LocalDocumentStorage

ADMIN_HEADERS = {
    "Authorization": "Bearer admin-token",
}

SME_ONE_HEADERS = {
    "Authorization": "Bearer sme-one-token",
}

SME_TWO_HEADERS = {
    "Authorization": "Bearer sme-two-token",
}

INVESTOR_HEADERS = {
    "Authorization": "Bearer investor-token",
}

SME_PAYLOAD = {
    "sme_id": "sme_001",
    "legal_name": "EcoPack Manufacturing LLC",
    "sector": "Sustainable Packaging",
    "jurisdiction": "United Arab Emirates",
}


class FakeTokenVerifier:
    """Resolve predictable test tokens without an identity provider."""

    def verify(self, token: str) -> AuthPrincipal:
        """Return the principal represented by a test token."""

        if token == "admin-token":
            return AuthPrincipal(
                user_id="admin-user",
                role=ApplicationRole.ADMIN,
            )

        if token == "sme-one-token":
            return AuthPrincipal(
                user_id="sme-user-001",
                role=ApplicationRole.SME_USER,
                sme_ids=("sme_001",),
            )

        if token == "sme-two-token":
            return AuthPrincipal(
                user_id="sme-user-002",
                role=ApplicationRole.SME_USER,
                sme_ids=("sme_002",),
            )

        if token == "investor-token":
            return AuthPrincipal(
                user_id="investor-user",
                role=ApplicationRole.INVESTOR,
            )

        raise AuthenticationError(
            "The supplied access token is invalid."
        )


def _client(tmp_path: Path) -> TestClient:
    """Create an isolated API client with test dependencies."""

    application = create_app(
        database_url=(
            f"sqlite:///{tmp_path / 'greensmecapt-test.db'}"
        ),
        token_verifier=FakeTokenVerifier(),
        document_storage=LocalDocumentStorage(
            tmp_path / "documents"
        ),
    )

    return TestClient(application)


def _create_sme(client: TestClient) -> None:
    """Create the standard SME used by API tests."""

    response = client.post(
        "/smes",
        json=SME_PAYLOAD,
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 201


def test_health_endpoint_is_public(tmp_path: Path) -> None:
    """The health endpoint should not require authentication."""

    with _client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
    }


def test_allow_configured_browser_origin(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Configured frontend origins should pass CORS preflight."""

    monkeypatch.setenv(
        "GREENSMECAPT_CORS_ORIGINS",
        "https://app.example.com",
    )

    with _client(tmp_path) as client:
        response = client.options(
            "/smes",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://app.example.com"
    )


def test_reject_missing_access_token(tmp_path: Path) -> None:
    """Protected API operations must require an access token."""

    with _client(tmp_path) as client:
        response = client.get("/smes")

    assert response.status_code == 401


def test_reject_invalid_access_token(tmp_path: Path) -> None:
    """Invalid bearer tokens must fail authentication."""

    with _client(tmp_path) as client:
        response = client.get(
            "/smes",
            headers={
                "Authorization": "Bearer invalid-token",
            },
        )

    assert response.status_code == 401


def test_create_and_retrieve_sme(tmp_path: Path) -> None:
    """An administrator should create and retrieve an SME."""

    with _client(tmp_path) as client:
        create_response = client.post(
            "/smes",
            json=SME_PAYLOAD,
            headers=ADMIN_HEADERS,
        )

        retrieve_response = client.get(
            "/smes/sme_001",
            headers=ADMIN_HEADERS,
        )

    assert create_response.status_code == 201
    assert retrieve_response.status_code == 200
    assert retrieve_response.json() == SME_PAYLOAD


def test_return_not_found_for_unknown_sme(
    tmp_path: Path,
) -> None:
    """Unknown SME identifiers should return a controlled response."""

    with _client(tmp_path) as client:
        response = client.get(
            "/smes/missing_sme",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 404


def test_sme_user_can_access_assigned_sme(
    tmp_path: Path,
) -> None:
    """An SME user should access the company assigned to them."""

    with _client(tmp_path) as client:
        _create_sme(client)

        response = client.get(
            "/smes/sme_001",
            headers=SME_ONE_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["sme_id"] == "sme_001"


def test_sme_user_cannot_access_another_sme(
    tmp_path: Path,
) -> None:
    """An SME user must not read another company's record."""

    with _client(tmp_path) as client:
        _create_sme(client)

        response = client.get(
            "/smes/sme_001",
            headers=SME_TWO_HEADERS,
        )

    assert response.status_code == 403


def test_upload_document_and_retrieve_record(
    tmp_path: Path,
) -> None:
    """An authorized upload should be stored and persisted."""

    content = b"Renewable energy share: 72 percent."
    expected_sha256 = sha256(content).hexdigest()

    with _client(tmp_path) as client:
        _create_sme(client)

        upload_response = client.post(
            "/smes/sme_001/documents",
            headers=SME_ONE_HEADERS,
            data={
                "document_type": "sustainability_report",
            },
            files={
                "file": (
                    "sustainability-report.txt",
                    content,
                    "text/plain",
                ),
            },
        )

        record_response = client.get(
            "/smes/sme_001/record",
            headers=SME_ONE_HEADERS,
        )

    assert upload_response.status_code == 201

    upload_result = upload_response.json()
    uploaded_document = upload_result["document"]

    assert uploaded_document["sme_id"] == "sme_001"
    assert (
        uploaded_document["file_name"]
        == "sustainability-report.txt"
    )
    assert uploaded_document["mime_type"] == "text/plain"
    assert uploaded_document["sha256"] == expected_sha256
    assert (
        uploaded_document["document_type"]
        == "sustainability_report"
    )

    assert upload_result["processing_status"] == "stored"
    assert upload_result["storage_key"] == (
        f"sme_001/{uploaded_document['document_id']}/"
        f"{expected_sha256}"
    )

    assert record_response.status_code == 200

    record = record_response.json()

    assert record["sme"]["sme_id"] == "sme_001"
    assert len(record["documents"]) == 1
    assert (
        record["documents"][0]
        == uploaded_document
    )
    assert record["evidence_items"] == []


def test_investor_cannot_upload_sme_document(
    tmp_path: Path,
) -> None:
    """Investor accounts must not upload SME evidence."""

    with _client(tmp_path) as client:
        _create_sme(client)

        response = client.post(
            "/smes/sme_001/documents",
            headers=INVESTOR_HEADERS,
            data={
                "document_type": "sustainability_report",
            },
            files={
                "file": (
                    "report.txt",
                    b"Renewable energy share: 72 percent.",
                    "text/plain",
                ),
            },
        )

    assert response.status_code == 403


def test_reject_unsupported_upload_type(
    tmp_path: Path,
) -> None:
    """The upload boundary should reject unsupported formats."""

    with _client(tmp_path) as client:
        _create_sme(client)

        response = client.post(
            "/smes/sme_001/documents",
            headers=SME_ONE_HEADERS,
            data={
                "document_type": "other",
            },
            files={
                "file": (
                    "malware.exe",
                    b"not a supported document",
                    "application/octet-stream",
                ),
            },
        )

    assert response.status_code == 415
