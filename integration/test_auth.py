"""Exercises authentication through the real ASGI app: the /me endpoint plus the
missing-token and not-configured paths."""

from collections.abc import AsyncIterator
from datetime import timedelta

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
def auth_settings() -> Settings:
    return Settings(_env_file=None, app_env="test", **OIDC_KWARGS)


@pytest.fixture
async def auth_client(auth_settings: Settings) -> AsyncIterator[AsyncClient]:
    """The app's real dependency graph, with only the network-calling JWKS client swapped
    for a fake (no other test doubles: DB, routing, error handling are all real)."""
    app = create_app(auth_settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_me_with_valid_token(auth_client: AsyncClient) -> None:
    token = make_token(
        subject="user-42", roles=["user", "admin"], extra_claims={"email": "a@x.com"}
    )
    response = await auth_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "subject": "user-42",
        "email": "a@x.com",
        "roles": ["admin", "user"],
    }


async def test_me_without_token_is_401(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_me_with_malformed_authorization_header_is_401(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/me", headers={"Authorization": "not-a-bearer-token"})
    assert response.status_code == 401


async def test_me_with_expired_token_is_401(auth_client: AsyncClient) -> None:
    token = make_token(expires_delta=timedelta(minutes=-1))
    response = await auth_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


async def test_me_with_wrong_audience_is_401(auth_client: AsyncClient) -> None:
    token = make_token(audience="a-different-api")
    response = await auth_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_AUDIENCE"


async def test_me_returns_503_when_auth_not_configured(client: AsyncClient) -> None:
    """`client` (tests/conftest.py) has no OIDC settings: auth is disabled app-wide."""
    response = await client.get("/api/v1/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


async def test_me_returns_503_if_verifier_present_without_matching_settings(
    settings: Settings,
) -> None:
    """Defensive path: a verifier wired into app.state without issuer/audience settings
    should fail closed (503), not raise an unhandled error or skip validation."""
    app = create_app(settings)  # `settings` (tests/conftest.py) has no OIDC config
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {make_token()}"}
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"
