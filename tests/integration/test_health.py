from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "not_configured"}}


async def test_openapi_available_outside_prod(client: AsyncClient) -> None:
    assert (await client.get("/openapi.json")).status_code == 200
    assert (await client.get("/docs")).status_code == 200


async def test_openapi_declares_operation_ids(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert schema["paths"]["/health/live"]["get"]["operationId"] == "health_live"
    assert schema["paths"]["/health/ready"]["get"]["operationId"] == "health_ready"
