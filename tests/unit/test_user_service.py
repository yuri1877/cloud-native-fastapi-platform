import uuid

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.models.order import Order
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService
from tests.unit.conftest import FakeSession, FakeUserRepository


async def _create(service: UserService, email: str = "a@example.com") -> uuid.UUID:
    user = await service.create_user(UserCreate(email=email, name="A"))
    return user.id


async def test_create_user_commits(
    user_service: UserService, session: FakeSession, users_repo: FakeUserRepository
) -> None:
    user = await user_service.create_user(UserCreate(email="A@Example.com", name="A"))
    assert user.email == "a@example.com"
    assert session.commits == 1
    assert len(users_repo.items) == 1


async def test_create_duplicate_email_conflicts(user_service: UserService) -> None:
    await _create(user_service)
    with pytest.raises(ConflictException) as excinfo:
        await _create(user_service)
    assert excinfo.value.code == "EMAIL_ALREADY_EXISTS"
    assert excinfo.value.status_code == 409


async def test_create_race_is_mapped_to_conflict_and_rolled_back(
    user_service: UserService, session: FakeSession, users_repo: FakeUserRepository
) -> None:
    users_repo.fail_add = True
    with pytest.raises(ConflictException) as excinfo:
        await _create(user_service)
    assert excinfo.value.code == "EMAIL_ALREADY_EXISTS"
    assert session.rollbacks == 1
    assert session.commits == 0


async def test_get_user_not_found(user_service: UserService) -> None:
    with pytest.raises(NotFoundException) as excinfo:
        await user_service.get_user(uuid.uuid4())
    assert excinfo.value.code == "USER_NOT_FOUND"
    assert excinfo.value.status_code == 404


async def test_update_user_changes_only_given_fields(user_service: UserService) -> None:
    user_id = await _create(user_service)
    updated = await user_service.update_user(user_id, UserUpdate(name="B"))
    assert (updated.name, updated.email) == ("B", "a@example.com")


async def test_update_email_to_existing_conflicts(user_service: UserService) -> None:
    await _create(user_service, "a@example.com")
    other = await _create(user_service, "b@example.com")
    with pytest.raises(ConflictException):
        await user_service.update_user(other, UserUpdate(email="a@example.com"))


async def test_update_email_to_own_email_is_allowed(user_service: UserService) -> None:
    user_id = await _create(user_service)
    updated = await user_service.update_user(user_id, UserUpdate(email="a@example.com"))
    assert updated.email == "a@example.com"


async def test_update_missing_user_not_found(user_service: UserService) -> None:
    with pytest.raises(NotFoundException):
        await user_service.update_user(uuid.uuid4(), UserUpdate(name="B"))


async def test_delete_user(user_service: UserService, users_repo: FakeUserRepository) -> None:
    user_id = await _create(user_service)
    await user_service.delete_user(user_id)
    assert users_repo.items == {}


async def test_delete_user_with_orders_conflicts(
    user_service: UserService, users_repo: FakeUserRepository, session: FakeSession
) -> None:
    user_id = await _create(user_service)
    users_repo.fail_delete = True  # simulates the ON DELETE RESTRICT foreign key violation
    with pytest.raises(ConflictException) as excinfo:
        await user_service.delete_user(user_id)
    assert excinfo.value.code == "USER_HAS_ORDERS"
    assert session.rollbacks == 1


async def test_list_users_is_paginated(user_service: UserService) -> None:
    for i in range(5):
        await _create(user_service, f"u{i}@example.com")
    page, total = await user_service.list_users(limit=2, offset=1)
    assert total == 5
    assert len(page) == 2


def test_order_model_is_not_needed_here() -> None:
    assert Order.__tablename__ == "orders"
