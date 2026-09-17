"""Authentication and authorization models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ApplicationRole(StrEnum):
    """Describe GREENSMECAPT application permissions."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    INVESTOR = "investor"
    SME_USER = "sme_user"


class AuthPrincipal(BaseModel):
    """Represent one authenticated application user."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    user_id: str = Field(min_length=1)
    role: ApplicationRole
    email: str | None = Field(default=None, min_length=1)
    sme_ids: tuple[str, ...] = ()

    def can_access_sme(self, sme_id: str) -> bool:
        """Report whether the principal may read one SME."""

        if self.role in {
            ApplicationRole.ADMIN,
            ApplicationRole.REVIEWER,
            ApplicationRole.INVESTOR,
        }:
            return True

        return sme_id in self.sme_ids