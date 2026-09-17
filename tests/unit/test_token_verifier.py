"""Tests for trusted JWT verification and claim conversion."""

from typing import Any

import jwt
import pytest

import greensmecapt.security.verifier as verifier_module
from greensmecapt.security import (
    ApplicationRole,
    AuthenticationError,
    DenyAllTokenVerifier,
    JWTVerifierConfiguration,
    SupabaseJWTVerifier,
    verifier_from_environment,
)
from greensmecapt.security.verifier import (
    _principal_from_claims,
)


class _FakeSigningKey:
    """Provide a predictable verification key."""

    key = "public-key"


class _FakeJwksClient:
    """Return a signing key without making a network request."""

    def get_signing_key_from_jwt(
        self,
        token: str,
    ) -> _FakeSigningKey:
        assert token == "signed-token"

        return _FakeSigningKey()


def _configuration() -> JWTVerifierConfiguration:
    return JWTVerifierConfiguration(
        issuer="https://example.supabase.co/auth/v1",
        audience="authenticated",
        jwks_url=(
            "https://example.supabase.co/auth/v1/"
            ".well-known/jwks.json"
        ),
    )


def _trusted_claims() -> dict[str, Any]:
    return {
        "sub": "user_001",
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": 4_000_000_000,
        "email": "owner@example.com",
        "app_metadata": {
            "greensmecapt_role": "sme_user",
            "sme_ids": ["sme_001"],
        },
    }


def test_build_principal_from_trusted_claims() -> None:
    """Trusted metadata should become application permissions."""

    principal = _principal_from_claims(
        {
            "sub": "user_001",
            "email": "owner@example.com",
            "app_metadata": {
                "greensmecapt_role": "sme_user",
                "sme_ids": [
                    "sme_002",
                    " sme_001 ",
                    "sme_001",
                ],
            },
        }
    )

    assert principal.user_id == "user_001"
    assert principal.role is ApplicationRole.SME_USER
    assert principal.email == "owner@example.com"
    assert principal.sme_ids == (
        "sme_001",
        "sme_002",
    )


def test_reject_missing_application_metadata() -> None:
    """Tokens without server-controlled metadata are unusable."""

    with pytest.raises(AuthenticationError):
        _principal_from_claims(
            {
                "sub": "user_001",
            }
        )


def test_reject_unknown_application_role() -> None:
    """Unknown roles must never receive implicit permissions."""

    with pytest.raises(AuthenticationError):
        _principal_from_claims(
            {
                "sub": "user_001",
                "app_metadata": {
                    "greensmecapt_role": "superuser",
                },
            }
        )


def test_reject_invalid_sme_assignments() -> None:
    """SME assignments must be nonblank strings."""

    with pytest.raises(AuthenticationError):
        _principal_from_claims(
            {
                "sub": "user_001",
                "app_metadata": {
                    "greensmecapt_role": "sme_user",
                    "sme_ids": [
                        "sme_001",
                        "",
                    ],
                },
            }
        )


def test_reject_blank_email_claim() -> None:
    """Malformed optional claims must fail authentication."""

    with pytest.raises(AuthenticationError):
        _principal_from_claims(
            {
                "sub": "user_001",
                "email": "   ",
                "app_metadata": {
                    "greensmecapt_role": "investor",
                },
            }
        )


def test_unconfigured_verifier_denies_access() -> None:
    """An unconfigured deployment must fail closed."""

    with pytest.raises(AuthenticationError):
        DenyAllTokenVerifier().verify("any-token")


def test_environment_without_issuer_denies_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing deployment configuration must select deny-all."""

    monkeypatch.delenv(
        "GREENSMECAPT_AUTH_ISSUER",
        raising=False,
    )

    token_verifier = verifier_from_environment()

    assert isinstance(
        token_verifier,
        DenyAllTokenVerifier,
    )


def test_verify_signed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification should constrain algorithm and JWT claims."""

    observed: dict[str, object] = {}

    def fake_decode(
        token: str,
        key: object,
        *,
        algorithms: list[str],
        audience: str,
        issuer: str,
        options: dict[str, object],
    ) -> dict[str, Any]:
        observed.update(
            {
                "token": token,
                "key": key,
                "algorithms": algorithms,
                "audience": audience,
                "issuer": issuer,
                "options": options,
            }
        )

        return _trusted_claims()

    monkeypatch.setattr(
        verifier_module.jwt,
        "get_unverified_header",
        lambda token: {"alg": "RS256"},
    )
    monkeypatch.setattr(
        verifier_module.jwt,
        "decode",
        fake_decode,
    )

    token_verifier = SupabaseJWTVerifier(
        _configuration()
    )
    token_verifier._jwks_client = _FakeJwksClient()

    principal = token_verifier.verify("signed-token")

    assert principal.user_id == "user_001"
    assert principal.role is ApplicationRole.SME_USER
    assert observed["token"] == "signed-token"
    assert observed["key"] == "public-key"
    assert observed["algorithms"] == [
        "ES256",
        "RS256",
    ]
    assert observed["audience"] == "authenticated"
    assert observed["issuer"] == (
        "https://example.supabase.co/auth/v1"
    )
    assert observed["options"] == {
        "require": [
            "aud",
            "exp",
            "iss",
            "sub",
        ]
    }


def test_reject_unsupported_signing_algorithm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared-secret algorithms must not bypass configuration."""

    monkeypatch.setattr(
        verifier_module.jwt,
        "get_unverified_header",
        lambda token: {"alg": "HS256"},
    )

    token_verifier = SupabaseJWTVerifier(
        _configuration()
    )

    with pytest.raises(
        AuthenticationError,
        match="unsupported algorithm",
    ):
        token_verifier.verify("signed-token")


def test_convert_signature_failure_to_authentication_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWT-library failures must become controlled failures."""

    monkeypatch.setattr(
        verifier_module.jwt,
        "get_unverified_header",
        lambda token: {"alg": "RS256"},
    )

    def reject_decode(*args, **kwargs):
        raise jwt.InvalidTokenError(
            "Invalid signature."
        )

    monkeypatch.setattr(
        verifier_module.jwt,
        "decode",
        reject_decode,
    )

    token_verifier = SupabaseJWTVerifier(
        _configuration()
    )
    token_verifier._jwks_client = _FakeJwksClient()

    with pytest.raises(
        AuthenticationError,
        match="invalid or expired",
    ):
        token_verifier.verify("signed-token")