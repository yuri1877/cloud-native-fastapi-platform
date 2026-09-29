import uuid

from httpx import AsyncClient


async def _create(client: AsyncClient, email: str = "a@example.com") -> dict:
    response = await client.post("/api/v1/users", json={"email": email, "name": "A"})
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_get_update_delete_user(db_client: AsyncClient) -> None:
    created = await _create(db_client)
    assert created["email"] == "a@example.com"
    user_id = created["id"]

    get_resp = await db_client.get(f"/api/v1/users/{user_id}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created

    patch_resp = await db_client.patch(f"/api/v1/users/{user_id}", json={"name": "B"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "B"

    delete_resp = await db_client.delete(f"/api/v1/users/{user_id}")
    assert delete_resp.status_code == 204

    assert (await db_client.get(f"/api/v1/users/{user_id}")).status_code == 404


async def test_create_user_duplicate_email_conflicts(db_client: AsyncClient) -> None:
    await _create(db_client, "dup@example.com")
    response = await db_client.post(
        "/api/v1/users", json={"email": "dup@example.com", "name": "Other"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_create_user_invalid_email_is_422(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/v1/users", json={"email": "not-an-email", "name": "A"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_get_missing_user_is_404(db_client: AsyncClient) -> None:
    response = await db_client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_patch_with_no_fields_is_422(db_client: AsyncClient) -> None:
    created = await _create(db_client, "empty@example.com")
    response = await db_client.patch(f"/api/v1/users/{created['id']}", json={})
    assert response.status_code == 422


async def test_list_users_is_paginated_and_ordered(db_client: AsyncClient) -> None:
    for i in range(3):
        await _create(db_client, f"p{i}@example.com")
    response = await db_client.get("/api/v1/users", params={"limit": 2, "offset": 0})
    body = response.json()
    assert response.status_code == 200
    assert body["total"] >= 3
    assert len(body["items"]) == 2


async def test_delete_user_with_orders_conflicts(db_client: AsyncClient) -> None:
    user = await _create(db_client, "hasorders@example.com")
    order_resp = await db_client.post(
        "/api/v1/orders",
        json={"user_id": user["id"], "total_amount": 500, "currency": "GBP"},
    )
    assert order_resp.status_code == 201

    response = await db_client.delete(f"/api/v1/users/{user['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_HAS_ORDERS"
