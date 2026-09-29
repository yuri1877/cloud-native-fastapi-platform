import uuid

import pytest
from pydantic import ValidationError

from app.schemas.order import OrderCreate, OrderUpdate
from app.schemas.user import UserCreate, UserUpdate


def test_user_email_is_lowercased_and_name_stripped() -> None:
    user = UserCreate(email="Someone@Example.COM", name="  Ada  ")
    assert user.email == "someone@example.com"
    assert user.name == "Ada"


@pytest.mark.parametrize("payload", [{"email": "nope", "name": "x"}, {"email": "a@example.com"}])
def test_user_create_rejects_invalid(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        UserCreate(**payload)


def test_user_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", name="A", is_admin=True)  # type: ignore[call-arg]


def test_user_update_requires_at_least_one_field() -> None:
    with pytest.raises(ValidationError):
        UserUpdate()


def test_user_update_rejects_explicit_null() -> None:
    with pytest.raises(ValidationError):
        UserUpdate(name=None)


def test_user_update_tracks_provided_fields_only() -> None:
    assert UserUpdate(name="B").model_dump(exclude_unset=True) == {"name": "B"}


def _order(**overrides: object) -> dict[str, object]:
    return {"user_id": uuid.uuid4(), "total_amount": 1999, "currency": "GBP", **overrides}


def test_order_create_valid() -> None:
    order = OrderCreate(**_order())  # type: ignore[arg-type]
    assert order.total_amount == 1999


@pytest.mark.parametrize(
    "bad",
    [
        {"total_amount": 19.99},
        {"total_amount": "1999"},
        {"total_amount": 0},
        {"total_amount": -5},
        {"total_amount": True},
        {"currency": "gbp"},
        {"currency": "GBPX"},
    ],
)
def test_order_create_rejects_invalid_money(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OrderCreate(**_order(**bad))  # type: ignore[arg-type]


def test_order_update_rules() -> None:
    assert OrderUpdate(status="PROCESSING").model_dump(exclude_unset=True) == {
        "status": "PROCESSING"
    }
    with pytest.raises(ValidationError):
        OrderUpdate()
    with pytest.raises(ValidationError):
        OrderUpdate(status="SHIPPED")
    with pytest.raises(ValidationError):
        OrderUpdate(total_amount=None)
