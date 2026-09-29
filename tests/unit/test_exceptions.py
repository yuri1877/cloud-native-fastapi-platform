import pytest

from app.core.exceptions import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    NotFoundException,
)


@pytest.mark.parametrize(
    ("exc_cls", "status_code", "code"),
    [
        (AppException, 500, "INTERNAL_ERROR"),
        (NotFoundException, 404, "NOT_FOUND"),
        (ConflictException, 409, "CONFLICT"),
        (AuthenticationException, 401, "AUTHENTICATION_REQUIRED"),
        (AuthorizationException, 403, "FORBIDDEN"),
    ],
)
def test_default_status_and_code(exc_cls: type[AppException], status_code: int, code: str) -> None:
    exc = exc_cls()
    assert exc.status_code == status_code
    assert exc.code == code


def test_message_and_code_are_overridable() -> None:
    exc = NotFoundException("Order was not found", code="ORDER_NOT_FOUND")
    assert exc.message == "Order was not found"
    assert exc.code == "ORDER_NOT_FOUND"
    assert exc.status_code == 404  # unchanged default


def test_status_code_is_overridable() -> None:
    exc = AppException("Nope", code="TEAPOT", status_code=418)
    assert (exc.status_code, exc.code) == (418, "TEAPOT")
