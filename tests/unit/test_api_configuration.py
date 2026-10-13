"""Tests for safe API deployment configuration."""

import pytest

from greensmecapt.api.configuration import (
    DeploymentConfigurationError,
    cors_origins_from_environment,
    validate_deployment_environment,
)


def _production_environment() -> dict[str, str]:
    return {
        "GREENSMECAPT_ENV": "production",
        "GREENSMECAPT_DATABASE_URL": (
            "postgresql://user:secret@db.example.com:5432/greensmecapt"
        ),
        "GREENSMECAPT_AUTH_ISSUER": "https://project.supabase.co/auth/v1",
        "GREENSMECAPT_SUPABASE_URL": "https://project.supabase.co",
        "GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY": "server-secret",
        "GREENSMECAPT_STORAGE_BACKEND": "supabase",
        "GREENSMECAPT_FRONTEND_URL": "https://app.example.com",
        "GREENSMECAPT_CORS_ORIGINS": "https://app.example.com",
    }


def test_parse_unique_explicit_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GREENSMECAPT_CORS_ORIGINS",
        (
            "https://app.example.com/, "
            "https://review.example.com,"
            "https://app.example.com"
        ),
    )

    assert cors_origins_from_environment() == (
        "https://app.example.com",
        "https://review.example.com",
    )


@pytest.mark.parametrize(
    "origin",
    (
        "*",
        "javascript:alert(1)",
        "https://app.example.com/path",
    ),
)
def test_reject_unsafe_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
) -> None:
    monkeypatch.setenv(
        "GREENSMECAPT_CORS_ORIGINS",
        origin,
    )

    with pytest.raises(ValueError):
        cors_origins_from_environment()


def test_accept_complete_production_environment() -> None:
    validate_deployment_environment(_production_environment())


def test_reject_production_sqlite_fallback() -> None:
    environment = _production_environment()
    environment["GREENSMECAPT_DATABASE_URL"] = "sqlite:///greensmecapt.db"

    with pytest.raises(DeploymentConfigurationError, match="PostgreSQL"):
        validate_deployment_environment(environment)


def test_reject_production_placeholder_secret() -> None:
    environment = _production_environment()
    environment["GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY"] = (
        "replace-with-server-only-service-role-key"
    )

    with pytest.raises(DeploymentConfigurationError, match="placeholders"):
        validate_deployment_environment(environment)


def test_reject_non_https_production_origin() -> None:
    environment = _production_environment()
    environment["GREENSMECAPT_CORS_ORIGINS"] = "http://app.example.com"

    with pytest.raises(DeploymentConfigurationError, match="HTTPS"):
        validate_deployment_environment(environment)


def test_require_frontend_url_in_cors_allowlist() -> None:
    environment = _production_environment()
    environment["GREENSMECAPT_FRONTEND_URL"] = "https://other.example.com"

    with pytest.raises(DeploymentConfigurationError, match="CORS origin"):
        validate_deployment_environment(environment)


def test_require_remote_provider_key_in_production() -> None:
    environment = _production_environment()
    environment.update(
        {
            "GREENSMECAPT_SEMANTIC_ENDPOINT": (
                "https://api.example.com/v1/chat/completions"
            ),
            "GREENSMECAPT_SEMANTIC_ALLOW_REMOTE": "true",
            "GREENSMECAPT_SEMANTIC_API_KEY_ENV": "PROVIDER_KEY",
        }
    )

    with pytest.raises(DeploymentConfigurationError, match="provider key"):
        validate_deployment_environment(environment)


def test_require_selected_google_document_ai_configuration() -> None:
    environment = _production_environment()
    environment["GREENSMECAPT_STRUCTURED_OCR_PROVIDER"] = "google_document_ai"

    with pytest.raises(DeploymentConfigurationError, match="Document AI"):
        validate_deployment_environment(environment)


def test_accept_vertex_pipeline_with_adc_configuration() -> None:
    environment = _production_environment()
    environment.update(
        {
            "GREENSMECAPT_STRUCTURED_OCR_PROVIDER": "google_document_ai",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID": "greensmecapt",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_LOCATION": "eu",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_OCR_PROCESSOR_ID": "processor-1",
            "GREENSMECAPT_SEMANTIC_PROVIDER": "vertex_gemini",
            "GREENSMECAPT_SEMANTIC_ALLOW_REMOTE": "true",
        }
    )

    validate_deployment_environment(environment)

