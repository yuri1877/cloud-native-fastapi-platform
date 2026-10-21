"""Real responses checked against the generated contract: a documented status, a body that
matches the documented schema, and the request-ID rules. Needs TEST_DATABASE_URL."""

import uuid

import pytest
from httpx import AsyncClient

from tests.contract.openapi_helpers import Spec, assert_conforms

pytestmark = pytest.mark.contract


async def _create_user(client: AsyncClient, email: str) -> str:
    response = await client.post("/api/v1/users", json={"email": email, "name": "Contract"})
    assert response.status_code == 201
    return str(response.json()["id"])


async def test_the_user_endpoints_conform_to_the_contract(
    db_client: AsyncClient, openapi_spec: Spec
) -> None:
    created = await db_client.post(
        "/api/v1/users", json={"email": "contract@example.com", "name": "C"}
    )
    assert_conforms(openapi_spec, "create_user", created, status=201)
    user_id = created.json()["id"]

    fetched = await db_client.get(f"/api/v1/users/{user_id}")
    assert_conforms(openapi_spec, "get_user", fetched, status=200)
    listed = await db_client.get("/api/v1/users")
    assert_conforms(openapi_spec, "list_users", listed, status=200)
    updated = await db_client.patch(f"/api/v1/users/{user_id}", json={"name": "D"})
    assert_conforms(openapi_spec, "update_user", updated, status=200)

    # Documented failures.
    duplicate = await db_client.post(
        "/api/v1/users", json={"email": "contract@example.com", "name": "C"}
    )
    assert_conforms(openapi_spec, "create_user", duplicate, status=409)
    invalid = await db_client.post("/api/v1/users", json={"email": "not-an-email", "name": "C"})
    assert_conforms(openapi_spec, "create_user", invalid, status=422)
    missing = await db_client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert_conforms(openapi_spec, "get_user", missing, status=404)
    malformed = await db_client.get("/api/v1/users/not-a-uuid")
    assert_conforms(openapi_spec, "get_user", malformed, status=422)
    empty_patch = await db_client.patch(f"/api/v1/users/{user_id}", json={})
    assert_conforms(openapi_spec, "update_user", empty_patch, status=422)

    deleted = await db_client.delete(f"/api/v1/users/{user_id}")
    assert_conforms(openapi_spec, "delete_user", deleted, status=204)
    deleted_again = await db_client.delete(f"/api/v1/users/{user_id}")
    assert_conforms(openapi_spec, "delete_user", deleted_again, status=404)


async def test_the_order_endpoints_conform_to_the_contract(
    db_client: AsyncClient, openapi_spec: Spec
) -> None:
    user_id = await _create_user(db_client, "orders-contract@example.com")
    order = {"user_id": user_id, "total_amount": 1999, "currency": "GBP"}

    created = await db_client.post("/api/v1/orders", json=order)
    assert_conforms(openapi_spec, "create_order", created, status=201)
    order_id = created.json()["id"]

    fetched = await db_client.get(f"/api/v1/orders/{order_id}")
    assert_conforms(openapi_spec, "get_order", fetched, status=200)
    listed = await db_client.get("/api/v1/orders", params={"user_id": user_id, "status": "PENDING"})
    assert_conforms(openapi_spec, "list_orders", listed, status=200)
    processing = await db_client.patch(f"/api/v1/orders/{order_id}", json={"status": "PROCESSING"})
    assert_conforms(openapi_spec, "update_order", processing, status=200)

    # Documented failures.
    backwards = await db_client.patch(f"/api/v1/orders/{order_id}", json={"status": "PENDING"})
    assert_conforms(openapi_spec, "update_order", backwards, status=409)
    unknown_user = await db_client.post(
        "/api/v1/orders", json={**order, "user_id": str(uuid.uuid4())}
    )
    assert_conforms(openapi_spec, "create_order", unknown_user, status=404)
    float_amount = await db_client.post("/api/v1/orders", json={**order, "total_amount": 19.99})
    assert_conforms(openapi_spec, "create_order", float_amount, status=422)
    not_deletable = await db_client.delete(f"/api/v1/orders/{order_id}")
    assert_conforms(openapi_spec, "delete_order", not_deletable, status=409)

    cancelled = await db_client.patch(f"/api/v1/orders/{order_id}", json={"status": "CANCELLED"})
    assert_conforms(openapi_spec, "update_order", cancelled, status=200)
    deleted = await db_client.delete(f"/api/v1/orders/{order_id}")
    assert_conforms(openapi_spec, "delete_order", deleted, status=204)
    deleted_again = await db_client.delete(f"/api/v1/orders/{order_id}")
    assert_conforms(openapi_spec, "delete_order", deleted_again, status=404)


async def test_collection_pagination_is_deterministic_and_complete(
    db_client: AsyncClient, openapi_spec: Spec
) -> None:
    for number in range(5):
        await _create_user(db_client, f"page{number}@example.com")

    def ids(response_body: dict[str, list[dict[str, str]]]) -> list[str]:
        return [item["id"] for item in response_body["items"]]

    full = await db_client.get("/api/v1/users", params={"limit": 100})
    assert_conforms(openapi_spec, "list_users", full, status=200)
    assert full.json()["total"] == 5

    again = await db_client.get("/api/v1/users", params={"limit": 100})
    assert ids(again.json()) == ids(full.json())  # the same request gives the same order

    from_pages: list[str] = []
    for offset in (0, 2, 4):
        page = await db_client.get("/api/v1/users", params={"limit": 2, "offset": offset})
        assert_conforms(openapi_spec, "list_users", page, status=200)
        assert (page.json()["limit"], page.json()["offset"]) == (2, offset)
        from_pages.extend(ids(page.json()))
    assert from_pages == ids(full.json())  # pages neither overlap nor skip anything


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_out_of_range_pagination_is_a_documented_422(
    db_client: AsyncClient, openapi_spec: Spec, params: dict[str, int]
) -> None:
    response = await db_client.get("/api/v1/users", params=params)
    assert_conforms(openapi_spec, "list_users", response, status=422)
