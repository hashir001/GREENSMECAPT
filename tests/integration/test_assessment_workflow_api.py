"""Integration tests for assessment preparation and comparison routes."""

from pathlib import Path

from fastapi.testclient import TestClient

from greensmecapt.api import create_app
from greensmecapt.security import (
    ApplicationRole,
    AuthenticationError,
    AuthPrincipal,
)
from greensmecapt.storage import LocalDocumentStorage

ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}
INVESTOR_HEADERS = {"Authorization": "Bearer investor-token"}


class FakeTokenVerifier:
    """Resolve predictable principals for API integration tests."""

    def verify(self, token: str) -> AuthPrincipal:
        if token == "admin-token":
            return AuthPrincipal(
                user_id="admin_001",
                role=ApplicationRole.ADMIN,
            )

        if token == "investor-token":
            return AuthPrincipal(
                user_id="investor_001",
                role=ApplicationRole.INVESTOR,
            )

        raise AuthenticationError("Invalid test token.")


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            database_url=(
                f"sqlite:///{tmp_path / 'assessment-api.db'}"
            ),
            token_verifier=FakeTokenVerifier(),
            document_storage=LocalDocumentStorage(
                tmp_path / "documents"
            ),
        )
    )


def _create_sme(
    client: TestClient,
    sme_id: str,
) -> None:
    response = client.post(
        "/smes",
        headers=ADMIN_HEADERS,
        json={
            "sme_id": sme_id,
            "legal_name": f"Company {sme_id}",
            "sector": "Green services",
            "jurisdiction": "United Arab Emirates",
        },
    )

    assert response.status_code == 201


def _submission(sme_id: str, rating: str) -> dict:
    return {
        "context": {
            "sme_id": sme_id,
            "activity_description": "Environmental service provider.",
            "facts": {
                "manufactures_or_processes": False,
                "burns_fuel_on_site": False,
                "operates_vehicle_fleet": False,
                "operates_facility": False,
                "uses_cloud_services": False,
                "handles_materials_or_waste": False,
                "provides_clean_energy": False,
                "provides_circular_services": False,
                "works_on_buildings": False,
                "works_in_agriculture_food_land": False,
                "provides_digital_services": False,
                "offers_environmental_solution": False,
                "operates_retail_or_hospitality": False,
                "plans_operational_transition": False,
            },
        },
        "responses": [
            {
                "response_id": f"response_{sme_id}",
                "sme_id": sme_id,
                "criterion_id": "green_contribution",
                "kind": "linguistic",
                "linguistic_value": rating,
                "submitted_by": "reviewer_001",
            }
        ],
    }


def _approve_and_publish(
    client: TestClient,
    sme_id: str,
    rating: str,
) -> None:
    revision = 1
    for target_status in ("submitted", "under_review", "approved"):
        transition = client.patch(
            f"/smes/{sme_id}/application",
            headers=ADMIN_HEADERS,
            json={
                "expected_revision": revision,
                "target_status": target_status,
            },
        )
        assert transition.status_code == 200
        revision = transition.json()["revision"]

    approval = client.post(
        f"/assessments/profiles/{sme_id}/approve",
        headers=ADMIN_HEADERS,
        json=_submission(sme_id, rating),
    )
    assert approval.status_code == 200

    publication = client.post(
        f"/assessments/profiles/{sme_id}/publish",
        headers=ADMIN_HEADERS,
        json={
            "revision_id": approval.json()["revision_id"],
            "expected_application_revision": revision,
        },
    )
    assert publication.status_code == 200


def test_compare_smes_through_api(tmp_path: Path) -> None:
    """The API should return all configured comparison methods."""

    with _client(tmp_path) as client:
        _create_sme(client, "sme_strong")
        _create_sme(client, "sme_weaker")

        response = client.post(
            "/assessments/compare",
            headers=ADMIN_HEADERS,
            json={
                "run_id": "run_001",
                "cohort_id": "cohort_001",
                "version": "1.0",
                "minimum_shared_criteria": 1,
                "submissions": [
                    _submission("sme_strong", "very_high"),
                    _submission("sme_weaker", "low"),
                ],
            },
        )

    assert response.status_code == 200
    record = response.json()
    result = record["result"]
    assert record["run_id"] == "run_001"
    assert (
        result["comparable_topsis"]["topsis_result"]
        ["ranking"][0]["sme_id"]
        == "sme_strong"
    )
    assert result["fuzzy_topsis"]["ranking"][0]["sme_id"] == (
        "sme_strong"
    )
    assert result["electre_iii"]["rank_levels"][0]["sme_ids"] == [
        "sme_strong"
    ]


def test_retrieve_persisted_assessment_run(tmp_path: Path) -> None:
    """Investors should only retrieve comparison runs they requested."""

    with _client(tmp_path) as client:
        _create_sme(client, "sme_strong")
        _create_sme(client, "sme_weaker")
        request = {
            "run_id": "run_saved",
            "cohort_id": "cohort_001",
            "version": "1.0",
            "minimum_shared_criteria": 1,
            "submissions": [
                _submission("sme_strong", "very_high"),
                _submission("sme_weaker", "low"),
            ],
        }

        create_response = client.post(
            "/assessments/compare",
            headers=ADMIN_HEADERS,
            json=request,
        )
        list_response = client.get(
            "/assessments/runs",
            headers=INVESTOR_HEADERS,
        )
        retrieve_response = client.get(
            "/assessments/runs/run_saved",
            headers=INVESTOR_HEADERS,
        )
        admin_retrieve_response = client.get(
            "/assessments/runs/run_saved",
            headers=ADMIN_HEADERS,
        )

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert retrieve_response.status_code == 404
    assert admin_retrieve_response.status_code == 200
    assert admin_retrieve_response.json() == create_response.json()


def test_investor_compares_centrally_approved_profiles(
    tmp_path: Path,
) -> None:
    """Investors should select SMEs without supplying scoring inputs."""

    with _client(tmp_path) as client:
        _create_sme(client, "sme_strong")
        _create_sme(client, "sme_weaker")

        _approve_and_publish(client, "sme_strong", "very_high")
        _approve_and_publish(client, "sme_weaker", "low")
        automatic_response = client.post(
            "/assessments/compare/automatic",
            headers=INVESTOR_HEADERS,
            json={
                "run_id": "run_investor",
                "cohort_id": "investor_comparison",
                "version": "1.0",
                "minimum_shared_criteria": 1,
                "minimum_shared_weight_ratio": 0.6,
                "sme_ids": [
                    "sme_strong",
                    "sme_weaker",
                ],
            },
        )
        investor_runs = client.get(
            "/assessments/runs",
            headers=INVESTOR_HEADERS,
        )
        investor_run = client.get(
            "/assessments/runs/run_investor",
            headers=INVESTOR_HEADERS,
        )

    assert automatic_response.status_code == 200
    assert investor_runs.json()[0]["run_id"] == "run_investor"
    assert investor_run.status_code == 200

    result = automatic_response.json()

    assert result["requested_by"] == "investor_001"
    assert result["sme_ids"] == [
        "sme_strong",
        "sme_weaker",
    ]
    assert (
        result["result"]["comparable_topsis"]
        ["topsis_result"]["ranking"][0]["sme_id"]
        == "sme_strong"
    )


def test_automatic_comparison_requires_approved_profiles(
    tmp_path: Path,
) -> None:
    """Missing governed profiles should produce an actionable response."""

    with _client(tmp_path) as client:
        _create_sme(client, "sme_001")
        _create_sme(client, "sme_002")

        response = client.post(
            "/assessments/compare/automatic",
            headers=INVESTOR_HEADERS,
            json={
                "run_id": "run_missing_profiles",
                "cohort_id": "missing_profiles",
                "version": "1.0",
                "sme_ids": ["sme_001", "sme_002"],
            },
        )

    assert response.status_code == 422
    assert "no published assessment profile" in response.json()["detail"]


def test_changes_requested_withdraws_investor_publication(
    tmp_path: Path,
) -> None:
    """Reopened application data must disappear from investor discovery."""

    with _client(tmp_path) as client:
        _create_sme(client, "sme_001")
        _approve_and_publish(client, "sme_001", "high")
        visible = client.get("/smes", headers=INVESTOR_HEADERS)
        reopened = client.patch(
            "/smes/sme_001/application",
            headers=ADMIN_HEADERS,
            json={
                "expected_revision": 5,
                "target_status": "changes_requested",
                "reason": "New evidence is required",
            },
        )
        hidden = client.get("/smes", headers=INVESTOR_HEADERS)

    assert [item["sme_id"] for item in visible.json()] == ["sme_001"]
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "changes_requested"
    assert hidden.json() == []


def test_investor_cannot_supply_assessment_inputs(
    tmp_path: Path,
) -> None:
    """Read-oriented investor accounts must not control scoring inputs."""

    with _client(tmp_path) as client:
        _create_sme(client, "sme_001")

        response = client.post(
            "/assessments/prepare",
            headers=INVESTOR_HEADERS,
            json=_submission("sme_001", "very_high"),
        )

    assert response.status_code == 403


def test_reviewer_can_retrieve_versioned_assessment_configuration(
    tmp_path: Path,
) -> None:
    """The frontend should render forms from backend-owned policy."""

    with _client(tmp_path) as client:
        response = client.get(
            "/assessments/configuration",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["assessment_policy"]["policy_id"]
        == "greensmecapt_activity_profiles"
    )
    assert (
        payload["normalization_policy"]["policy_id"]
        == "greensmecapt_normalization"
    )
    assert "very_high" in (
        payload["normalization_policy"]
        ["default_linguistic_scale"]
    )
