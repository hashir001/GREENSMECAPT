"""Integration tests for the GREENSMECAPT API."""

from fastapi.testclient import TestClient

from greensmecapt.api import create_app


def _client(tmp_path):
    app = create_app(
        database_url=(
            f"sqlite:///{tmp_path / 'api-test.db'}"
        )
    )

    return TestClient(app)


def test_health_endpoint(tmp_path) -> None:
    """The API should report readiness."""

    with _client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_create_and_retrieve_sme(tmp_path) -> None:
    """SME metadata should persist through the API."""

    payload = {
        "sme_id": "sme_001",
        "legal_name": "EcoPack Manufacturing LLC",
        "sector": "Sustainable Packaging",
        "jurisdiction": "United Arab Emirates",
    }

    with _client(tmp_path) as client:
        created = client.post(
            "/smes",
            json=payload,
        )
        retrieved = client.get("/smes/sme_001")
        record = client.get(
            "/smes/sme_001/record"
        )

    assert created.status_code == 201
    assert created.json() == payload
    assert retrieved.status_code == 200
    assert retrieved.json() == payload

    assert record.status_code == 200
    assert record.json()["sme"] == payload
    assert record.json()["documents"] == []
    assert record.json()["evidence_items"] == []


def test_return_not_found_for_unknown_sme(tmp_path) -> None:
    """Unknown SMEs should produce a controlled response."""

    with _client(tmp_path) as client:
        response = client.get("/smes/missing")

    assert response.status_code == 404