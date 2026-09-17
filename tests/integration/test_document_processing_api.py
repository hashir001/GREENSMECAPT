"""Integration tests for API-driven document processing."""

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
SME_HEADERS = {
    "Authorization": "Bearer sme-token",
}
INVESTOR_HEADERS = {
    "Authorization": "Bearer investor-token",
}


class FakeTokenVerifier:
    """Resolve predictable principals for API tests."""

    def verify(self, token: str) -> AuthPrincipal:
        if token == "admin-token":
            return AuthPrincipal(
                user_id="admin-user",
                role=ApplicationRole.ADMIN,
            )

        if token == "sme-token":
            return AuthPrincipal(
                user_id="sme-user-001",
                role=ApplicationRole.SME_USER,
                sme_ids=("sme_001",),
            )

        if token == "investor-token":
            return AuthPrincipal(
                user_id="investor-user",
                role=ApplicationRole.INVESTOR,
            )

        raise AuthenticationError("Invalid test token.")


def _client(tmp_path: Path) -> TestClient:
    application = create_app(
        database_url=(
            f"sqlite:///{tmp_path / 'document-processing-api.db'}"
        ),
        token_verifier=FakeTokenVerifier(),
        document_storage=LocalDocumentStorage(
            tmp_path / "documents"
        ),
    )
    return TestClient(application)


def _create_sme(client: TestClient) -> None:
    response = client.post(
        "/smes",
        headers=ADMIN_HEADERS,
        json={
            "sme_id": "sme_001",
            "legal_name": "EcoPack Manufacturing LLC",
            "sector": "Sustainable Packaging",
            "jurisdiction": "United Arab Emirates",
        },
    )
    assert response.status_code == 201


def _upload(client: TestClient, content: bytes) -> str:
    response = client.post(
        "/smes/sme_001/documents",
        headers=SME_HEADERS,
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
    assert response.status_code == 201
    return response.json()["document"]["document_id"]


def test_process_uploaded_document_and_persist_evidence(
    tmp_path: Path,
) -> None:
    """The API should run the real stored-document processing flow."""

    with _client(tmp_path) as client:
        _create_sme(client)
        document_id = _upload(
            client,
            b"Renewable energy share: 72 percent.",
        )

        stored_response = client.get(
            f"/smes/sme_001/documents/{document_id}/processing",
            headers=SME_HEADERS,
        )
        processing_response = client.post(
            f"/smes/sme_001/documents/{document_id}/process",
            headers=SME_HEADERS,
        )
        record_response = client.get(
            "/smes/sme_001/record",
            headers=SME_HEADERS,
        )

    assert stored_response.status_code == 200
    assert stored_response.json()["state"]["status"] == "stored"
    assert processing_response.status_code == 200

    processing_result = processing_response.json()

    assert processing_result["state"]["status"] == "completed"
    assert processing_result["state"]["evidence_count"] == 1
    assert processing_result["report"][
        "intelligent_provider_status"
    ] == "disabled"
    assert processing_result["evidence_items"][0][
        "normalized_value"
    ] == 72.0

    record = record_response.json()

    assert len(record["evidence_items"]) == 1
    assert record["evidence_items"][0]["document_id"] == document_id
    assert record["evidence_items"][0][
        "validation_status"
    ] == "unvalidated"


def test_processing_is_idempotent_through_api(tmp_path: Path) -> None:
    """A repeated API request must reuse the completed result."""

    with _client(tmp_path) as client:
        _create_sme(client)
        document_id = _upload(
            client,
            b"Waste diversion rate: 64%.",
        )
        path = f"/smes/sme_001/documents/{document_id}/process"

        first = client.post(path, headers=SME_HEADERS)
        second = client.post(path, headers=SME_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["state"]["attempt_count"] == 1
    assert second.json()["evidence_items"] == first.json()["evidence_items"]


def test_investor_cannot_start_document_processing(
    tmp_path: Path,
) -> None:
    """Read-only investor accounts must not trigger processing."""

    with _client(tmp_path) as client:
        _create_sme(client)
        document_id = _upload(
            client,
            b"Renewable energy share: 72 percent.",
        )

        response = client.post(
            f"/smes/sme_001/documents/{document_id}/process",
            headers=INVESTOR_HEADERS,
        )

    assert response.status_code == 403


def test_reject_document_path_from_another_sme(
    tmp_path: Path,
) -> None:
    """A URL must not relabel a document as another SME's document."""

    with _client(tmp_path) as client:
        _create_sme(client)
        document_id = _upload(
            client,
            b"Renewable energy share: 72 percent.",
        )

        response = client.get(
            f"/smes/sme_002/documents/{document_id}/processing",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 404
