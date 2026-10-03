"""Simple role-based access control.

Roles form a hierarchy: ADMIN > OPERATOR > USER. A principal needs a role at or above the
required level; unrecognised role strings in a token are ignored rather than rejected
(forward-compatible with an IdP adding roles this API doesn't know about yet).
"""

import enum
from collections.abc import Iterable


class Role(enum.StrEnum):
    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"


_ROLE_LEVEL: dict[Role, int] = {Role.USER: 1, Role.OPERATOR: 2, Role.ADMIN: 3}


def _max_role_level(roles: Iterable[str]) -> int:
    levels = []
    for raw in roles:
        try:
            levels.append(_ROLE_LEVEL[Role(raw)])
        except ValueError:
            continue  # unrecognised role claim; ignored, not an error
    return max(levels, default=0)


def principal_meets_role(roles: Iterable[str], minimum: Role) -> bool:
    return _max_role_level(roles) >= _ROLE_LEVEL[minimum]
