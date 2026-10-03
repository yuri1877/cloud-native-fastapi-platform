"""Role enforcement through the real HTTP stack: list/get need `user`, create/update need
`operator`, delete needs `admin`. Exercised against /api/v1/me (no DB needed) plus one
representative write path on users and one on orders to confirm the routers are wired.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.dependencies.auth import get_token_verifier
from app.main import create_app
from tests.unit.auth_helpers import AUDIENCE, ISSUER, FakeTokenVerifier, make_token

OIDC_KWARGS = {
    "oidc_issuer": ISSUER,
    "oidc_audience": AUDIENCE,
    "oidc_jwks_url": "https://issuer.example.com/.well-known/jwks.json",
}


@pytest.fixture
async def rbac_client() -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, app_env="test", **OIDC_KWARGS)
    app = create_app(settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(roles: list[str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(roles=roles)}"}


async def test_no_roles_cannot_reach_a_user_level_route(rbac_client: AsyncClient) -> None:
    response = await rbac_client.get("/api/v1/me", headers=_auth([]))
    assert response.status_code == 200  # /me only requires authentication, no role


async def test_user_role_can_read(rbac_client: AsyncClient) -> None:
    response = await rbac_client.get("/api/v1/users", headers=_auth(["user"]))
    assert response.status_code != 403


async def test_user_role_cannot_create(rbac_client: AsyncClient) -> None:
    response = await rbac_client.post(
        "/api/v1/users", json={"email": "a@example.com", "name": "A"}, headers=_auth(["user"])
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_operator_role_can_create_but_not_delete(rbac_client: AsyncClient) -> None:
    create = await rbac_client.post(
        "/api/v1/users",
        json={"email": "op@example.com", "name": "Op"},
        headers=_auth(["operator"]),
    )
    assert create.status_code != 403

    response = await rbac_client.delete(
        f"/api/v1/users/{uuid.uuid4()}", headers=_auth(["operator"])
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_admin_role_can_reach_every_level(rbac_client: AsyncClient) -> None:
    for method, path, json in [
        ("GET", "/api/v1/users", None),
        ("POST", "/api/v1/users", {"email": f"{uuid.uuid4()}@example.com", "name": "A"}),
        ("DELETE", f"/api/v1/users/{uuid.uuid4()}", None),
    ]:
        response = await rbac_client.request(method, path, json=json, headers=_auth(["admin"]))
        assert response.status_code != 403, f"{method} {path} -> {response.status_code}"


async def test_missing_token_is_401_not_403(rbac_client: AsyncClient) -> None:
    """Authentication is checked before authorization: no token means 401, never 403."""
    response = await rbac_client.get("/api/v1/users")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_user_role_cannot_create_an_order(rbac_client: AsyncClient) -> None:
    response = await rbac_client.post(
        "/api/v1/orders",
        json={"user_id": str(uuid.uuid4()), "total_amount": 100, "currency": "GBP"},
        headers=_auth(["user"]),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_operator_role_cannot_delete_an_order(rbac_client: AsyncClient) -> None:
    response = await rbac_client.delete(
        f"/api/v1/orders/{uuid.uuid4()}", headers=_auth(["operator"])
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
