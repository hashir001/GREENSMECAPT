"""Authentication, authorization and capability models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ApplicationRole(StrEnum):
    """Describe GREENSMECAPT application roles."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    EXPERT = "expert"
    INVESTOR = "investor"
    SME_USER = "sme_user"


class ApplicationPermission(StrEnum):
    """Describe explicit operations instead of relying on broad roles."""

    MANAGE_USERS = "manage_users"
    CREATE_SME = "create_sme"
    VIEW_RAW_SME = "view_raw_sme"
    MANAGE_DOCUMENTS = "manage_documents"
    VALIDATE_EVIDENCE = "validate_evidence"
    RUN_ASSESSMENTS = "run_assessments"
    APPROVE_PROFILES = "approve_profiles"
    PUBLISH_PROFILES = "publish_profiles"
    VIEW_PUBLISHED_PROFILES = "view_published_profiles"
    COMPLETE_EXPERT_SURVEY = "complete_expert_survey"
    MANAGE_EXPERT_STUDIES = "manage_expert_studies"


_GLOBAL_PERMISSIONS: dict[ApplicationRole, frozenset[ApplicationPermission]] = {
    ApplicationRole.ADMIN: frozenset(ApplicationPermission),
    ApplicationRole.REVIEWER: frozenset(
        {
            ApplicationPermission.VIEW_RAW_SME,
            ApplicationPermission.MANAGE_DOCUMENTS,
            ApplicationPermission.VALIDATE_EVIDENCE,
            ApplicationPermission.RUN_ASSESSMENTS,
            ApplicationPermission.APPROVE_PROFILES,
            ApplicationPermission.PUBLISH_PROFILES,
            ApplicationPermission.VIEW_PUBLISHED_PROFILES,
        }
    ),
    ApplicationRole.EXPERT: frozenset(
        {ApplicationPermission.COMPLETE_EXPERT_SURVEY}
    ),
    ApplicationRole.INVESTOR: frozenset(
        {ApplicationPermission.VIEW_PUBLISHED_PROFILES}
    ),
    ApplicationRole.SME_USER: frozenset(),
}

_SME_SCOPED_PERMISSIONS = frozenset(
    {
        ApplicationPermission.VIEW_RAW_SME,
        ApplicationPermission.MANAGE_DOCUMENTS,
    }
)


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

    def has_permission(
        self,
        permission: ApplicationPermission,
        *,
        sme_id: str | None = None,
    ) -> bool:
        """Evaluate a capability and optional SME ownership boundary."""

        if permission in _GLOBAL_PERMISSIONS[self.role]:
            return True

        return (
            self.role is ApplicationRole.SME_USER
            and permission in _SME_SCOPED_PERMISSIONS
            and sme_id is not None
            and sme_id in self.sme_ids
        )

    def can_access_sme(self, sme_id: str) -> bool:
        """Retain the raw-record check at existing API boundaries."""

        return self.has_permission(
            ApplicationPermission.VIEW_RAW_SME,
            sme_id=sme_id,
        )

