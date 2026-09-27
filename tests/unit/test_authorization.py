"""Tests for role and SME authorization."""

from greensmecapt.security import (
    ApplicationPermission,
    ApplicationRole,
    AuthPrincipal,
)


def test_admin_can_access_every_sme() -> None:
    principal = AuthPrincipal(
        user_id="admin_001",
        role=ApplicationRole.ADMIN,
    )

    assert principal.can_access_sme("sme_anything")


def test_investor_can_only_access_published_profiles() -> None:
    principal = AuthPrincipal(
        user_id="investor_001",
        role=ApplicationRole.INVESTOR,
    )

    assert not principal.can_access_sme("sme_001")
    assert principal.has_permission(
        ApplicationPermission.VIEW_PUBLISHED_PROFILES
    )


def test_expert_is_isolated_to_expert_studies() -> None:
    principal = AuthPrincipal(
        user_id="expert_001",
        role=ApplicationRole.EXPERT,
    )

    assert not principal.can_access_sme("sme_001")
    assert principal.has_permission(
        ApplicationPermission.COMPLETE_EXPERT_SURVEY
    )
    assert not principal.has_permission(
        ApplicationPermission.RUN_ASSESSMENTS
    )


def test_sme_user_can_access_assigned_sme() -> None:
    principal = AuthPrincipal(
        user_id="user_001",
        role=ApplicationRole.SME_USER,
        sme_ids=("sme_001",),
    )

    assert principal.can_access_sme("sme_001")
    assert not principal.can_access_sme("sme_002")
    assert principal.has_permission(
        ApplicationPermission.EDIT_SME,
        sme_id="sme_001",
    )
    assert not principal.has_permission(
        ApplicationPermission.EDIT_SME,
        sme_id="sme_002",
    )
    assert not principal.has_permission(
        ApplicationPermission.DELETE_SME,
        sme_id="sme_001",
    )
