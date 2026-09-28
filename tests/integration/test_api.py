"""Integration tests for the GREENSMECAPT API."""

from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from greensmecapt.api import create_app
from greensmecapt.security import (
    ApplicationRole,
    AuthenticationError,
    AuthPrincipal,
    ManagedUser,
)
from greensmecapt.storage import (
    DocumentStorage,
    DocumentStorageError,
    LocalDocumentStorage,
)

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

REVIEWER_HEADERS = {
    "Authorization": "Bearer reviewer-token",
}

EXPERT_HEADERS = {
    "Authorization": "Bearer expert-token",
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

        if token == "reviewer-token":
            return AuthPrincipal(
                user_id="reviewer-user",
                role=ApplicationRole.REVIEWER,
            )

        if token == "expert-token":
            return AuthPrincipal(
                user_id="expert-user",
                role=ApplicationRole.EXPERT,
            )

        raise AuthenticationError(
            "The supplied access token is invalid."
        )


class FakeIdentityAdmin:
    """Provide deterministic user administration for API tests."""

    configured = True

    def __init__(self) -> None:
        self.users = {
            "admin-user": ManagedUser(
                user_id="admin-user",
                email="admin@example.com",
                role=ApplicationRole.ADMIN,
            )
        }

    def list_users(self) -> tuple[ManagedUser, ...]:
        return tuple(self.users.values())

    def invite_user(
        self,
        *,
        email: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        user = ManagedUser(
            user_id="invited-user",
            email=email,
            role=role,
            sme_ids=sme_ids,
        )
        self.users[user.user_id] = user
        return user

    def update_access(
        self,
        *,
        user_id: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        current = self.users[user_id]
        updated = current.model_copy(
            update={"role": role, "sme_ids": sme_ids}
        )
        self.users[user_id] = updated
        return updated


def _client(
    tmp_path: Path,
    document_storage: DocumentStorage | None = None,
) -> TestClient:
    """Create an isolated API client with test dependencies."""

    application = create_app(
        database_url=(
            f"sqlite:///{tmp_path / 'greensmecapt-test.db'}"
        ),
        token_verifier=FakeTokenVerifier(),
        document_storage=(
            document_storage
            or LocalDocumentStorage(tmp_path / "documents")
        ),
        identity_administrator=FakeIdentityAdmin(),
    )

    return TestClient(application)


class DeleteThenFailStorage(LocalDocumentStorage):
    """Simulate a provider error after deleting the remote object."""

    def delete(self, storage_key: str) -> None:
        super().delete(storage_key)
        raise DocumentStorageError("Simulated post-delete failure.")


class UnreadableLegacyStorage(LocalDocumentStorage):
    """Represent legacy metadata whose source object can no longer be read."""

    def read(self, storage_key: str) -> bytes:
        del storage_key
        raise DocumentStorageError("Legacy source object is unavailable.")


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


def test_report_runtime_document_capabilities(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/system/capabilities",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    assert response.json() == {
        "native_pdf_reading": True,
        "ocr_routing": True,
        "table_extraction": True,
        "semantic_provider_configured": False,
        "visual_provider_configured": False,
        "identity_admin_configured": True,
        "human_validation_required": True,
    }


def test_admin_can_invite_and_manage_user_access(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        invitation = client.post(
            "/admin/users/invitations",
            headers=ADMIN_HEADERS,
            json={
                "email": "owner@example.com",
                "role": "sme_user",
                "sme_ids": ["sme_001"],
            },
        )
        update = client.patch(
            "/admin/users/invited-user/access",
            headers=ADMIN_HEADERS,
            json={
                "role": "reviewer",
                "sme_ids": [],
            },
        )
        listing = client.get(
            "/admin/users",
            headers=ADMIN_HEADERS,
        )

    assert invitation.status_code == 201
    assert invitation.json()["sme_ids"] == ["sme_001"]
    assert update.status_code == 200
    assert update.json()["role"] == "reviewer"
    assert len(listing.json()) == 2


def test_non_admin_cannot_manage_users(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/admin/users",
            headers=INVESTOR_HEADERS,
        )

    assert response.status_code == 403


def test_sme_financial_submission_is_reviewed_separately(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _create_sme(client)
        draft = client.put(
            "/smes/sme_001/financial-submission",
            headers=SME_ONE_HEADERS,
            json={
                "expected_revision": None,
                "observations": [
                    {
                        "observation_id": "finance_roa_001",
                        "sme_id": "sme_001",
                        "metric_id": "roa_percentage",
                        "state": "unknown",
                        "source_ids": [],
                    }
                ],
            },
        )
        submitted = client.post(
            "/smes/sme_001/financial-submission/submit",
            headers=SME_ONE_HEADERS,
            json={"expected_revision": draft.json()["revision"]},
        )
        reviewed = client.post(
            "/smes/sme_001/financial-submission/review",
            headers=REVIEWER_HEADERS,
            json={
                "expected_revision": submitted.json()["revision"],
                "decision": "approved",
            },
        )

    assert draft.status_code == 200
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"
    assert reviewed.json()["observations"][0]["metric_id"] == "roa_percentage"


def test_admin_cannot_remove_own_admin_access(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.patch(
            "/admin/users/admin-user/access",
            headers=ADMIN_HEADERS,
            json={
                "role": "reviewer",
                "sme_ids": [],
            },
        )

    assert response.status_code == 409


def test_semantic_provider_check_reports_disabled_provider(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/system/providers/semantic/check",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "No intelligent semantic provider is configured."
    )


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


def test_sme_user_updates_draft_with_revision_check(
    tmp_path: Path,
) -> None:
    """Assigned SME users may edit drafts and receive a new revision."""

    with _client(tmp_path) as client:
        _create_sme(client)
        updated = client.patch(
            "/smes/sme_001",
            headers=SME_ONE_HEADERS,
            json={
                "expected_application_revision": 1,
                "legal_name": "EcoPack Circular Manufacturing LLC",
                "reason": "Registered legal name corrected",
            },
        )
        stale = client.patch(
            "/smes/sme_001",
            headers=SME_ONE_HEADERS,
            json={
                "expected_application_revision": 1,
                "sector": "Circular manufacturing",
            },
        )
        record = client.get(
            "/smes/sme_001/record",
            headers=SME_ONE_HEADERS,
        )

    assert updated.status_code == 200
    assert updated.json()["application"]["revision"] == 2
    assert (
        updated.json()["sme"]["legal_name"]
        == "EcoPack Circular Manufacturing LLC"
    )
    assert stale.status_code == 409
    assert (
        record.json()["sme"]["legal_name"]
        == "EcoPack Circular Manufacturing LLC"
    )


def test_approved_sme_cannot_be_silently_edited(
    tmp_path: Path,
) -> None:
    """Approved metadata requires a governed changes-requested transition."""

    with _client(tmp_path) as client:
        _create_sme(client)
        revision = 1
        for target in ("submitted", "under_review", "approved"):
            response = client.patch(
                "/smes/sme_001/application",
                headers=ADMIN_HEADERS,
                json={
                    "expected_revision": revision,
                    "target_status": target,
                },
            )
            revision = response.json()["revision"]

        update = client.patch(
            "/smes/sme_001",
            headers=ADMIN_HEADERS,
            json={
                "expected_application_revision": revision,
                "sector": "Changed after approval",
            },
        )

    assert update.status_code == 409


def test_new_sme_has_revision_checked_application_lifecycle(
    tmp_path: Path,
) -> None:
    """SME and reviewer actions should follow the governed state machine."""

    with _client(tmp_path) as client:
        _create_sme(client)
        draft = client.get(
            "/smes/sme_001/application",
            headers=SME_ONE_HEADERS,
        )
        submitted = client.patch(
            "/smes/sme_001/application",
            headers=SME_ONE_HEADERS,
            json={
                "expected_revision": 1,
                "target_status": "submitted",
            },
        )
        under_review = client.patch(
            "/smes/sme_001/application",
            headers=REVIEWER_HEADERS,
            json={
                "expected_revision": 2,
                "target_status": "under_review",
            },
        )
        stale = client.patch(
            "/smes/sme_001/application",
            headers=REVIEWER_HEADERS,
            json={
                "expected_revision": 2,
                "target_status": "approved",
            },
        )
        forbidden = client.patch(
            "/smes/sme_001/application",
            headers=SME_ONE_HEADERS,
            json={
                "expected_revision": 3,
                "target_status": "approved",
            },
        )

    assert draft.json()["status"] == "draft"
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["revision"] == 2
    assert under_review.json()["status"] == "under_review"
    assert under_review.json()["revision"] == 3
    assert stale.status_code == 409
    assert forbidden.status_code == 403


def test_application_cannot_bypass_profile_publication(
    tmp_path: Path,
) -> None:
    """Published status must only come from explicit profile publication."""

    with _client(tmp_path) as client:
        _create_sme(client)
        response = client.patch(
            "/smes/sme_001/application",
            headers=ADMIN_HEADERS,
            json={
                "expected_revision": 1,
                "target_status": "published",
            },
        )

    assert response.status_code == 403


def test_investor_and_expert_cannot_read_raw_sme_data(
    tmp_path: Path,
) -> None:
    """Published-profile roles must not cross the raw-record boundary."""

    with _client(tmp_path) as client:
        _create_sme(client)
        investor_sme = client.get(
            "/smes/sme_001",
            headers=INVESTOR_HEADERS,
        )
        investor_record = client.get(
            "/smes/sme_001/record",
            headers=INVESTOR_HEADERS,
        )
        expert_record = client.get(
            "/smes/sme_001/record",
            headers=EXPERT_HEADERS,
        )

    assert investor_sme.status_code == 403
    assert investor_record.status_code == 403
    assert expert_record.status_code == 403


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
    assert upload_result["application"]["revision"] == 2
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


def test_delete_document_removes_derived_data_and_storage(
    tmp_path: Path,
) -> None:
    """Document deletion should cascade and remove the private object."""

    content = b"Renewable energy share: 72 percent."

    with _client(tmp_path) as client:
        _create_sme(client)
        upload = client.post(
            "/smes/sme_001/documents",
            headers=SME_ONE_HEADERS,
            data={
                "document_type": "sustainability_report",
                "expected_application_revision": "1",
            },
            files={
                "file": ("report.txt", content, "text/plain"),
            },
        )
        document_id = upload.json()["document"]["document_id"]
        storage_key = upload.json()["storage_key"]
        processed = client.post(
            f"/smes/sme_001/documents/{document_id}/process",
            headers=SME_ONE_HEADERS,
        )
        deleted = client.request(
            "DELETE",
            f"/smes/sme_001/documents/{document_id}",
            headers=SME_ONE_HEADERS,
            json={
                "expected_application_revision": 2,
                "reason": "Incorrect source uploaded",
            },
        )
        record = client.get(
            "/smes/sme_001/record",
            headers=SME_ONE_HEADERS,
        )

    assert processed.status_code == 200
    assert processed.json()["evidence_items"]
    assert deleted.status_code == 200
    assert deleted.json()["application"]["revision"] == 3
    assert record.json()["documents"] == []
    assert record.json()["evidence_items"] == []
    assert not (tmp_path / "documents" / storage_key).exists()


def test_failed_document_delete_restores_storage_and_database(
    tmp_path: Path,
) -> None:
    """Cross-system deletion should compensate if storage reports failure."""

    storage = DeleteThenFailStorage(tmp_path / "documents")

    with _client(tmp_path, document_storage=storage) as client:
        _create_sme(client)
        upload = client.post(
            "/smes/sme_001/documents",
            headers=SME_ONE_HEADERS,
            data={
                "document_type": "sustainability_report",
                "expected_application_revision": "1",
            },
            files={
                "file": ("report.txt", b"Green evidence.", "text/plain"),
            },
        )
        document_id = upload.json()["document"]["document_id"]
        storage_key = upload.json()["storage_key"]
        deleted = client.request(
            "DELETE",
            f"/smes/sme_001/documents/{document_id}",
            headers=SME_ONE_HEADERS,
            json={
                "expected_application_revision": 2,
                "reason": "Testing compensation",
            },
        )
        record = client.get(
            "/smes/sme_001/record",
            headers=SME_ONE_HEADERS,
        )
        application = client.get(
            "/smes/sme_001/application",
            headers=SME_ONE_HEADERS,
        )

    assert deleted.status_code == 409
    assert [item["document_id"] for item in record.json()["documents"]] == [
        document_id
    ]
    assert application.json()["revision"] == 2
    assert (tmp_path / "documents" / storage_key).exists()


def test_admin_purges_sme_documents_and_storage(
    tmp_path: Path,
) -> None:
    """Admin purge should remove an SME and all private source objects."""

    with _client(tmp_path) as client:
        _create_sme(client)
        upload = client.post(
            "/smes/sme_001/documents",
            headers=ADMIN_HEADERS,
            data={
                "document_type": "sustainability_report",
                "expected_application_revision": "1",
            },
            files={"file": ("report.txt", b"Green evidence.", "text/plain")},
        )
        storage_key = upload.json()["storage_key"]
        deleted = client.request(
            "DELETE",
            "/smes/sme_001",
            headers=ADMIN_HEADERS,
            json={
                "expected_application_revision": 2,
                "reason": "Duplicate workspace",
            },
        )
        missing = client.get(
            "/smes/sme_001",
            headers=ADMIN_HEADERS,
        )

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert not (tmp_path / "documents" / storage_key).exists()


def test_admin_purge_tolerates_unreadable_legacy_storage(
    tmp_path: Path,
) -> None:
    storage = UnreadableLegacyStorage(tmp_path / "documents")
    with _client(tmp_path, storage) as client:
        _create_sme(client)
        upload = client.post(
            "/smes/sme_001/documents",
            headers=ADMIN_HEADERS,
            data={
                "document_type": "sustainability_report",
                "expected_application_revision": "1",
            },
            files={"file": ("legacy.txt", b"Old evidence.", "text/plain")},
        )
        deleted = client.request(
            "DELETE",
            "/smes/sme_001",
            headers=ADMIN_HEADERS,
            json={
                "expected_application_revision": upload.json()["application"]["revision"],
                "reason": "Legacy demo cleanup",
            },
        )

    assert deleted.status_code == 204


def test_admin_purge_removes_superseded_profile_rows(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _create_sme(client)
        with client.app.state.database.session() as session:
            session.execute(text(
                "create table sme_assessment_profiles ("
                "sme_id text primary key, profile_version integer not null, "
                "context_json text not null, responses_json text not null, "
                "approved_by text not null, created_at text, updated_at text)"
            ))
            session.execute(
                text(
                    "insert into sme_assessment_profiles "
                    "(sme_id, profile_version, context_json, responses_json, approved_by) "
                    "values (:sme_id, 1, '{}', '[]', 'legacy-reviewer')"
                ),
                {"sme_id": "sme_001"},
            )
            session.commit()

        deleted = client.request(
            "DELETE",
            "/smes/sme_001",
            headers=ADMIN_HEADERS,
            json={
                "expected_application_revision": 1,
                "reason": "Remove superseded profile",
            },
        )
        with client.app.state.database.session() as session:
            legacy_count = session.execute(
                text("select count(*) from sme_assessment_profiles")
            ).scalar_one()

    assert deleted.status_code == 204
    assert legacy_count == 0


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
