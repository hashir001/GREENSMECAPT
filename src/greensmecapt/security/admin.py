"""Server-side Supabase identity administration."""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

from greensmecapt.security.models import ApplicationRole


class IdentityAdministrationError(ValueError):
    """Raised when identity administration cannot complete safely."""


class ManagedUser(BaseModel):
    """Expose only the identity fields needed by platform administrators."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    user_id: str = Field(min_length=1)
    email: str = Field(min_length=3)
    role: ApplicationRole | None = None
    sme_ids: tuple[str, ...] = ()
    invited_at: str | None = None
    last_sign_in_at: str | None = None


class IdentityAdmin(Protocol):
    """Administer authentication users without exposing provider secrets."""

    @property
    def configured(self) -> bool:
        """Report whether a real identity administrator is available."""
        ...

    def list_users(self) -> tuple[ManagedUser, ...]:
        """Return application users."""
        ...

    def invite_user(
        self,
        *,
        email: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        """Invite a user and attach server-controlled access claims."""
        ...

    def update_access(
        self,
        *,
        user_id: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        """Replace one user's application role and SME assignments."""
        ...


class DisabledIdentityAdmin:
    """Fail closed when Supabase administration is not configured."""

    @property
    def configured(self) -> bool:
        return False

    def list_users(self) -> tuple[ManagedUser, ...]:
        raise IdentityAdministrationError(
            "Supabase identity administration is not configured."
        )

    def invite_user(
        self,
        *,
        email: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        del email, role, sme_ids
        raise IdentityAdministrationError(
            "Supabase identity administration is not configured."
        )

    def update_access(
        self,
        *,
        user_id: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        del user_id, role, sme_ids
        raise IdentityAdministrationError(
            "Supabase identity administration is not configured."
        )


@dataclass(frozen=True)
class IdentityResponse:
    """Contain the bounded HTTP response used by the provider adapter."""

    status: int
    body: bytes


class IdentityTransport(Protocol):
    """Send one authenticated Supabase Auth request."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_seconds: float,
    ) -> IdentityResponse:
        """Return status and body without leaking credentials."""
        ...


class UrllibIdentityTransport:
    """Use the Python standard library for identity-provider requests."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_seconds: float,
    ) -> IdentityResponse:
        request = Request(
            url=url,
            data=content,
            headers=dict(headers),
            method=method,
        )

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return IdentityResponse(
                    status=response.status,
                    body=response.read(),
                )
        except HTTPError as error:
            return IdentityResponse(
                status=error.code,
                body=error.read(),
            )
        except (URLError, TimeoutError, OSError) as error:
            raise IdentityAdministrationError(
                "Supabase Auth could not be reached."
            ) from error


@dataclass(frozen=True)
class SupabaseIdentityAdminConfiguration:
    """Configure server-only Supabase Auth administration."""

    project_url: str
    service_role_key: str
    frontend_url: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        project_url = self.project_url.rstrip("/")
        frontend_url = self.frontend_url.rstrip("/")

        if not project_url.startswith(("http://", "https://")):
            raise ValueError("Supabase project URL must be HTTP or HTTPS.")

        if not frontend_url.startswith(("http://", "https://")):
            raise ValueError("Frontend URL must be HTTP or HTTPS.")

        if not self.service_role_key.strip():
            raise ValueError("Supabase service-role key must not be blank.")

        if self.timeout_seconds <= 0:
            raise ValueError("Identity timeout must be positive.")

        object.__setattr__(self, "project_url", project_url)
        object.__setattr__(self, "frontend_url", frontend_url)


class SupabaseIdentityAdmin:
    """Manage users through Supabase's server-only Auth Admin API."""

    def __init__(
        self,
        configuration: SupabaseIdentityAdminConfiguration,
        *,
        transport: IdentityTransport | None = None,
    ) -> None:
        self._configuration = configuration
        self._transport = transport or UrllibIdentityTransport()

    @property
    def configured(self) -> bool:
        return True

    def list_users(self) -> tuple[ManagedUser, ...]:
        payload = self._request(
            method="GET",
            path="/auth/v1/admin/users?page=1&per_page=1000",
            expected_statuses={200},
        )
        users = payload.get("users")

        if not isinstance(users, list):
            raise IdentityAdministrationError(
                "Supabase returned an invalid user list."
            )

        return tuple(
            sorted(
                (_managed_user(item) for item in users),
                key=lambda item: (item.email.casefold(), item.user_id),
            )
        )

    def invite_user(
        self,
        *,
        email: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        normalized_sme_ids = _validate_access(role, sme_ids)
        query = urlencode(
            {
                "redirect_to": (
                    f"{self._configuration.frontend_url}/settings"
                )
            }
        )
        invited = self._request(
            method="POST",
            path=f"/auth/v1/invite?{query}",
            body={"email": email.strip().casefold()},
            expected_statuses={200, 201},
        )
        user_id = invited.get("id")

        if not isinstance(user_id, str) or not user_id.strip():
            raise IdentityAdministrationError(
                "Supabase invitation returned no user identifier."
            )

        return self.update_access(
            user_id=user_id,
            role=role,
            sme_ids=normalized_sme_ids,
        )

    def update_access(
        self,
        *,
        user_id: str,
        role: ApplicationRole,
        sme_ids: tuple[str, ...],
    ) -> ManagedUser:
        normalized_sme_ids = _validate_access(role, sme_ids)
        payload = self._request(
            method="PUT",
            path=(
                "/auth/v1/admin/users/"
                + quote(user_id.strip(), safe="")
            ),
            body={
                "app_metadata": {
                    "greensmecapt_role": role.value,
                    "sme_ids": list(normalized_sme_ids),
                }
            },
            expected_statuses={200},
        )
        return _managed_user(payload)

    def _request(
        self,
        *,
        method: str,
        path: str,
        expected_statuses: set[int],
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        configuration = self._configuration
        content = (
            json.dumps(body, separators=(",", ":")).encode()
            if body is not None
            else None
        )
        response = self._transport.request(
            method=method,
            url=f"{configuration.project_url}{path}",
            headers={
                "apikey": configuration.service_role_key,
                "Authorization": (
                    f"Bearer {configuration.service_role_key}"
                ),
                "Content-Type": "application/json",
            },
            content=content,
            timeout_seconds=configuration.timeout_seconds,
        )

        if response.status not in expected_statuses:
            raise IdentityAdministrationError(
                _provider_error(response.body)
            )

        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IdentityAdministrationError(
                "Supabase returned an invalid identity response."
            ) from error

        if not isinstance(payload, dict):
            raise IdentityAdministrationError(
                "Supabase returned an invalid identity response."
            )

        return payload


def identity_admin_from_environment() -> IdentityAdmin:
    """Build identity administration from existing Supabase secrets."""

    project_url = os.environ.get("GREENSMECAPT_SUPABASE_URL")
    service_role_key = os.environ.get(
        "GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY"
    )
    frontend_url = os.environ.get("GREENSMECAPT_FRONTEND_URL")

    if not project_url or not service_role_key or not frontend_url:
        return DisabledIdentityAdmin()

    return SupabaseIdentityAdmin(
        SupabaseIdentityAdminConfiguration(
            project_url=project_url,
            service_role_key=service_role_key,
            frontend_url=frontend_url,
        )
    )


def _validate_access(
    role: ApplicationRole,
    sme_ids: tuple[str, ...],
) -> tuple[str, ...]:
    normalized = tuple(
        sorted({item.strip() for item in sme_ids if item.strip()})
    )

    if role is ApplicationRole.SME_USER and not normalized:
        raise IdentityAdministrationError(
            "SME users require at least one SME assignment."
        )

    if role is not ApplicationRole.SME_USER and normalized:
        raise IdentityAdministrationError(
            "Only SME users may receive SME-specific assignments."
        )

    return normalized


def _managed_user(payload: object) -> ManagedUser:
    if not isinstance(payload, Mapping):
        raise IdentityAdministrationError(
            "Supabase returned an invalid user record."
        )

    user_id = payload.get("id")
    email = payload.get("email")
    metadata = payload.get("app_metadata")

    if not isinstance(user_id, str) or not isinstance(email, str):
        raise IdentityAdministrationError(
            "Supabase returned an incomplete user record."
        )

    role: ApplicationRole | None = None
    sme_ids: tuple[str, ...] = ()

    if isinstance(metadata, Mapping):
        raw_role = metadata.get("greensmecapt_role")

        if isinstance(raw_role, str):
            try:
                role = ApplicationRole(raw_role)
            except ValueError:
                role = None

        raw_sme_ids = metadata.get("sme_ids")

        if isinstance(raw_sme_ids, list):
            sme_ids = tuple(
                sorted(
                    {
                        item.strip()
                        for item in raw_sme_ids
                        if isinstance(item, str) and item.strip()
                    }
                )
            )

    return ManagedUser(
        user_id=user_id,
        email=email,
        role=role,
        sme_ids=sme_ids,
        invited_at=_optional_string(payload.get("invited_at")),
        last_sign_in_at=_optional_string(payload.get("last_sign_in_at")),
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _provider_error(body: bytes) -> str:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "Supabase rejected the identity operation."

    if isinstance(payload, Mapping):
        for key in ("msg", "message", "error_description", "error"):
            value = payload.get(key)

            if isinstance(value, str) and value.strip():
                return f"Supabase rejected the identity operation: {value}"

    return "Supabase rejected the identity operation."
