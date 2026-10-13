"""GET /metrics end to end: what a scraper actually sees after real requests."""

import re

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


async def _scrape(client: AsyncClient) -> str:
    response = await client.get("/metrics")
    assert response.status_code == 200
    return response.text


async def test_metrics_endpoint_serves_prometheus_text(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE http_requests_total counter" in response.text


async def test_requests_are_counted_by_route_template(client: AsyncClient) -> None:
    await client.get("/health/live")

    body = await _scrape(client)
    assert 'http_requests_total{method="GET",route="/health/live",status_code="200"} 1.0' in body


async def test_route_labels_are_templates_not_raw_paths(client: AsyncClient) -> None:
    user_id = "3f2b8c1e-5a4d-4c7e-9b1a-0d6e8f2a7c11"
    await client.get(f"/api/v1/users/{user_id}")

    body = await _scrape(client)
    assert 'route="/api/v1/users/{user_id}"' in body
    assert user_id not in body


async def test_unmatched_paths_share_one_label(client: AsyncClient) -> None:
    await client.get("/no/such/route")

    body = await _scrape(client)
    assert 'http_requests_total{method="GET",route="unmatched",status_code="404"} 1.0' in body
    assert "/no/such/route" not in body


async def test_unrecognised_methods_do_not_create_new_series(client: AsyncClient) -> None:
    await client.request("BREW", "/health/live")

    body = await _scrape(client)
    assert 'method="OTHER"' in body
    assert "BREW" not in body


async def test_request_duration_is_recorded(client: AsyncClient) -> None:
    await client.get("/health/live")

    body = await _scrape(client)
    assert 'http_request_duration_seconds_count{method="GET",route="/health/live"} 1.0' in body


async def test_unhandled_exceptions_are_counted_as_errors(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/boom")
        body = await _scrape(client)

    assert 'http_errors_total{method="GET",route="/boom"} 1.0' in body
    assert 'http_requests_total{method="GET",route="/boom",status_code="500"} 1.0' in body


async def test_the_metrics_endpoint_is_not_in_the_openapi_schema(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/metrics" not in schema["paths"]


async def test_a_failing_metrics_backend_never_fails_the_request(settings: Settings) -> None:
    app = create_app(settings)

    class BrokenMetrics:
        def observe_request(self, **_: object) -> None:
            raise RuntimeError("metrics are broken")

    app.state.metrics = BrokenMetrics()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200


async def test_database_statements_are_timed(db_client: AsyncClient) -> None:
    """Needs TEST_DATABASE_URL: proves the hooks fire through the real asyncpg driver."""
    created = await db_client.post(
        "/api/v1/users", json={"email": "metrics@example.com", "name": "M"}
    )
    assert created.status_code == 201

    body = await _scrape(db_client)
    for operation in ("SELECT", "INSERT"):
        pattern = (
            r'database_operation_duration_seconds_count\{operation="'
            + operation
            + r'"\} (\d+(?:\.\d+)?)'
        )
        match = re.search(pattern, body)
        assert match is not None, f"no {operation} timing was recorded"
        assert float(match.group(1)) >= 1
