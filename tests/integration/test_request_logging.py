"""Request logging end to end: what a request actually writes to the log stream."""

import json
import uuid
from collections.abc import Callable
from typing import Any

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.request_context import REQUEST_ID_HEADER
from app.main import create_app

LogReader = Callable[[], list[dict[str, Any]]]

FAKE_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJl"


def _access_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [line for line in lines if line["logger"] == "app.access"]


async def test_request_is_logged_with_the_planned_fields(
    client: AsyncClient, json_logs: LogReader
) -> None:
    response = await client.get("/health/live", headers={REQUEST_ID_HEADER: "log-test-0001"})

    [line] = _access_lines(json_logs())
    assert line["message"] == "request completed"
    assert line["level"] == "INFO"
    assert line["method"] == "GET"
    assert line["route"] == "/health/live"
    assert line["path"] == "/health/live"
    assert line["status_code"] == response.status_code == 200
    assert isinstance(line["duration_ms"], float)
    assert line["duration_ms"] >= 0
    assert line["request_id"] == "log-test-0001"
    assert line["trace_id"] is None
    assert line["service"] == "test-service"
    assert line["environment"] == "test"


async def test_route_is_the_template_not_the_raw_path(
    client: AsyncClient, json_logs: LogReader
) -> None:
    """The route must be bounded (safe to aggregate on), so it is the matched template."""
    user_id = uuid.uuid4()
    response = await client.get(f"/api/v1/users/{user_id}")

    [line] = _access_lines(json_logs())
    assert line["route"] == "/api/v1/users/{user_id}"
    assert line["path"] == f"/api/v1/users/{user_id}"
    assert line["status_code"] == response.status_code


async def test_unmatched_route_is_logged_as_unmatched(
    client: AsyncClient, json_logs: LogReader
) -> None:
    response = await client.get("/no/such/route")

    [line] = _access_lines(json_logs())
    assert line["route"] == "unmatched"  # not the arbitrary, attacker-chosen path
    assert line["status_code"] == response.status_code == 404
    assert line["level"] == "INFO"


async def test_query_strings_and_credentials_never_reach_the_logs(
    client: AsyncClient, json_logs: LogReader
) -> None:
    await client.get(
        "/health/live",
        params={"access_token": "query-secret-value"},
        headers={"Authorization": f"Bearer {FAKE_JWT}", "Cookie": "session=cookie-secret-value"},
    )

    lines = json_logs()
    assert _access_lines(lines)[0]["path"] == "/health/live"
    everything = json.dumps(lines)
    for secret in ("query-secret-value", FAKE_JWT, "cookie-secret-value"):
        assert secret not in everything


async def test_unhandled_exception_is_logged_and_still_carries_the_request_id(
    settings: Settings, json_logs: LogReader
) -> None:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("cannot connect to postgresql+asyncpg://app:s3cr3t-pw@db:5432/app")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom", headers={REQUEST_ID_HEADER: "boom-test-0001"})

    assert response.status_code == 500
    # This response is built by Starlette's ServerErrorMiddleware, outside RequestIDMiddleware,
    # so the header has to come from the error handler itself.
    assert response.headers[REQUEST_ID_HEADER] == "boom-test-0001"
    assert response.json()["error"]["request_id"] == "boom-test-0001"

    lines = json_logs()
    [access] = _access_lines(lines)
    assert access["status_code"] == 500
    assert access["level"] == "ERROR"
    assert access["route"] == "/boom"

    [failure] = [line for line in lines if line["message"] == "Unhandled exception"]
    assert failure["level"] == "ERROR"
    assert failure["request_id"] == "boom-test-0001"
    assert "RuntimeError" in failure["exception"]
    assert "s3cr3t-pw" not in json.dumps(lines)
