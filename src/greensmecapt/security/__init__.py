"""Authentication and authorization for GREENSMECAPT."""

from greensmecapt.security.admin import (
    DisabledIdentityAdmin,
    IdentityAdmin,
    IdentityAdministrationError,
    IdentityResponse,
    ManagedUser,
    SupabaseIdentityAdmin,
    SupabaseIdentityAdminConfiguration,
    identity_admin_from_environment,
)
from greensmecapt.security.dependencies import (
    get_current_principal,
    require_permission,
    require_roles,
    require_sme_permission,
)
from greensmecapt.security.models import (
    ApplicationPermission,
    ApplicationRole,
    AuthPrincipal,
)
from greensmecapt.security.verifier import (
    AuthenticationError,
    DenyAllTokenVerifier,
    JWTVerifierConfiguration,
    SupabaseJWTVerifier,
    TokenVerifier,
    verifier_from_environment,
)

__all__ = [
    "ApplicationPermission",
    "ApplicationRole",
    "AuthPrincipal",
    "AuthenticationError",
    "DenyAllTokenVerifier",
    "DisabledIdentityAdmin",
    "IdentityAdmin",
    "IdentityAdministrationError",
    "IdentityResponse",
    "JWTVerifierConfiguration",
    "ManagedUser",
    "SupabaseIdentityAdmin",
    "SupabaseIdentityAdminConfiguration",
    "SupabaseJWTVerifier",
    "TokenVerifier",
    "get_current_principal",
    "identity_admin_from_environment",
    "require_permission",
    "require_roles",
    "require_sme_permission",
    "verifier_from_environment",
]
