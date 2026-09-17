"""Authentication and authorization for GREENSMECAPT."""

from greensmecapt.security.dependencies import (
    get_current_principal,
    require_roles,
)
from greensmecapt.security.models import (
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
    "ApplicationRole",
    "AuthPrincipal",
    "AuthenticationError",
    "DenyAllTokenVerifier",
    "JWTVerifierConfiguration",
    "SupabaseJWTVerifier",
    "TokenVerifier",
    "get_current_principal",
    "require_roles",
    "verifier_from_environment",
]