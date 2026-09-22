"""Tests for server-side Supabase identity administration."""

import json

import pytest

from greensmecapt.security import (
    ApplicationRole,
    IdentityAdministrationError,
    IdentityResponse,
    SupabaseIdentityAdmin,
    SupabaseIdentityAdminConfiguration,
)


class FakeTransport:
    """Capture requests and return queued provider responses."""

    def __init__(self, *responses: IdentityResponse) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def request(self, **kwargs) -> IdentityResponse:
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _response(payload: object, status: int = 200) -> IdentityResponse:
    return IdentityResponse(
        status=status,
        body=json.dumps(payload).encode(),
    )


def _admin(transport: FakeTransport) -> SupabaseIdentityAdmin:
    return SupabaseIdentityAdmin(
        SupabaseIdentityAdminConfiguration(
            project_url="https://project.supabase.co",
            service_role_key="server-secret",
            frontend_url="https://app.example.com",
        ),
        transport=transport,
    )


def test_list_users_normalizes_application_access() -> None:
    transport = FakeTransport(
        _response(
            {
                "users": [
                    {
                        "id": "user_002",
                        "email": "owner@example.com",
                        "app_metadata": {
                            "greensmecapt_role": "sme_user",
                            "sme_ids": ["sme_002", "sme_001"],
                        },
                    },
                    {
                        "id": "user_001",
                        "email": "admin@example.com",
                        "app_metadata": {
                            "greensmecapt_role": "admin",
                        },
                    },
                ]
            }
        )
    )

    users = _admin(transport).list_users()

    assert [user.email for user in users] == [
        "admin@example.com",
        "owner@example.com",
    ]
    assert users[1].role is ApplicationRole.SME_USER
    assert users[1].sme_ids == ("sme_001", "sme_002")
    assert transport.requests[0]["url"] == (
        "https://project.supabase.co/auth/v1/admin/users"
        "?page=1&per_page=1000"
    )


def test_invite_then_assign_access_claims() -> None:
    transport = FakeTransport(
        _response(
            {
                "id": "user_001",
                "email": "owner@example.com",
            },
            status=201,
        ),
        _response(
            {
                "id": "user_001",
                "email": "owner@example.com",
                "app_metadata": {
                    "greensmecapt_role": "sme_user",
                    "sme_ids": ["sme_001"],
                },
            }
        ),
    )

    user = _admin(transport).invite_user(
        email="Owner@Example.com",
        role=ApplicationRole.SME_USER,
        sme_ids=("sme_001",),
    )

    assert user.role is ApplicationRole.SME_USER
    assert len(transport.requests) == 2
    assert "redirect_to=https%3A%2F%2Fapp.example.com%2Fsettings" in str(
        transport.requests[0]["url"]
    )
    update_body = json.loads(transport.requests[1]["content"])
    assert update_body["app_metadata"] == {
        "greensmecapt_role": "sme_user",
        "sme_ids": ["sme_001"],
    }


def test_reject_sme_user_without_assignment() -> None:
    with pytest.raises(
        IdentityAdministrationError,
        match="at least one SME assignment",
    ):
        _admin(FakeTransport()).update_access(
            user_id="user_001",
            role=ApplicationRole.SME_USER,
            sme_ids=(),
        )


def test_reject_provider_error_without_leaking_secret() -> None:
    transport = FakeTransport(
        _response(
            {"message": "User already registered"},
            status=422,
        )
    )

    with pytest.raises(
        IdentityAdministrationError,
        match="User already registered",
    ) as captured:
        _admin(transport).invite_user(
            email="owner@example.com",
            role=ApplicationRole.REVIEWER,
            sme_ids=(),
        )

    assert "server-secret" not in str(captured.value)
