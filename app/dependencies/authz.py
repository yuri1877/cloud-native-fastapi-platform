"""Authorization dependencies: require a minimum role, layered on top of authentication.

    Authenticated principal (Phase 9)
            |
    Required role (this module)
            |
    Allow / deny

Kept independent of individual route implementations: routes attach `require_*` via
`dependencies=[...]`, never duplicating the role check themselves.
"""

from collections.abc import Awaitable, Callable

from app.core.authorization import Role, principal_meets_role
from app.core.exceptions import AuthorizationException
from app.core.security import Principal
from app.dependencies.auth import CurrentPrincipal


def require_role(minimum: Role) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory. Runs after authentication, so a missing/invalid token still
    yields 401 before any role is checked; a recognised-but-insufficient role yields 403.
    """

    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal_meets_role(principal.roles, minimum):
            raise AuthorizationException(
                f"Requires the '{minimum.value}' role or higher", code="INSUFFICIENT_ROLE"
            )
        return principal

    return dependency


require_user = require_role(Role.USER)
require_operator = require_role(Role.OPERATOR)
require_admin = require_role(Role.ADMIN)
