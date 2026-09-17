"""FastAPI authentication and authorization dependencies."""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from greensmecapt.security.models import (
    ApplicationRole,
    AuthPrincipal,
)
from greensmecapt.security.verifier import (
    AuthenticationError,
)

_bearer = HTTPBearer(auto_error=False)


def get_current_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> AuthPrincipal:
    """Verify a bearer token using the application verifier."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return request.app.state.token_verifier.verify(
            credentials.credentials
        )
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def require_roles(
    *allowed_roles: ApplicationRole,
) -> Callable[..., AuthPrincipal]:
    """Create a role-checking dependency."""

    def dependency(
        principal: Annotated[
            AuthPrincipal,
            Depends(get_current_principal),
        ],
    ) -> AuthPrincipal:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "The authenticated user does not have "
                    "permission for this operation."
                ),
            )

        return principal

    return dependency