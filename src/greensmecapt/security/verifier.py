"""Supabase-compatible JWT verification."""

import os
from collections.abc import Mapping
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

from greensmecapt.security.models import (
    ApplicationRole,
    AuthPrincipal,
)


class AuthenticationError(ValueError):
    """Raised when an access token cannot be trusted."""


class TokenVerifier(Protocol):
    """Verify one bearer token."""

    def verify(self, token: str) -> AuthPrincipal:
        """Return a trusted application principal."""
        ...


class JWTVerifierConfiguration(BaseModel):
    """Configure asymmetric Supabase JWT verification."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    issuer: str = Field(min_length=1)
    audience: str = Field(
        default="authenticated",
        min_length=1,
    )
    jwks_url: str = Field(min_length=1)
    algorithms: tuple[str, ...] = Field(
        default=(
            "ES256",
            "RS256",
        ),
        min_length=1,
    )


class SupabaseJWTVerifier:
    """Verify Supabase tokens using public signing keys."""

    def __init__(
        self,
        configuration: JWTVerifierConfiguration,
    ) -> None:
        self._configuration = configuration
        self._jwks_client = PyJWKClient(
            configuration.jwks_url
        )

    def verify(self, token: str) -> AuthPrincipal:
        """Verify signature, expiry, issuer and application claims."""

        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")

            if algorithm not in self._configuration.algorithms:
                raise AuthenticationError(
                    "The token uses an unsupported algorithm."
                )

            signing_key = (
                self._jwks_client.get_signing_key_from_jwt(
                    token
                )
            )

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(
                    self._configuration.algorithms
                ),
                audience=self._configuration.audience,
                issuer=self._configuration.issuer,
                options={
                    "require": [
                        "aud",
                        "exp",
                        "iss",
                        "sub",
                    ]
                },
            )
        except AuthenticationError:
            raise
        except jwt.ExpiredSignatureError as error:
            raise AuthenticationError(
                "The access token has expired. Sign in again; if a fresh token "
                "fails immediately, verify the computer's UTC clock."
            ) from error
        except jwt.ImmatureSignatureError as error:
            raise AuthenticationError(
                "The access token is not valid yet. Verify the computer's UTC clock."
            ) from error
        except Exception as error:
            raise AuthenticationError(
                "The access token is invalid or expired."
            ) from error

        return _principal_from_claims(claims)


class DenyAllTokenVerifier:
    """Secure default used when authentication is unconfigured."""

    def verify(self, token: str) -> AuthPrincipal:
        """Reject every protected request."""

        raise AuthenticationError(
            "Authentication has not been configured."
        )


def verifier_from_environment() -> TokenVerifier:
    """Create Supabase verification from environment variables."""

    issuer = os.environ.get(
        "GREENSMECAPT_AUTH_ISSUER"
    )

    if not issuer:
        return DenyAllTokenVerifier()

    normalized_issuer = issuer.rstrip("/")
    jwks_url = os.environ.get(
        "GREENSMECAPT_AUTH_JWKS_URL",
        (
            f"{normalized_issuer}/"
            ".well-known/jwks.json"
        ),
    )
    audience = os.environ.get(
        "GREENSMECAPT_AUTH_AUDIENCE",
        "authenticated",
    )

    return SupabaseJWTVerifier(
        JWTVerifierConfiguration(
            issuer=normalized_issuer,
            audience=audience,
            jwks_url=jwks_url,
        )
    )


def _principal_from_claims(
    claims: Mapping[str, Any],
) -> AuthPrincipal:
    """Build permissions from trusted token claims."""

    subject = claims.get("sub")

    if not isinstance(subject, str) or not subject.strip():
        raise AuthenticationError(
            "The token contains no valid subject."
        )

    app_metadata = claims.get("app_metadata")

    if not isinstance(app_metadata, Mapping):
        raise AuthenticationError(
            "The token contains no application metadata."
        )

    raw_role = app_metadata.get(
        "greensmecapt_role"
    )

    try:
        role = ApplicationRole(raw_role)
    except (TypeError, ValueError) as error:
        raise AuthenticationError(
            "The token contains no valid application role."
        ) from error

    raw_sme_ids = app_metadata.get("sme_ids", [])

    if (
        not isinstance(raw_sme_ids, list)
        or not all(
            isinstance(item, str) and item.strip()
            for item in raw_sme_ids
        )
    ):
        raise AuthenticationError(
            "The token contains invalid SME assignments."
        )

    email = claims.get("email")

    if (
        email is not None
        and (
            not isinstance(email, str)
            or not email.strip()
        )
    ):
        raise AuthenticationError(
            "The token contains an invalid email claim."
        )

    normalized_sme_ids = tuple(
        sorted(
            {
                item.strip()
                for item in raw_sme_ids
            }
        )
    )

    try:
        return AuthPrincipal(
            user_id=subject,
            role=role,
            email=email,
            sme_ids=normalized_sme_ids,
        )
    except ValidationError as error:
        raise AuthenticationError(
            "The token contains invalid application claims."
        ) from error
