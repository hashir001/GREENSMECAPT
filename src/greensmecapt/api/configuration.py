"""Validate API deployment configuration."""

import os
from collections.abc import Mapping
from urllib.parse import urlsplit


class DeploymentConfigurationError(ValueError):
    """Raised when a production runtime would start incompletely."""


def validate_deployment_environment(
    environment: Mapping[str, str] | None = None,
) -> None:
    """Refuse insecure production fallbacks and placeholder settings."""

    configured = environment if environment is not None else os.environ
    mode = configured.get("GREENSMECAPT_ENV", "development").strip().casefold()

    if mode not in {"development", "test", "production"}:
        raise DeploymentConfigurationError(
            "GREENSMECAPT_ENV must be development, test or production."
        )

    if mode != "production":
        return

    required = (
        "GREENSMECAPT_DATABASE_URL",
        "GREENSMECAPT_AUTH_ISSUER",
        "GREENSMECAPT_SUPABASE_URL",
        "GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY",
        "GREENSMECAPT_FRONTEND_URL",
        "GREENSMECAPT_CORS_ORIGINS",
    )
    missing = tuple(name for name in required if not configured.get(name))

    if missing:
        raise DeploymentConfigurationError(
            "Production configuration is missing: " + ", ".join(missing) + "."
        )

    database_url = configured["GREENSMECAPT_DATABASE_URL"]

    if database_url.startswith("sqlite"):
        raise DeploymentConfigurationError(
            "Production must use durable PostgreSQL storage, not SQLite."
        )

    if configured.get("GREENSMECAPT_STORAGE_BACKEND", "local") != "supabase":
        raise DeploymentConfigurationError(
            "Production document storage must explicitly use Supabase."
        )

    placeholder_markers = (
        "replace-with",
        "project_ref",
        "db_password",
        "your-project",
    )
    placeholder_names = tuple(
        name
        for name in required
        if any(
            marker in configured[name].casefold()
            for marker in placeholder_markers
        )
    )

    if placeholder_names:
        raise DeploymentConfigurationError(
            "Production configuration still contains placeholders: "
            + ", ".join(placeholder_names)
            + "."
        )

    cors_origins = _cors_origins(configured)

    for origin in cors_origins:
        if urlsplit(origin).scheme != "https":
            raise DeploymentConfigurationError(
                "Production CORS origins must use HTTPS."
            )

    frontend_url = configured["GREENSMECAPT_FRONTEND_URL"].rstrip("/")

    if urlsplit(frontend_url).scheme != "https":
        raise DeploymentConfigurationError(
            "Production frontend URL must use HTTPS."
        )

    if frontend_url not in cors_origins:
        raise DeploymentConfigurationError(
            "Production frontend URL must be an allowed CORS origin."
        )

    _validate_provider_key(configured, "SEMANTIC")
    _validate_provider_key(configured, "VISUAL")
    _validate_google_pipeline(configured)


def cors_origins_from_environment() -> tuple[str, ...]:
    """Return unique, explicit browser origins for CORS."""

    return _cors_origins(os.environ)


def _cors_origins(environment: Mapping[str, str]) -> tuple[str, ...]:
    raw_origins = environment.get(
        "GREENSMECAPT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    origins = tuple(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in raw_origins.split(",")
            if origin.strip()
        )
    )

    for origin in origins:
        parsed = urlsplit(origin)

        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                f"Invalid GREENSMECAPT CORS origin: {origin!r}."
            )

    return origins


def _validate_provider_key(
    environment: Mapping[str, str],
    provider_kind: str,
) -> None:
    """Require a real key whenever a production remote provider names one."""

    prefix = f"GREENSMECAPT_{provider_kind}"
    endpoint = environment.get(f"{prefix}_ENDPOINT")

    if endpoint is None:
        return

    hostname = urlsplit(endpoint).hostname

    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return

    if environment.get(f"{prefix}_ALLOW_REMOTE", "false").casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise DeploymentConfigurationError(
            f"{provider_kind.title()} remote transmission is not approved."
        )

    key_variable = environment.get(f"{prefix}_API_KEY_ENV")

    if not key_variable or not environment.get(key_variable):
        raise DeploymentConfigurationError(
            f"{provider_kind.title()} provider key is not available in its "
            "configured environment variable."
        )


def _validate_google_pipeline(environment: Mapping[str, str]) -> None:
    """Fail before startup when the selected Google pipeline is incomplete."""

    if (
        environment.get("GREENSMECAPT_STRUCTURED_OCR_PROVIDER", "")
        .strip()
        .casefold()
        == "google_document_ai"
    ):
        required = (
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_LOCATION",
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_OCR_PROCESSOR_ID",
        )
        missing = tuple(name for name in required if not environment.get(name))
        if missing:
            raise DeploymentConfigurationError(
                "Google Document AI configuration is missing: "
                + ", ".join(missing)
                + "."
            )

    if (
        environment.get("GREENSMECAPT_SEMANTIC_PROVIDER", "")
        .strip()
        .casefold()
        == "vertex_gemini"
    ):
        project_id = environment.get("GREENSMECAPT_VERTEX_PROJECT_ID") or environment.get(
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID"
        )
        if not project_id:
            raise DeploymentConfigurationError(
                "Vertex Gemini requires GREENSMECAPT_VERTEX_PROJECT_ID or "
                "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID."
            )
        if environment.get("GREENSMECAPT_SEMANTIC_ALLOW_REMOTE", "false").casefold() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise DeploymentConfigurationError(
                "Vertex Gemini remote transmission must be explicitly approved."
            )

