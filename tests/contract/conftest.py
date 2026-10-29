from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.dependencies.auth import get_token_verifier
from app.main import create_app
from tests.contract.openapi_helpers import Spec
from tests.unit.auth_helpers import AUDIENCE, ISSUER, FakeTokenVerifier


@pytest.fixture(scope="session")
def openapi_spec() -> Spec:
    """The document FastAPI generates for the application: the contract under test."""
    return create_app(Settings(_env_file=None, app_env="test")).openapi()


@pytest.fixture
async def auth_client() -> AsyncIterator[AsyncClient]:
    """The real app with authentication on (a fake JWKS client) and no database. Whether a
    caller is authenticated and allowed is decided before any database work, so 401 and 403
    can be exercised without one."""
    settings = Settings(
        _env_file=None,
        app_env="test",
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url="https://issuer.example.com/.well-known/jwks.json",
    )
    app = create_app(settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
