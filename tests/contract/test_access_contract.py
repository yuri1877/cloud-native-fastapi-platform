"""Access control, identity and the operational endpoints against the contract. No database:
authentication and authorisation are decided before any database work."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from tests.contract.openapi_helpers import Spec, assert_conforms
from tests.unit.auth_helpers import make_token

pytestmark = pytest.mark.contract

UNREACHABLE_DATABASE = "postgresql+asyncpg://user:pw@127.0.0.1:1/nodb"


def _auth(roles: list[str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(roles=roles)}"}


async def test_a_missing_token_is_a_documented_401(
    auth_client: AsyncClient, openapi_spec: Spec
) -> None:
    response = await auth_client.get("/api/v1/users")

    assert_conforms(openapi_spec, "list_users", response, status=401)
    assert response.headers["www-authenticate"] == "Bearer"


async def test_an_insufficient_role_is_a_documented_403(
    auth_client: AsyncClient, openapi_spec: Spec
) -> None:
    response = await auth_client.post(
        "/api/v1/users", json={"email": "a@example.com", "name": "A"}, headers=_auth(["user"])
    )

    assert_conforms(openapi_spec, "create_user", response, status=403)
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_the_current_principal_conforms(auth_client: AsyncClient, openapi_spec: Spec) -> None:
    response = await auth_client.get("/api/v1/me", headers=_auth(["user"]))

    assert_conforms(openapi_spec, "get_current_principal", response, status=200)
    assert response.json()["roles"] == ["user"]


async def test_liveness_conforms(client: AsyncClient, openapi_spec: Spec) -> None:
    assert_conforms(openapi_spec, "health_live", await client.get("/health/live"), status=200)


async def test_readiness_conforms_when_ready(client: AsyncClient, openapi_spec: Spec) -> None:
    assert_conforms(openapi_spec, "health_ready", await client.get("/health/ready"), status=200)


async def test_a_failing_readiness_check_is_a_documented_503(openapi_spec: Spec) -> None:
    app = create_app(Settings(_env_file=None, app_env="test", database_url=UNREACHABLE_DATABASE))
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert_conforms(openapi_spec, "health_ready", response, status=503)
