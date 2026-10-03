import uuid

from httpx import AsyncClient


async def _create_user(client: AsyncClient, email: str = "orders-user@example.com") -> str:
    response = await client.post("/api/v1/users", json={"email": email, "name": "A"})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_order(client: AsyncClient, user_id: str, **overrides: object) -> dict:
    payload = {"user_id": user_id, "total_amount": 1999, "currency": "GBP", **overrides}
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_order_lifecycle(db_client: AsyncClient) -> None:
    user_id = await _create_user(db_client)
    order = await _create_order(db_client, user_id)
    assert order["status"] == "PENDING"
    order_id = order["id"]

    processing = await db_client.patch(f"/api/v1/orders/{order_id}", json={"status": "PROCESSING"})
    assert processing.status_code == 200
    assert processing.json()["status"] == "PROCESSING"

    invalid = await db_client.patch(f"/api/v1/orders/{order_id}", json={"status": "PENDING"})
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    completed = await db_client.patch(f"/api/v1/orders/{order_id}", json={"status": "COMPLETED"})
    assert completed.status_code == 200

    not_deletable = await db_client.delete(f"/api/v1/orders/{order_id}")
    assert not_deletable.status_code == 409
    assert not_deletable.json()["error"]["code"] == "ORDER_NOT_DELETABLE"


async def test_create_order_unknown_user_is_404(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/orders",
        json={"user_id": str(uuid.uuid4()), "total_amount": 100, "currency": "GBP"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_create_order_rejects_float_amount(db_client: AsyncClient) -> None:
    user_id = await _create_user(db_client, "float@example.com")
    response = await db_client.post(
        "/api/v1/orders",
        json={"user_id": user_id, "total_amount": 19.99, "currency": "GBP"},
    )
    assert response.status_code == 422


async def test_amount_immutable_once_processing(db_client: AsyncClient) -> None:
    user_id = await _create_user(db_client, "immutable@example.com")
    order = await _create_order(db_client, user_id)
    await db_client.patch(f"/api/v1/orders/{order['id']}", json={"status": "PROCESSING"})

    response = await db_client.patch(f"/api/v1/orders/{order['id']}", json={"total_amount": 1})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_NOT_MODIFIABLE"


async def test_list_orders_filters_by_user_and_status(db_client: AsyncClient) -> None:
    user_id = await _create_user(db_client, "filter@example.com")
    other_user_id = await _create_user(db_client, "filter2@example.com")
    await _create_order(db_client, user_id)
    await _create_order(db_client, other_user_id)

    response = await db_client.get("/api/v1/orders", params={"user_id": user_id})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["user_id"] == user_id

    response = await db_client.get("/api/v1/orders", params={"status": "PENDING"})
    assert response.json()["total"] >= 2


async def test_delete_pending_order_succeeds(db_client: AsyncClient) -> None:
    user_id = await _create_user(db_client, "delpending@example.com")
    order = await _create_order(db_client, user_id)
    response = await db_client.delete(f"/api/v1/orders/{order['id']}")
    assert response.status_code == 204
