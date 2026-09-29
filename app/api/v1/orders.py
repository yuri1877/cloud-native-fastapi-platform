import uuid
from typing import Any

from fastapi import APIRouter, Response

from app.dependencies.services import OrderServiceDep
from app.models.order import OrderStatus
from app.schemas.common import ErrorResponse, Limit, Offset, Page
from app.schemas.order import OrderCreate, OrderRead, OrderUpdate

router = APIRouter(prefix="/orders", tags=["orders"])

_422: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Validation error"}
}
_404: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Order (or referenced user) not found"}
}
_409: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Conflict with current order state"}
}


@router.get(
    "",
    operation_id="list_orders",
    summary="List orders",
    response_model=Page[OrderRead],
    responses=_422,
)
async def list_orders(
    service: OrderServiceDep,
    limit: Limit = 20,
    offset: Offset = 0,
    user_id: uuid.UUID | None = None,
    status: OrderStatus | None = None,
) -> Page[OrderRead]:
    orders, total = await service.list_orders(
        limit=limit, offset=offset, user_id=user_id, status=status
    )
    return Page[OrderRead](
        items=[OrderRead.model_validate(o) for o in orders], total=total, limit=limit, offset=offset
    )


@router.get(
    "/{order_id}",
    operation_id="get_order",
    summary="Get an order",
    response_model=OrderRead,
    responses={**_404, **_422},
)
async def get_order(order_id: uuid.UUID, service: OrderServiceDep) -> OrderRead:
    return OrderRead.model_validate(await service.get_order(order_id))


@router.post(
    "",
    operation_id="create_order",
    summary="Create an order",
    status_code=201,
    response_model=OrderRead,
    responses={**_404, **_422},
)
async def create_order(
    payload: OrderCreate, service: OrderServiceDep, response: Response
) -> OrderRead:
    order = await service.create_order(payload)
    response.headers["Location"] = f"/api/v1/orders/{order.id}"
    return OrderRead.model_validate(order)


@router.patch(
    "/{order_id}",
    operation_id="update_order",
    summary="Update an order (partial)",
    response_model=OrderRead,
    responses={**_404, **_409, **_422},
)
async def update_order(
    order_id: uuid.UUID, payload: OrderUpdate, service: OrderServiceDep
) -> OrderRead:
    return OrderRead.model_validate(await service.update_order(order_id, payload))


@router.delete(
    "/{order_id}",
    operation_id="delete_order",
    summary="Delete an order",
    status_code=204,
    responses={**_404, **_409, **_422},
)
async def delete_order(order_id: uuid.UUID, service: OrderServiceDep) -> None:
    await service.delete_order(order_id)
