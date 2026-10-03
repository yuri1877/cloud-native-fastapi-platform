import pytest

from app.core.authorization import Role, principal_meets_role


@pytest.mark.parametrize(
    ("roles", "minimum", "expected"),
    [
        (["user"], Role.USER, True),
        (["user"], Role.OPERATOR, False),
        (["user"], Role.ADMIN, False),
        (["operator"], Role.USER, True),
        (["operator"], Role.OPERATOR, True),
        (["operator"], Role.ADMIN, False),
        (["admin"], Role.USER, True),
        (["admin"], Role.OPERATOR, True),
        (["admin"], Role.ADMIN, True),
        ([], Role.USER, False),
        (["user", "admin"], Role.ADMIN, True),  # highest of several roles wins
    ],
)
def test_role_hierarchy(roles: list[str], minimum: Role, expected: bool) -> None:
    assert principal_meets_role(roles, minimum) is expected


def test_unrecognised_role_claims_are_ignored_not_rejected() -> None:
    assert principal_meets_role(["super-mega-admin", "user"], Role.USER) is True
    assert principal_meets_role(["super-mega-admin"], Role.USER) is False


def test_empty_roles_meet_no_requirement() -> None:
    assert principal_meets_role([], Role.USER) is False
