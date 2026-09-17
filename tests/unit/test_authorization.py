"""Tests for role and SME authorization."""

from greensmecapt.security import (
    ApplicationRole,
    AuthPrincipal,
)


def test_admin_can_access_every_sme() -> None:
    principal = AuthPrincipal(
        user_id="admin_001",
        role=ApplicationRole.ADMIN,
    )

    assert principal.can_access_sme("sme_anything")


def test_investor_can_access_every_sme() -> None:
    principal = AuthPrincipal(
        user_id="investor_001",
        role=ApplicationRole.INVESTOR,
    )

    assert principal.can_access_sme("sme_001")


def test_sme_user_can_access_assigned_sme() -> None:
    principal = AuthPrincipal(
        user_id="user_001",
        role=ApplicationRole.SME_USER,
        sme_ids=("sme_001",),
    )

    assert principal.can_access_sme("sme_001")
    assert not principal.can_access_sme("sme_002")