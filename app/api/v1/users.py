import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response

from app.dependencies.authz import require_admin, require_operator, require_user
from app.dependencies.services import UserServiceDep
from app.schemas.common import ErrorResponse, Limit, Offset, Page
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

_401: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required"}
}
_403: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "Insufficient role"}
}
_422: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Validation error"}
}
_404: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "User not found"}
}
_409: dict[int | str, dict[str, Any]] = {409: {"model": ErrorResponse, "description": "Conflict"}}


@router.get(
    "",
    operation_id="list_users",
    summary="List users",
    response_model=Page[UserRead],
    responses={**_401, **_422},
    dependencies=[Depends(require_user)],
)
async def list_users(
    service: UserServiceDep, limit: Limit = 20, offset: Offset = 0
) -> Page[UserRead]:
    users, total = await service.list_users(limit=limit, offset=offset)
    return Page[UserRead](
        items=[UserRead.model_validate(u) for u in users], total=total, limit=limit, offset=offset
    )


@router.get(
    "/{user_id}",
    operation_id="get_user",
    summary="Get a user",
    response_model=UserRead,
    responses={**_401, **_404, **_422},
    dependencies=[Depends(require_user)],
)
async def get_user(user_id: uuid.UUID, service: UserServiceDep) -> UserRead:
    return UserRead.model_validate(await service.get_user(user_id))


@router.post(
    "",
    operation_id="create_user",
    summary="Create a user",
    status_code=201,
    response_model=UserRead,
    responses={**_401, **_403, **_409, **_422},
    dependencies=[Depends(require_operator)],
)
async def create_user(payload: UserCreate, service: UserServiceDep, response: Response) -> UserRead:
    user = await service.create_user(payload)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return UserRead.model_validate(user)


@router.patch(
    "/{user_id}",
    operation_id="update_user",
    summary="Update a user (partial)",
    response_model=UserRead,
    responses={**_401, **_403, **_404, **_409, **_422},
    dependencies=[Depends(require_operator)],
)
async def update_user(user_id: uuid.UUID, payload: UserUpdate, service: UserServiceDep) -> UserRead:
    return UserRead.model_validate(await service.update_user(user_id, payload))


@router.delete(
    "/{user_id}",
    operation_id="delete_user",
    summary="Delete a user",
    status_code=204,
    responses={**_401, **_403, **_404, **_409, **_422},
    dependencies=[Depends(require_admin)],
)
async def delete_user(user_id: uuid.UUID, service: UserServiceDep) -> None:
    await service.delete_user(user_id)
